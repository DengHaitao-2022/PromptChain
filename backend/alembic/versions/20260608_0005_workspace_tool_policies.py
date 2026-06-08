"""add workspace tool auto-run policies

Revision ID: 20260608_0005
Revises: 20260608_0004
Create Date: 2026-06-08 00:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260608_0005"
down_revision: str | None = "20260608_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 workspace 级工具 auto-run 显式授权表。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_tool_policies (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            tool_name VARCHAR(160) NOT NULL,
            auto_run_enabled BOOLEAN NOT NULL DEFAULT false,
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            updated_by VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            metadata_json JSON DEFAULT '{}'::json,
            CONSTRAINT uq_workspace_tool_policy UNIQUE (workspace_id, tool_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspace_tool_policies_workspace_id "
        "ON workspace_tool_policies (workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspace_tool_policies_tool_name "
        "ON workspace_tool_policies (tool_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspace_tool_policies_workspace_tool "
        "ON workspace_tool_policies (workspace_id, tool_name)"
    )


def downgrade() -> None:
    """删除 workspace 工具 auto-run 授权表。"""
    op.execute("DROP INDEX IF EXISTS ix_workspace_tool_policies_workspace_tool")
    op.execute("DROP INDEX IF EXISTS ix_workspace_tool_policies_tool_name")
    op.execute("DROP INDEX IF EXISTS ix_workspace_tool_policies_workspace_id")
    op.execute("DROP TABLE IF EXISTS workspace_tool_policies")
