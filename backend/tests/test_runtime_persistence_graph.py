import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.artifact_store as artifact_store_module
from db import postgres_store as postgres_store_module
from db.postgres_store import PostgresArtifactStore
from graph.content_generation_graph import ContentGenerationWorkflow
from models.artifact import WorkflowRun


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


def test_runtime_schema_statements_include_workflow_reference_columns():
    statements = postgres_store_module._runtime_schema_statements(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain"
    )

    assert any("ADD COLUMN IF NOT EXISTS workflow_definition_id" in stmt for stmt in statements)
    assert any("ADD COLUMN IF NOT EXISTS workflow_version_id" in stmt for stmt in statements)


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
