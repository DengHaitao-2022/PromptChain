import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.errors.codes import (
    WORKFLOW_NOT_FOUND,
    WORKFLOW_VALIDATION_FAILED,
    WORKFLOW_VERSION_NOT_FOUND,
)
from core.errors.context import REQUEST_ID_HEADER
from core.errors.models import ErrorEnvelope
from main import app
from models.auth_models import MemberRole
from models.result import Result
from models.workflow_definition import (
    WorkflowValidationMode,
    WorkflowValidationResult,
)


class _AsyncSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _StoreStub:
    def __init__(self, session):
        self._session = session

    def async_session(self):
        return _AsyncSessionContext(self._session)


async def _current_user(_request):
    return {
        "sub": "user-1",
        "default_workspace_id": "ws-1",
    }


async def _allow_workflow_permission(self, user_id, workspace_id, resource, action):
    assert user_id == "user-1"
    assert workspace_id == "ws-1"
    assert resource == "workflow"
    assert action in {"read", "update"}
    return MemberRole.EDITOR


def test_workflow_definition_not_found_returns_unified_error_envelope(monkeypatch):
    session = object()
    monkeypatch.setattr(
        "routes.workflow_definition_routes.get_postgres_store",
        lambda: _StoreStub(session),
    )
    monkeypatch.setattr("routes.workflow_definition_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workflow_definition_routes.PermissionService.require_permission",
        _allow_workflow_permission,
    )

    async def _get_by_id(self, workflow_id, workspace_id, **_kwargs):
        assert workflow_id == "wf-missing"
        assert workspace_id == "ws-1"
        return None

    monkeypatch.setattr(
        "routes.workflow_definition_routes.WorkflowDefinitionService.get_by_id",
        _get_by_id,
    )

    client = TestClient(app)
    response = client.get(
        "/api/workflows/wf-missing",
        headers={REQUEST_ID_HEADER: "req-workflow-definition-404"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": WORKFLOW_NOT_FOUND,
        "message": "工作流不存在",
        "request_id": "req-workflow-definition-404",
        "details": None,
        "data": None,
    }


def test_publish_invalid_workflow_returns_unified_validation_error(monkeypatch):
    session = object()
    monkeypatch.setattr(
        "routes.workflow_definition_routes.get_postgres_store",
        lambda: _StoreStub(session),
    )
    monkeypatch.setattr("routes.workflow_definition_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workflow_definition_routes.PermissionService.require_permission",
        _allow_workflow_permission,
    )

    async def _publish(self, workflow_id, workspace_id, user_id, *, change_log=""):
        assert workflow_id == "wf-invalid"
        assert workspace_id == "ws-1"
        assert user_id == "user-1"
        assert change_log == ""
        return (
            SimpleNamespace(id="wf-invalid"),
            WorkflowValidationResult(
                mode=WorkflowValidationMode.PUBLISH,
                is_valid=False,
                errors=["工作流必须至少包含一个节点"],
                warnings=[],
            ),
            None,
        )

    monkeypatch.setattr(
        "routes.workflow_definition_routes.WorkflowDefinitionService.publish",
        _publish,
    )

    client = TestClient(app)
    response = client.post(
        "/api/workflows/wf-invalid/publish",
        headers={REQUEST_ID_HEADER: "req-workflow-publish-invalid"},
        json={"change_log": ""},
    )

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "code": WORKFLOW_VALIDATION_FAILED,
        "message": "工作流未通过发布校验",
        "request_id": "req-workflow-publish-invalid",
        "details": {
            "validation": {
                "mode": "publish",
                "is_valid": False,
                "errors": ["工作流必须至少包含一个节点"],
                "warnings": [],
            }
        },
        "data": None,
    }


def test_workflow_version_not_found_returns_unified_error_envelope(monkeypatch):
    session = object()
    monkeypatch.setattr(
        "routes.workflow_version_routes.get_postgres_store",
        lambda: _StoreStub(session),
    )
    monkeypatch.setattr("routes.workflow_version_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workflow_version_routes.PermissionService.require_permission",
        _allow_workflow_permission,
    )

    async def _get_version_by_id(self, workflow_id, workspace_id, version_id):
        assert workflow_id == "wf-1"
        assert workspace_id == "ws-1"
        assert version_id == "version-missing"
        return SimpleNamespace(id="wf-1"), None

    monkeypatch.setattr(
        "routes.workflow_version_routes.WorkflowDefinitionService.get_version_by_id",
        _get_version_by_id,
    )

    client = TestClient(app)
    response = client.get(
        "/api/workflows/wf-1/versions/version-missing",
        headers={REQUEST_ID_HEADER: "req-workflow-version-404"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": WORKFLOW_VERSION_NOT_FOUND,
        "message": "工作流版本不存在",
        "request_id": "req-workflow-version-404",
        "details": None,
        "data": None,
    }


def test_result_bridge_maps_workflow_validation_error_to_legacy_numeric_code():
    result = Result.from_error_envelope(
        ErrorEnvelope(
            code=WORKFLOW_VALIDATION_FAILED,
            message="工作流未通过发布校验",
            request_id="req-result-bridge-001",
        )
    )

    assert result.code == 40000
    assert result.message == "工作流未通过发布校验"
    assert result.data is None
