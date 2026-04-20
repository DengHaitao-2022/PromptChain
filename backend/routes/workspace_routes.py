"""
工作空间 API 路由

提供工作空间管理、成员管理等功能
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from db.postgres_store import get_postgres_store
from fastapi import APIRouter, HTTPException, Request, Response
from models.auth_models import MemberRole
from models.auth_orm import MembershipORM, UserORM, WorkspaceInviteORM, WorkspaceORM
from pydantic import BaseModel, EmailStr, Field
from services.auth_service import create_access_token
from services.email_service import EmailService
from services.permission_service import (
    PermissionService,
    resolve_membership_role,
    serialize_membership_role,
)
from sqlalchemy import and_
from sqlalchemy.future import select

from routes.auth_routes import (
    ACCESS_TOKEN_COOKIE,
    COOKIE_HTTPONLY,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    get_current_user,
)

router = APIRouter()


# ==================== 请求模型 ====================


class CreateWorkspaceRequest(BaseModel):
    """创建工作空间请求"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class UpdateWorkspaceRequest(BaseModel):
    """更新工作空间请求"""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    logo_url: str | None = None


class InviteMemberRequest(BaseModel):
    """邀请成员请求"""

    email: EmailStr
    role: MemberRole = MemberRole.VIEWER


class UpdateMemberRoleRequest(BaseModel):
    """更新成员角色请求"""

    role: MemberRole


class SwitchWorkspaceRequest(BaseModel):
    """切换工作空间请求"""

    workspace_id: str


# ==================== 响应模型 ====================


class WorkspaceResponse(BaseModel):
    """工作空间响应"""

    id: str
    name: str
    description: str | None
    logo_url: str | None
    owner_id: str
    created_at: datetime


class MemberResponse(BaseModel):
    """成员响应"""

    id: str
    user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    role: str
    workspace_access: str
    account_status: str
    email_verified: bool
    joined_at: datetime


class InviteResponse(BaseModel):
    """邀请响应"""

    id: str
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


# ==================== API 路由 ====================


@router.get("/workspaces")
async def list_workspaces(request: Request):
    """
    获取当前用户的所有工作空间
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        result = await session.execute(
            select(MembershipORM, WorkspaceORM)
            .join(WorkspaceORM, MembershipORM.workspace_id == WorkspaceORM.id)
            .where(MembershipORM.user_id == user_id)
        )
        rows = result.all()

        workspaces = []
        for membership, workspace in rows:
            role, is_suspended = resolve_membership_role(membership.role)
            if not role or is_suspended:
                continue
            workspaces.append(
                {
                    "id": workspace.id,
                    "name": workspace.name,
                    "description": workspace.description,
                    "logo_url": workspace.logo_url,
                    "owner_id": workspace.owner_id,
                    "role": role.value,
                    "joined_at": membership.joined_at,
                    "created_at": workspace.created_at,
                }
            )

        return {"workspaces": workspaces}


@router.post("/workspaces")
async def create_workspace(request: Request, body: CreateWorkspaceRequest):
    """
    创建新的工作空间

    创建者自动成为 Owner
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        # 创建工作空间
        workspace_id = str(uuid.uuid4())
        workspace = WorkspaceORM(
            id=workspace_id,
            name=body.name,
            description=body.description,
            owner_id=user_id,
        )
        session.add(workspace)

        # 添加创建者为 Owner
        membership = MembershipORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            workspace_id=workspace_id,
            role=MemberRole.OWNER.value,
        )
        session.add(membership)
        await session.commit()

        return {
            "id": workspace_id,
            "name": body.name,
            "description": body.description,
            "owner_id": user_id,
            "role": MemberRole.OWNER.value,
        }


@router.get("/workspaces/{workspace_id}")
async def get_workspace(request: Request, workspace_id: str):
    """
    获取工作空间详情
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查用户是否是工作空间成员
        permission_service = PermissionService(session)
        role = await permission_service.get_user_role_in_workspace(user_id, workspace_id)

        if not role:
            raise HTTPException(status_code=403, detail="您不是该工作空间的成员")

        # 获取工作空间
        result = await session.execute(select(WorkspaceORM).where(WorkspaceORM.id == workspace_id))
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise HTTPException(status_code=404, detail="工作空间不存在")

        return {
            "id": workspace.id,
            "name": workspace.name,
            "description": workspace.description,
            "logo_url": workspace.logo_url,
            "owner_id": workspace.owner_id,
            "created_at": workspace.created_at,
            "role": role.value,
        }


@router.patch("/workspaces/{workspace_id}")
async def update_workspace(request: Request, workspace_id: str, body: UpdateWorkspaceRequest):
    """
    更新工作空间信息

    需要 workspace.update 权限
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "workspace", "update")

        # 更新工作空间
        result = await session.execute(select(WorkspaceORM).where(WorkspaceORM.id == workspace_id))
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise HTTPException(status_code=404, detail="工作空间不存在")

        if body.name is not None:
            workspace.name = body.name
        if body.description is not None:
            workspace.description = body.description
        if body.logo_url is not None:
            workspace.logo_url = body.logo_url

        await session.commit()

        return {"message": "工作空间已更新"}


@router.get("/workspaces/{workspace_id}/members")
async def list_members(request: Request, workspace_id: str):
    """
    获取工作空间成员列表
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "member", "read")

        # 获取成员列表
        result = await session.execute(
            select(MembershipORM, UserORM)
            .join(UserORM, MembershipORM.user_id == UserORM.id)
            .where(MembershipORM.workspace_id == workspace_id)
        )
        rows = result.all()

        members = []
        for membership, user in rows:
            role, is_suspended = resolve_membership_role(membership.role)
            if not role:
                continue
            members.append(
                {
                    "id": membership.id,
                    "user_id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "role": role.value,
                    "workspace_access": "suspended" if is_suspended else "active",
                    "account_status": user.status,
                    "email_verified": user.email_verified,
                    "joined_at": membership.joined_at,
                }
            )

        return {"members": members}


@router.post("/workspaces/{workspace_id}/invite")
async def invite_member(request: Request, workspace_id: str, body: InviteMemberRequest):
    """
    邀请成员加入工作空间

    需要 member.manage 权限
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "member", "manage")

        # 检查是否已经是成员
        result = await session.execute(select(UserORM).where(UserORM.email == body.email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            result = await session.execute(
                select(MembershipORM).where(
                    and_(
                        MembershipORM.user_id == existing_user.id,
                        MembershipORM.workspace_id == workspace_id,
                    )
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="该用户已经是工作空间成员")

        # 获取工作空间名称和邀请者信息
        result = await session.execute(select(WorkspaceORM).where(WorkspaceORM.id == workspace_id))
        workspace = result.scalar_one_or_none()

        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        inviter = result.scalar_one_or_none()

        # 生成邀请 Token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(days=7)

        # 保存邀请
        invite = WorkspaceInviteORM(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            email=body.email,
            role=body.role.value,
            invited_by=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        session.add(invite)
        await session.commit()

        # 发送邀请邮件
        import os

        APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:3000")
        invite_link = f"{APP_BASE_URL}/invite?token={token}"

        email_service = EmailService(session)
        await email_service.send_workspace_invite_email(
            email=body.email,
            workspace_name=workspace.name,
            inviter_name=inviter.display_name or inviter.email,
            invite_link=invite_link,
        )

        return {
            "message": f"邀请已发送至 {body.email}",
            "invite_id": invite.id,
        }


@router.post("/workspaces/accept-invite")
async def accept_invite(request: Request, token: str):
    """
    接受工作空间邀请
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    store = get_postgres_store()
    async with store.async_session() as session:
        # 查找邀请
        result = await session.execute(
            select(WorkspaceInviteORM).where(
                and_(
                    WorkspaceInviteORM.token_hash == token_hash,
                    WorkspaceInviteORM.accepted_at.is_(None),
                    WorkspaceInviteORM.expires_at > datetime.utcnow(),
                )
            )
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise HTTPException(status_code=400, detail="邀请链接无效或已过期")

        # 获取当前用户信息
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user = result.scalar_one_or_none()

        # 检查邮箱是否匹配（可选，可以允许任何登录用户接受）
        # if user.email != invite.email:
        #     raise HTTPException(status_code=400, detail="邀请是发送给其他邮箱的")

        # 检查是否已经是成员
        result = await session.execute(
            select(MembershipORM).where(
                and_(
                    MembershipORM.user_id == user_id,
                    MembershipORM.workspace_id == invite.workspace_id,
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="您已经是该工作空间的成员")

        # 添加为成员
        membership = MembershipORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            workspace_id=invite.workspace_id,
            role=invite.role,
            invited_by=invite.invited_by,
        )
        session.add(membership)

        # 标记邀请为已接受
        invite.accepted_at = datetime.utcnow()
        await session.commit()

        return {"message": "您已成功加入工作空间"}


@router.patch("/memberships/{membership_id}")
async def update_member_role(request: Request, membership_id: str, body: UpdateMemberRoleRequest):
    """
    更新成员角色

    需要 member.manage 权限
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        # 获取成员关系
        result = await session.execute(
            select(MembershipORM).where(MembershipORM.id == membership_id)
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise HTTPException(status_code=404, detail="成员关系不存在")

        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(
            user_id, membership.workspace_id, "member", "manage"
        )

        current_role, is_suspended = resolve_membership_role(membership.role)
        if not current_role:
            raise HTTPException(status_code=400, detail="成员角色状态无效")

        # 不能修改 Owner 的角色
        if current_role == MemberRole.OWNER:
            raise HTTPException(status_code=400, detail="不能修改 Owner 的角色")

        if membership.user_id == user_id:
            raise HTTPException(status_code=400, detail="不能修改自己的角色")

        # 不能将自己设为 Owner（需要专门的转让流程）
        if body.role == MemberRole.OWNER:
            raise HTTPException(status_code=400, detail="不能直接设置 Owner 角色，请使用转让功能")

        # 更新角色
        membership.role = serialize_membership_role(body.role, suspended=is_suspended)
        await session.commit()

        return {
            "message": "成员角色已更新",
            "membership_id": membership.id,
            "role": body.role.value,
        }


@router.delete("/memberships/{membership_id}")
async def remove_member(request: Request, membership_id: str):
    """
    移除成员

    需要 member.manage 权限，不能移除 Owner
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        # 获取成员关系
        result = await session.execute(
            select(MembershipORM).where(MembershipORM.id == membership_id)
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise HTTPException(status_code=404, detail="成员关系不存在")

        membership_role, _ = resolve_membership_role(membership.role)

        # 不能移除 Owner
        if membership_role == MemberRole.OWNER:
            raise HTTPException(status_code=400, detail="不能移除 Owner")

        # 检查权限（自己可以离开，或者有管理权限）
        if membership.user_id != user_id:
            permission_service = PermissionService(session)
            await permission_service.require_permission(
                user_id, membership.workspace_id, "member", "manage"
            )

        # 删除成员关系
        await session.delete(membership)
        await session.commit()

        return {"message": "成员已移除", "membership_id": membership_id}


@router.post("/workspace-context/switch")
async def switch_workspace(request: Request, response: Response, body: SwitchWorkspaceRequest):
    """
    切换当前工作空间，并刷新 access_token 中的工作空间上下文。
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        role = await permission_service.get_user_role_in_workspace(user_id, body.workspace_id)

        if not role:
            raise HTTPException(status_code=403, detail="您不是该工作空间的成员")

        access_token = create_access_token(user_id=user_id, workspace_id=body.workspace_id)
        response.set_cookie(
            key=ACCESS_TOKEN_COOKIE,
            value=access_token,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=15 * 60,
        )

        return {
            "message": "工作空间已切换",
            "workspace_id": body.workspace_id,
            "role": role.value,
        }
