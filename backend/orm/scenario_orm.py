"""MVP3 场景工作台 SQLAlchemy ORM。"""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core.time import utc_now_naive
from db.postgres_store import Base
from models.scenario import (
    ContentProjectStatus,
    ProjectAssetEmbeddingStatus,
    ScenarioTemplateStatus,
)


class ScenarioTemplateORM(Base):
    """场景模板表。"""

    __tablename__ = "scenario_templates"

    id = Column(String(36), primary_key=True)
    code = Column(String(80), nullable=False, unique=True, index=True)
    name = Column(String(160), nullable=False)
    category = Column(String(80), nullable=False, index=True)
    description = Column(Text, nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)
    input_schema = Column(JSON, default=dict, nullable=False)
    ui_schema = Column(JSON, default=dict, nullable=False)
    artifact_schema = Column(JSON, default=dict, nullable=False)
    default_workflow_definition_id = Column(String(36), nullable=True)
    default_workflow_version_id = Column(String(36), nullable=True)
    default_generation_modes = Column(JSON, default=list, nullable=False)
    checker_rules = Column(JSON, default=dict, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=ScenarioTemplateStatus.ACTIVE.value,
        index=True,
    )
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class ContentProjectORM(Base):
    """内容项目表。"""

    __tablename__ = "content_projects"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    scenario_code = Column(String(80), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default=ContentProjectStatus.ACTIVE.value,
        index=True,
    )
    config = Column(JSON, default=dict, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    assets = relationship(
        "ProjectAssetORM",
        back_populates="project",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_content_projects_workspace_scenario_status",
            "workspace_id",
            "scenario_code",
            "status",
        ),
    )


class ProjectAssetORM(Base):
    """项目资产当前版本表。"""

    __tablename__ = "project_assets"

    id = Column(String(36), primary_key=True)
    project_id = Column(
        String(36),
        ForeignKey("content_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type = Column(String(80), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(JSON, default=dict, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    source_artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=True, index=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    embedding_status = Column(
        String(20),
        nullable=False,
        default=ProjectAssetEmbeddingStatus.SKIPPED.value,
        index=True,
    )
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    project = relationship("ContentProjectORM", back_populates="assets")
    versions = relationship(
        "ProjectAssetVersionORM",
        back_populates="asset",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("ix_project_assets_project_type", "project_id", "asset_type"),)


class ProjectAssetVersionORM(Base):
    """项目资产不可变历史版本表。"""

    __tablename__ = "project_asset_versions"

    id = Column(String(36), primary_key=True)
    asset_id = Column(
        String(36),
        ForeignKey("project_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    content = Column(JSON, default=dict, nullable=False)
    source_artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=True, index=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive)

    asset = relationship("ProjectAssetORM", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_project_asset_version"),
        Index("ix_project_asset_versions_asset_version", "asset_id", "version"),
    )
