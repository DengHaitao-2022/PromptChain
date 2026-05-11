import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.workflow_helpers as workflow_helpers
from main import app
from routes.auth_routes import ACCESS_TOKEN_COOKIE
from services.auth_service import create_access_token


def authenticated_client(
    monkeypatch,
    *,
    user_id: str = "user-1",
    workspace_id: str = "ws-1",
    role: str = "editor",
) -> TestClient:
    async def _allow_workspace_permission(request, resource: str, action: str):
        return user_id, workspace_id, role

    async def _fake_current_user(request):
        return {
            "id": user_id,
            "sub": user_id,
            "workspace_id": workspace_id,
            "default_workspace_id": workspace_id,
        }

    async def _skip_workflow_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(
        workflow_helpers,
        "require_workspace_permission",
        _allow_workspace_permission,
        raising=False,
    )
    monkeypatch.setattr("routes.auth_routes.get_current_user", _fake_current_user)
    monkeypatch.setattr("routes.workflow_routes._record_workflow_audit", _skip_workflow_audit)

    client = TestClient(app)
    client.cookies.set(
        ACCESS_TOKEN_COOKIE,
        create_access_token(user_id=user_id, workspace_id=workspace_id),
    )
    return client


def ownership_metadata(
    metadata: dict | None = None,
    *,
    user_id: str = "user-1",
    workspace_id: str = "ws-1",
) -> dict:
    result = {
        "user_id": user_id,
        "workspace_id": workspace_id,
    }
    if metadata:
        result.update(metadata)
    return result
