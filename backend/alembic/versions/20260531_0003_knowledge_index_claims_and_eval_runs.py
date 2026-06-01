"""add knowledge index claim and evaluation run tables

Revision ID: 20260531_0003
Revises: 20260520_0002
Create Date: 2026-05-31 00:03:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260531_0003"
down_revision: str | None = "20260520_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """补充索引领取队列索引和检索评测持久化表。"""
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_index_claim "
        "ON kb_documents (index_status, updated_at, created_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_retrieval_evaluation_runs (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            evaluation_type VARCHAR(40) NOT NULL DEFAULT 'retrieval',
            request_json JSON NOT NULL DEFAULT '{}'::json,
            summary_json JSON NOT NULL DEFAULT '{}'::json,
            results_json JSON NOT NULL DEFAULT '[]'::json,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "ALTER TABLE kb_retrieval_evaluation_runs "
        "ADD COLUMN IF NOT EXISTS evaluation_type VARCHAR(40) NOT NULL DEFAULT 'retrieval'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_eval_runs_workspace_created "
        "ON kb_retrieval_evaluation_runs (workspace_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_eval_runs_user_created "
        "ON kb_retrieval_evaluation_runs (user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_eval_runs_type_created "
        "ON kb_retrieval_evaluation_runs (evaluation_type, created_at DESC)"
    )


def downgrade() -> None:
    """回滚检索评测持久化结构。"""
    op.execute("DROP INDEX IF EXISTS ix_kb_eval_runs_type_created")
    op.execute("DROP TABLE IF EXISTS kb_retrieval_evaluation_runs")
    op.execute("DROP INDEX IF EXISTS ix_kb_documents_index_claim")
