from pathlib import Path
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


class _FakeWorkflowRun:
    def __init__(self, metadata: dict | None = None):
        self.id = "wf-123"
        self.metadata = metadata or {}


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


@pytest.mark.asyncio
async def test_annotate_workflow_run_ownership_persists_workspace_and_user(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr("services.get_artifact_store", lambda: store)

    workflow_run = await main.annotate_workflow_run_ownership("wf-123", "user-1", "ws-1")

    assert workflow_run is store.workflow_run
    assert workflow_run.metadata["user_id"] == "user-1"
    assert workflow_run.metadata["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_require_workflow_run_access_allows_same_user_in_same_workspace(monkeypatch):
    store = _FakeStore(_FakeWorkflowRun({"workspace_id": "ws-1", "user_id": "user-1"}))
    monkeypatch.setattr("services.get_artifact_store", lambda: store)

    async def _allow_workspace_permission(user, resource, action):
        return ("user-1", "ws-1", "editor")

    monkeypatch.setattr(main, "require_workspace_permission", _allow_workspace_permission)
    monkeypatch.setattr("services.permission_service.is_admin_role", lambda role: False)

    workflow_run = await main.require_workflow_run_access({"sub": "user-1", "workspace_id": "ws-1"}, "wf-123")

    assert workflow_run is store.workflow_run


@pytest.mark.asyncio
async def test_require_workflow_run_access_rejects_foreign_user(monkeypatch):
    store = _FakeStore(_FakeWorkflowRun({"workspace_id": "ws-1", "user_id": "user-2"}))
    monkeypatch.setattr("services.get_artifact_store", lambda: store)

    async def _allow_workspace_permission(user, resource, action):
        return ("user-1", "ws-1", "editor")

    monkeypatch.setattr(main, "require_workspace_permission", _allow_workspace_permission)
    monkeypatch.setattr("services.permission_service.is_admin_role", lambda role: False)

    with pytest.raises(HTTPException) as exc_info:
        await main.require_workflow_run_access({"sub": "user-1", "workspace_id": "ws-1"}, "wf-123")

    assert exc_info.value.status_code == 403
    assert "只能访问自己的任务" in exc_info.value.detail
