"""add mvp3 scenario projects

Revision ID: 20260607_0004
Revises: 20260607_0001
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260607_0004"
down_revision: str | None = "20260607_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ui_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "artifact_schema",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("default_workflow_definition_id", sa.String(length=36), nullable=True),
        sa.Column("default_workflow_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "default_generation_modes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("checker_rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_scenario_templates_code", "scenario_templates", ["code"], unique=True)
    op.create_index("ix_scenario_templates_category", "scenario_templates", ["category"])
    op.create_index("ix_scenario_templates_status", "scenario_templates", ["status"])

    op.create_table(
        "content_projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
    )
    op.create_index("ix_content_projects_workspace_id", "content_projects", ["workspace_id"])
    op.create_index("ix_content_projects_scenario_code", "content_projects", ["scenario_code"])
    op.create_index("ix_content_projects_status", "content_projects", ["status"])
    op.create_index("ix_content_projects_created_by", "content_projects", ["created_by"])
    op.create_index(
        "ix_content_projects_workspace_scenario_status",
        "content_projects",
        ["workspace_id", "scenario_code", "status"],
    )

    op.create_table(
        "project_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "embedding_status", sa.String(length=20), nullable=False, server_default="skipped"
        ),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["content_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.id"]),
    )
    op.create_index("ix_project_assets_project_id", "project_assets", ["project_id"])
    op.create_index("ix_project_assets_asset_type", "project_assets", ["asset_type"])
    op.create_index(
        "ix_project_assets_source_artifact_id", "project_assets", ["source_artifact_id"]
    )
    op.create_index("ix_project_assets_embedding_status", "project_assets", ["embedding_status"])
    op.create_index("ix_project_assets_created_by", "project_assets", ["created_by"])
    op.create_index(
        "ix_project_assets_project_type", "project_assets", ["project_id", "asset_type"]
    )

    op.create_table(
        "project_asset_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("source_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["project_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.id"]),
        sa.UniqueConstraint("asset_id", "version", name="uq_project_asset_version"),
    )
    op.create_index("ix_project_asset_versions_asset_id", "project_asset_versions", ["asset_id"])
    op.create_index(
        "ix_project_asset_versions_source_artifact_id",
        "project_asset_versions",
        ["source_artifact_id"],
    )
    op.create_index(
        "ix_project_asset_versions_created_by", "project_asset_versions", ["created_by"]
    )
    op.create_index(
        "ix_project_asset_versions_asset_version",
        "project_asset_versions",
        ["asset_id", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_asset_versions_asset_version", table_name="project_asset_versions")
    op.drop_index("ix_project_asset_versions_created_by", table_name="project_asset_versions")
    op.drop_index(
        "ix_project_asset_versions_source_artifact_id",
        table_name="project_asset_versions",
    )
    op.drop_index("ix_project_asset_versions_asset_id", table_name="project_asset_versions")
    op.drop_table("project_asset_versions")

    op.drop_index("ix_project_assets_project_type", table_name="project_assets")
    op.drop_index("ix_project_assets_created_by", table_name="project_assets")
    op.drop_index("ix_project_assets_embedding_status", table_name="project_assets")
    op.drop_index("ix_project_assets_source_artifact_id", table_name="project_assets")
    op.drop_index("ix_project_assets_asset_type", table_name="project_assets")
    op.drop_index("ix_project_assets_project_id", table_name="project_assets")
    op.drop_table("project_assets")

    op.drop_index("ix_content_projects_workspace_scenario_status", table_name="content_projects")
    op.drop_index("ix_content_projects_created_by", table_name="content_projects")
    op.drop_index("ix_content_projects_status", table_name="content_projects")
    op.drop_index("ix_content_projects_scenario_code", table_name="content_projects")
    op.drop_index("ix_content_projects_workspace_id", table_name="content_projects")
    op.drop_table("content_projects")

    op.drop_index("ix_scenario_templates_status", table_name="scenario_templates")
    op.drop_index("ix_scenario_templates_category", table_name="scenario_templates")
    op.drop_index("ix_scenario_templates_code", table_name="scenario_templates")
    op.drop_table("scenario_templates")
