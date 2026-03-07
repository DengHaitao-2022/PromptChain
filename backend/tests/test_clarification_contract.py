from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app


class _FakeWorkflowRun:
    def __init__(self):
        self.id = "wf-clarify"
        self.status = "running"


class _FakeStore:
    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == "wf-clarify":
            return _FakeWorkflowRun()
        return None


class _FakeGraph:
    async def aget_state(self, config):
        return SimpleNamespace(
            values={
                "needs_clarification": True,
                "clarification_questions": [
                    {
                        "field": "tone",
                        "question": "希望语气更正式还是更轻松？",
                        "priority": 1,
                        "default_assumption": "轻松活泼",
                    }
                ],
            }
        )


class _FakeWorkflow:
    def __init__(self):
        self.graph = _FakeGraph()

    def _get_workflow_status(self, state):
        return "needs_clarification"


def test_clarification_questions_are_exposed_with_enum_priority(monkeypatch):
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakeStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = TestClient(app)
    res = client.get("/api/workflow/wf-clarify")

    assert res.status_code == 200
    q = res.json()["state"]["clarification_questions"][0]
    assert q["priority"] in {"high", "medium", "low"}
    assert "field" in q and "question" in q
    gate = res.json()["state"]["gate"]
    assert gate["gate_type"] == "clarification"
    assert gate["questions"][0]["default_assumption"] == "轻松活泼"
