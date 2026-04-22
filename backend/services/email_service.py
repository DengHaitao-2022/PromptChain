"""
邮件服务

提供邮件发送功能，用于邮箱验证和密码重置
"""

import hashlib
import logging
import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.auth_orm import EmailVerificationTokenORM, PasswordResetTokenORM

# ==================== 配置 ====================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@promptchain.com")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

# Token 有效期
EMAIL_VERIFICATION_EXPIRE_HOURS = 24
PASSWORD_RESET_EXPIRE_HOURS = 1

# 应用URL（用于生成邮件中的链接）
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:3000")
EMAIL_DEV_LOG_BODY = os.getenv("EMAIL_DEV_LOG_BODY", "false").lower() == "true"

logger = logging.getLogger(__name__)


# ==================== Token 生成 ====================


def generate_email_token() -> tuple[str, str]:
    """
    生成邮件验证/密码重置 Token

    Returns:
        (原始token, token哈希)
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


# ==================== 邮件服务类 ====================


class EmailService:
    """邮件服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _sanitize_html_for_log(html_content: str) -> str:
        """对包含 token 的链接做脱敏，避免在日志中泄露凭证。"""
        return re.sub(r"(token=)([^&\"'>\s]+)", r"\1***", html_content)

    async def send_email(
        self, to_email: str, subject: str, html_content: str, text_content: str | None = None
    ) -> bool:
        """
        发送邮件

        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            html_content: HTML 内容
            text_content: 纯文本内容（可选）

        Returns:
            是否发送成功
        """
        if not SMTP_USER or not SMTP_PASSWORD:
            # 开发回退：未配置 SMTP 时仅输出脱敏摘要。
            logger.warning("SMTP 未配置，跳过真实发送，收件人=%s 主题=%s", to_email, subject)
            if EMAIL_DEV_LOG_BODY:
                logger.debug(
                    "邮件内容(脱敏)=%s",
                    self._sanitize_html_for_log(html_content),
                )
            return True

        try:
            # 创建邮件
            message = MIMEMultipart("alternative")
            message["From"] = SMTP_FROM
            message["To"] = to_email
            message["Subject"] = subject

            # 添加纯文本和HTML内容
            if text_content:
                message.attach(MIMEText(text_content, "plain", "utf-8"))
            message.attach(MIMEText(html_content, "html", "utf-8"))

            # 发送邮件
            await aiosmtplib.send(
                message,
                hostname=SMTP_HOST,
                port=SMTP_PORT,
                username=SMTP_USER,
                password=SMTP_PASSWORD,
                start_tls=SMTP_USE_TLS,
            )
            return True

        except Exception:
            logger.exception("邮件发送失败，收件人=%s 主题=%s", to_email, subject)
            return False

    async def send_verification_email(self, user_id: str, email: str) -> bool:
        """
        发送邮箱验证邮件

        Args:
            user_id: 用户ID
            email: 用户邮箱

        Returns:
            是否发送成功
        """
        # 生成验证 Token
        token, token_hash = generate_email_token()
        expires_at = datetime.now(UTC) + timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS)

        # 保存到数据库
        token_orm = EmailVerificationTokenORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token_orm)
        await self.session.commit()

        # 构建验证链接
        verification_link = f"{APP_BASE_URL}/verify-email?token={token}"

        # 邮件内容
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">验证您的邮箱</h2>
            <p>感谢您注册 PromptChain！请点击下方按钮验证您的邮箱地址：</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{verification_link}"
                   style="background-color: #4F46E5; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; display: inline-block;">
                    验证邮箱
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">
                或者复制以下链接到浏览器：<br>
                <a href="{verification_link}">{verification_link}</a>
            </p>
            <p style="color: #999; font-size: 12px;">
                此链接将在 {EMAIL_VERIFICATION_EXPIRE_HOURS} 小时后过期。<br>
                如果您没有注册 PromptChain 账号，请忽略此邮件。
            </p>
        </div>
        """

        return await self.send_email(
            to_email=email,
            subject="验证您的 PromptChain 邮箱",
            html_content=html_content,
        )

    async def send_password_reset_email(self, user_id: str, email: str) -> bool:
        """
        发送密码重置邮件

        Args:
            user_id: 用户ID
            email: 用户邮箱

        Returns:
            是否发送成功
        """
        # 生成重置 Token
        token, token_hash = generate_email_token()
        expires_at = datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_EXPIRE_HOURS)

        # 保存到数据库
        token_orm = PasswordResetTokenORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token_orm)
        await self.session.commit()

        # 构建重置链接
        reset_link = f"{APP_BASE_URL}/reset-password?token={token}"

        # 邮件内容
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">重置您的密码</h2>
            <p>您请求重置 PromptChain 账号的密码。请点击下方按钮设置新密码：</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}"
                   style="background-color: #DC2626; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; display: inline-block;">
                    重置密码
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">
                或者复制以下链接到浏览器：<br>
                <a href="{reset_link}">{reset_link}</a>
            </p>
            <p style="color: #999; font-size: 12px;">
                此链接将在 {PASSWORD_RESET_EXPIRE_HOURS} 小时后过期。<br>
                如果您没有请求重置密码，请忽略此邮件，您的密码不会被更改。
            </p>
        </div>
        """

        return await self.send_email(
            to_email=email,
            subject="重置您的 PromptChain 密码",
            html_content=html_content,
        )

    async def verify_email_token(self, token: str) -> str | None:
        """
        验证邮箱验证 Token

        Args:
            token: 验证 Token

        Returns:
            用户ID 或 None
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        result = await self.session.execute(
            select(EmailVerificationTokenORM).where(
                and_(
                    EmailVerificationTokenORM.token_hash == token_hash,
                    EmailVerificationTokenORM.used_at.is_(None),
                    EmailVerificationTokenORM.expires_at > datetime.now(UTC),
                )
            )
        )
        token_orm = result.scalar_one_or_none()

        if not token_orm:
            return None

        # 标记为已使用
        token_orm.used_at = datetime.now(UTC)
        await self.session.commit()

        return token_orm.user_id

    async def verify_password_reset_token(self, token: str) -> str | None:
        """
        验证密码重置 Token

        Args:
            token: 重置 Token

        Returns:
            用户ID 或 None
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        result = await self.session.execute(
            select(PasswordResetTokenORM).where(
                and_(
                    PasswordResetTokenORM.token_hash == token_hash,
                    PasswordResetTokenORM.used_at.is_(None),
                    PasswordResetTokenORM.expires_at > datetime.now(UTC),
                )
            )
        )
        token_orm = result.scalar_one_or_none()

        if not token_orm:
            return None

        # 标记为已使用
        token_orm.used_at = datetime.now(UTC)
        await self.session.commit()

        return token_orm.user_id

    async def send_workspace_invite_email(
        self, email: str, workspace_name: str, inviter_name: str, invite_link: str
    ) -> bool:
        """
        发送工作空间邀请邮件

        Args:
            email: 被邀请人邮箱
            workspace_name: 工作空间名称
            inviter_name: 邀请人名称
            invite_link: 邀请链接

        Returns:
            是否发送成功
        """
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #333;">您被邀请加入工作空间</h2>
            <p><strong>{inviter_name}</strong> 邀请您加入 PromptChain 工作空间 <strong>{workspace_name}</strong>。</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{invite_link}"
                   style="background-color: #10B981; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; display: inline-block;">
                    接受邀请
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">
                或者复制以下链接到浏览器：<br>
                <a href="{invite_link}">{invite_link}</a>
            </p>
            <p style="color: #999; font-size: 12px;">
                此邀请链接将在 7 天后过期。
            </p>
        </div>
        """

        return await self.send_email(
            to_email=email,
            subject=f"{inviter_name} 邀请您加入 {workspace_name}",
            html_content=html_content,
        )
