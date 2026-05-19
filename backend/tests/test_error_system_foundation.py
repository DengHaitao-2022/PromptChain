import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app
from core.errors.codes import (
    AUTH_UNAUTHENTICATED,
    COMMON_INTERNAL_ERROR,
    COMMON_NOT_FOUND,
    COMMON_VALIDATION_ERROR,
    INFRA_DATABASE_ERROR,
    INFRA_EMAIL_SERVICE_ERROR,
    WORKFLOW_NOT_FOUND,
    WORKFLOW_VALIDATION_FAILED,
    WORKFLOW_VERSION_NOT_FOUND,
    WORKSPACE_ACCESS_DENIED,
    WORKSPACE_CONTEXT_REQUIRED,
    WORKSPACE_MEMBER_CONFLICT,
)
from core.errors.context import REQUEST_ID_HEADER
from core.errors.exceptions import (
    DomainError,
    InfrastructureError,
    PromptChainError,
    ValidationFailedError,
)
from core.errors.handlers import install_error_infrastructure
from core.errors.mapping import map_exception
from core.errors.models import ErrorEnvelope
from models.result import Result
from routes.workflow_routes import _format_sse_app_error_event
from services.permission_service import PermissionService


def test_install_error_infrastructure_returns_unified_domain_error_envelope():
    application = FastAPI()
    install_error_infrastructure(application)

    @application.get("/_tests/domain-error")
    async def _raise_domain_error():
        raise DomainError(code=COMMON_NOT_FOUND, message="工作流不存在")

    client = TestClient(application)
    response = client.get(
        "/_tests/domain-error",
        headers={REQUEST_ID_HEADER: "req-domain-001"},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "req-domain-001"
    assert response.json() == {
        "success": False,
        "code": COMMON_NOT_FOUND,
        "message": "工作流不存在",
        "request_id": "req-domain-001",
        "details": None,
        "data": None,
    }


def test_map_exception_redacts_infrastructure_error_details():
    mapped = map_exception(
        InfrastructureError(
            code=INFRA_DATABASE_ERROR,
            message="数据库连接失败",
            details={
                "service": "postgres",
                "operation": "connect",
                "dsn": "postgresql://secret",
                "raw_error": "password authentication failed",
            },
            cause=RuntimeError("password authentication failed"),
        ),
        request_id="req-infra-001",
        path="/api/workflow/start",
        method="POST",
    )

    assert mapped.http_status == 503
    assert mapped.envelope.code == INFRA_DATABASE_ERROR
    assert mapped.envelope.message == "数据库暂时不可用，请稍后重试"
    assert mapped.envelope.details == {
        "service": "postgres",
        "operation": "connect",
    }
    assert mapped.context.internal_cause == "password authentication failed"


def test_promptchain_error_rejects_unregistered_code_at_construction():
    with pytest.raises(ValueError, match="未注册的 PromptChain 错误码"):
        PromptChainError(code="TYPO_UNREGISTERED_CODE", message="不应被接受")


def test_map_exception_falls_back_when_promptchain_error_code_is_unregistered():
    error = PromptChainError.__new__(PromptChainError)
    error.code = "TYPO_UNREGISTERED_CODE"
    error.message = "不应泄露给客户端"
    error.details = {"secret": "do-not-expose"}
    error.cause = None

    mapped = map_exception(
        error,
        request_id="req-invalid-code-001",
        path="/api/_tests",
        method="GET",
    )

    assert mapped.http_status == 500
    assert mapped.envelope.code == COMMON_INTERNAL_ERROR
    assert mapped.envelope.message == "服务器开小差了，请稍后重试"
    assert mapped.envelope.details is None
    assert mapped.context.internal_cause == "未注册错误码: TYPO_UNREGISTERED_CODE"


def test_validation_failed_error_maps_to_validation_error_status():
    mapped = map_exception(
        ValidationFailedError("字段校验失败", details={"field": "title"}),
        request_id="req-validation-001",
        path="/api/_tests",
        method="POST",
    )

    assert mapped.http_status == 422
    assert mapped.envelope.code == COMMON_VALIDATION_ERROR
    assert mapped.envelope.message == "字段校验失败"
    assert mapped.envelope.details == {"field": "title"}


def test_result_keeps_legacy_shape_as_error_compatibility_layer():
    error = ErrorEnvelope(
        code=COMMON_NOT_FOUND,
        message="资源不存在",
        request_id="req-legacy-001",
    )

    result = Result.from_error_envelope(error)

    assert result.code == 40400
    assert result.message == "资源不存在"
    assert result.data is None


def test_result_legacy_mapping_keeps_workspace_client_errors_as_4xx():
    error = ErrorEnvelope(
        code=WORKSPACE_CONTEXT_REQUIRED,
        message="请先选择工作空间",
        request_id="req-legacy-workspace-001",
    )
    conflict_error = ErrorEnvelope(
        code=WORKSPACE_MEMBER_CONFLICT,
        message="成员已存在",
        request_id="req-legacy-member-001",
    )

    assert Result.from_error_envelope(error).code == 40000
    assert Result.from_error_envelope(conflict_error).code == 40000


class _FakeRequestUrl:
    path = "/api/workflow/run-1/events"


class _FakeRequestState:
    request_id = "req-sse-001"


class _FakeRequest:
    def __init__(self):
        self.headers = {}
        self.state = _FakeRequestState()
        self.url = _FakeRequestUrl()
        self.method = "GET"


def _parse_sse_payload(event: str) -> dict:
    data_lines = [
        line.removeprefix("data: ") for line in event.splitlines() if line.startswith("data: ")
    ]
    return json.loads("\n".join(data_lines))


def test_sse_app_error_event_uses_unified_redacted_envelope():
    event = _format_sse_app_error_event(
        InfrastructureError(
            code=INFRA_EMAIL_SERVICE_ERROR,
            message="smtp://user:secret@example.com failed",
            details={
                "service": "smtp",
                "operation": "send",
                "raw_error": "password=secret",
            },
            cause=RuntimeError("password=secret"),
        ),
        request=_FakeRequest(),
        workflow_run_id="run-1",
    )

    payload = _parse_sse_payload(event)

    assert event.startswith("event: app_error\n")
    assert payload["success"] is False
    assert payload["code"] == INFRA_EMAIL_SERVICE_ERROR
    assert payload["message"] == "邮件服务暂时不可用，请稍后重试"
    assert payload["request_id"] == "req-sse-001"
    assert payload["details"] == {"service": "smtp", "operation": "send"}
    assert payload["status"] == 503
    assert payload["workflow_run_id"] == "run-1"
    assert "secret" not in event


def test_me_without_auth_returns_unified_auth_error_envelope():
    client = TestClient(app)

    response = client.get("/api/me", headers={REQUEST_ID_HEADER: "req-auth-001"})

    assert response.status_code == 401
    assert response.headers[REQUEST_ID_HEADER] == "req-auth-001"
    assert response.json() == {
        "success": False,
        "code": AUTH_UNAUTHENTICATED,
        "message": "未登录或登录已过期",
        "request_id": "req-auth-001",
        "details": None,
        "data": None,
    }


class _NoMembershipResult:
    def scalar_one_or_none(self):
        return None


class _NoMembershipSession:
    async def execute(self, statement):
        return _NoMembershipResult()


def test_permission_service_missing_membership_uses_workspace_access_denied():
    service = PermissionService(_NoMembershipSession())

    async def _run():
        try:
            await service.require_permission("user-1", "ws-1", "workflow", "read")
        except DomainError as exc:
            return exc
        raise AssertionError("expected DomainError")

    error = asyncio.run(_run())
    assert error.code == WORKSPACE_ACCESS_DENIED
    assert error.message == "您不是该工作空间的成员"


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


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _EmailFailureSession:
    def __init__(self):
        self.added = []
        self.commit_called = False
        self.rollback_called = False
        self._execute_values = []

    def set_execute_values(self, values):
        self._execute_values = list(values)

    async def execute(self, statement):
        if not self._execute_values:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self._execute_values.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commit_called = True

    async def rollback(self):
        self.rollback_called = True


def test_register_email_failure_returns_unified_error_envelope(monkeypatch):
    session = _EmailFailureSession()
    monkeypatch.setattr("routes.auth_routes.get_postgres_store", lambda: _StoreStub(session))
    monkeypatch.setattr(
        "routes.auth_routes.build_auth_context",
        lambda user_id: {"user": {"id": user_id}, "workspace": None},
    )

    async def _register_user(self, email, password, username=None, display_name=None):
        return type("User", (), {"id": "user-1", "email": email})()

    async def _send_verification_email(self, user_id, email):
        from services.email_service import EmailDeliveryError

        raise EmailDeliveryError("smtp unavailable")

    monkeypatch.setattr("routes.auth_routes.AuthService.register_user", _register_user)
    monkeypatch.setattr(
        "routes.auth_routes.EmailService.send_verification_email",
        _send_verification_email,
    )

    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        headers={REQUEST_ID_HEADER: "req-register-mail-001"},
        json={
            "email": "mail-failure@example.com",
            "password": "Password1234!",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "code": INFRA_EMAIL_SERVICE_ERROR,
        "message": "邮件服务暂时不可用，请稍后重试",
        "request_id": "req-register-mail-001",
        "details": None,
        "data": None,
    }
    assert session.rollback_called is True


def test_workspace_invite_email_failure_returns_unified_error_envelope(monkeypatch):
    session = _EmailFailureSession()
    session.set_execute_values(
        [
            None,
            type("Workspace", (), {"id": "ws-1", "name": "示例工作空间"})(),
            type(
                "User", (), {"id": "user-1", "email": "owner@example.com", "display_name": "Owner"}
            )(),
        ]
    )
    monkeypatch.setattr("routes.workspace_routes.get_postgres_store", lambda: _StoreStub(session))

    async def _current_user(request):
        return {"sub": "user-1"}

    async def _allow_permission(self, user_id, workspace_id, resource, action):
        return None

    async def _skip_audit_record(self, **kwargs):
        return None

    async def _send_workspace_invite_email(self, email, workspace_name, inviter_name, invite_link):
        from services.email_service import EmailDeliveryError

        raise EmailDeliveryError("smtp unavailable")

    monkeypatch.setattr("routes.workspace_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workspace_routes.PermissionService.require_permission",
        _allow_permission,
    )
    monkeypatch.setattr("routes.workspace_routes.AuditLogService.record", _skip_audit_record)
    monkeypatch.setattr(
        "routes.workspace_routes.EmailService.send_workspace_invite_email",
        _send_workspace_invite_email,
    )

    client = TestClient(app)
    response = client.post(
        "/api/workspaces/ws-1/invite",
        headers={REQUEST_ID_HEADER: "req-invite-mail-001"},
        json={"email": "invitee@example.com", "role": "viewer"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "code": INFRA_EMAIL_SERVICE_ERROR,
        "message": "邮件服务暂时不可用，请稍后重试",
        "request_id": "req-invite-mail-001",
        "details": None,
        "data": None,
    }
    assert session.commit_called is False
    assert session.rollback_called is True


def test_forgot_password_email_failure_keeps_neutral_success(monkeypatch):
    session = _EmailFailureSession()
    session.set_execute_values(
        [type("User", (), {"id": "user-1", "email": "registered@example.com"})()]
    )
    captured_logs = []
    monkeypatch.setattr("routes.auth_routes.get_postgres_store", lambda: _StoreStub(session))

    async def _send_password_reset_email(self, user_id, email):
        from services.email_service import EmailDeliveryError

        raise EmailDeliveryError("smtp unavailable")

    def _capture_exception(message, *args, **kwargs):
        captured_logs.append(message % args if args else message)

    monkeypatch.setattr(
        "routes.auth_routes.EmailService.send_password_reset_email",
        _send_password_reset_email,
    )
    monkeypatch.setattr("routes.auth_routes.logger.exception", _capture_exception)

    client = TestClient(app)
    response = client.post(
        "/api/auth/forgot-password",
        headers={REQUEST_ID_HEADER: "req-forgot-mail-001"},
        json={"email": "registered@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "如果该邮箱已注册，您将收到密码重置邮件"}
    assert session.rollback_called is True
    assert any("密码重置邮件发送失败" in item for item in captured_logs)


def test_admin_workspace_context_missing_uses_unified_error(monkeypatch):
    async def _current_user(request):
        return {"sub": "user-1"}

    monkeypatch.setattr("routes.admin_routes.get_current_user", _current_user)

    client = TestClient(app)
    response = client.get(
        "/api/admin/dashboard",
        headers={REQUEST_ID_HEADER: "req-admin-workspace-001"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == WORKSPACE_CONTEXT_REQUIRED
    assert response.json()["request_id"] == "req-admin-workspace-001"


def test_workflow_definition_not_found_uses_unified_error(monkeypatch):
    session = object()
    monkeypatch.setattr(
        "routes.workflow_definition_routes.get_postgres_store",
        lambda: _StoreStub(session),
    )

    async def _current_user(request):
        return {"sub": "user-1", "workspace_id": "ws-1"}

    async def _allow_permission(self, user_id, workspace_id, resource, action):
        from models.auth_models import MemberRole

        return MemberRole.EDITOR

    async def _missing_workflow(self, **kwargs):
        return None

    monkeypatch.setattr("routes.workflow_definition_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workflow_definition_routes.PermissionService.require_permission",
        _allow_permission,
    )
    monkeypatch.setattr(
        "routes.workflow_definition_routes.WorkflowDefinitionService.get_by_id",
        _missing_workflow,
    )

    client = TestClient(app)
    response = client.get(
        "/api/workflows/wf-missing",
        headers={REQUEST_ID_HEADER: "req-workflow-definition-001"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": WORKFLOW_NOT_FOUND,
        "message": "工作流不存在",
        "request_id": "req-workflow-definition-001",
        "details": None,
        "data": None,
    }


def test_workflow_publish_validation_failure_uses_unified_error(monkeypatch):
    session = object()
    monkeypatch.setattr(
        "routes.workflow_definition_routes.get_postgres_store",
        lambda: _StoreStub(session),
    )

    async def _current_user(request):
        return {"sub": "user-1", "workspace_id": "ws-1"}

    async def _allow_permission(self, user_id, workspace_id, resource, action):
        from models.auth_models import MemberRole

        return MemberRole.EDITOR

    class _Workflow:
        id = "wf-1"

    class _Validation:
        is_valid = False

        def model_dump(self):
            return {"is_valid": False, "errors": ["工作流必须至少包含一个节点"]}

    async def _publish(self, **kwargs):
        return _Workflow(), _Validation(), None

    monkeypatch.setattr("routes.workflow_definition_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workflow_definition_routes.PermissionService.require_permission",
        _allow_permission,
    )
    monkeypatch.setattr(
        "routes.workflow_definition_routes.WorkflowDefinitionService.publish",
        _publish,
    )

    client = TestClient(app)
    response = client.post(
        "/api/workflows/wf-1/publish",
        headers={REQUEST_ID_HEADER: "req-workflow-publish-001"},
        json={"change_log": "尝试发布"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "code": WORKFLOW_VALIDATION_FAILED,
        "message": "工作流未通过发布校验",
        "request_id": "req-workflow-publish-001",
        "details": {"validation": {"is_valid": False, "errors": ["工作流必须至少包含一个节点"]}},
        "data": None,
    }


def test_workflow_version_not_found_uses_unified_error(monkeypatch):
    session = object()
    monkeypatch.setattr(
        "routes.workflow_version_routes.get_postgres_store",
        lambda: _StoreStub(session),
    )

    async def _current_user(request):
        return {"sub": "user-1", "workspace_id": "ws-1"}

    async def _allow_permission(self, user_id, workspace_id, resource, action):
        from models.auth_models import MemberRole

        return MemberRole.EDITOR

    class _Workflow:
        id = "wf-1"
        published_version_id = None

    async def _missing_version(self, workflow_id, workspace_id, version_id):
        return _Workflow(), None

    monkeypatch.setattr("routes.workflow_version_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workflow_version_routes.PermissionService.require_permission",
        _allow_permission,
    )
    monkeypatch.setattr(
        "routes.workflow_version_routes.WorkflowDefinitionService.get_version_by_id",
        _missing_version,
    )

    client = TestClient(app)
    response = client.get(
        "/api/workflows/wf-1/versions/ver-missing",
        headers={REQUEST_ID_HEADER: "req-workflow-version-001"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": WORKFLOW_VERSION_NOT_FOUND,
        "message": "版本不存在",
        "request_id": "req-workflow-version-001",
        "details": None,
        "data": None,
    }
