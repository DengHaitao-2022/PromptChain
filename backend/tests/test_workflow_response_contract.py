from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app


class _FakeWorkflowRun:
    def __init__(self):
        self.id = "wf-123"
        self.status = "running"

    def model_dump(self):
        # 模拟旧接口形状（不符合统一 WorkflowResponse）
        return {
            "id": self.id,
            "status": self.status,
            "workflow_name": "content_generation",
            "user_input": "test",
        }


class _FakeStore:
    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == "wf-123":
            return _FakeWorkflowRun()
        return None


class _FakeGraph:
    async def aget_state(self, config):
        return SimpleNamespace(
            values={
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


class _FakeWorkflow:
    def __init__(self):
        self.graph = _FakeGraph()

    def _get_workflow_status(self, state):
        return "needs_clarification"


class _FakePausedWorkflowRun:
    def __init__(self):
        self.id = "wf-paused"
        self.status = "paused"


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
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakeStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = TestClient(app)
    res = client.get("/api/workflow/wf-123")

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"workflow_run_id", "status", "state"}


def test_manual_pause_status_beats_running_graph_snapshot(monkeypatch):
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakePausedStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeRunningWorkflow())

    client = TestClient(app)
    res = client.get("/api/workflow/wf-paused")

    assert res.status_code == 200
    assert res.json()["status"] == "paused"
