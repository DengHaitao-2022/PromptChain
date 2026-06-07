"""extend tool call audit table for workflow tools

Revision ID: 20260608_0004
Revises: 20260607_0001
Create Date: 2026-06-08 00:04:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260608_0004"
down_revision: str | None = "20260607_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """扩展统一 tool_calls 表，兼容 Agent 与 Workflow 工具调用。"""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_calls (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) REFERENCES agent_runs(id),
            step_id VARCHAR(36),
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
            cost JSON DEFAULT '{}'::json,
            token_cost INTEGER,
            money_cost DOUBLE PRECISION,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            approved_by VARCHAR(36) REFERENCES users(id),
            approved_at TIMESTAMPTZ,
            created_by VARCHAR(36) REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ DEFAULT now(),
            metadata_json JSON DEFAULT '{}'::json
        )
        """
    )
    op.execute("ALTER TABLE tool_calls ALTER COLUMN run_id DROP NOT NULL")
    op.execute("ALTER TABLE tool_calls ALTER COLUMN tool_name TYPE VARCHAR(160)")
    op.execute("ALTER TABLE tool_calls ALTER COLUMN risk_level TYPE VARCHAR(40)")
    op.execute("ALTER TABLE tool_calls ALTER COLUMN status TYPE VARCHAR(40)")
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(36) REFERENCES workspaces(id)"
    )
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36) REFERENCES workflow_runs(id)"
    )
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS node_run_id VARCHAR(36) REFERENCES node_runs(id)"
    )
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS tool_version VARCHAR(40) NOT NULL DEFAULT '1.0.0'"
    )
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS source_type VARCHAR(40) NOT NULL DEFAULT 'internal'"
    )
    op.execute("ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS cost JSON DEFAULT '{}'::json")
    op.execute("ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS token_cost INTEGER")
    op.execute("ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS money_cost DOUBLE PRECISION")
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS requires_approval INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS approved_by VARCHAR(36) REFERENCES users(id)"
    )
    op.execute("ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS created_by VARCHAR(36) REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()"
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
    """回滚 Workflow Tool Factory 为 tool_calls 添加的扩展列。"""
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_name_created")
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_workspace_status")
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_node_created")
    op.execute("DROP INDEX IF EXISTS ix_tool_calls_workflow_created")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS approved_by")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS requires_approval")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS money_cost")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS token_cost")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS source_type")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS tool_version")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS node_run_id")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS workflow_run_id")
    op.execute("ALTER TABLE tool_calls DROP COLUMN IF EXISTS workspace_id")
