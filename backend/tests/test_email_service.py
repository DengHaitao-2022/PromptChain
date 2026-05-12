import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from services.email_service import EmailDeliveryError, EmailService

EMAIL_ENV_KEYS = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_USE_TLS",
    "SMTP_TIMEOUT_SECONDS",
    "APP_BASE_URL",
    "EMAIL_DEV_LOG_BODY",
]


class _FakeSession:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self.commit_count = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1


@pytest.fixture(autouse=True)
def reset_email_settings(monkeypatch):
    for key in EMAIL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_send_email_dev_mode_does_not_call_smtp(monkeypatch):
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("开发模式不应调用真实 SMTP")

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _fail_if_called)

    service = EmailService(_FakeSession())

    assert await service.send_email("user@example.com", "验证邮箱", "<p>token=secret</p>")


@pytest.mark.asyncio
async def test_send_email_uses_runtime_smtp_settings(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "7")
    get_settings.cache_clear()

    captured = {}

    async def _fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _fake_send)

    service = EmailService(_FakeSession())

    assert await service.send_email(
        "user@example.com",
        "验证邮箱",
        "<p>hello</p>",
        text_content="hello",
    )
    assert captured["message"]["From"] == "noreply@example.com"
    assert captured["message"]["To"] == "user@example.com"
    assert captured["kwargs"] == {
        "hostname": "smtp.example.com",
        "port": 2525,
        "username": "smtp-user",
        "password": "smtp-password",
        "start_tls": False,
        "timeout": 7.0,
    }


@pytest.mark.asyncio
async def test_send_email_raises_on_smtp_failure(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    get_settings.cache_clear()

    async def _raise_smtp_failure(*args, **kwargs):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _raise_smtp_failure)

    service = EmailService(_FakeSession())

    with pytest.raises(EmailDeliveryError, match="邮件服务暂不可用"):
        await service.send_email("user@example.com", "验证邮箱", "<p>hello</p>")


@pytest.mark.asyncio
async def test_verification_email_commits_after_successful_send(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("APP_BASE_URL", "https://promptchain.example.com")
    get_settings.cache_clear()

    captured = {}

    async def _fake_send(message, **kwargs):
        captured["html"] = message.get_payload()[0].get_payload(decode=True).decode("utf-8")

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _fake_send)

    session = _FakeSession()
    service = EmailService(session)

    assert await service.send_verification_email("user-1", "user@example.com")
    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.added[0].user_id == "user-1"
    assert "https://promptchain.example.com/verify-email?token=" in captured["html"]


@pytest.mark.asyncio
async def test_verification_email_does_not_commit_when_send_fails(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    get_settings.cache_clear()

    async def _raise_smtp_failure(*args, **kwargs):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _raise_smtp_failure)

    session = _FakeSession()
    service = EmailService(session)

    with pytest.raises(EmailDeliveryError):
        await service.send_verification_email("user-1", "user@example.com")

    assert session.flush_count == 1
    assert session.commit_count == 0


@pytest.mark.asyncio
async def test_password_reset_email_uses_reset_link_and_commits(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("APP_BASE_URL", "https://promptchain.example.com")
    get_settings.cache_clear()

    captured = {}

    async def _fake_send(message, **kwargs):
        captured["html"] = message.get_payload()[0].get_payload(decode=True).decode("utf-8")

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _fake_send)

    session = _FakeSession()
    service = EmailService(session)

    assert await service.send_password_reset_email("user-1", "user@example.com")
    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.added[0].user_id == "user-1"
    assert "https://promptchain.example.com/reset-password?token=" in captured["html"]


@pytest.mark.asyncio
async def test_workspace_invite_email_uses_invite_link(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    get_settings.cache_clear()

    captured = {}

    async def _fake_send(message, **kwargs):
        captured["to"] = message["To"]
        captured["subject"] = message["Subject"]
        captured["html"] = message.get_payload()[0].get_payload(decode=True).decode("utf-8")

    monkeypatch.setattr("services.email_service.aiosmtplib.send", _fake_send)

    service = EmailService(_FakeSession())

    assert await service.send_workspace_invite_email(
        email="invitee@example.com",
        workspace_name="内容团队",
        inviter_name="管理员",
        invite_link="https://promptchain.example.com/invite?token=invite-token",
    )
    assert captured["to"] == "invitee@example.com"
    assert "内容团队" in captured["subject"]
    assert "https://promptchain.example.com/invite?token=invite-token" in captured["html"]
