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
from core.errors.exceptions import PromptChainError
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
