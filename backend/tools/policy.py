"""工具权限、风险、审批与基础限流策略。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from models.auth_models import MemberRole
from services.permission_service import PermissionService, check_permission, is_admin_role
from tools.runtime import ToolRuntime
from tools.schemas import RiskLevel, ToolApprovalMode, ToolPolicyDecision, ToolSpec

DEFAULT_RISK_PERMISSIONS: dict[RiskLevel, list[str]] = {
    RiskLevel.READ_PUBLIC: [],
    RiskLevel.READ_PRIVATE: ["workflow_run.read"],
    RiskLevel.WRITE_INTERNAL: ["workflow.update"],
    RiskLevel.EXTERNAL_ACTION: ["workflow.execute"],
    RiskLevel.DESTRUCTIVE: ["workspace.manage"],
}


class ToolPolicyEngine:
    """后端强制执行工具治理策略，不信任模型或前端判断。"""

    def __init__(self):
        self._rate_windows: dict[str, deque[float]] = defaultdict(deque)

    async def evaluate(
        self,
        spec: ToolSpec,
        runtime: ToolRuntime,
        *,
        approval_mode: ToolApprovalMode = ToolApprovalMode.POLICY_DEFAULT,
    ) -> ToolPolicyDecision:
        if not spec.enabled:
            return ToolPolicyDecision(
                allowed=False,
                reason=f"工具 {spec.name} 已禁用",
            )

        required_permissions = spec.permissions or DEFAULT_RISK_PERMISSIONS[spec.risk_level]
        permission_denied = await self._check_permissions(required_permissions, runtime)
        if permission_denied:
            return ToolPolicyDecision(
                allowed=False,
                reason=permission_denied,
                required_permissions=required_permissions,
            )

        if spec.risk_level == RiskLevel.DESTRUCTIVE and not await self.is_destructive_allowed(
            runtime
        ):
            return ToolPolicyDecision(
                allowed=False,
                reason="破坏性工具仅允许管理员或拥有者调用",
                required_permissions=required_permissions,
            )

        rate_denied = self._check_rate_limit(spec, runtime)
        if rate_denied:
            return ToolPolicyDecision(
                allowed=False,
                reason=rate_denied,
                required_permissions=required_permissions,
            )

        requires_approval = self._requires_approval(spec, approval_mode)
        return ToolPolicyDecision(
            allowed=True,
            requires_approval=requires_approval,
            required_permissions=required_permissions,
        )

    def _requires_approval(self, spec: ToolSpec, approval_mode: ToolApprovalMode) -> bool:
        if spec.risk_level == RiskLevel.DESTRUCTIVE:
            return True
        if approval_mode == ToolApprovalMode.AUTO:
            return False
        if approval_mode == ToolApprovalMode.GATE_REQUIRED:
            return True
        return spec.requires_approval or spec.risk_level in {
            RiskLevel.EXTERNAL_ACTION,
            RiskLevel.DESTRUCTIVE,
        }

    async def _check_permissions(
        self,
        required_permissions: list[str],
        runtime: ToolRuntime,
    ) -> str | None:
        if not required_permissions:
            return None
        if not runtime.user_id or not runtime.workspace_id:
            return "工具调用缺少用户或工作空间上下文"

        role = self._coerce_role(runtime.role)
        if role is not None:
            for permission in required_permissions:
                resource, action = self._split_permission(permission)
                if not check_permission(role, resource, action):
                    return f"缺少工具权限: {permission}"
            return None

        if runtime.db_session is not None:
            service = PermissionService(runtime.db_session)
            for permission in required_permissions:
                resource, action = self._split_permission(permission)
                allowed = await service.check_user_permission(
                    runtime.user_id,
                    runtime.workspace_id,
                    resource,
                    action,
                )
                if not allowed:
                    return f"缺少工具权限: {permission}"
            return None

        try:
            from db.postgres_store import get_postgres_store

            async with get_postgres_store().initialized_session() as session:
                service = PermissionService(session)
                for permission in required_permissions:
                    resource, action = self._split_permission(permission)
                    allowed = await service.check_user_permission(
                        runtime.user_id,
                        runtime.workspace_id,
                        resource,
                        action,
                    )
                    if not allowed:
                        return f"缺少工具权限: {permission}"
            return None
        except Exception:
            return "无法校验工具权限"

    def _check_rate_limit(self, spec: ToolSpec, runtime: ToolRuntime) -> str | None:
        policy = spec.cost_policy or {}
        limit = self._positive_int(policy.get("max_calls_per_minute"))
        if not limit:
            return None

        key = ":".join(
            [
                runtime.workspace_id or "anonymous-workspace",
                runtime.user_id or "anonymous-user",
                spec.name,
            ]
        )
        now = time.monotonic()
        window = self._rate_windows[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return f"工具 {spec.name} 超过每分钟 {limit} 次调用限制"
        window.append(now)
        return None

    @staticmethod
    def _split_permission(permission: str) -> tuple[str, str]:
        parts = permission.split(".", 1)
        if len(parts) != 2:
            return permission, "read"
        return parts[0], parts[1]

    @staticmethod
    def _coerce_role(value: Any) -> MemberRole | None:
        if isinstance(value, MemberRole):
            return value
        if isinstance(value, str):
            try:
                return MemberRole(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    async def is_destructive_allowed(self, runtime: ToolRuntime) -> bool:
        """L4 工具需要管理员或 owner，供后续插件治理复用。"""
        role = self._coerce_role(runtime.role)
        if role is not None:
            return is_admin_role(role)
        return False
