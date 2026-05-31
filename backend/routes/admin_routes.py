"""
后台管理 API 路由

提供模型配置、密钥管理、API Key 管理、审计日志、Dashboard 等功能
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, desc, func
from sqlalchemy.future import select

from core.time import app_day_start_as_utc_naive, utc_now_naive
from db.postgres_store import get_postgres_store
from models.admin_models import (
    ApiKeyCreate,
    AuditAction,
    ModelProviderCreate,
    ModelProviderTestRequest,
    ModelProviderUpdate,
    SecretCreate,
)
from models.admin_orm import ApiKeyORM, ModelProviderORM, SecretORM
from models.auth_models import UserStatus
from models.auth_orm import MembershipORM, UserORM
from routes.auth_routes import get_current_user
from services.audit_log_service import AuditLogService, AuditOutcome
from services.llm_provider import (
    LLMProviderFactory,
    get_current_model_info_for_workspace,
)
from services.model_provider_tester import test_model_provider
from services.permission_service import (
    PermissionService,
    check_permission,
    resolve_membership_role,
    serialize_membership_role,
)
from services.secret_crypto import (
    decrypt_config_value,
    encrypt_config_value,
    encrypt_secret,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateUserStatusRequest(BaseModel):
    """更新当前工作空间访问状态请求"""

    status: UserStatus


# ==================== 辅助函数 ====================

_RUNTIME_DEFAULT_CONFIG_KEY = "_runtime_default"
_SENSITIVE_CONFIG_KEYWORDS = ("key", "secret", "token", "credential", "password")


async def get_workspace_id_from_request(request: Request) -> str:
    """从请求中获取当前工作空间ID"""
    payload = await get_current_user(request)
    workspace_id = payload.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="请先选择工作空间")
    return workspace_id


def _is_sensitive_config_key(key: str) -> bool:
    """识别模型配置中的敏感字段。"""
    lowered_key = key.lower()
    return any(keyword in lowered_key for keyword in _SENSITIVE_CONFIG_KEYWORDS)


def _prepare_model_config(
    current_config: dict | None,
    incoming_config: dict | None,
    *,
    set_as_default: bool | None = None,
) -> dict:
    """合并并加密模型配置；空密钥或掩码值表示沿用旧值。"""
    prepared = dict(current_config or {})

    for key, value in (incoming_config or {}).items():
        if key == _RUNTIME_DEFAULT_CONFIG_KEY:
            continue
        if value in (None, "", "***"):
            continue

        if _is_sensitive_config_key(key):
            prepared[key] = encrypt_config_value(value)
        else:
            prepared[key] = value

    if set_as_default is True:
        prepared[_RUNTIME_DEFAULT_CONFIG_KEY] = True
    elif set_as_default is False:
        prepared.pop(_RUNTIME_DEFAULT_CONFIG_KEY, None)

    return prepared


def _mask_model_config(config: dict | None) -> dict:
    """返回前端可展示的脱敏配置，隐藏内部运行标记。"""
    masked: dict = {}
    for key, value in (config or {}).items():
        if key == _RUNTIME_DEFAULT_CONFIG_KEY:
            continue
        if _is_sensitive_config_key(key):
            masked[key] = "***" if value not in (None, "") else ""
        else:
            masked[key] = decrypt_config_value(value)
    return masked


def _is_default_model_provider(provider: ModelProviderORM) -> bool:
    """判断模型供应商是否是当前工作空间运行默认。"""
    return bool((provider.config or {}).get(_RUNTIME_DEFAULT_CONFIG_KEY))


def _model_provider_to_response(provider: ModelProviderORM) -> dict:
    """统一模型供应商列表响应，避免敏感配置外泄。"""
    supported_providers = set(LLMProviderFactory.get_supported_provider_names())
    return {
        "id": provider.id,
        "provider": provider.provider,
        "name": provider.name,
        "description": provider.description,
        "enabled": provider.enabled,
        "is_default": _is_default_model_provider(provider),
        "runtime_supported": provider.provider in supported_providers,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
        "config": _mask_model_config(provider.config),
    }


async def _clear_workspace_default_model_provider(
    session,
    workspace_id: str,
    *,
    exclude_provider_id: str | None = None,
) -> None:
    """清理同一工作空间内其他默认标记，确保运行入口唯一。"""
    result = await session.execute(
        select(ModelProviderORM).where(ModelProviderORM.workspace_id == workspace_id)
    )
    for provider in result.scalars().all():
        if exclude_provider_id and provider.id == exclude_provider_id:
            continue
        if _is_default_model_provider(provider):
            provider.config = _prepare_model_config(
                provider.config,
                None,
                set_as_default=False,
            )


async def log_audit(
    session,
    workspace_id: str,
    user_id: str,
    action: AuditAction,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request: Request | None = None,
    outcome: AuditOutcome = "success",
    target_snapshot: dict | None = None,
):
    """记录审计日志，保留旧调用形态并委托给统一审计服务。"""
    audit_log = await AuditLogService(session).record(
        workspace_id=workspace_id,
        actor_user_id=user_id,
        action=action.value,
        request=request,
        outcome=outcome,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        target_snapshot=target_snapshot,
    )
    if ip_address and not audit_log.ip_address:
        audit_log.ip_address = ip_address
    if user_agent and not audit_log.user_agent:
        audit_log.user_agent = user_agent


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
        permission_service = PermissionService(session)
        role = await permission_service.require_permission(
            user_id,
            workspace_id,
            "workflow_run",
            "read",
        )

        # 获取统计数据（使用现有的 workflow_runs 表）
        from db.postgres_store import WorkflowRunORM
        from models.artifact import WorkflowRunStatus

        today = app_day_start_as_utc_naive()
        filters = [WorkflowRunORM.metadata_json["workspace_id"].as_string() == workspace_id]
        can_read_members = check_permission(role, "member", "read")
        if not can_read_members:
            # 普通成员只能看到自己的运行数据，避免控制台首页泄露工作空间全量运行态。
            filters.append(WorkflowRunORM.metadata_json["user_id"].as_string() == user_id)

        # 今日运行次数
        result = await session.execute(
            select(func.count(WorkflowRunORM.id)).where(
                and_(
                    WorkflowRunORM.started_at >= today,
                    *filters,
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
                    *filters,
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
                    *filters,
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
                    *filters,
                )
            )
        )
        today_avg_duration = result.scalar() or 0

        # 总运行次数
        result = await session.execute(select(func.count(WorkflowRunORM.id)).where(and_(*filters)))
        total_runs = result.scalar() or 0

        # 成员数量
        total_members = None
        if can_read_members:
            result = await session.execute(
                select(func.count(MembershipORM.id)).where(
                    MembershipORM.workspace_id == workspace_id
                )
            )
            total_members = result.scalar() or 0

        # 最近运行
        result = await session.execute(
            select(WorkflowRunORM)
            .where(and_(*filters))
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
            request=request,
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

        result = await session.execute(
            select(ModelProviderORM)
            .where(ModelProviderORM.workspace_id == workspace_id)
            .order_by(desc(ModelProviderORM.updated_at), desc(ModelProviderORM.created_at))
        )
        providers = result.scalars().all()

        return {
            "providers": [_model_provider_to_response(provider) for provider in providers],
            "supported_providers": LLMProviderFactory.get_supported_provider_names(),
        }


@router.get("/admin/model-providers/runtime")
async def get_model_provider_runtime(request: Request):
    """获取当前工作空间实际运行模型配置读模型。"""
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        await permission_service.require_permission(user_id, workspace_id, "model_provider", "read")

    return {
        "runtime": await get_current_model_info_for_workspace(workspace_id),
        "supported_providers": LLMProviderFactory.get_supported_provider_names(),
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

        result = await session.execute(
            select(func.count(ModelProviderORM.id)).where(
                ModelProviderORM.workspace_id == workspace_id
            )
        )
        is_first_provider = (result.scalar() or 0) == 0
        set_as_default = body.set_as_default or is_first_provider
        if set_as_default:
            await _clear_workspace_default_model_provider(session, workspace_id)

        config = _prepare_model_config(
            None,
            body.config,
            set_as_default=set_as_default,
        )

        provider = ModelProviderORM(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            provider=body.provider.value,
            name=body.name,
            description=body.description,
            enabled=True if set_as_default else body.enabled,
            config=config,
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
            request=request,
            target_snapshot={
                "id": provider.id,
                "name": provider.name,
                "provider": provider.provider,
                "enabled": provider.enabled,
            },
        )

        await session.commit()

        return {
            "id": provider.id,
            "message": "模型供应商配置已创建",
            "provider": _model_provider_to_response(provider),
        }


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
        if body.config is not None or body.set_as_default is not None:
            provider.config = _prepare_model_config(
                provider.config,
                body.config,
                set_as_default=body.set_as_default,
            )
        if body.set_as_default is True:
            provider.enabled = True
            await _clear_workspace_default_model_provider(
                session,
                workspace_id,
                exclude_provider_id=provider.id,
            )
        elif body.enabled is False and _is_default_model_provider(provider):
            provider.config = _prepare_model_config(
                provider.config,
                None,
                set_as_default=False,
            )

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.MODEL_PROVIDER_UPDATE,
            "model_provider",
            provider_id,
            {
                "updated_fields": [
                    key
                    for key, value in {
                        "name": body.name,
                        "description": body.description,
                        "enabled": body.enabled,
                        "config": body.config,
                    }.items()
                    if value is not None
                ]
            },
            request=request,
            target_snapshot={
                "id": provider.id,
                "name": provider.name,
                "provider": provider.provider,
                "enabled": provider.enabled,
            },
        )

        await session.commit()

        return {
            "message": "模型供应商配置已更新",
            "provider": _model_provider_to_response(provider),
        }


@router.post("/admin/model-providers/{provider_id}/test")
async def test_model_provider_config(
    request: Request,
    provider_id: str,
    body: ModelProviderTestRequest,
):
    """测试模型供应商配置，按静态校验、连通性、凭证、模型列表和短 Prompt 分步返回。"""
    payload = await get_current_user(request)
    user_id = payload["sub"]
    workspace_id = await get_workspace_id_from_request(request)

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        # 测试会使用已保存密钥并可能产生模型调用费用，因此要求具备更新权限。
        await permission_service.require_permission(
            user_id,
            workspace_id,
            "model_provider",
            "update",
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

        return await test_model_provider(
            provider,
            selected_model=body.model,
            prompt=body.prompt,
        )


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
            request=request,
            target_snapshot={
                "id": provider.id,
                "name": provider.name,
                "provider": provider.provider,
            },
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
            select(SecretORM)
            .where(SecretORM.workspace_id == workspace_id)
            .order_by(desc(SecretORM.created_at))
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
            request=request,
            target_snapshot={"id": secret.id, "name": secret.name, "last4": secret.last4},
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
            request=request,
            target_snapshot={"id": secret.id, "name": secret.name, "last4": secret.last4},
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
            select(ApiKeyORM)
            .where(ApiKeyORM.workspace_id == workspace_id)
            .order_by(desc(ApiKeyORM.created_at))
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
            expires_at = utc_now_naive() + timedelta(days=body.expires_in_days)

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
            {"name": body.name, "scopes": [s.value for s in body.scopes]},
            request=request,
            target_snapshot={
                "id": api_key.id,
                "name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "expires_at": expires_at,
            },
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

        api_key.revoked_at = utc_now_naive()

        await log_audit(
            session,
            workspace_id,
            user_id,
            AuditAction.API_KEY_REVOKE,
            "api_key",
            key_id,
            {"name": api_key.name},
            request=request,
            target_snapshot={
                "id": api_key.id,
                "name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "revoked_at": api_key.revoked_at,
            },
        )

        await session.commit()

        return {"message": "API Key 已撤销"}


# ==================== 审计日志 API ====================


@router.get("/admin/audit-logs")
async def list_audit_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    outcome: str | None = None,
    user_id_filter: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
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

        audit_service = AuditLogService(session)
        return await audit_service.list_logs(
            workspace_id=workspace_id,
            page=page,
            page_size=page_size,
            action=action,
            outcome=outcome,
            user_id=user_id_filter,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            start_time=start_time,
            end_time=end_time,
        )
