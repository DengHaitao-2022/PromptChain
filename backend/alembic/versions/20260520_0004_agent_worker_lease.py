"""add autonomous agent worker lease fields

Revision ID: 20260520_0004
Revises: 20260520_0003
Create Date: 2026-05-20 00:04:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260520_0004"
down_revision: str | None = "20260520_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为 AgentRun 增加 durable worker claim/lease 字段。"""
    op.add_column(
        "agent_runs",
        sa.Column("queue_status", sa.String(length=32), nullable=False, server_default="idle"),
    )
    op.add_column("agent_runs", sa.Column("queued_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runs", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runs", sa.Column("worker_id", sa.String(length=100), nullable=True))
    op.add_column("agent_runs", sa.Column("lease_token", sa.String(length=64), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("agent_runs", sa.Column("last_worker_error", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_agent_runs_queue_status"), "agent_runs", ["queue_status"], unique=False
    )
    op.create_index(
        op.f("ix_agent_runs_lease_expires_at"),
        "agent_runs",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index(op.f("ix_agent_runs_worker_id"), "agent_runs", ["worker_id"], unique=False)


def downgrade() -> None:
    """回滚 AgentRun worker lease 字段。"""
    op.drop_index(op.f("ix_agent_runs_worker_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_lease_expires_at"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_queue_status"), table_name="agent_runs")
    op.drop_column("agent_runs", "last_worker_error")
    op.drop_column("agent_runs", "attempt_count")
    op.drop_column("agent_runs", "lease_token")
    op.drop_column("agent_runs", "worker_id")
    op.drop_column("agent_runs", "heartbeat_at")
    op.drop_column("agent_runs", "lease_expires_at")
    op.drop_column("agent_runs", "claimed_at")
    op.drop_column("agent_runs", "queued_at")
    op.drop_column("agent_runs", "queue_status")
