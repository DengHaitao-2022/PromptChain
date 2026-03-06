from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph.content_generation_graph import ContentGenerationWorkflow
from main import app


class _FakeWorkflow:
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


def test_approve_fact_check_endpoint_exists_and_resumes_workflow(monkeypatch):
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
