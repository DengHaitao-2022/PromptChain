import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.workflow_helpers as workflow_helpers
from main import app
from routes.auth_routes import ACCESS_TOKEN_COOKIE
from services.auth_service import create_access_token


class _FakeWorkflowRun:
    def __init__(
        self,
        workflow_run_id: str,
        *,
        metadata: dict | None = None,
        status: str = "running",
        current_node: str = "generate_content",
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        total_duration_ms: int | None = None,
    ):
        self.id = workflow_run_id
        self.status = status
        self.current_node = current_node
        self.metadata = metadata or {}
        self.workflow_name = "content_generation"
        self.workflow_version = "1.0.0"
        self.user_input = "hello"
        self.started_at = started_at or datetime(2026, 3, 8, 10, 0, tzinfo=UTC)
        self.completed_at = completed_at
        self.total_duration_ms = total_duration_ms

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "current_node": self.current_node,
            "metadata": self.metadata,
            "workflow_name": self.workflow_name,
            "workflow_version": self.workflow_version,
            "user_input": self.user_input,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
        }


class _FakeNodeRun:
    def __init__(self, node_run_id: str, workflow_run_id: str):
        self.id = node_run_id
        self.workflow_run_id = workflow_run_id
        self.node_name = "generate_outline"
        self.input_artifact_ids = []
        self.output_artifact_ids = []

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "workflow_run_id": self.workflow_run_id,
            "node_name": self.node_name,
            "input_artifact_ids": self.input_artifact_ids,
            "output_artifact_ids": self.output_artifact_ids,
        }


class _FakeArtifact:
    def __init__(self, artifact_id: str, workflow_run_id: str):
        self.id = artifact_id
        self.workflow_run_id = workflow_run_id
        self.type = "outline"
        self.version = 1
        self.content = {"title": "t"}
        self.metadata = {}

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "workflow_run_id": self.workflow_run_id,
            "type": self.type,
            "version": self.version,
            "content": self.content,
            "metadata": self.metadata,
        }


class _FakeStore:
    def __init__(self):
        base_time = datetime(2026, 3, 8, 10, 0, tzinfo=UTC)
        self.workflow_runs = {
            "wf-123": _FakeWorkflowRun(
                "wf-123",
                metadata={"workspace_id": "ws-1", "user_id": "user-1"},
                started_at=base_time,
            ),
            "wf-124": _FakeWorkflowRun(
                "wf-124",
                metadata={"workspace_id": "ws-1", "user_id": "user-1"},
                status="completed",
                current_node="finalize",
                started_at=base_time + timedelta(hours=1),
                completed_at=base_time + timedelta(hours=1, minutes=5),
                total_duration_ms=300000,
            ),
            "wf-same-workspace-other-user": _FakeWorkflowRun(
                "wf-same-workspace-other-user",
                metadata={"workspace_id": "ws-1", "user_id": "user-2"},
                started_at=base_time + timedelta(hours=2),
            ),
            "wf-new": _FakeWorkflowRun("wf-new"),
            "wf-rerun": _FakeWorkflowRun("wf-rerun"),
            "wf-foreign": _FakeWorkflowRun(
                "wf-foreign",
                metadata={"workspace_id": "ws-2", "user_id": "user-2"},
                started_at=base_time + timedelta(hours=3),
            ),
        }
        self.node_runs = {
            "node-123": _FakeNodeRun("node-123", "wf-123"),
            "node-foreign": _FakeNodeRun("node-foreign", "wf-foreign"),
        }
        self.artifacts = {
            "art-123": _FakeArtifact("art-123", "wf-123"),
            "art-foreign": _FakeArtifact("art-foreign", "wf-foreign"),
        }

    async def get_workflow_run(self, workflow_run_id: str):
        return self.workflow_runs.get(workflow_run_id)

    async def update_workflow_run(self, workflow_run):
        self.workflow_runs[workflow_run.id] = workflow_run
        return workflow_run

    async def get_node_run(self, node_run_id: str):
        return self.node_runs.get(node_run_id)

    async def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    async def get_version_history(self, artifact_id: str):
        artifact = self.artifacts.get(artifact_id)
        return [artifact] if artifact else []

    async def get_all_workflow_runs(self):
        return list(self.workflow_runs.values())

    async def list_workflow_runs(self, *, workspace_id: str, user_id: str | None = None):
        runs = []
        for workflow_run in self.workflow_runs.values():
            metadata = workflow_run.metadata or {}
            if metadata.get("workspace_id") != workspace_id:
                continue
            if user_id is not None and metadata.get("user_id") != user_id:
                continue
            runs.append(workflow_run)
        return sorted(runs, key=lambda run: run.started_at, reverse=True)


class _FakeTraceService:
    async def get_workflow_trace(self, workflow_run_id: str):
        return {
            "workflow": {
                "id": workflow_run_id,
                "status": "running",
                "current_node": "generate_content",
                "metadata": {},
            },
            "nodes": [],
            "artifacts": {},
            "timeline": [],
        }

    async def get_node_detail(self, node_run_id: str):
        return {"node": {"id": node_run_id}, "input_artifacts": [], "output_artifacts": []}

    async def get_artifact_history(self, artifact_id: str):
        return [{"id": artifact_id, "version": 1}]


class _FakeRerunService:
    def __init__(self, store: _FakeStore):
        self.store = store

    async def get_rerun_options(self, workflow_run_id: str):
        return [{"node_name": "generate_outline"}]

    async def prepare_rerun_state(
        self, workflow_run_id: str, from_node: str, updated_input: dict | None = None
    ):
        return updated_input or {}

    async def create_rerun_workflow(self, workflow_run_id: str, from_node: str, reason: str = ""):
        return self.store.workflow_runs["wf-rerun"]

    async def get_rerun_history(self, workflow_run_id: str):
        return [{"id": workflow_run_id}]


class _FakeGraph:
    async def aget_state(self, config):
        class _Snapshot:
            def __init__(self):
                self.values = {}

        return _Snapshot()


class _FakeWorkflow:
    def __init__(self, store: _FakeStore):
        self.store = store
        self.graph = _FakeGraph()

    def _get_workflow_status(self, state):
        if state.get("is_paused"):
            return "paused"
        return "running"

    async def start(
        self,
        user_input: str,
        workflow_definition_id: str | None = None,
        workflow_version_id: str | None = None,
    ):
        return {
            "workflow_run_id": "wf-new",
            "status": "running",
            "state": {},
        }

    async def pause(self, workflow_run_id: str, reason: str = ""):
        return {"workflow_run_id": workflow_run_id, "status": "paused", "state": {}}

    async def resume_paused(self, workflow_run_id: str):
        return {"workflow_run_id": workflow_run_id, "status": "running", "state": {}}

    async def resume(self, workflow_run_id: str, user_input: dict):
        return {"workflow_run_id": workflow_run_id, "status": "running", "state": user_input}

    async def approve_outline(
        self,
        workflow_run_id: str,
        action: str,
        feedback: str = "",
        modified_outline: dict | None = None,
    ):
        return {"workflow_run_id": workflow_run_id, "status": "running", "state": {}}


def _make_client(user_id: str | None = None, workspace_id: str | None = None) -> TestClient:
    client = TestClient(app)
    if user_id:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(user_id=user_id, workspace_id=workspace_id),
        )
    return client


def _install_runtime_fakes(monkeypatch, store: _FakeStore | None = None) -> _FakeStore:
    fake_store = store or _FakeStore()
    monkeypatch.setattr("services.get_artifact_store", lambda: fake_store)
    monkeypatch.setattr("services.get_trace_service", lambda: _FakeTraceService())
    monkeypatch.setattr("services.get_rerun_service", lambda: _FakeRerunService(fake_store))
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow(fake_store))
    return fake_store


async def _allow_workspace_permission(request, resource: str, action: str):
    return "user-1", "ws-1", "editor"


async def _allow_workspace_admin_permission(request, resource: str, action: str):
    return "user-1", "ws-1", "admin"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/workflow/start", {"user_input": "hello"}),
        ("get", "/api/workflow/runs", None),
        ("get", "/api/workflow/wf-123", None),
        ("post", "/api/workflow/wf-123/pause", {"reason": "先暂停"}),
        ("post", "/api/workflow/wf-123/resume", {}),
        ("post", "/api/workflow/wf-123/clarify", {"clarifications": {"topic": "A"}}),
        ("post", "/api/workflow/wf-123/approve-outline", {"action": "approve"}),
        ("post", "/api/workflow/wf-123/approve-fact-check", {"decisions": {"claim-1": "confirm"}}),
        ("get", "/api/workflow/wf-123/rerun-options", None),
        ("post", "/api/workflow/wf-123/rerun", {"from_node": "generate_outline"}),
        ("get", "/api/workflow/wf-123/rerun-history", None),
        ("get", "/api/trace/wf-123", None),
        ("get", "/api/trace/node/node-123", None),
        ("get", "/api/artifact/art-123", None),
        ("get", "/api/artifact/art-123/history", None),
    ],
)
def test_runtime_and_trace_routes_require_authentication(
    monkeypatch, method: str, path: str, payload: dict | None
):
    _install_runtime_fakes(monkeypatch)
    client = _make_client()

    response = (
        getattr(client, method)(path, json=payload)
        if payload is not None
        else getattr(client, method)(path)
    )

    assert response.status_code == 401


def test_start_workflow_persists_runtime_ownership(monkeypatch):
    store = _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.post("/api/workflow/start", json={"user_input": "hello"})

    assert response.status_code == 200
    assert store.workflow_runs["wf-new"].metadata["user_id"] == "user-1"
    assert store.workflow_runs["wf-new"].metadata["workspace_id"] == "ws-1"


def test_runs_list_returns_current_user_visible_runs(monkeypatch):
    _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.get("/api/workflow/runs")

    assert response.status_code == 200
    body = response.json()
    assert [run["id"] for run in body["runs"]] == ["wf-124", "wf-123"]
    assert set(body["runs"][0].keys()) == {
        "id",
        "workflow_name",
        "status",
        "current_node",
        "user_input",
        "started_at",
        "completed_at",
        "total_duration_ms",
    }


def test_runs_list_admin_scope_still_excludes_foreign_workspace(monkeypatch):
    _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_admin_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.get("/api/workflow/runs")

    assert response.status_code == 200
    body = response.json()
    assert [run["id"] for run in body["runs"]] == [
        "wf-same-workspace-other-user",
        "wf-124",
        "wf-123",
    ]


def test_workflow_status_rejects_foreign_workspace(monkeypatch):
    _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.get("/api/workflow/wf-foreign")

    assert response.status_code == 403
    assert response.json()["detail"] == "您无权访问该工作空间中的任务"


def test_trace_rejects_foreign_workspace(monkeypatch):
    _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.get("/api/trace/wf-foreign")

    assert response.status_code == 403
    assert response.json()["detail"] == "您无权访问该工作空间中的任务"


def test_trace_node_returns_404_for_missing_resource(monkeypatch):
    _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.get("/api/trace/node/node-missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "NodeRun not found"


def test_artifact_history_rejects_foreign_workspace_without_wrapping_500(monkeypatch):
    _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.get("/api/artifact/art-foreign/history")

    assert response.status_code == 403
    assert response.json()["detail"] == "您无权访问该工作空间中的任务"


def test_rerun_persists_runtime_ownership(monkeypatch):
    store = _install_runtime_fakes(monkeypatch)
    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    client = _make_client(user_id="user-1", workspace_id="ws-1")

    response = client.post("/api/workflow/wf-123/rerun", json={"from_node": "generate_outline"})

    assert response.status_code == 200
    assert store.workflow_runs["wf-rerun"].metadata["user_id"] == "user-1"
    assert store.workflow_runs["wf-rerun"].metadata["workspace_id"] == "ws-1"
