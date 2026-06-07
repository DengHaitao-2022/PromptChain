"""merge autonomous agent and knowledge index heads

Revision ID: 20260607_0001
Revises: 20260520_0004, 20260531_0003
Create Date: 2026-06-07 21:25:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "20260607_0001"
down_revision: tuple[str, str] | None = ("20260520_0004", "20260531_0003")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """合并迁移分支，不执行额外 DDL。"""


def downgrade() -> None:
    """回退 merge revision 时不执行额外 DDL。"""
