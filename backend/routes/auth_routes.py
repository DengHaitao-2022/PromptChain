"""
认证 API 路由

提供登录、注册、登出、Token 刷新等认证功能
"""

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from core.time import utc_max_naive
from db.postgres_store import get_postgres_store
from models.admin_models import AuditAction
from models.auth_models import UserStatus
from services.audit_log_service import AuditLogService
from services.auth_service import (
    AuthService,
    create_access_token,
    create_refresh_token,
    verify_access_token,
)
from services.email_service import EmailDeliveryError, EmailService
from services.permission_service import resolve_membership_role

router = APIRouter()
logger = logging.getLogger(__name__)

# Cookie 配置
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = "lax"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


# ==================== 请求模型 ====================


class RegisterRequest(BaseModel):
    """注册请求"""

    email: EmailStr
    password: str = Field(..., min_length=8)
    username: str | None = Field(None, min_length=2, max_length=50)
    display_name: str | None = Field(None, max_length=100)


class LoginRequest(BaseModel):
    """登录请求"""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """刷新 Token 请求（可选，主要通过 Cookie）"""

    refresh_token: str | None = None
    workspace_id: str | None = None


class ForgotPasswordRequest(BaseModel):
    """忘记密码请求"""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""

    token: str
    password: str = Field(..., min_length=8)


class VerifyEmailRequest(BaseModel):
    """验证邮箱请求"""

    token: str


# ==================== 响应模型 ====================


class MessageResponse(BaseModel):
    """通用消息响应"""

    message: str


class UserResponse(BaseModel):
    """用户信息响应"""

    id: str
    email: str
    username: str | None
    display_name: str | None
    avatar_url: str | None
    status: UserStatus
    email_verified: bool
    created_at: datetime


class MeResponse(BaseModel):
    """当前用户信息响应"""

    user: UserResponse
    workspace: dict[str, Any] | None = None
    role: str | None = None
    workspaces: list[dict[str, Any]] = Field(default_factory=list)


# ==================== 辅助函数 ====================


def get_client_ip(request: Request) -> str:
    """获取客户端IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """设置认证 Cookie"""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=15 * 60,  # 15分钟
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 24 * 60 * 60,  # 7天
    )


def clear_auth_cookies(response: Response):
    """清除认证 Cookie"""
    response.delete_cookie(key=ACCESS_TOKEN_COOKIE)
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE)


async def get_current_user_optional(request: Request) -> dict | None:
    """获取当前用户（可选，不强制登录）"""
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not access_token:
        return None

    payload = verify_access_token(access_token)
    if not payload:
        return None

    return payload


async def get_current_user(request: Request) -> dict:
    """获取当前用户（强制登录）"""
    payload = await get_current_user_optional(request)
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    store = get_postgres_store()
    async with store.async_session() as session:
        auth_service = AuthService(session)
        user = await auth_service.get_user_by_id(payload["sub"])

        if not user:
            raise HTTPException(status_code=401, detail="当前登录状态无效")

        if user.status == UserStatus.SUSPENDED.value:
            raise HTTPException(status_code=403, detail="账号已被停用")

        if user.status != UserStatus.ACTIVE.value or not user.email_verified:
            raise HTTPException(status_code=403, detail="账号尚未激活")

    return payload


def serialize_workspace(membership, workspace, role: str) -> dict[str, Any]:
    """统一工作空间上下文输出结构。"""
    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "logo_url": workspace.logo_url,
        "owner_id": workspace.owner_id,
        "role": role,
        "joined_at": membership.joined_at,
        "created_at": workspace.created_at,
    }


def get_workspace_sort_key(workspace: dict[str, Any]) -> tuple[datetime, datetime, str]:
    """为工作空间上下文提供稳定排序键，避免 fallback 选择漂移。"""
    fallback_time = utc_max_naive()
    joined_at = workspace.get("joined_at") or workspace.get("created_at") or fallback_time
    created_at = workspace.get("created_at") or joined_at or fallback_time
    return joined_at, created_at, workspace["id"]


def select_current_workspace(
    workspace_list: list[dict[str, Any]],
    preferred_workspace_id: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """按稳定顺序选择当前工作空间。"""
    ordered_workspaces = sorted(workspace_list, key=get_workspace_sort_key)

    if preferred_workspace_id:
        current_workspace = next(
            (
                workspace
                for workspace in ordered_workspaces
                if workspace["id"] == preferred_workspace_id
            ),
            None,
        )
        if current_workspace:
            return current_workspace, ordered_workspaces

    if not ordered_workspaces:
        return None, ordered_workspaces

    return ordered_workspaces[0], ordered_workspaces


async def build_auth_context(
    user_id: str, preferred_workspace_id: str | None = None
) -> dict[str, Any]:
    """构建登录态上下文，供登录、刷新和 `/api/me` 复用。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        auth_service = AuthService(session)

        user = await auth_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        workspaces = await auth_service.get_user_workspaces(user_id)
        workspace_list = []
        for membership, workspace in workspaces:
            role, is_suspended = resolve_membership_role(membership.role)
            if not role or is_suspended:
                continue
            workspace_list.append(serialize_workspace(membership, workspace, role.value))

        current_workspace, workspace_list = select_current_workspace(
            workspace_list,
            preferred_workspace_id=preferred_workspace_id,
        )
        current_role = current_workspace["role"] if current_workspace else None

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
                "status": user.status,
                "email_verified": user.email_verified,
                "created_at": user.created_at,
            },
            "workspace": current_workspace,
            "role": current_role,
            "workspaces": workspace_list,
        }


# ==================== API 路由 ====================


@router.post("/auth/register", response_model=MessageResponse)
async def register(request: Request, body: RegisterRequest):
    """
    用户注册

    注册成功后会发送验证邮件，用户需要验证邮箱后才能登录
    """
    store = get_postgres_store()
    async with store.async_session() as session:
        auth_service = AuthService(session)
        email_service = EmailService(session)

        try:
            # 创建用户
            user = await auth_service.register_user(
                email=body.email,
                password=body.password,
                username=body.username,
                display_name=body.display_name,
            )

            # 发送验证邮件
            await email_service.send_verification_email(user.id, user.email)
            auth_context = await build_auth_context(user.id)
            workspace = auth_context["workspace"]
            if workspace:
                await AuditLogService(session).record(
                    workspace_id=workspace["id"],
                    actor_user_id=user.id,
                    action=AuditAction.USER_REGISTER,
                    request=request,
                    target_type="user",
                    target_id=user.id,
                    detail={"email_verified": False},
                    target_snapshot=auth_context["user"],
                )
                await session.commit()

            return MessageResponse(message="注册成功，请查收验证邮件")

        except EmailDeliveryError as e:
            await session.rollback()
            raise HTTPException(status_code=502, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/auth/login")
async def login(request: Request, response: Response, body: LoginRequest):
    """
    用户登录

    登录成功后会在 Cookie 中设置 access_token 和 refresh_token
    """
    store = get_postgres_store()
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    async with store.async_session() as session:
        auth_service = AuthService(session)

        try:
            # 验证用户
            user = await auth_service.authenticate_user(
                email=body.email,
                password=body.password,
                ip_address=ip_address,
            )

            if not user:
                raise HTTPException(status_code=401, detail="邮箱或密码错误")

            # 检查邮箱是否验证
            if not user.email_verified:
                raise HTTPException(status_code=403, detail="请先验证您的邮箱")

            # 获取登录后上下文，统一 `/api/me` 与登录响应结构
            auth_context = await build_auth_context(user.id)
            current_workspace = auth_context["workspace"]

            # 创建 Token
            access_token = create_access_token(
                user_id=user.id,
                workspace_id=current_workspace["id"] if current_workspace else None,
            )
            refresh_token_raw, refresh_token_hash = create_refresh_token()

            # 保存 Refresh Token
            await auth_service.create_refresh_token_record(
                user_id=user.id,
                token_hash=refresh_token_hash,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            if current_workspace:
                await AuditLogService(session).record(
                    workspace_id=current_workspace["id"],
                    actor_user_id=user.id,
                    action=AuditAction.USER_LOGIN,
                    request=request,
                    target_type="user",
                    target_id=user.id,
                    detail={"workspace_id": current_workspace["id"]},
                    target_snapshot=auth_context["user"],
                )
                await session.commit()

            # 设置 Cookie
            set_auth_cookies(response, access_token, refresh_token_raw)

            return {"message": "登录成功", **auth_context}

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response, body: RefreshRequest | None = None):
    """
    刷新 Access Token

    使用 Cookie 中的 refresh_token 获取新的 access_token
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="未找到 Refresh Token")

    store = get_postgres_store()
    async with store.async_session() as session:
        auth_service = AuthService(session)

        # 验证 Refresh Token
        user = await auth_service.validate_refresh_token(refresh_token)
        if not user:
            clear_auth_cookies(response)
            raise HTTPException(status_code=401, detail="Refresh Token 无效或已过期")

        preferred_workspace_id = None
        access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if access_token:
            payload = verify_access_token(access_token)
            if payload:
                preferred_workspace_id = payload.get("workspace_id")

        if not preferred_workspace_id and body:
            preferred_workspace_id = body.workspace_id

        auth_context = await build_auth_context(
            user.id, preferred_workspace_id=preferred_workspace_id
        )
        workspace = auth_context["workspace"]
        workspace_id = workspace["id"] if workspace else None

        # 创建新的 Access Token
        access_token = create_access_token(
            user_id=user.id,
            workspace_id=workspace_id,
        )

        # 只更新 Access Token Cookie
        response.set_cookie(
            key=ACCESS_TOKEN_COOKIE,
            value=access_token,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=15 * 60,
        )

        return {"message": "Token 已刷新", "workspace": workspace}


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response):
    """
    用户登出

    撤销 Refresh Token 并清除 Cookie
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)

    payload = await get_current_user_optional(request)
    store = get_postgres_store()
    async with store.async_session() as session:
        if refresh_token:
            auth_service = AuthService(session)
            await auth_service.revoke_refresh_token(refresh_token)
        if payload and payload.get("workspace_id") and payload.get("sub"):
            await AuditLogService(session).record(
                workspace_id=payload["workspace_id"],
                actor_user_id=payload["sub"],
                action=AuditAction.USER_LOGOUT,
                request=request,
                target_type="user",
                target_id=payload["sub"],
            )
            await session.commit()

    clear_auth_cookies(response)
    return MessageResponse(message="登出成功")


@router.post("/auth/verify-email", response_model=MessageResponse)
async def verify_email(request: Request, body: VerifyEmailRequest):
    """
    验证邮箱

    使用邮件中的验证链接完成邮箱验证
    """
    store = get_postgres_store()
    async with store.async_session() as session:
        email_service = EmailService(session)
        auth_service = AuthService(session)

        # 验证 Token
        user_id = await email_service.verify_email_token(body.token)
        if not user_id:
            raise HTTPException(status_code=400, detail="验证链接无效或已过期")

        # 激活用户
        await auth_service.activate_user(user_id)
        auth_context = await build_auth_context(user_id)
        workspace = auth_context["workspace"]
        if workspace:
            await AuditLogService(session).record(
                workspace_id=workspace["id"],
                actor_user_id=user_id,
                action=AuditAction.USER_UPDATE,
                request=request,
                target_type="user",
                target_id=user_id,
                detail={"email_verified": True, "source": "email_verification"},
                target_snapshot=auth_context["user"],
            )
            await session.commit()

        return MessageResponse(message="邮箱验证成功，您现在可以登录了")


@router.post("/auth/forgot-password", response_model=MessageResponse)
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """
    忘记密码

    发送密码重置邮件
    """
    store = get_postgres_store()
    async with store.async_session() as session:
        from sqlalchemy.future import select

        from models.auth_orm import UserORM

        # 查找用户
        result = await session.execute(select(UserORM).where(UserORM.email == body.email))
        user = result.scalar_one_or_none()

        # 无论用户是否存在都返回成功（安全考虑）
        if user:
            email_service = EmailService(session)
            try:
                await email_service.send_password_reset_email(user.id, user.email)
            except EmailDeliveryError:
                await session.rollback()
                logger.exception("密码重置邮件发送失败，user_id=%s", user.id)
            else:
                auth_context = await build_auth_context(user.id)
                workspace = auth_context["workspace"]
                if workspace:
                    await AuditLogService(session).record(
                        workspace_id=workspace["id"],
                        actor_user_id=user.id,
                        action=AuditAction.USER_PASSWORD_RESET,
                        request=request,
                        target_type="user",
                        target_id=user.id,
                        detail={"stage": "reset_email_requested"},
                        target_snapshot=auth_context["user"],
                    )
                    await session.commit()

        return MessageResponse(message="如果该邮箱已注册，您将收到密码重置邮件")


@router.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(request: Request, body: ResetPasswordRequest):
    """
    重置密码

    使用邮件中的重置链接设置新密码
    """
    store = get_postgres_store()
    async with store.async_session() as session:
        from sqlalchemy.future import select

        from models.auth_orm import UserORM
        from services.auth_service import hash_password

        email_service = EmailService(session)
        auth_service = AuthService(session)

        # 验证 Token
        user_id = await email_service.verify_password_reset_token(body.token)
        if not user_id:
            raise HTTPException(status_code=400, detail="重置链接无效或已过期")

        # 更新密码
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=400, detail="用户不存在")

        user.password_hash = hash_password(body.password)
        await session.commit()

        # 撤销所有 Refresh Token（强制重新登录）
        await auth_service.revoke_all_user_tokens(user_id)
        auth_context = await build_auth_context(user_id)
        workspace = auth_context["workspace"]
        if workspace:
            await AuditLogService(session).record(
                workspace_id=workspace["id"],
                actor_user_id=user_id,
                action=AuditAction.USER_PASSWORD_RESET,
                request=request,
                target_type="user",
                target_id=user_id,
                detail={"stage": "password_changed", "revoked_refresh_tokens": True},
                target_snapshot=auth_context["user"],
            )
            await session.commit()

        return MessageResponse(message="密码重置成功，请使用新密码登录")


@router.get("/me")
async def get_me(request: Request, response: Response):
    """
    获取当前用户信息

    返回当前登录用户的信息及其工作空间列表
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    auth_context = await build_auth_context(
        user_id, preferred_workspace_id=payload.get("workspace_id")
    )
    workspace = auth_context["workspace"]
    workspace_id = workspace["id"] if workspace else None

    # 如果当前 token 中的 workspace 已经失效或被移除，刷新为新的可访问上下文。
    if workspace_id != payload.get("workspace_id"):
        access_token = create_access_token(user_id=user_id, workspace_id=workspace_id)
        response.set_cookie(
            key=ACCESS_TOKEN_COOKIE,
            value=access_token,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=15 * 60,
        )

    return auth_context
