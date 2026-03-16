import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._runtime_auth import authenticated_client, ownership_metadata


class _FakeWorkflowRun:
    def __init__(
        self,
        *,
        status: str = "running",
        current_node: str | None = None,
        metadata: dict | None = None,
    ):
        self.id = "wf-123"
        self.status = status
        self.current_node = current_node
        self.metadata = ownership_metadata(metadata)
        self.started_at = datetime(2026, 3, 8, 10, 0, tzinfo=UTC)

    def model_dump(self):
        return {
            "id": self.id,
            "status": self.status,
            "workflow_name": "content_generation",
            "user_input": "test",
            "current_node": self.current_node,
            "metadata": self.metadata,
        }


class _FakeStore:
    def __init__(self, workflow_run: _FakeWorkflowRun | None = None):
        self.workflow_run = workflow_run or _FakeWorkflowRun()

    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == self.workflow_run.id:
            return self.workflow_run
        return None

    async def update_workflow_run(self, workflow_run: _FakeWorkflowRun):
        self.workflow_run = workflow_run
        return workflow_run


class _FakeGraph:
    def __init__(self, values: dict | None = None):
        self.values = values or {}

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values)


class _FakeWorkflow:
    def __init__(self, state: dict | None = None, store: _FakeStore | None = None):
        self.graph = _FakeGraph(state)
        self.store = store

    def _get_workflow_status(self, state):
        if state.get("needs_clarification"):
            return "needs_clarification"
        if state.get("is_paused"):
            return "paused"
        return "running"

    async def pause(self, workflow_run_id: str, reason: str = ""):
        if self.store:
            self.store.workflow_run.status = "paused"
        return {
            "workflow_run_id": workflow_run_id,
            "status": "paused",
            "state": {
                "current_node": "generate_content",
                "is_paused": True,
                "pause": {
                    "reason": reason,
                    "paused_at": "2026-03-08T10:02:00Z",
                    "source": "user",
                },
            },
        }

    async def resume_paused(self, workflow_run_id: str):
        if self.store:
            self.store.workflow_run.status = "running"
        return {
            "workflow_run_id": workflow_run_id,
            "status": "running",
            "state": {
                "current_node": "generate_content",
                "is_paused": False,
                "pause": {
                    "reason": "等待人工复核",
                    "paused_at": "2026-03-08T10:02:00Z",
                    "resumed_at": "2026-03-08T10:03:00Z",
                    "source": "user",
                },
            },
        }


class _FakePausedWorkflowRun:
    def __init__(self):
        self.id = "wf-paused"
        self.status = "paused"
        self.metadata = ownership_metadata()


class _FakePausedStore:
    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == "wf-paused":
            return _FakePausedWorkflowRun()
        return None


class _FakeRunningGraph:
    async def aget_state(self, config):
        return SimpleNamespace(values={"current_node": "generate_outline"})


class _FakeRunningWorkflow:
    def __init__(self):
        self.graph = _FakeRunningGraph()

    def _get_workflow_status(self, state):
        return "running"


def test_get_workflow_status_returns_workflow_response_shape(monkeypatch):
    store = _FakeStore(
        _FakeWorkflowRun(
            current_node="parse_intent",
            metadata={"gate": {"opened_at": "2026-03-08T10:01:00Z"}},
        )
    )
    workflow = _FakeWorkflow(
        {
            "needs_clarification": True,
            "clarification_questions": [
                {
                    "field": "audience",
                    "question": "目标读者是谁？",
                    "priority": 1,
                }
            ],
        }
    )
    monkeypatch.setattr("services.get_artifact_store", lambda: store)
    monkeypatch.setattr("graph.get_workflow", lambda: workflow)

    client = authenticated_client(monkeypatch)
    res = client.get("/api/workflow/wf-123")

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"workflow_run_id", "status", "state"}
    assert body["status"] == "needs_clarification"
    assert body["state"]["current_node"] == "parse_intent"
    assert body["state"]["gate"]["gate_type"] == "clarification"
    assert body["state"]["gate"]["opened_at"] == "2026-03-08T10:01:00Z"


def test_pause_and_resume_endpoints_round_trip_pause_metadata(monkeypatch):
    store = _FakeStore(_FakeWorkflowRun(current_node="generate_content"))
    workflow = _FakeWorkflow({}, store=store)
    monkeypatch.setattr("services.get_artifact_store", lambda: store)
    monkeypatch.setattr("graph.get_workflow", lambda: workflow)

    client = authenticated_client(monkeypatch)

    pause_res = client.post(
        "/api/workflow/wf-123/pause",
        json={"reason": "等待人工复核"},
    )
    assert pause_res.status_code == 200
    pause_body = pause_res.json()
    assert pause_body["status"] == "paused"
    assert pause_body["state"]["current_node"] == "generate_content"
    assert pause_body["state"]["pause"]["reason"] == "等待人工复核"
    assert pause_body["state"]["pause"]["paused_at"]

    resume_res = client.post("/api/workflow/wf-123/resume", json={})
    assert resume_res.status_code == 200
    resume_body = resume_res.json()
    assert resume_body["status"] == "running"
    assert resume_body["state"]["pause"]["paused_at"]
    assert resume_body["state"]["pause"]["resumed_at"]


def test_pause_rejects_gate_waiting_workflow(monkeypatch):
    store = _FakeStore(_FakeWorkflowRun(current_node="parse_intent"))
    workflow = _FakeWorkflow(
        {
            "needs_clarification": True,
            "clarification_questions": [
                {
                    "field": "audience",
                    "question": "目标读者是谁？",
                    "priority": 1,
                }
            ],
        }
    )
    monkeypatch.setattr("services.get_artifact_store", lambda: store)
    monkeypatch.setattr("graph.get_workflow", lambda: workflow)

    client = authenticated_client(monkeypatch)
    res = client.post("/api/workflow/wf-123/pause", json={"reason": "先暂停"})

    assert res.status_code == 409
    assert "Gate" in res.json()["detail"]


def test_manual_pause_status_beats_running_graph_snapshot(monkeypatch):
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakePausedStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeRunningWorkflow())

    client = authenticated_client(monkeypatch)
    res = client.get("/api/workflow/wf-paused")

    assert res.status_code == 200
    assert res.json()["status"] == "paused"


def test_failed_workflow_status_surfaces_persisted_error(monkeypatch):
    store = _FakeStore(
        _FakeWorkflowRun(
            status="failed",
            metadata={"error": "LLM API key 无效"},
        )
    )
    workflow = _FakeWorkflow({})
    monkeypatch.setattr("services.get_artifact_store", lambda: store)
    monkeypatch.setattr("graph.get_workflow", lambda: workflow)

    client = authenticated_client(monkeypatch)
    res = client.get("/api/workflow/wf-123")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failed"
    assert body["state"]["error"] == "LLM API key 无效"
