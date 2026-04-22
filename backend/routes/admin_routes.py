"""
后台管理 API 路由

提供模型配置、密钥管理、API Key 管理、审计日志、Dashboard 等功能
"""

import base64
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from db.postgres_store import get_postgres_store
from fastapi import APIRouter, HTTPException, Request
from models.admin_models import (
    ApiKeyCreate,
    AuditAction,
    ModelProviderCreate,
    ModelProviderUpdate,
    SecretCreate,
)
from models.admin_orm import ApiKeyORM, AuditLogORM, ModelProviderORM, SecretORM
from models.auth_models import UserStatus
from models.auth_orm import MembershipORM, UserORM
from pydantic import BaseModel
from services.auth_service import JWT_SECRET_KEY
from services.permission_service import (
    PermissionService,
    resolve_membership_role,
    serialize_membership_role,
)
from sqlalchemy import and_, desc, func
from sqlalchemy.future import select

from routes.auth_routes import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateUserStatusRequest(BaseModel):
    """更新当前工作空间访问状态请求"""

    status: UserStatus


# ==================== 辅助函数 ====================


async def get_workspace_id_from_request(request: Request) -> str:
    """从请求中获取当前工作空间ID"""
    payload = await get_current_user(request)
    workspace_id = payload.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="请先选择工作空间")
    return workspace_id


def _derive_fernet_key(source: str) -> bytes:
    """从任意字符串稳定导出 Fernet key。"""
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _get_fernet() -> Fernet:
    """获取密钥加密器，优先使用显式配置的 SECRETS_ENCRYPTION_KEY。"""
    configured_key = os.getenv("SECRETS_ENCRYPTION_KEY", "").strip()
    if configured_key:
        return Fernet(configured_key.encode("utf-8"))

    # 兼容：未配置专用密钥时，使用 JWT_SECRET_KEY 派生，避免明文/伪加密存储。
    logger.warning("SECRETS_ENCRYPTION_KEY 未配置，使用 JWT_SECRET_KEY 派生临时密钥")
    return Fernet(_derive_fernet_key(JWT_SECRET_KEY))


def encrypt_secret(value: str) -> str:
    """加密密钥。"""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """解密密钥，兼容历史 Base64 存储。"""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # 历史数据兼容：旧版本用 Base64 存储。
        return base64.b64decode(ciphertext.encode("utf-8")).decode("utf-8")


async def log_audit(
    session,
    workspace_id: str,
    user_id: str,
    action: AuditAction,
    target_type: str = None,
    target_id: str = None,
    detail: dict = None,
    ip_address: str = None,
    user_agent: str = None,
):
    """记录审计日志"""
    audit_log = AuditLogORM(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        user_id=user_id,
        action=action.value,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(audit_log)


# ==================== Dashboard API ====================


@router.get("/admin/dashboard")
async def get_dashboard(request: Request):
    """
    获取 Dashboard 统计数据
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        # Dashboard 属于管理后台资源，普通成员不应访问。
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "member", "read")

        # 获取统计数据（使用现有的 workflow_runs 表）
        from db.postgres_store import WorkflowRunORM
        from models.artifact import WorkflowRunStatus

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        workspace_filter = WorkflowRunORM.metadata_json["workspace_id"].as_string() == workspace_id

        # 今日运行次数
        result = await session.execute(
            select(func.count(WorkflowRunORM.id)).where(
                and_(
                    WorkflowRunORM.started_at >= today,
                    workspace_filter,
                )
            )
        )
        today_runs = result.scalar() or 0

        # 今日成功运行
        result = await session.execute(
            select(func.count(WorkflowRunORM.id)).where(
                and_(
                    WorkflowRunORM.started_at >= today,
                    WorkflowRunORM.status == WorkflowRunStatus.COMPLETED.value,
                    workspace_filter,
                )
            )
        )
        today_success = result.scalar() or 0

        # 今日失败运行
        result = await session.execute(
            select(func.count(WorkflowRunORM.id)).where(
                and_(
                    WorkflowRunORM.started_at >= today,
                    WorkflowRunORM.status == WorkflowRunStatus.FAILED.value,
                    workspace_filter,
                )
            )
        )
        today_failed = result.scalar() or 0

        # 今日平均耗时
        result = await session.execute(
            select(func.avg(WorkflowRunORM.total_duration_ms)).where(
                and_(
                    WorkflowRunORM.started_at >= today,
                    WorkflowRunORM.total_duration_ms.isnot(None),
                    workspace_filter,
                )
            )
        )
        today_avg_duration = result.scalar() or 0

        # 总运行次数
        result = await session.execute(
            select(func.count(WorkflowRunORM.id)).where(workspace_filter)
        )
        total_runs = result.scalar() or 0

        # 成员数量
        result = await session.execute(
            select(func.count(MembershipORM.id)).where(MembershipORM.workspace_id == workspace_id)
        )
        total_members = result.scalar() or 0

        # 最近运行
        result = await session.execute(
            select(WorkflowRunORM)
            .where(workspace_filter)
            .order_by(desc(WorkflowRunORM.started_at))
            .limit(10)
        )
        recent_runs_orm = result.scalars().all()

        recent_runs = []
        for run in recent_runs_orm:
            recent_runs.append(
                {
                    "id": run.id,
                    "workflow_name": run.workflow_name,
                    "status": run.status,
                    "started_at": run.started_at,
                    "duration_ms": run.total_duration_ms,
                }
            )

        return {
            "today_runs": today_runs,
            "today_success_runs": today_success,
            "today_failed_runs": today_failed,
            "today_avg_duration_ms": float(today_avg_duration),
            "total_runs": total_runs,
            "total_members": total_members,
            "recent_runs": recent_runs,
        }


@router.patch("/admin/users/{target_user_id}/status")
async def update_user_status(request: Request, target_user_id: str, body: UpdateUserStatusRequest):
    """
    更新当前工作空间中的访问状态。

    这里的“停用”只影响当前工作空间，不会修改全局用户账号状态。
    """
    if body.status not in {UserStatus.ACTIVE, UserStatus.SUSPENDED}:
        raise HTTPException(status_code=400, detail="仅支持启用或暂停当前工作空间访问")

    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "member", "manage")

        result = await session.execute(
            select(MembershipORM, UserORM)
            .join(UserORM, MembershipORM.user_id == UserORM.id)
            .where(
                MembershipORM.workspace_id == workspace_id,
                MembershipORM.user_id == target_user_id,
            )
        )
        row = result.one_or_none()

        if not row:
            raise HTTPException(status_code=404, detail="目标用户不在当前工作空间")

        membership, user = row

        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="不能修改自己的工作空间访问状态")

        current_role, is_suspended = resolve_membership_role(membership.role)
        if not current_role:
            raise HTTPException(status_code=400, detail="成员角色状态无效")

        if current_role.value == "owner":
            raise HTTPException(status_code=400, detail="不能修改拥有者的工作空间访问状态")

        if body.status == UserStatus.SUSPENDED and is_suspended:
            return {
                "message": "该成员当前已暂停访问此工作空间",
                "user_id": user.id,
                "workspace_access": "suspended",
            }

        if body.status == UserStatus.ACTIVE and not is_suspended:
            return {
                "message": "该成员当前可正常访问此工作空间",
                "user_id": user.id,
                "workspace_access": "active",
            }

        membership.role = serialize_membership_role(
            current_role,
            suspended=body.status == UserStatus.SUSPENDED,
        )

        await log_audit(
            session=session,
            workspace_id=workspace_id,
            user_id=user_id,
            action=AuditAction.USER_UPDATE,
            target_type="membership",
            target_id=membership.id,
            detail={
                "workspace_access": "suspended"
                if body.status == UserStatus.SUSPENDED
                else "active",
                "account_status_unchanged": user.status,
                "role": current_role.value,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
        await session.commit()

        return {
            "message": "工作空间访问状态已更新",
            "user_id": user.id,
            "workspace_access": "suspended" if body.status == UserStatus.SUSPENDED else "active",
        }


# ==================== 模型供应商 API ====================


@router.get("/admin/model-providers")
async def list_model_providers(request: Request):
    """
    获取模型供应商配置列表
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "model_provider", "read")

        # 获取列表
        result = await session.execute(
            select(ModelProviderORM).where(ModelProviderORM.workspace_id == workspace_id)
        )
        providers = result.scalars().all()

        # 脱敏返回
        return {
            "providers": [
                {
                    "id": p.id,
                    "provider": p.provider,
                    "name": p.name,
                    "description": p.description,
                    "enabled": p.enabled,
                    "created_at": p.created_at,
                    # config 中的敏感信息需要脱敏
                    "config": {
                        k: "***" if "key" in k.lower() or "secret" in k.lower() else v
                        for k, v in (p.config or {}).items()
                    },
                }
                for p in providers
            ]
        }


@router.post("/admin/model-providers")
async def create_model_provider(request: Request, body: ModelProviderCreate):
    """
    创建模型供应商配置
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(
            user_id, workspace_id, "model_provider", "create"
        )

        # 创建
        provider = ModelProviderORM(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            provider=body.provider.value,
            name=body.name,
            description=body.description,
            enabled=body.enabled,
            config=body.config,
            created_by=user_id,
        )
        session.add(provider)

        # 记录审计日志
        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.MODEL_PROVIDER_CREATE,
            "model_provider",
            provider.id,
            {"name": body.name, "provider": body.provider.value},
        )

        await session.commit()

        return {"id": provider.id, "message": "模型供应商配置已创建"}


@router.patch("/admin/model-providers/{provider_id}")
async def update_model_provider(request: Request, provider_id: str, body: ModelProviderUpdate):
    """
    更新模型供应商配置
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(
            user_id, workspace_id, "model_provider", "update"
        )

        # 获取并更新
        result = await session.execute(
            select(ModelProviderORM).where(
                and_(
                    ModelProviderORM.id == provider_id,
                    ModelProviderORM.workspace_id == workspace_id,
                )
            )
        )
        provider = result.scalar_one_or_none()

        if not provider:
            raise HTTPException(status_code=404, detail="模型供应商配置不存在")

        if body.name is not None:
            provider.name = body.name
        if body.description is not None:
            provider.description = body.description
        if body.enabled is not None:
            provider.enabled = body.enabled
        if body.config is not None:
            provider.config = body.config

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.MODEL_PROVIDER_UPDATE,
            "model_provider",
            provider_id,
        )

        await session.commit()

        return {"message": "模型供应商配置已更新"}


@router.delete("/admin/model-providers/{provider_id}")
async def delete_model_provider(request: Request, provider_id: str):
    """
    删除模型供应商配置
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        # 检查权限
        permission_service = PermissionService(session)
        await permission_service.require_permission(
            user_id, workspace_id, "model_provider", "delete"
        )

        result = await session.execute(
            select(ModelProviderORM).where(
                and_(
                    ModelProviderORM.id == provider_id,
                    ModelProviderORM.workspace_id == workspace_id,
                )
            )
        )
        provider = result.scalar_one_or_none()

        if not provider:
            raise HTTPException(status_code=404, detail="模型供应商配置不存在")

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.MODEL_PROVIDER_DELETE,
            "model_provider",
            provider_id,
            {"name": provider.name},
        )

        await session.delete(provider)
        await session.commit()

        return {"message": "模型供应商配置已删除"}


# ==================== 密钥管理 API ====================


@router.get("/admin/secrets")
async def list_secrets(request: Request):
    """
    获取密钥列表（仅显示名称和后4位）
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "secret", "read")

        result = await session.execute(
            select(SecretORM).where(SecretORM.workspace_id == workspace_id)
        )
        secrets_list = result.scalars().all()

        return {
            "secrets": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "last4": s.last4,
                    "created_at": s.created_at,
                }
                for s in secrets_list
            ]
        }


@router.post("/admin/secrets")
async def create_secret(request: Request, body: SecretCreate):
    """
    创建密钥
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "secret", "create")

        # 加密存储
        ciphertext = encrypt_secret(body.value)
        last4 = body.value[-4:] if len(body.value) >= 4 else body.value

        secret = SecretORM(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=body.name,
            description=body.description,
            ciphertext=ciphertext,
            last4=last4,
            created_by=user_id,
        )
        session.add(secret)

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.SECRET_CREATE,
            "secret",
            secret.id,
            {"name": body.name},
        )

        await session.commit()

        return {"id": secret.id, "message": "密钥已创建"}


@router.delete("/admin/secrets/{secret_id}")
async def delete_secret(request: Request, secret_id: str):
    """
    删除密钥
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "secret", "delete")

        result = await session.execute(
            select(SecretORM).where(
                and_(SecretORM.id == secret_id, SecretORM.workspace_id == workspace_id)
            )
        )
        secret = result.scalar_one_or_none()

        if not secret:
            raise HTTPException(status_code=404, detail="密钥不存在")

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.SECRET_DELETE,
            "secret",
            secret_id,
            {"name": secret.name},
        )

        await session.delete(secret)
        await session.commit()

        return {"message": "密钥已删除"}


# ==================== API Key 管理 ====================


@router.get("/admin/api-keys")
async def list_api_keys(request: Request):
    """
    获取 API Key 列表
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "api_key", "read")

        result = await session.execute(
            select(ApiKeyORM).where(ApiKeyORM.workspace_id == workspace_id)
        )
        keys = result.scalars().all()

        return {
            "api_keys": [
                {
                    "id": k.id,
                    "name": k.name,
                    "description": k.description,
                    "key_prefix": k.key_prefix,
                    "scopes": k.scopes,
                    "expires_at": k.expires_at,
                    "revoked_at": k.revoked_at,
                    "last_used_at": k.last_used_at,
                    "created_at": k.created_at,
                }
                for k in keys
            ]
        }


@router.post("/admin/api-keys")
async def create_api_key(request: Request, body: ApiKeyCreate):
    """
    创建 API Key

    返回完整的 Key，仅此一次显示
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "api_key", "create")

        # 生成 API Key
        key_raw = f"pc_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key_raw.encode()).hexdigest()
        key_prefix = key_raw[:8] + "..." + key_raw[-4:]

        expires_at = None
        if body.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days)

        api_key = ApiKeyORM(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=body.name,
            description=body.description,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=[s.value for s in body.scopes],
            expires_at=expires_at,
            created_by=user_id,
        )
        session.add(api_key)

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.API_KEY_CREATE,
            "api_key",
            api_key.id,
            {"name": body.name},
        )

        await session.commit()

        return {
            "id": api_key.id,
            "name": body.name,
            "key": key_raw,  # 完整的 Key，仅此一次显示
            "key_prefix": key_prefix,
            "scopes": [s.value for s in body.scopes],
            "expires_at": expires_at,
            "created_at": api_key.created_at,
            "message": "请立即保存此 API Key，它只会显示一次！",
        }


@router.delete("/admin/api-keys/{key_id}")
async def revoke_api_key(request: Request, key_id: str):
    """
    撤销 API Key
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "api_key", "delete")

        result = await session.execute(
            select(ApiKeyORM).where(
                and_(ApiKeyORM.id == key_id, ApiKeyORM.workspace_id == workspace_id)
            )
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=404, detail="API Key 不存在")

        api_key.revoked_at = datetime.utcnow()

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.API_KEY_REVOKE,
            "api_key",
            key_id,
            {"name": api_key.name},
        )

        await session.commit()

        return {"message": "API Key 已撤销"}


# ==================== 审计日志 API ====================


@router.get("/admin/audit-logs")
async def list_audit_logs(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    user_id_filter: str | None = None,
):
    """
    获取审计日志列表
    """
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "audit_log", "read")

        # 构建查询
        query = select(AuditLogORM).where(AuditLogORM.workspace_id == workspace_id)

        if action:
            query = query.where(AuditLogORM.action == action)
        if user_id_filter:
            query = query.where(AuditLogORM.user_id == user_id_filter)

        query = query.order_by(desc(AuditLogORM.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)
        logs = result.scalars().all()

        # 获取总数
        count_query = select(func.count(AuditLogORM.id)).where(
            AuditLogORM.workspace_id == workspace_id
        )
        if action:
            count_query = count_query.where(AuditLogORM.action == action)
        if user_id_filter:
            count_query = count_query.where(AuditLogORM.user_id == user_id_filter)

        result = await session.execute(count_query)
        total = result.scalar() or 0

        return {
            "logs": [
                {
                    "id": log.id,
                    "user_id": log.user_id,
                    "action": log.action,
                    "target_type": log.target_type,
                    "target_id": log.target_id,
                    "detail": log.detail,
                    "ip_address": log.ip_address,
                    "created_at": log.created_at,
                }
                for log in logs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
