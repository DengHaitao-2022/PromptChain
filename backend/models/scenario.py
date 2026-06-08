"""MVP3 场景工作台领域模型。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.time import utc_now_naive


class ScenarioTemplateStatus(StrEnum):
    """场景模板状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class ContentProjectStatus(StrEnum):
    """内容项目状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ProjectAssetEmbeddingStatus(StrEnum):
    """项目资产检索索引状态。"""

    SKIPPED = "skipped"
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ProjectAssetLifecycleStatus(StrEnum):
    """项目资产生命周期状态。"""

    DRAFT = "draft"
    CANDIDATE = "candidate"
    CANON = "canon"
    CONFLICT = "conflict"
    DEPRECATED = "deprecated"


class ScenarioTemplate(BaseModel):
    """场景模板读模型。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    name: str
    category: str
    description: str | None = None
    schema_version: int = 1
    input_schema: dict[str, Any] = Field(default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)
    artifact_schema: dict[str, Any] = Field(default_factory=dict)
    default_workflow_definition_id: str | None = None
    default_workflow_version_id: str | None = None
    default_generation_modes: list[dict[str, Any]] = Field(default_factory=list)
    checker_rules: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    status: ScenarioTemplateStatus = ScenarioTemplateStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)


class ContentProject(BaseModel):
    """内容项目读模型。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    scenario_code: str
    title: str
    description: str | None = None
    status: ContentProjectStatus = ContentProjectStatus.ACTIVE
    config: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)


class ProjectAssetVersion(BaseModel):
    """项目资产历史版本。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    version: int = Field(ge=1)
    content: Any
    source_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime = Field(default_factory=utc_now_naive)


class ProjectAsset(BaseModel):
    """项目资产当前版本读模型。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    asset_type: str
    title: str
    content: Any
    version: int = Field(default=1, ge=1)
    source_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    lifecycle_status: ProjectAssetLifecycleStatus = ProjectAssetLifecycleStatus.CANON
    embedding_status: ProjectAssetEmbeddingStatus = ProjectAssetEmbeddingStatus.SKIPPED
    created_by: str
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)
