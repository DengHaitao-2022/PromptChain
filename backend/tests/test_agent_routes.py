import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("ALLOW_INSECURE_JWT_SECRET", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db.postgres_store as postgres_store_module
import routes.agent_routes as agent_routes
import routes.workflow_helpers as workflow_helpers
import services.artifact_store as artifact_store_module
from core.config import get_settings
from main import app
from routes.auth_routes import ACCESS_TOKEN_COOKIE
from services.artifact_store import ArtifactStore
from services.auth_service import create_access_token


def _client(
    monkeypatch, *, user_id: str = "user-1", workspace_id: str = "ws-1", role: str = "editor"
):
    async def _allow_workspace_permission(request, resource: str, action: str):
        return user_id, workspace_id, role

    async def _fake_current_user(request):
        return {
            "id": user_id,
            "sub": user_id,
            "workspace_id": workspace_id,
            "default_workspace_id": workspace_id,
        }

    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    monkeypatch.setattr(agent_routes, "get_current_user", _fake_current_user)
    monkeypatch.setattr(postgres_store_module, "_postgres_store", None)
    monkeypatch.setattr(postgres_store_module, "_postgres_checkpoint_saver", None)
    monkeypatch.setattr(artifact_store_module, "_artifact_store", ArtifactStore())

    client = TestClient(app)
    client.cookies.set(
        ACCESS_TOKEN_COOKIE,
        create_access_token(user_id=user_id, workspace_id=workspace_id),
    )
    return client


def test_agent_run_api_returns_full_autonomous_runtime_snapshot(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "fake")
    get_settings.cache_clear()
    client = _client(monkeypatch)

    response = client.post(
        "/api/agents/runs",
        json={
            "goal": "请围绕当前项目调研 Workflow Agent 到 Autonomous Agent 的技术路线，输出完整报告材料",
            "auto_execute": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["goal"].startswith("请围绕当前项目")
    assert body["run"]["metadata"]["planner_mode"] == "auto"
    assert body["run"]["metadata"]["generation_mode"] == "auto"
    assert body["run"]["metadata"]["fact_check_mode"] == "cove"
    assert body["plans"][0]["goal_card"]["task_type"] == "research_report"
    assert body["plans"][0]["metadata"]["planner_mode"] == "llm"
    assert body["plans"][0]["metadata"]["selected_template"] == "fake_llm_dynamic_plan"
    assert body["plans"][0]["plan_graph"]["nodes"]
    assert body["steps"]
    assert body["tool_calls"]
    assert body["eval_results"]
    assert {
        "read_artifact",
        "write_artifact",
        "retrieve_memory",
        "retrieve_trace",
        "fact_check",
        "export_docx",
    } <= {tool["name"] for tool in body["tool_definitions"]}

    detail = client.get(f"/api/agents/runs/{body['run']['id']}")
    assert detail.status_code == 200
    assert detail.json()["run"]["id"] == body["run"]["id"]


def test_agent_run_list_filters_to_visible_workspace_user(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    client = _client(monkeypatch)

    first = client.post(
        "/api/agents/runs",
        json={"goal": "生成一份完整 Autonomous Agent 方案", "auto_execute": False},
    )
    assert first.status_code == 200

    list_response = client.get("/api/agents/runs")

    assert list_response.status_code == 200
    runs = list_response.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["user_id"] == "user-1"
    assert runs[0]["workspace_id"] == "ws-1"


def test_agent_plan_can_be_modified_before_resume(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    client = _client(monkeypatch)

    created = client.post(
        "/api/agents/runs",
        json={"goal": "生成一份完整 Autonomous Agent 方案", "auto_execute": False},
    )
    assert created.status_code == 200
    body = created.json()
    plan_graph = body["plans"][0]["plan_graph"]
    plan_graph["nodes"][0]["title"] = "人工确认后的目标理解"

    updated = client.put(
        f"/api/agents/runs/{body['run']['id']}/plan",
        json={"plan_graph": plan_graph, "reason": "调整首节点标题"},
    )

    assert updated.status_code == 200
    updated_body = updated.json()
    assert len(updated_body["plans"]) == 2
    assert updated_body["plans"][-1]["version"] == 2
    assert updated_body["plans"][-1]["created_by"] == "human"
    assert updated_body["plans"][-1]["plan_graph"]["nodes"][0]["title"] == "人工确认后的目标理解"
    assert updated_body["plans"][-1]["metadata"]["artifact_id"]


def test_agent_plan_node_can_be_skipped_before_resume(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    client = _client(monkeypatch)

    created = client.post(
        "/api/agents/runs",
        json={"goal": "验证 Autonomous Agent 动态跳过节点", "auto_execute": False},
    )
    assert created.status_code == 200
    body = created.json()

    skipped = client.post(
        f"/api/agents/runs/{body['run']['id']}/skip-node",
        json={"node_id": "goal_interpretation", "reason": "目标已由人工确认"},
    )

    assert skipped.status_code == 200
    skipped_body = skipped.json()
    assert skipped_body["steps"][0]["node_id"] == "goal_interpretation"
    assert skipped_body["steps"][0]["status"] == "skipped"
    assert skipped_body["run"]["metadata"]["last_skipped_node"]["node_id"] == "goal_interpretation"


def test_agent_run_can_be_paused_resumed_and_cancelled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    client = _client(monkeypatch)

    created = client.post(
        "/api/agents/runs",
        json={"goal": "验证 Autonomous Agent 运行控制", "auto_execute": False},
    )
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]

    paused = client.post(
        f"/api/agents/runs/{run_id}/pause",
        json={"reason": "等待人工检查"},
    )
    assert paused.status_code == 200
    assert paused.json()["run"]["status"] == "paused"
    assert paused.json()["run"]["metadata"]["pause"]["reason"] == "等待人工检查"

    resumed = client.post(f"/api/agents/runs/{run_id}/resume", json={})
    assert resumed.status_code == 200
    assert resumed.json()["run"]["status"] in {"running", "completed", "failed", "awaiting_gate"}

    second = client.post(
        "/api/agents/runs",
        json={"goal": "验证 Autonomous Agent 取消", "auto_execute": False},
    )
    assert second.status_code == 200
    second_run_id = second.json()["run"]["id"]

    cancelled = client.post(
        f"/api/agents/runs/{second_run_id}/cancel",
        json={"reason": "目标已废弃"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["status"] == "cancelled"
    assert cancelled.json()["run"]["error_message"] == "目标已废弃"


def test_agent_goal_clarification_recovers_planner_gate(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    client = _client(monkeypatch)

    created = client.post(
        "/api/agents/runs",
        json={"goal": "   ", "auto_execute": False},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["run"]["status"] == "awaiting_gate"
    assert body["run"]["gate"]["gate_type"] == "planner_clarification"
    run_id = body["run"]["id"]

    clarified = client.post(
        f"/api/agents/runs/{run_id}/clarify",
        json={"clarification": "补充完整交付物：输出 Autonomous Agent 技术路线报告。"},
    )

    assert clarified.status_code == 200
    clarified_body = clarified.json()
    assert clarified_body["run"]["status"] == "planning"
    assert clarified_body["plans"][0]["metadata"]["artifact_id"]
