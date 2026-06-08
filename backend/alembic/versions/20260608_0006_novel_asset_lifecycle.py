"""add novel asset lifecycle status

Revision ID: 20260608_0006
Revises: 20260608_0005
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260608_0006"
down_revision: str | None = "20260608_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_assets",
        sa.Column(
            "lifecycle_status",
            sa.String(length=20),
            nullable=False,
            server_default="canon",
        ),
    )
    op.create_index(
        "ix_project_assets_lifecycle_status",
        "project_assets",
        ["lifecycle_status"],
    )
    op.create_index(
        "ix_project_assets_project_type_lifecycle",
        "project_assets",
        ["project_id", "asset_type", "lifecycle_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_assets_project_type_lifecycle", table_name="project_assets")
    op.drop_index("ix_project_assets_lifecycle_status", table_name="project_assets")
    op.drop_column("project_assets", "lifecycle_status")
