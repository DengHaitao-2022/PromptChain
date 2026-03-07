from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph.content_generation_graph import ContentGenerationWorkflow
from main import app


class _FakeWorkflowRun:
    def __init__(self):
        self.id = "wf-123"
        self.status = "running"
        self.current_node = "check_facts"
        self.metadata = {}


class _FakeStore:
    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == "wf-123":
            return _FakeWorkflowRun()
        return None


class _FakeGraph:
    async def aget_state(self, config):
        return SimpleNamespace(values={"awaiting_fact_check_approval": True})


class _FakeWorkflow:
    def __init__(self):
        self.graph = _FakeGraph()

    async def resume(self, workflow_run_id: str, user_input: dict):
        return {
            "workflow_run_id": workflow_run_id,
            "status": "running",
            "state": {
                "awaiting_fact_check_approval": False,
                "fact_check_report": {
                    "claims": [],
                    "results": [],
                    "total_claims": 0,
                    "verified_count": 0,
                    "high_risk_count": 0,
                },
            },
        }

    def _get_workflow_status(self, state: dict):
        return "awaiting_fact_check_approval" if state.get("awaiting_fact_check_approval") else "running"


def test_approve_fact_check_endpoint_exists_and_resumes_workflow(monkeypatch):
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakeStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = TestClient(app)
    payload = {
        "decisions": {"c1": "confirm"},
        "manual_corrections": {},
    }
    res = client.post("/api/workflow/wf-123/approve-fact-check", json=payload)

    assert res.status_code == 200
    assert res.json()["status"] in {"running", "completed"}


def test_workflow_status_includes_fact_check_waiting_state():
    workflow = object.__new__(ContentGenerationWorkflow)
    status = ContentGenerationWorkflow._get_workflow_status(
        workflow,
        {"awaiting_fact_check_approval": True},
    )
    assert status == "awaiting_fact_check_approval"
