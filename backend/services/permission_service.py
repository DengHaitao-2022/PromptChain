"""
权限服务

实现 Workspace 级别 RBAC 权限控制
"""

from typing import Literal

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.errors.codes import (
    AUTH_UNAUTHENTICATED,
    WORKSPACE_ACCESS_DENIED,
    WORKSPACE_CONTEXT_REQUIRED,
)
from core.errors.exceptions import ApplicationError, DomainError
from db.postgres_store import get_postgres_store
from models.auth_models import MemberRole
from models.auth_orm import MembershipORM

# ==================== 权限定义 ====================

# 资源类型
RESOURCES = [
    "workflow",  # 工作流
    "workflow_run",  # 运行记录
    "template",  # 模板
    "model_provider",  # 模型供应商
    "secret",  # 密钥
    "api_key",  # API Key
    "member",  # 成员管理
    "workspace",  # 工作空间设置
    "audit_log",  # 审计日志
]

# 动作类型
ACTIONS = [
    "read",  # 读取
    "create",  # 创建
    "update",  # 更新
    "delete",  # 删除
    "execute",  # 执行（如运行工作流）
    "export",  # 导出
    "manage",  # 管理权限（如邀请成员、配置密钥）
]


# 角色权限映射
ROLE_PERMISSIONS: dict[MemberRole, dict[str, list[str]]] = {
    MemberRole.VIEWER: {
        "workflow": ["read", "execute"],
        "workflow_run": ["read", "create"],
        "template": ["read"],
        "model_provider": [],
        "secret": [],
        "api_key": [],
        "member": [],
        "workspace": ["read"],
        "audit_log": [],
    },
    MemberRole.EDITOR: {
        "workflow": ["read", "create", "update", "execute"],
        "workflow_run": ["read", "create"],
        "template": ["read", "create", "update"],
        "model_provider": [],
        "secret": [],
        "api_key": [],
        "member": [],
        "workspace": ["read"],
        "audit_log": [],
    },
    MemberRole.ADMIN: {
        "workflow": ["read", "create", "update", "delete", "execute", "export", "manage"],
        "workflow_run": ["read", "create", "delete", "export"],
        "template": ["read", "create", "update", "delete", "manage"],
        "model_provider": ["read", "create", "update", "delete", "manage"],
        "secret": ["read", "create", "update", "delete", "manage"],
        "api_key": ["read", "create", "update", "delete", "manage"],
        "member": ["read", "create", "update", "delete", "manage"],
        "workspace": ["read", "update", "manage"],
        "audit_log": ["read", "export"],
    },
    MemberRole.OWNER: {
        "workflow": ["read", "create", "update", "delete", "execute", "export", "manage"],
        "workflow_run": ["read", "create", "delete", "export", "manage"],
        "template": ["read", "create", "update", "delete", "manage"],
        "model_provider": ["read", "create", "update", "delete", "manage"],
        "secret": ["read", "create", "update", "delete", "manage"],
        "api_key": ["read", "create", "update", "delete", "manage"],
        "member": ["read", "create", "update", "delete", "manage"],
        "workspace": ["read", "update", "delete", "manage"],
        "audit_log": ["read", "export"],
    },
}

ROLE_ORDER: tuple[MemberRole, ...] = (
    MemberRole.VIEWER,
    MemberRole.EDITOR,
    MemberRole.ADMIN,
    MemberRole.OWNER,
)
SUSPENDED_MEMBERSHIP_PREFIX = "suspended:"

PermissionResource = Literal[
    "workflow",
    "workflow_run",
    "template",
    "model_provider",
    "secret",
    "api_key",
    "member",
    "workspace",
    "audit_log",
]

PermissionAction = Literal[
    "read",
    "create",
    "update",
    "delete",
    "execute",
    "export",
    "manage",
]


# ==================== 权限检查函数 ====================


def check_permission(
    role: MemberRole, resource: PermissionResource | str, action: PermissionAction | str
) -> bool:
    """
    检查角色是否有指定资源的指定操作权限

    Args:
        role: 用户角色
        resource: 资源类型
        action: 操作类型

    Returns:
        是否有权限
    """
    if role not in ROLE_PERMISSIONS:
        return False

    role_perms = ROLE_PERMISSIONS[role]
    if resource not in role_perms:
        return False

    return action in role_perms[resource]


def is_at_least_role(current_role: MemberRole, required_role: MemberRole) -> bool:
    """检查当前角色是否不低于指定角色。"""
    return ROLE_ORDER.index(current_role) >= ROLE_ORDER.index(required_role)


def is_admin_role(role: MemberRole | None) -> bool:
    """管理员与拥有者均视为管理角色。"""
    return role in {MemberRole.ADMIN, MemberRole.OWNER}


def resolve_membership_role(raw_role: str | None) -> tuple[MemberRole | None, bool]:
    """解析成员关系中的原始角色字符串，并识别工作空间级暂停状态。"""
    if not raw_role:
        return None, False

    is_suspended = raw_role.startswith(SUSPENDED_MEMBERSHIP_PREFIX)
    normalized_role = raw_role[len(SUSPENDED_MEMBERSHIP_PREFIX) :] if is_suspended else raw_role

    try:
        return MemberRole(normalized_role), is_suspended
    except ValueError:
        return None, is_suspended


def serialize_membership_role(role: MemberRole | str, suspended: bool = False) -> str:
    """将成员角色编码为数据库中的字符串格式。"""
    normalized_role = role.value if isinstance(role, MemberRole) else role
    if suspended:
        return f"{SUSPENDED_MEMBERSHIP_PREFIX}{normalized_role}"
    return normalized_role


def is_membership_suspended(raw_role: str | None) -> bool:
    """判断成员关系是否处于当前工作空间访问暂停状态。"""
    return bool(raw_role and raw_role.startswith(SUSPENDED_MEMBERSHIP_PREFIX))


def get_role_permissions(role: MemberRole) -> dict[str, list[str]]:
    """获取角色的所有权限"""
    return ROLE_PERMISSIONS.get(role, {})


def get_allowed_actions(role: MemberRole, resource: str) -> list[str]:
    """获取角色对指定资源的所有允许操作"""
    return ROLE_PERMISSIONS.get(role, {}).get(resource, [])


# ==================== 权限服务类 ====================


class PermissionService:
    """权限服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_role_in_workspace(
        self, user_id: str, workspace_id: str
    ) -> MemberRole | None:
        """
        获取用户在工作空间中的角色

        Args:
            user_id: 用户ID
            workspace_id: 工作空间ID

        Returns:
            用户角色或None
        """
        result = await self.session.execute(
            select(MembershipORM).where(
                MembershipORM.user_id == user_id, MembershipORM.workspace_id == workspace_id
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            return None

        role, is_suspended = resolve_membership_role(membership.role)
        if is_suspended:
            return None

        return role

    async def check_user_permission(
        self, user_id: str, workspace_id: str, resource: str, action: str
    ) -> bool:
        """
        检查用户是否有指定权限

        Args:
            user_id: 用户ID
            workspace_id: 工作空间ID
            resource: 资源类型
            action: 操作类型

        Returns:
            是否有权限
        """
        role = await self.get_user_role_in_workspace(user_id, workspace_id)
        if not role:
            return False

        return check_permission(role, resource, action)

    async def require_permission(
        self, user_id: str, workspace_id: str, resource: str, action: str
    ) -> MemberRole:
        """
        检查权限，无权限时抛出异常

        Args:
            user_id: 用户ID
            workspace_id: 工作空间ID
            resource: 资源类型
            action: 操作类型

        Returns:
            用户角色

        Raises:
            DomainError: 无权限时抛出统一权限错误
        """
        role = await self.get_user_role_in_workspace(user_id, workspace_id)

        if not role:
            raise DomainError(
                code=WORKSPACE_ACCESS_DENIED,
                message="您不是该工作空间的成员",
            )

        if not check_permission(role, resource, action):
            raise DomainError(
                code=WORKSPACE_ACCESS_DENIED,
                message=f"您没有 {resource}.{action} 的权限",
            )

        return role

    async def get_user_workspaces_with_permission(
        self, user_id: str, resource: str, action: str
    ) -> list[str]:
        """
        获取用户有指定权限的所有工作空间ID

        Args:
            user_id: 用户ID
            resource: 资源类型
            action: 操作类型

        Returns:
            工作空间ID列表
        """
        result = await self.session.execute(
            select(MembershipORM).where(MembershipORM.user_id == user_id)
        )
        memberships = result.scalars().all()

        workspace_ids = []
        for membership in memberships:
            role, is_suspended = resolve_membership_role(membership.role)
            if not role or is_suspended:
                continue
            if check_permission(role, resource, action):
                workspace_ids.append(membership.workspace_id)

        return workspace_ids


# ==================== FastAPI 依赖 ====================


def require_permission_dependency(resource: str, action: str):
    """
    创建权限检查依赖

    使用方式:
    @app.get("/workflows")
    async def list_workflows(
        permission = Depends(require_permission_dependency("workflow", "read"))
    ):
        ...

    Args:
        resource: 资源类型
        action: 操作类型

    Returns:
        FastAPI 依赖函数
    """

    async def dependency(
        request: Request,
    ):
        user_id = getattr(request.state, "user_id", None)
        workspace_id = getattr(request.state, "workspace_id", None)

        if not user_id:
            raise ApplicationError(
                code=AUTH_UNAUTHENTICATED,
                message="未登录",
            )
        if not workspace_id:
            raise ApplicationError(
                code=WORKSPACE_CONTEXT_REQUIRED,
                message="请先选择工作空间",
            )

        store = get_postgres_store()

        async with store.async_session() as session:
            permission_service = PermissionService(session)
            role = await permission_service.require_permission(
                user_id, workspace_id, resource, action
            )
            request.state.role = role
            return role

    return dependency
