from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from main import app


@pytest.fixture(autouse=True)
def _runtime_auth_bypass(monkeypatch):
    app.dependency_overrides[main.get_current_user] = lambda: {
        "sub": "user-1",
        "workspace_id": "ws-1",
    }

    async def _allow_workflow_run_access(user, workflow_run_id, resource="workflow_run", action="read"):
        return None

    monkeypatch.setattr(main, "require_workflow_run_access", _allow_workflow_run_access)
    yield
    app.dependency_overrides.clear()


class _FakeWorkflowRun:
    def __init__(self, *, status: str = "running"):
        self.id = "wf-pause"
        self.status = status
        self.current_node = "generate_content"
        self.metadata = {}


class _FakeStore:
    def __init__(self):
        self.workflow_run = _FakeWorkflowRun()

    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == self.workflow_run.id:
            return self.workflow_run
        return None

    async def update_workflow_run(self, workflow_run: _FakeWorkflowRun):
        self.workflow_run = workflow_run
        return workflow_run


class _FakeGraph:
    async def aget_state(self, config):
        class _Snapshot:
            values = {}

        return _Snapshot()


class _FakeWorkflow:
    def __init__(self, store: _FakeStore):
        self.store = store
        self.graph = _FakeGraph()

    def _get_workflow_status(self, state):
        if state.get("is_paused"):
            return "paused"
        return "running"

    async def pause(self, workflow_run_id: str, reason: str = ""):
        self.store.workflow_run.status = "paused"
        return {
            "workflow_run_id": workflow_run_id,
            "status": "paused",
            "state": {
                "is_paused": True,
                "pause_reason": reason,
            },
        }

    async def resume_paused(self, workflow_run_id: str):
        self.store.workflow_run.status = "running"
        return {
            "workflow_run_id": workflow_run_id,
            "status": "running",
            "state": {
                "is_paused": False,
            },
        }


def test_pause_endpoint_exists_and_returns_workflow_response(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr("services.get_artifact_store", lambda: store)
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow(store))

    client = TestClient(app)
    response = client.post(
        "/api/workflow/wf-pause/pause",
        json={"reason": "用户主动暂停"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    assert response.json()["state"]["pause"]["reason"] == "用户主动暂停"
    assert response.json()["state"]["pause"]["paused_at"]
    assert response.json()["state"]["pause"]["source"] == "user"


def test_resume_endpoint_exists_and_returns_workflow_response(monkeypatch):
    store = _FakeStore()
    store.workflow_run.status = "paused"
    store.workflow_run.metadata = {
        "pause": {
            "reason": "用户主动暂停",
            "paused_at": "2026-03-08T10:00:00Z",
            "source": "user",
        }
    }
    monkeypatch.setattr("services.get_artifact_store", lambda: store)
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow(store))

    client = TestClient(app)
    response = client.post("/api/workflow/wf-pause/resume", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["state"]["pause"]["reason"] == "用户主动暂停"
    assert response.json()["state"]["pause"]["paused_at"] == "2026-03-08T10:00:00Z"
    assert response.json()["state"]["pause"]["resumed_at"]
