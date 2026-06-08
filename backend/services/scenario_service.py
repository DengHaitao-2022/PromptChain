"""MVP3 场景模板、内容项目与项目记忆服务。"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.time import utc_now_naive
from models.auth_models import MemberRole
from models.knowledge import KnowledgeScope
from models.scenario import (
    ContentProject,
    ContentProjectStatus,
    ProjectAsset,
    ProjectAssetEmbeddingStatus,
    ProjectAssetLifecycleStatus,
    ProjectAssetVersion,
    ScenarioTemplate,
    ScenarioTemplateStatus,
)
from orm.scenario_orm import (
    ContentProjectORM,
    ProjectAssetORM,
    ProjectAssetVersionORM,
    ScenarioTemplateORM,
)
from services.knowledge_service import KnowledgeService, _row_to_knowledge_base
from services.novel import NOVEL_ASSET_TYPES
from services.permission_service import check_permission

DEFAULT_SCENARIO_TEMPLATES: list[dict[str, Any]] = [
    {
        "code": "novel_writing",
        "name": "小说创作",
        "category": "creative",
        "description": "面向长篇故事的 Story Bible、人物、世界观、时间线与场景生成工作台。",
        "schema_version": 1,
        "default_generation_modes": [
            {"code": "initialize_story", "name": "初始化故事资产"},
            {"code": "plan_scene", "name": "规划场景"},
            {"code": "continue_scene", "name": "续写当前场景"},
            {"code": "generate_scene", "name": "生成场景正文"},
            {"code": "rewrite_scene", "name": "重写当前场景"},
            {"code": "expand_scene", "name": "扩写场景描写"},
            {"code": "compress_scene", "name": "压缩场景"},
            {"code": "branch_plot", "name": "生成剧情分支"},
            {"code": "polish_style", "name": "只润色风格"},
            {"code": "fix_character_consistency", "name": "修复人物一致性"},
            {"code": "fix_timeline_conflict", "name": "修复时间线冲突"},
        ],
        "artifact_schema": {"asset_types": list(NOVEL_ASSET_TYPES)},
        "checker_rules": {
            "required_checks": [
                "character_consistency_check",
                "timeline_consistency_check",
                "worldbuilding_consistency_check",
            ]
        },
        "ui_schema": {
            "fields": [
                {"name": "story_goal", "label": "故事目标", "type": "textarea", "required": True},
                {"name": "genre", "label": "类型", "type": "text"},
                {"name": "target_words", "label": "目标字数", "type": "number"},
                {"name": "tone", "label": "叙事风格", "type": "text"},
            ]
        },
    },
    {
        "code": "marketing_copy",
        "name": "营销文案",
        "category": "business",
        "description": "面向品牌语气、受众画像、产品知识和多渠道营销文案的内容项目。",
        "schema_version": 1,
        "default_generation_modes": [
            {"code": "xiaohongshu_post", "name": "小红书文案"},
            {"code": "ecommerce_detail", "name": "电商详情页"},
            {"code": "ad_headlines", "name": "广告标题"},
            {"code": "short_video_pitch", "name": "短视频口播"},
            {"code": "ab_variants", "name": "A/B 多版本"},
            {"code": "brand_voice_rewrite", "name": "品牌语气改写"},
            {"code": "compliance_check", "name": "合规检查"},
        ],
        "artifact_schema": {
            "asset_types": [
                "brand_voice",
                "style_guide",
                "audience_profile",
                "product_knowledge",
                "campaign_brief",
                "content_variants",
                "compliance_report",
            ]
        },
        "checker_rules": {"required_checks": ["brand_voice_check", "compliance_check"]},
        "ui_schema": {
            "fields": [
                {
                    "name": "campaign_goal",
                    "label": "活动目标",
                    "type": "textarea",
                    "required": True,
                },
                {"name": "channel", "label": "投放渠道", "type": "text"},
                {"name": "audience", "label": "目标受众", "type": "textarea"},
            ]
        },
    },
    {
        "code": "short_video_script",
        "name": "短视频脚本",
        "category": "media",
        "description": "面向口播、分镜、标题和平台变体的短视频脚本生成项目。",
        "schema_version": 1,
        "default_generation_modes": [
            {"code": "hook_options", "name": "生成开场钩子"},
            {"code": "voiceover_script", "name": "生成口播稿"},
            {"code": "shot_list", "name": "生成分镜清单"},
            {"code": "caption_pack", "name": "生成标题与字幕包"},
            {"code": "platform_variant", "name": "平台变体改写"},
        ],
        "artifact_schema": {
            "asset_types": [
                "topic_brief",
                "hook_options",
                "script_outline",
                "shot_list",
                "voiceover_script",
                "caption_pack",
                "platform_variant",
            ]
        },
        "checker_rules": {"required_checks": ["style_guide_check"]},
        "ui_schema": {
            "fields": [
                {"name": "topic", "label": "选题", "type": "textarea", "required": True},
                {"name": "platform", "label": "平台", "type": "text"},
                {"name": "duration_seconds", "label": "时长（秒）", "type": "number"},
            ]
        },
    },
    {
        "code": "prd",
        "name": "产品需求文档",
        "category": "product",
        "description": "面向用户故事、流程、验收标准和风险报告的 PRD 生成项目。",
        "schema_version": 1,
        "default_generation_modes": [
            {"code": "requirement_card", "name": "需求卡片"},
            {"code": "user_story", "name": "用户故事"},
            {"code": "feature_list", "name": "功能清单"},
            {"code": "business_flow", "name": "业务流程"},
            {"code": "exception_flow", "name": "异常流程"},
            {"code": "acceptance_criteria", "name": "验收标准"},
            {"code": "risk_report", "name": "风险报告"},
        ],
        "artifact_schema": {
            "asset_types": [
                "requirement_card",
                "user_story",
                "feature_list",
                "business_flow",
                "exception_flow",
                "acceptance_criteria",
                "risk_report",
            ]
        },
        "checker_rules": {"required_checks": ["requirement_completeness_check"]},
        "ui_schema": {
            "fields": [
                {"name": "problem", "label": "问题背景", "type": "textarea", "required": True},
                {"name": "target_user", "label": "目标用户", "type": "text"},
                {"name": "success_metric", "label": "成功指标", "type": "textarea"},
            ]
        },
    },
]


def _row_to_template(row: ScenarioTemplateORM) -> ScenarioTemplate:
    return ScenarioTemplate(
        id=row.id,
        code=row.code,
        name=row.name,
        category=row.category,
        description=row.description,
        schema_version=row.schema_version,
        input_schema=row.input_schema or {},
        ui_schema=row.ui_schema or {},
        artifact_schema=row.artifact_schema or {},
        default_workflow_definition_id=row.default_workflow_definition_id,
        default_workflow_version_id=row.default_workflow_version_id,
        default_generation_modes=row.default_generation_modes or [],
        checker_rules=row.checker_rules or {},
        config=row.config or {},
        status=ScenarioTemplateStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_project(row: ContentProjectORM) -> ContentProject:
    return ContentProject(
        id=row.id,
        workspace_id=row.workspace_id,
        scenario_code=row.scenario_code,
        title=row.title,
        description=row.description,
        status=ContentProjectStatus(row.status),
        config=row.config or {},
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_asset(row: ProjectAssetORM) -> ProjectAsset:
    return ProjectAsset(
        id=row.id,
        project_id=row.project_id,
        asset_type=row.asset_type,
        title=row.title,
        content=row.content,
        version=row.version,
        source_artifact_id=row.source_artifact_id,
        metadata=row.metadata_json or {},
        lifecycle_status=ProjectAssetLifecycleStatus(
            row.lifecycle_status or ProjectAssetLifecycleStatus.CANON.value
        ),
        embedding_status=ProjectAssetEmbeddingStatus(row.embedding_status),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_asset_version(row: ProjectAssetVersionORM) -> ProjectAssetVersion:
    return ProjectAssetVersion(
        id=row.id,
        asset_id=row.asset_id,
        version=row.version,
        content=row.content,
        source_artifact_id=row.source_artifact_id,
        metadata=row.metadata_json or {},
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _normalize_role_value(role: Any) -> MemberRole | str:
    try:
        return MemberRole(str(getattr(role, "value", role)))
    except ValueError:
        return str(getattr(role, "value", role))


def _serialize_asset_content(content: Any) -> bytes:
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False, indent=2, default=str)
    return text.encode("utf-8")


def _template_asset_types(template: ScenarioTemplate) -> set[str]:
    asset_types = template.artifact_schema.get("asset_types")
    if not isinstance(asset_types, list):
        return set()
    return {str(asset_type) for asset_type in asset_types if asset_type}


def _template_generation_modes(template: ScenarioTemplate) -> set[str]:
    modes = template.default_generation_modes or []
    return {str(mode.get("code")) for mode in modes if isinstance(mode, dict) and mode.get("code")}


class ScenarioService:
    """场景工作台领域服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def seed_default_templates(self) -> None:
        """幂等写入内置场景模板，便于后续按 schema_version 升级。"""
        for template in DEFAULT_SCENARIO_TEMPLATES:
            result = await self.session.execute(
                select(ScenarioTemplateORM).where(ScenarioTemplateORM.code == template["code"])
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = ScenarioTemplateORM(id=str(uuid.uuid4()), code=template["code"])
                self.session.add(row)
            row.name = template["name"]
            row.category = template["category"]
            row.description = template.get("description")
            row.schema_version = int(template.get("schema_version") or 1)
            row.input_schema = template.get("input_schema") or {}
            row.ui_schema = template.get("ui_schema") or {}
            row.artifact_schema = template.get("artifact_schema") or {}
            row.default_generation_modes = template.get("default_generation_modes") or []
            row.checker_rules = template.get("checker_rules") or {}
            row.config = template.get("config") or {}
            row.status = ScenarioTemplateStatus.ACTIVE.value
            row.updated_at = utc_now_naive()
        await self.session.commit()

    async def list_templates(self) -> list[ScenarioTemplate]:
        await self.seed_default_templates()
        result = await self.session.execute(
            select(ScenarioTemplateORM)
            .where(ScenarioTemplateORM.status == ScenarioTemplateStatus.ACTIVE.value)
            .order_by(ScenarioTemplateORM.category, ScenarioTemplateORM.name)
        )
        return [_row_to_template(row) for row in result.scalars().all()]

    async def get_template(self, scenario_code: str) -> ScenarioTemplate:
        await self.seed_default_templates()
        result = await self.session.execute(
            select(ScenarioTemplateORM).where(ScenarioTemplateORM.code == scenario_code)
        )
        row = result.scalar_one_or_none()
        if row is None or row.status != ScenarioTemplateStatus.ACTIVE.value:
            raise ValueError("场景模板不存在或已停用")
        return _row_to_template(row)

    async def create_project(
        self,
        *,
        workspace_id: str,
        user_id: str,
        scenario_code: str,
        title: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> ContentProject:
        await self.get_template(scenario_code)
        row = ContentProjectORM(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            scenario_code=scenario_code,
            title=title,
            description=description,
            status=ContentProjectStatus.ACTIVE.value,
            config=config or {},
            created_by=user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _row_to_project(row)

    async def list_projects(
        self,
        *,
        workspace_id: str,
        scenario_code: str | None = None,
        status: ContentProjectStatus | None = None,
    ) -> list[ContentProject]:
        filters = [ContentProjectORM.workspace_id == workspace_id]
        if scenario_code:
            filters.append(ContentProjectORM.scenario_code == scenario_code)
        if status:
            filters.append(ContentProjectORM.status == status.value)
        result = await self.session.execute(
            select(ContentProjectORM)
            .where(and_(*filters))
            .order_by(ContentProjectORM.updated_at.desc())
        )
        return [_row_to_project(row) for row in result.scalars().all()]

    async def get_project(self, *, project_id: str, workspace_id: str) -> ContentProjectORM:
        result = await self.session.execute(
            select(ContentProjectORM).where(
                ContentProjectORM.id == project_id,
                ContentProjectORM.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("内容项目不存在")
        return row

    async def get_project_model(self, *, project_id: str, workspace_id: str) -> ContentProject:
        return _row_to_project(
            await self.get_project(project_id=project_id, workspace_id=workspace_id)
        )

    async def update_project(
        self,
        *,
        project_id: str,
        workspace_id: str,
        title: str | None = None,
        description: str | None = None,
        status: ContentProjectStatus | None = None,
        config: dict[str, Any] | None = None,
    ) -> ContentProject:
        row = await self.get_project(project_id=project_id, workspace_id=workspace_id)
        if title is not None:
            row.title = title
        if description is not None:
            row.description = description
        if status is not None:
            row.status = status.value
        if config is not None:
            row.config = config
        row.updated_at = utc_now_naive()
        await self.session.commit()
        await self.session.refresh(row)
        return _row_to_project(row)

    async def get_asset_row(self, *, asset_id: str, workspace_id: str) -> ProjectAssetORM:
        result = await self.session.execute(
            select(ProjectAssetORM)
            .join(ContentProjectORM, ProjectAssetORM.project_id == ContentProjectORM.id)
            .where(ProjectAssetORM.id == asset_id, ContentProjectORM.workspace_id == workspace_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("项目资产不存在")
        return row

    async def get_asset(self, *, asset_id: str, workspace_id: str) -> ProjectAsset:
        return _row_to_asset(await self.get_asset_row(asset_id=asset_id, workspace_id=workspace_id))

    async def list_assets(
        self,
        *,
        project_id: str,
        workspace_id: str,
        asset_type: str | None = None,
        lifecycle_status: ProjectAssetLifecycleStatus | None = None,
    ) -> list[ProjectAsset]:
        await self.get_project(project_id=project_id, workspace_id=workspace_id)
        filters = [ProjectAssetORM.project_id == project_id]
        if asset_type:
            filters.append(ProjectAssetORM.asset_type == asset_type)
        if lifecycle_status:
            filters.append(ProjectAssetORM.lifecycle_status == lifecycle_status.value)
        result = await self.session.execute(
            select(ProjectAssetORM)
            .where(and_(*filters))
            .order_by(ProjectAssetORM.asset_type, ProjectAssetORM.updated_at.desc())
        )
        return [_row_to_asset(row) for row in result.scalars().all()]

    async def create_asset(
        self,
        *,
        project_id: str,
        workspace_id: str,
        user_id: str,
        asset_type: str,
        title: str,
        content: Any,
        source_artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        lifecycle_status: ProjectAssetLifecycleStatus = ProjectAssetLifecycleStatus.CANON,
    ) -> ProjectAsset:
        project = await self.get_project(project_id=project_id, workspace_id=workspace_id)
        await self._validate_asset_type(project.scenario_code, asset_type)
        row = ProjectAssetORM(
            id=str(uuid.uuid4()),
            project_id=project_id,
            asset_type=asset_type,
            title=title,
            content=content,
            version=1,
            source_artifact_id=source_artifact_id,
            metadata_json=metadata or {},
            lifecycle_status=lifecycle_status.value,
            embedding_status=ProjectAssetEmbeddingStatus.SKIPPED.value,
            created_by=user_id,
        )
        self.session.add(row)
        await self.session.flush()
        self._add_asset_version(row, user_id=user_id)
        await self.session.commit()
        await self.session.refresh(row)
        return _row_to_asset(row)

    async def validate_project_run_context(
        self,
        *,
        project_id: str,
        workspace_id: str,
        scenario_code: str | None = None,
        generation_mode: str | None = None,
        target_asset_id: str | None = None,
    ) -> ContentProject:
        """校验项目运行上下文，避免跨场景、跨项目或无效模式进入运行态。"""
        project = await self.get_project(project_id=project_id, workspace_id=workspace_id)
        if scenario_code and scenario_code != project.scenario_code:
            raise ValueError("场景与内容项目不匹配")

        template = await self.get_template(project.scenario_code)
        if generation_mode:
            allowed_modes = _template_generation_modes(template)
            if allowed_modes and generation_mode not in allowed_modes:
                raise ValueError("生成模式不属于当前场景模板")

        if target_asset_id:
            asset = await self.get_asset_row(asset_id=target_asset_id, workspace_id=workspace_id)
            if asset.project_id != project.id:
                raise ValueError("目标资产不属于当前内容项目")

        return _row_to_project(project)

    async def update_asset(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        user_id: str,
        title: str | None = None,
        content: Any | None = None,
        source_artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        lifecycle_status: ProjectAssetLifecycleStatus | None = None,
        embedding_status: ProjectAssetEmbeddingStatus | None = None,
    ) -> ProjectAsset:
        row = await self.get_asset_row(asset_id=asset_id, workspace_id=workspace_id)
        if title is not None:
            row.title = title
        if content is not None:
            row.content = content
            row.version += 1
        if source_artifact_id is not None:
            row.source_artifact_id = source_artifact_id
        if metadata is not None:
            row.metadata_json = metadata
        if lifecycle_status is not None:
            row.lifecycle_status = lifecycle_status.value
        if embedding_status is not None:
            row.embedding_status = embedding_status.value
        row.updated_at = utc_now_naive()
        if content is not None:
            self._add_asset_version(row, user_id=user_id)
        await self.session.commit()
        await self.session.refresh(row)
        return _row_to_asset(row)

    async def list_asset_versions(
        self,
        *,
        asset_id: str,
        workspace_id: str,
    ) -> list[ProjectAssetVersion]:
        await self.get_asset_row(asset_id=asset_id, workspace_id=workspace_id)
        result = await self.session.execute(
            select(ProjectAssetVersionORM)
            .where(ProjectAssetVersionORM.asset_id == asset_id)
            .order_by(ProjectAssetVersionORM.version.desc())
        )
        return [_row_to_asset_version(row) for row in result.scalars().all()]

    async def restore_asset_version(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        user_id: str,
        version: int,
    ) -> ProjectAsset:
        asset = await self.get_asset_row(asset_id=asset_id, workspace_id=workspace_id)
        result = await self.session.execute(
            select(ProjectAssetVersionORM).where(
                ProjectAssetVersionORM.asset_id == asset_id,
                ProjectAssetVersionORM.version == version,
            )
        )
        version_row = result.scalar_one_or_none()
        if version_row is None:
            raise ValueError("资产版本不存在")
        restored_lifecycle_status = (version_row.metadata_json or {}).get("lifecycle_status")
        asset.content = version_row.content
        asset.source_artifact_id = version_row.source_artifact_id
        asset.metadata_json = {
            **(version_row.metadata_json or {}),
            "restored_from_version": version,
            "restored_from_lifecycle_status": restored_lifecycle_status
            or ProjectAssetLifecycleStatus.CANON.value,
            "restored_at": utc_now_naive().isoformat(),
        }
        asset.lifecycle_status = (
            restored_lifecycle_status or ProjectAssetLifecycleStatus.CANON.value
        )
        asset.version += 1
        asset.updated_at = utc_now_naive()
        self._add_asset_version(asset, user_id=user_id)
        await self.session.commit()
        await self.session.refresh(asset)
        return _row_to_asset(asset)

    async def load_structured_memory(
        self,
        *,
        project_id: str,
        workspace_id: str,
        asset_types: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        assets = await self.list_assets(
            project_id=project_id,
            workspace_id=workspace_id,
        )
        allowed = set(asset_types or [])
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for asset in assets:
            if allowed and asset.asset_type not in allowed:
                continue
            grouped[asset.asset_type].append(asset.model_dump(mode="json"))
        return dict(grouped)

    async def ensure_project_knowledge_base(
        self,
        *,
        project: ContentProjectORM,
        user_id: str,
        role: Any,
    ):
        config = dict(project.config or {})
        kb_id = config.get("knowledge_base_id")
        knowledge_service = KnowledgeService(self.session)
        if isinstance(kb_id, str) and kb_id:
            try:
                row = await knowledge_service.get_knowledge_base(
                    kb_id=kb_id,
                    workspace_id=project.workspace_id,
                    user_id=user_id,
                )
                return _row_to_knowledge_base(row)
            except ValueError:
                config.pop("knowledge_base_id", None)

        if not check_permission(_normalize_role_value(role), "knowledge_base", "create"):
            raise ValueError("没有创建项目记忆知识库的权限")
        kb = await knowledge_service.create_knowledge_base(
            workspace_id=project.workspace_id,
            user_id=user_id,
            role=role,
            name=f"项目记忆：{project.title}",
            description="由 Project Asset 同步生成的项目级检索记忆。",
            scope=KnowledgeScope.WORKSPACE,
        )
        config["knowledge_base_id"] = kb.id
        project.config = config
        project.updated_at = utc_now_naive()
        await self.session.commit()
        return kb

    async def sync_asset_to_knowledge(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        user_id: str,
        role: Any,
    ) -> ProjectAsset:
        asset = await self.get_asset_row(asset_id=asset_id, workspace_id=workspace_id)
        project = await self.get_project(project_id=asset.project_id, workspace_id=workspace_id)
        asset.embedding_status = ProjectAssetEmbeddingStatus.PROCESSING.value
        await self.session.commit()

        try:
            kb = await self.ensure_project_knowledge_base(
                project=project,
                user_id=user_id,
                role=role,
            )
            metadata = {
                **(asset.metadata_json or {}),
                "source": "project_asset",
                "project_id": project.id,
                "scenario_code": project.scenario_code,
                "asset_id": asset.id,
                "asset_type": asset.asset_type,
                "asset_version": asset.version,
            }
            await KnowledgeService(self.session).add_document(
                kb_id=kb.id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                file_name=f"{asset.asset_type}-{asset.version}.md",
                content=_serialize_asset_content(asset.content),
                metadata=metadata,
                index_immediately=True,
            )
            asset.embedding_status = ProjectAssetEmbeddingStatus.READY.value
        except Exception:
            asset.embedding_status = ProjectAssetEmbeddingStatus.FAILED.value
            await self.session.commit()
            raise

        asset.updated_at = utc_now_naive()
        await self.session.commit()
        await self.session.refresh(asset)
        return _row_to_asset(asset)

    def _add_asset_version(self, row: ProjectAssetORM, *, user_id: str) -> None:
        self.session.add(
            ProjectAssetVersionORM(
                id=str(uuid.uuid4()),
                asset_id=row.id,
                version=row.version,
                content=row.content,
                source_artifact_id=row.source_artifact_id,
                metadata_json=self._asset_version_metadata(row),
                created_by=user_id,
            )
        )

    def _asset_version_metadata(self, row: ProjectAssetORM) -> dict[str, Any]:
        """记录版本快照对应的资产生命周期，便于恢复时还原 canon/candidate 语义。"""
        return {
            **(row.metadata_json or {}),
            "lifecycle_status": row.lifecycle_status or ProjectAssetLifecycleStatus.CANON.value,
        }

    async def _validate_asset_type(self, scenario_code: str, asset_type: str) -> None:
        template = await self.get_template(scenario_code)
        allowed_asset_types = _template_asset_types(template)
        if allowed_asset_types and asset_type not in allowed_asset_types:
            raise ValueError("资产类型不属于当前场景模板")
