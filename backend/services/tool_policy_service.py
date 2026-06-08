"""Workspace 级工具治理策略服务。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.time import utc_now
from orm.tool_orm import WorkspaceToolPolicyORM


class ToolPolicyService:
    """管理 workspace 对单个工具的显式 auto-run 授权。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_policies(self, workspace_id: str) -> list[WorkspaceToolPolicyORM]:
        result = await self.session.execute(
            select(WorkspaceToolPolicyORM)
            .where(WorkspaceToolPolicyORM.workspace_id == workspace_id)
            .order_by(WorkspaceToolPolicyORM.tool_name)
        )
        return list(result.scalars().all())

    async def get_policy(
        self,
        workspace_id: str,
        tool_name: str,
    ) -> WorkspaceToolPolicyORM | None:
        result = await self.session.execute(
            select(WorkspaceToolPolicyORM).where(
                WorkspaceToolPolicyORM.workspace_id == workspace_id,
                WorkspaceToolPolicyORM.tool_name == tool_name,
            )
        )
        return result.scalar_one_or_none()

    async def is_auto_run_enabled(self, workspace_id: str, tool_name: str) -> bool:
        policy = await self.get_policy(workspace_id, tool_name)
        return bool(policy and policy.auto_run_enabled)

    async def upsert_policy(
        self,
        *,
        workspace_id: str,
        tool_name: str,
        auto_run_enabled: bool,
        actor_user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceToolPolicyORM:
        policy = await self.get_policy(workspace_id, tool_name)
        now = utc_now()
        if policy is None:
            policy = WorkspaceToolPolicyORM(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                tool_name=tool_name,
                auto_run_enabled=auto_run_enabled,
                created_by=actor_user_id,
                updated_by=actor_user_id,
                created_at=now,
                updated_at=now,
                metadata_json=metadata or {},
            )
            self.session.add(policy)
            return policy

        policy.auto_run_enabled = auto_run_enabled
        policy.updated_by = actor_user_id
        policy.updated_at = now
        if metadata is not None:
            policy.metadata_json = metadata
        return policy
