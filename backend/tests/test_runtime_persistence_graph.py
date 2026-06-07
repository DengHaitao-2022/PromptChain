import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.artifact_store as artifact_store_module
import services.workflow_definition_service as workflow_definition_service_module
from db import postgres_store as postgres_store_module
from db.postgres_store import PostgresArtifactStore
from graph.conditions import should_proceed_after_fact_check, should_regenerate_outline
from graph.content_generation_graph import ContentGenerationWorkflow
from models.artifact import WorkflowRun
from tools import ToolCall, ToolCallStatus


def reset_store_singleton() -> None:
    artifact_store_module._artifact_store = None


def test_get_artifact_store_defaults_to_postgres_backend(monkeypatch):
    monkeypatch.delenv("RUNTIME_STORE_BACKEND", raising=False)
    reset_store_singleton()

    store = artifact_store_module.get_artifact_store()

    assert isinstance(store, PostgresArtifactStore)


def test_get_artifact_store_can_fall_back_to_memory(monkeypatch):
    monkeypatch.setenv("RUNTIME_STORE_BACKEND", "memory")
    reset_store_singleton()

    store = artifact_store_module.get_artifact_store()

    assert isinstance(store, artifact_store_module.ArtifactStore)


def test_workflow_run_tracks_published_workflow_references():
    workflow_run = WorkflowRun(
        user_input="写一篇 Agent 架构文章",
        workflow_definition_id="wf-def-1",
        workflow_version_id="wf-ver-3",
    )

    dumped = workflow_run.model_dump()

    assert dumped["workflow_definition_id"] == "wf-def-1"
    assert dumped["workflow_version_id"] == "wf-ver-3"


def test_workflow_status_prioritizes_gate_over_manual_pause():
    workflow = object.__new__(ContentGenerationWorkflow)

    assert (
        ContentGenerationWorkflow._get_workflow_status(
            workflow,
            {"needs_clarification": True, "is_paused": True},
        )
        == "needs_clarification"
    )
    assert (
        ContentGenerationWorkflow._get_workflow_status(
            workflow,
            {"is_paused": True},
        )
        == "paused"
    )
    assert (
        ContentGenerationWorkflow._get_workflow_status(
            workflow,
            {"awaiting_tool_approval": True, "is_paused": True},
        )
        == "awaiting_tool_approval"
    )


def test_runtime_schema_statements_include_workflow_reference_columns():
    statements = postgres_store_module._runtime_upgrade_statements(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain"
    )

    assert any("ADD COLUMN IF NOT EXISTS workflow_definition_id" in stmt for stmt in statements)
    assert any("ADD COLUMN IF NOT EXISTS workflow_version_id" in stmt for stmt in statements)


def test_runtime_schema_statements_match_audit_log_baseline_index():
    statements = postgres_store_module._runtime_upgrade_statements(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain"
    )

    assert any(
        stmt == "CREATE INDEX IF NOT EXISTS ix_audit_logs_event_id ON audit_logs (event_id)"
        for stmt in statements
    )
    assert not any(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_logs_event_id" in stmt for stmt in statements
    )


def test_runtime_schema_statements_prepare_pgvector_before_metadata_create_all():
    statements = postgres_store_module._runtime_schema_statements(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain"
    )

    assert "CREATE EXTENSION IF NOT EXISTS vector" in statements


@pytest.mark.asyncio
async def test_workflow_definition_schema_guard_skips_runtime_ddl(monkeypatch):
    class FakeDialect:
        name = "postgresql"

    class FakeBind:
        dialect = FakeDialect()

    class FakeSession:
        executed: list[str]
        committed: bool

        def __init__(self):
            self.executed = []
            self.committed = False

        def get_bind(self):
            return FakeBind()

        async def execute(self, statement):
            self.executed.append(str(statement))

        async def commit(self):
            self.committed = True

    monkeypatch.setenv("DATABASE_AUTO_SCHEMA_INIT", "false")
    workflow_definition_service_module.WorkflowDefinitionService._schema_ready = False
    session = FakeSession()

    await workflow_definition_service_module.WorkflowDefinitionService.ensure_schema(session)

    assert session.executed == []
    assert session.committed is False
    assert workflow_definition_service_module.WorkflowDefinitionService._schema_ready is True
    workflow_definition_service_module.WorkflowDefinitionService._schema_ready = False


def test_split_migration_statements_handles_transactions_comments_and_do_blocks():
    statements = postgres_store_module._split_migration_statements(
        """
        -- 注释不应成为语句
        BEGIN;
        CREATE EXTENSION IF NOT EXISTS vector;
        DO $$
        BEGIN
            IF TRUE THEN
                CREATE INDEX IF NOT EXISTS demo_idx ON demo (id);
            END IF;
        END $$;
        COMMIT;
        """
    )

    assert statements == [
        "CREATE EXTENSION IF NOT EXISTS vector",
        """DO $$
        BEGIN
            IF TRUE THEN
                CREATE INDEX IF NOT EXISTS demo_idx ON demo (id);
            END IF;
        END $$""",
    ]


def test_outline_gate_routes_pending_decision_to_approval_node():
    route = should_regenerate_outline(
        {
            "outline": {"title": "原提纲"},
            "outline_approved": False,
            "awaiting_outline_approval": False,
            "user_decision": {"action": "modify", "modified_outline": {"title": "新提纲"}},
        }
    )

    assert route == "approve_outline"


def test_fact_check_gate_routes_pending_decisions_to_approval_node():
    route = should_proceed_after_fact_check(
        {
            "fact_check_report": {"results": []},
            "awaiting_fact_check_approval": False,
            "fact_check_decisions": {"claim-1": "confirm"},
        }
    )

    assert route == "approve_fact_check"


class _FakeGraph:
    def __init__(self):
        self.updated = []
        self.invoked = []

    async def aget_state(self, config):
        return SimpleNamespace(
            values={"needs_clarification": True},
            config=config,
            next=("clarify_intent",),
        )

    async def aupdate_state(self, config, values, as_node=None, task_id=None):
        self.updated.append((config, values, as_node, task_id))
        return {
            "configurable": {
                "thread_id": config["configurable"]["thread_id"],
                "checkpoint_id": "cp-next",
            }
        }

    async def ainvoke(self, payload, config):
        self.invoked.append((payload, config))
        return {"final_content": {"intro": "done"}}


@pytest.mark.asyncio
async def test_resume_updates_checkpoint_state_before_continuing():
    workflow = object.__new__(ContentGenerationWorkflow)
    workflow.graph = _FakeGraph()

    async def fake_drive(
        workflow_run_id: str,
        *,
        initial_state=None,
        config=None,
        emit_resumed=False,
    ):
        workflow.graph.invoked.append((None, config))
        return {
            "workflow_run_id": workflow_run_id,
            "state": {"final_content": {"intro": "done"}},
            "status": "completed",
        }

    workflow._drive_workflow = fake_drive

    result = await ContentGenerationWorkflow.resume(
        workflow,
        workflow_run_id="wf-123",
        user_input={"user_clarifications": {"tone": "正式"}},
    )

    assert workflow.graph.updated[0][1] == {"user_clarifications": {"tone": "正式"}}
    assert workflow.graph.invoked[0][0] is None
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_approve_outline_resumes_from_generate_outline_checkpoint():
    workflow = object.__new__(ContentGenerationWorkflow)
    workflow.graph = _FakeGraph()

    async def fake_drive(
        workflow_run_id: str,
        *,
        initial_state=None,
        config=None,
        emit_resumed=False,
    ):
        workflow.graph.invoked.append((None, config, emit_resumed))
        return {
            "workflow_run_id": workflow_run_id,
            "state": {"outline_approved": True},
            "status": "running",
        }

    workflow._drive_workflow = fake_drive

    await ContentGenerationWorkflow.approve_outline(
        workflow,
        workflow_run_id="wf-123",
        action="approve",
        feedback="",
    )

    assert workflow.graph.updated[0][1] == {
        "user_decision": {"action": "approve", "feedback": ""},
        "awaiting_outline_approval": False,
    }
    assert workflow.graph.updated[0][2] == "generate_outline"


@pytest.mark.asyncio
async def test_approve_fact_check_resumes_from_check_facts_checkpoint():
    workflow = object.__new__(ContentGenerationWorkflow)
    workflow.graph = _FakeGraph()

    async def fake_drive(
        workflow_run_id: str,
        *,
        initial_state=None,
        config=None,
        emit_resumed=False,
    ):
        workflow.graph.invoked.append((None, config, emit_resumed))
        return {
            "workflow_run_id": workflow_run_id,
            "state": {"awaiting_fact_check_approval": False},
            "status": "running",
        }

    workflow._drive_workflow = fake_drive

    await ContentGenerationWorkflow.approve_fact_check(
        workflow,
        workflow_run_id="wf-123",
        decisions={"claim-1": "confirm"},
        manual_corrections={},
    )

    assert workflow.graph.updated[0][1] == {
        "fact_check_decisions": {"claim-1": "confirm"},
        "manual_corrections": {},
        "awaiting_fact_check_approval": False,
    }
    assert workflow.graph.updated[0][2] == "check_facts"


@pytest.mark.asyncio
async def test_quality_metrics_include_tool_call_usage():
    store = artifact_store_module.ArtifactStore()
    workflow_run = WorkflowRun(user_input="测试工具调用指标")
    await store.create_workflow_run(workflow_run)
    await store.create_tool_call(
        ToolCall(
            workflow_run_id=workflow_run.id,
            tool_name="validation.json_schema_validate",
            status=ToolCallStatus.SUCCEEDED,
            latency_ms=120,
            token_cost=7,
            money_cost=0.03,
        )
    )
    await store.create_tool_call(
        ToolCall(
            workflow_run_id=workflow_run.id,
            tool_name="artifact.write",
            status=ToolCallStatus.FAILED,
            latency_ms=80,
            token_cost=0,
            money_cost=0,
            error_message="写入失败",
        )
    )
    workflow = object.__new__(ContentGenerationWorkflow)
    workflow.store = store

    metrics = await ContentGenerationWorkflow._build_quality_metrics(workflow, workflow_run, [])

    assert metrics["tools"] == {
        "total_calls": 2,
        "succeeded": 1,
        "failed": 1,
        "pending_approval": 0,
        "denied": 0,
        "timeout": 0,
        "total_latency_ms": 200,
        "total_token_cost": 7,
        "total_money_cost": 0.03,
        "by_tool": {
            "artifact.write": {"total_calls": 1, "failed": 1},
            "validation.json_schema_validate": {"total_calls": 1, "succeeded": 1},
        },
    }
