import sys
from pathlib import Path
from types import SimpleNamespace

import aiosmtplib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.errors.codes import (
    AUTH_REGISTRATION_CONFLICT,
    AUTH_UNAUTHENTICATED,
    INFRA_DATABASE_ERROR,
    INFRA_EMAIL_SERVICE_ERROR,
    WORKSPACE_ACCESS_DENIED,
    WORKSPACE_CONTEXT_REQUIRED,
)
from core.errors.context import REQUEST_ID_HEADER
from core.errors.exceptions import InfrastructureError, PromptChainError
from core.errors.mapping import map_exception
from main import app
from routes.admin_routes import get_workspace_id_from_request
from services.auth_service import AuthService
from services.permission_service import PermissionService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DuplicateEmailSession:
    async def execute(self, _statement):
        return _ScalarResult(SimpleNamespace(id="user-existing"))

    def add(self, _obj):
        raise AssertionError("重复邮箱场景不应继续写入数据库")

    async def commit(self):
        raise AssertionError("重复邮箱场景不应提交事务")


def test_me_requires_auth_with_unified_error_envelope():
    client = TestClient(app)

    response = client.get(
        "/api/me",
        headers={REQUEST_ID_HEADER: "req-auth-001"},
    )

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


@pytest.mark.asyncio
async def test_auth_service_register_duplicate_email_raises_registered_conflict():
    service = AuthService(_DuplicateEmailSession())

    with pytest.raises(PromptChainError) as exc_info:
        await service.register_user(
            email="existing@example.com",
            password="password123",
            username="new-user",
        )

    assert exc_info.value.code == AUTH_REGISTRATION_CONFLICT
    assert exc_info.value.message == "该邮箱已被注册"


@pytest.mark.asyncio
async def test_permission_service_missing_membership_raises_workspace_access_denied(monkeypatch):
    service = PermissionService(session=None)

    async def _no_role(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "get_user_role_in_workspace", _no_role)

    with pytest.raises(PromptChainError) as exc_info:
        await service.require_permission("user-1", "ws-1", "workflow", "read")

    assert exc_info.value.code == WORKSPACE_ACCESS_DENIED
    assert exc_info.value.message == "您不是该工作空间的成员"


@pytest.mark.asyncio
async def test_admin_helper_requires_workspace_context(monkeypatch):
    async def _current_user(_request):
        return {"sub": "user-1"}

    monkeypatch.setattr("routes.admin_routes.get_current_user", _current_user)

    with pytest.raises(PromptChainError) as exc_info:
        await get_workspace_id_from_request(SimpleNamespace())

    assert exc_info.value.code == WORKSPACE_CONTEXT_REQUIRED
    assert exc_info.value.message == "请先选择工作空间"


def test_map_exception_recognizes_raw_database_errors():
    mapped = map_exception(
        OperationalError("SELECT 1", {}, RuntimeError("database unavailable")),
        request_id="req-db-001",
        path="/api/workflow/start",
        method="POST",
    )

    assert mapped.http_status == 503
    assert mapped.envelope.code == INFRA_DATABASE_ERROR
    assert mapped.envelope.message == "数据库暂时不可用，请稍后重试"
    assert mapped.envelope.details is None
    assert mapped.context.internal_cause


def test_map_exception_recognizes_raw_email_errors():
    mapped = map_exception(
        aiosmtplib.errors.SMTPException("smtp auth failed"),
        request_id="req-mail-001",
        path="/api/auth/register",
        method="POST",
    )

    assert mapped.http_status == 503
    assert mapped.envelope.code == INFRA_EMAIL_SERVICE_ERROR
    assert mapped.envelope.message == "邮件服务暂时不可用，请稍后重试"
    assert mapped.envelope.details is None
    assert mapped.context.internal_cause == "smtp auth failed"


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


class _InviteSession:
    def __init__(self):
        self.added = []
        self.commit_called = False
        self.rollback_called = False
        self._execute_count = 0

    async def execute(self, _statement):
        self._execute_count += 1
        if self._execute_count == 1:
            return _ScalarResult(None)
        if self._execute_count == 2:
            return _ScalarResult(SimpleNamespace(id="ws-1", name="示例工作空间"))
        if self._execute_count == 3:
            return _ScalarResult(
                SimpleNamespace(id="user-1", email="owner@example.com", display_name="Owner")
            )
        raise AssertionError(f"unexpected execute call: {self._execute_count}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_called = True

    async def rollback(self):
        self.rollback_called = True


def test_register_email_failure_returns_unified_error_envelope(monkeypatch):
    session = object()
    monkeypatch.setattr("routes.auth_routes.get_postgres_store", lambda: _StoreStub(session))

    async def _register_user(self, email, password, username=None, display_name=None):
        return SimpleNamespace(id="user-1", email=email)

    async def _send_verification_email(self, user_id, email):
        raise InfrastructureError(
            code=INFRA_EMAIL_SERVICE_ERROR,
            message="邮件服务暂时不可用，请稍后重试",
        )

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
            "display_name": "Mail Failure",
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


def test_workspace_invite_email_failure_returns_unified_error_envelope(monkeypatch):
    session = _InviteSession()
    monkeypatch.setattr("routes.workspace_routes.get_postgres_store", lambda: _StoreStub(session))

    async def _current_user(_request):
        return {"sub": "user-1"}

    async def _allow_permission(self, user_id, workspace_id, resource, action):
        return None

    async def _send_workspace_invite_email(self, email, workspace_name, inviter_name, invite_link):
        raise InfrastructureError(
            code=INFRA_EMAIL_SERVICE_ERROR,
            message="邮件服务暂时不可用，请稍后重试",
        )

    monkeypatch.setattr("routes.workspace_routes.get_current_user", _current_user)
    monkeypatch.setattr(
        "routes.workspace_routes.PermissionService.require_permission",
        _allow_permission,
    )
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
    printed = []

    class _ForgotPasswordSession:
        async def execute(self, _statement):
            return _ScalarResult(SimpleNamespace(id="user-1", email="registered@example.com"))

    monkeypatch.setattr(
        "routes.auth_routes.get_postgres_store", lambda: _StoreStub(_ForgotPasswordSession())
    )

    async def _send_password_reset_email(self, user_id, email):
        raise InfrastructureError(
            code=INFRA_EMAIL_SERVICE_ERROR,
            message="邮件服务暂时不可用，请稍后重试",
        )

    monkeypatch.setattr(
        "routes.auth_routes.EmailService.send_password_reset_email",
        _send_password_reset_email,
    )
    monkeypatch.setattr(
        "builtins.print", lambda *args, **kwargs: printed.append(" ".join(map(str, args)))
    )

    client = TestClient(app)
    response = client.post(
        "/api/auth/forgot-password",
        headers={REQUEST_ID_HEADER: "req-forgot-mail-001"},
        json={"email": "registered@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "如果该邮箱已注册，您将收到密码重置邮件"}
    assert any("req-forgot-mail-001" in line for line in printed)
    assert any(INFRA_EMAIL_SERVICE_ERROR in line for line in printed)
