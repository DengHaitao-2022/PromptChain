from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app


class _FakeWorkflow:
    async def pause(self, workflow_run_id: str, reason: str = ""):
        return {
            "workflow_run_id": workflow_run_id,
            "status": "paused",
            "state": {
                "is_paused": True,
                "pause_reason": reason,
            },
        }

    async def resume_paused(self, workflow_run_id: str):
        return {
            "workflow_run_id": workflow_run_id,
            "status": "running",
            "state": {
                "is_paused": False,
            },
        }


def test_pause_endpoint_exists_and_returns_workflow_response(monkeypatch):
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = TestClient(app)
    response = client.post(
        "/api/workflow/wf-pause/pause",
        json={"reason": "用户主动暂停"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    assert response.json()["state"]["is_paused"] is True


def test_resume_endpoint_exists_and_returns_workflow_response(monkeypatch):
    monkeypatch.setattr("graph.get_workflow", lambda: _FakeWorkflow())

    client = TestClient(app)
    response = client.post("/api/workflow/wf-pause/resume", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["state"]["is_paused"] is False
