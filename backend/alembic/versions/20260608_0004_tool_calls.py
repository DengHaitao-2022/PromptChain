"""add tool call audit table

Revision ID: 20260608_0004
Revises: 20260531_0003
Create Date: 2026-06-08 00:04:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260608_0004"
down_revision: str | None = "20260531_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建工具调用审计表和查询索引。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_calls (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) REFERENCES workspaces(id),
            workflow_run_id VARCHAR(36) REFERENCES workflow_runs(id),
            node_run_id VARCHAR(36) REFERENCES node_runs(id),
            tool_name VARCHAR(160) NOT NULL,
            tool_version VARCHAR(40) NOT NULL DEFAULT '1.0.0',
            source_type VARCHAR(40) NOT NULL DEFAULT 'internal',
            risk_level VARCHAR(40) NOT NULL DEFAULT 'read_public',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            input_json JSON NOT NULL DEFAULT '{}'::json,
            output_json JSON,
            error_message TEXT,
            latency_ms INTEGER,
            token_cost INTEGER,
            money_cost DOUBLE PRECISION,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            approved_by VARCHAR(36) REFERENCES users(id),
            approved_at TIMESTAMPTZ,
            created_by VARCHAR(36) REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            metadata_json JSON DEFAULT '{}'::json
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_calls_workflow_created "
        "ON tool_calls (workflow_run_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_calls_node_created "
        "ON tool_calls (node_run_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_calls_workspace_status "
        "ON tool_calls (workspace_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_calls_name_created "
        "ON tool_calls (tool_name, created_at DESC)"
    )


def downgrade() -> None:
    """回滚工具调用审计表。"""
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_name_created")
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_workspace_status")
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_node_created")
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_workflow_created")
    op.execute("DROP TABLE IF EXISTS tool_calls")
