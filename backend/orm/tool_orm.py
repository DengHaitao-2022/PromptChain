"""Tool Factory ORM 兼容入口。

tool_calls 表已与 Autonomous Agent Runtime 共享，避免两个运行态重复注册同名表。
"""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, String, UniqueConstraint

from core.time import utc_now
from db.postgres_store import Base
from orm.autonomous_agent_orm import ToolCallORM


class WorkspaceToolPolicyORM(Base):
    """Workspace 级工具策略，记录显式 auto-run 授权。"""

    __tablename__ = "workspace_tool_policies"
    __table_args__ = (
        UniqueConstraint("workspace_id", "tool_name", name="uq_workspace_tool_policy"),
        Index("ix_workspace_tool_policies_workspace_tool", "workspace_id", "tool_name"),
    )

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    tool_name = Column(String(160), nullable=False, index=True)
    auto_run_enabled = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    metadata_json = Column(JSON, default=dict)


__all__ = ["ToolCallORM", "WorkspaceToolPolicyORM"]
