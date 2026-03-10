from pathlib import Path
import sys
from datetime import datetime, UTC
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._runtime_auth import authenticated_client, ownership_metadata
from main import app


class _FakeWorkflowRun:
    def __init__(self):
        self.id = "wf-trace"
        self.status = "running"
        self.current_node = "check_facts"
        self.started_at = datetime(2026, 3, 8, 11, 0, tzinfo=UTC)
        self.metadata = ownership_metadata({"gate": {"opened_at": "2026-03-08T11:02:00Z"}})


class _FakeStore:
    async def get_workflow_run(self, workflow_run_id: str):
        if workflow_run_id == "wf-trace":
            return _FakeWorkflowRun()
        return None


class _FakeTraceService:
    async def get_workflow_trace(self, workflow_run_id: str):
        return {
            "workflow": {
                "id": workflow_run_id,
                "status": "running",
                "current_node": "check_facts",
                "metadata": {},
            },
            "nodes": [],
            "artifacts": {},
            "timeline": [],
        }


class _FakeGraph:
    async def aget_state(self, config):
        return SimpleNamespace(
            values={
                "awaiting_fact_check_approval": True,
                "fact_check_report": {
                    "claims": [{"id": "claim-1", "text": "结论", "category": "事实", "section_id": "intro"}],
                    "results": [
                        {
                            "claim_id": "claim-1",
                            "is_verified": False,
                            "confidence": 0.2,
                            "risk_level": "high",
                            "suggested_correction": "建议修正",
                            "verification_question": "该结论是否有来源支撑？",
                            "verification_answer": "",
                        }
                    ],
                    "total_claims": 1,
                    "verified_count": 0,
                    "high_risk_count": 1,
                },
            }
        )


class _FakeWorkflow:
    def __init__(self):
        self.graph = _FakeGraph()

    def _get_workflow_status(self, state):
        return "awaiting_fact_check_approval"


def test_trace_payload_includes_public_status_and_gate_timeline(monkeypatch):
    monkeypatch.setattr("services.get_trace_service", lambda: _FakeTraceService())
    monkeypatch.setattr("services.get_artifact_store", lambda: _FakeStore())
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = authenticated_client(monkeypatch)
    res = client.get("/api/trace/wf-trace")

    assert res.status_code == 200
    body = res.json()
    assert body["workflow"]["status"] == "awaiting_fact_check_approval"
    assert body["workflow"]["current_node"] == "check_facts"
    assert body["workflow"]["gate"]["gate_type"] == "fact_check"
    assert any(event["event"] == "workflow_gate_waiting" for event in body["timeline"])
