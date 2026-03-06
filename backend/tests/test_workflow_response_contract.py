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


def test_get_workflow_status_returns_workflow_response_shape(monkeypatch):
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakeStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = TestClient(app)
    res = client.get("/api/workflow/wf-123")

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"workflow_run_id", "status", "state"}
