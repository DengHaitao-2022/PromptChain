"""MVP3 多场景内容工作台 API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import routes.workflow_helpers as workflow_helpers
from db.postgres_store import get_postgres_store
from models.auth_models import MemberRole
from models.knowledge import RetrievalConfig
from models.scenario import (
    ContentProject,
    ContentProjectStatus,
    ProjectAsset,
    ProjectAssetEmbeddingStatus,
    ProjectAssetVersion,
    ScenarioTemplate,
)
from routes.workflow_helpers import WorkflowResponse, _build_workflow_response
from services.permission_service import check_permission, is_admin_role
from services.scenario_service import ScenarioService

router = APIRouter(tags=["scenario"])


class ScenarioTemplateListResponse(BaseModel):
    """场景模板列表响应。"""

    scenarios: list[ScenarioTemplate]


class ContentProjectListResponse(BaseModel):
    """内容项目列表响应。"""

    projects: list[ContentProject]


class ProjectAssetListResponse(BaseModel):
    """项目资产列表响应。"""

    assets: list[ProjectAsset]


class ProjectAssetVersionListResponse(BaseModel):
    """项目资产版本列表响应。"""

    versions: list[ProjectAssetVersion]


class CreateContentProjectRequest(BaseModel):
    """创建内容项目请求。"""

    scenario_code: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateContentProjectRequest(BaseModel):
    """更新内容项目请求。"""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: ContentProjectStatus | None = None
    config: dict[str, Any] | None = None


class CreateProjectAssetRequest(BaseModel):
    """创建项目资产请求。"""

    asset_type: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=200)
    content: Any
    source_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateProjectAssetRequest(BaseModel):
    """更新项目资产请求。"""

    title: str | None = Field(None, min_length=1, max_length=200)
    content: Any | None = None
    source_artifact_id: str | None = None
    metadata: dict[str, Any] | None = None
    embedding_status: ProjectAssetEmbeddingStatus | None = None


class RestoreProjectAssetRequest(BaseModel):
    """恢复项目资产历史版本请求。"""

    version: int = Field(..., ge=1)


class CreateProjectRunRequest(BaseModel):
    """从项目工作台启动运行请求。"""

    user_input: str = Field(..., min_length=1)
    edit_mode: str | None = None
    generation_mode: str | None = None
    target_asset_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_version_id: str | None = None
    model_provider_id: str | None = None
    model_name: str | None = None
    retrieval_config: RetrievalConfig | None = None


class ApplyMemoryUpdatesRequest(BaseModel):
    """应用项目记忆更新候选请求。"""

    workflow_run_id: str
    candidate_indexes: list[int] | None = None
    sync_to_knowledge: bool = False


class ApplyMemoryUpdatesResponse(BaseModel):
    """应用项目记忆更新候选响应。"""

    assets: list[ProjectAsset]


def _normalize_service_error(exc: ValueError, *, not_found: bool = False) -> HTTPException:
    message = str(exc)
    if "无权" in message or "没有" in message:
        return HTTPException(status_code=403, detail=message)
    # 只有明确的资源缺失才归一化为 404；场景不匹配、资产类型非法等校验错误应保留为 400。
    if "不存在" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


def _role_value(role: object) -> str:
    return str(getattr(role, "value", role))


def _member_role(role: object) -> MemberRole:
    return role if isinstance(role, MemberRole) else MemberRole(_role_value(role))


def _build_project_run_list_response(workflow_runs: list[Any]) -> dict[str, list[dict[str, Any]]]:
    response = workflow_helpers._build_workflow_run_list_response(workflow_runs)
    items: list[dict[str, Any]] = []
    for item, workflow_run in zip(response.runs, workflow_runs, strict=False):
        payload = item.model_dump(mode="json")
        metadata = workflow_helpers._ensure_workflow_metadata(workflow_run)
        payload["metadata"] = {
            key: metadata.get(key)
            for key in (
                "scenario_code",
                "project_id",
                "generation_mode",
                "edit_mode",
                "target_asset_id",
                "scenario_check_report",
                "project_memory_update_candidates",
            )
            if key in metadata
        }
        items.append(payload)
    return {"runs": items}


async def _project_context(request: Request, action: str = "read") -> tuple[str, str, object]:
    return await workflow_helpers.require_workspace_permission(
        request,
        "content_project",
        action,
    )


@router.get("/scenarios", response_model=ScenarioTemplateListResponse)
async def list_scenarios(request: Request) -> ScenarioTemplateListResponse:
    """列出内置商业化场景模板。"""
    await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        scenarios = await ScenarioService(session).list_templates()
        return ScenarioTemplateListResponse(scenarios=scenarios)


@router.get("/scenarios/{scenario_code}", response_model=ScenarioTemplate)
async def get_scenario(scenario_code: str, request: Request) -> ScenarioTemplate:
    """获取单个场景模板详情。"""
    await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).get_template(scenario_code)
        except ValueError as exc:
            raise _normalize_service_error(exc) from exc


@router.post("/content-projects", response_model=ContentProject)
async def create_content_project(
    request: Request,
    body: CreateContentProjectRequest,
) -> ContentProject:
    """创建内容项目并绑定场景。"""
    user_id, workspace_id, _ = await _project_context(request, action="create")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).create_project(
                workspace_id=workspace_id,
                user_id=user_id,
                scenario_code=body.scenario_code,
                title=body.title,
                description=body.description,
                config=body.config,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc) from exc


@router.get("/content-projects", response_model=ContentProjectListResponse)
async def list_content_projects(
    request: Request,
    scenario_code: str | None = None,
    status: ContentProjectStatus | None = None,
) -> ContentProjectListResponse:
    """列出当前工作空间的内容项目。"""
    _, workspace_id, _ = await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        projects = await ScenarioService(session).list_projects(
            workspace_id=workspace_id,
            scenario_code=scenario_code,
            status=status,
        )
        return ContentProjectListResponse(projects=projects)


@router.get("/content-projects/{project_id}", response_model=ContentProject)
async def get_content_project(project_id: str, request: Request) -> ContentProject:
    """获取内容项目详情。"""
    _, workspace_id, _ = await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).get_project_model(
                project_id=project_id,
                workspace_id=workspace_id,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.patch("/content-projects/{project_id}", response_model=ContentProject)
async def update_content_project(
    project_id: str,
    request: Request,
    body: UpdateContentProjectRequest,
) -> ContentProject:
    """更新内容项目基础信息。"""
    _, workspace_id, _ = await _project_context(request, action="update")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).update_project(
                project_id=project_id,
                workspace_id=workspace_id,
                title=body.title,
                description=body.description,
                status=body.status,
                config=body.config,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.get("/content-projects/{project_id}/assets", response_model=ProjectAssetListResponse)
async def list_project_assets(
    project_id: str,
    request: Request,
    asset_type: str | None = None,
) -> ProjectAssetListResponse:
    """列出内容项目下的长期资产。"""
    _, workspace_id, _ = await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        try:
            assets = await ScenarioService(session).list_assets(
                project_id=project_id,
                workspace_id=workspace_id,
                asset_type=asset_type,
            )
            return ProjectAssetListResponse(assets=assets)
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post("/content-projects/{project_id}/assets", response_model=ProjectAsset)
async def create_project_asset(
    project_id: str,
    request: Request,
    body: CreateProjectAssetRequest,
) -> ProjectAsset:
    """创建项目资产。"""
    user_id, workspace_id, _ = await _project_context(request, action="update")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).create_asset(
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=user_id,
                asset_type=body.asset_type,
                title=body.title,
                content=body.content,
                source_artifact_id=body.source_artifact_id,
                metadata=body.metadata,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.get("/project-assets/{asset_id}", response_model=ProjectAsset)
async def get_project_asset(asset_id: str, request: Request) -> ProjectAsset:
    """获取项目资产当前版本。"""
    _, workspace_id, _ = await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).get_asset(
                asset_id=asset_id,
                workspace_id=workspace_id,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.patch("/project-assets/{asset_id}", response_model=ProjectAsset)
async def update_project_asset(
    asset_id: str,
    request: Request,
    body: UpdateProjectAssetRequest,
) -> ProjectAsset:
    """更新项目资产，内容变更会生成新版本。"""
    user_id, workspace_id, _ = await _project_context(request, action="update")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).update_asset(
                asset_id=asset_id,
                workspace_id=workspace_id,
                user_id=user_id,
                title=body.title,
                content=body.content,
                source_artifact_id=body.source_artifact_id,
                metadata=body.metadata,
                embedding_status=body.embedding_status,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.get("/project-assets/{asset_id}/versions", response_model=ProjectAssetVersionListResponse)
async def list_project_asset_versions(
    asset_id: str,
    request: Request,
) -> ProjectAssetVersionListResponse:
    """列出项目资产历史版本。"""
    _, workspace_id, _ = await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        try:
            versions = await ScenarioService(session).list_asset_versions(
                asset_id=asset_id,
                workspace_id=workspace_id,
            )
            return ProjectAssetVersionListResponse(versions=versions)
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post("/project-assets/{asset_id}/restore", response_model=ProjectAsset)
async def restore_project_asset(
    asset_id: str,
    request: Request,
    body: RestoreProjectAssetRequest,
) -> ProjectAsset:
    """把项目资产恢复到指定历史版本。"""
    user_id, workspace_id, _ = await _project_context(request, action="update")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).restore_asset_version(
                asset_id=asset_id,
                workspace_id=workspace_id,
                user_id=user_id,
                version=body.version,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post("/project-assets/{asset_id}/sync-knowledge", response_model=ProjectAsset)
async def sync_project_asset_to_knowledge(asset_id: str, request: Request) -> ProjectAsset:
    """把项目资产同步到知识库索引，供项目记忆检索使用。"""
    user_id, workspace_id, role = await _project_context(request, action="update")
    async with get_postgres_store().initialized_session() as session:
        try:
            return await ScenarioService(session).sync_asset_to_knowledge(
                asset_id=asset_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc


@router.post("/content-projects/{project_id}/runs", response_model=WorkflowResponse)
async def start_content_project_run(
    project_id: str,
    request: Request,
    body: CreateProjectRunRequest,
) -> WorkflowResponse:
    """从内容项目工作台启动工作流，并写入项目 metadata。"""
    from graph import get_workflow

    user_id, workspace_id, role = await _project_context(request, action="read")
    if not check_permission(_member_role(role), "workflow", "execute"):
        raise HTTPException(status_code=403, detail="没有执行工作流的权限")

    async with get_postgres_store().initialized_session() as session:
        try:
            service = ScenarioService(session)
            project = await service.validate_project_run_context(
                project_id=project_id,
                workspace_id=workspace_id,
                generation_mode=body.generation_mode,
                target_asset_id=body.target_asset_id,
            )
            template = await service.get_template(project.scenario_code)
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc

    workflow_definition_id = body.workflow_definition_id or template.default_workflow_definition_id
    workflow_version_id = body.workflow_version_id or template.default_workflow_version_id
    workflow = get_workflow()
    result = await workflow.start(
        body.user_input,
        workflow_definition_id=workflow_definition_id,
        workflow_version_id=workflow_version_id,
        workspace_id=workspace_id,
        user_id=user_id,
        model_provider_id=body.model_provider_id,
        model_name=body.model_name,
        retrieval_config=body.retrieval_config,
        scenario_code=project.scenario_code,
        project_id=project.id,
        edit_mode=body.edit_mode,
        generation_mode=body.generation_mode,
        target_asset_id=body.target_asset_id,
    )
    workflow_run = await workflow_helpers._get_workflow_run_if_exists(result["workflow_run_id"])
    status = workflow_helpers._normalize_status(result["status"])
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=status,
        state=result["state"],
        workflow_run=workflow_run,
        viewer_user_id=user_id,
    )


@router.get("/content-projects/{project_id}/runs")
async def list_content_project_runs(project_id: str, request: Request):
    """列出内容项目关联的运行记录。"""
    _, workspace_id, role = await _project_context(request, action="read")
    async with get_postgres_store().initialized_session() as session:
        try:
            await ScenarioService(session).get_project_model(
                project_id=project_id,
                workspace_id=workspace_id,
            )
        except ValueError as exc:
            raise _normalize_service_error(exc, not_found=True) from exc

    from services import get_artifact_store

    store = get_artifact_store()
    user_id, _, _ = await workflow_helpers.require_workspace_permission(
        request,
        "workflow_run",
        "read",
    )
    visible_user_id = None if is_admin_role(role) else user_id
    runs = await store.list_workflow_runs(workspace_id=workspace_id, user_id=visible_user_id)
    filtered_runs = [
        run
        for run in runs
        if isinstance(run.metadata, dict) and run.metadata.get("project_id") == project_id
    ]
    return _build_project_run_list_response(filtered_runs)


@router.post(
    "/content-projects/{project_id}/memory-updates/apply",
    response_model=ApplyMemoryUpdatesResponse,
)
async def apply_project_memory_updates(
    project_id: str,
    request: Request,
    body: ApplyMemoryUpdatesRequest,
) -> ApplyMemoryUpdatesResponse:
    """人工确认后，把工作流生成的记忆候选写回项目资产。"""
    from services import get_artifact_store

    user_id, workspace_id, role = await _project_context(request, action="update")
    workflow_run = await get_artifact_store().get_workflow_run(body.workflow_run_id)
    if workflow_run is None:
        raise HTTPException(status_code=404, detail="工作流运行不存在")
    metadata = workflow_run.metadata if isinstance(workflow_run.metadata, dict) else {}
    if metadata.get("project_id") != project_id or metadata.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=403, detail="工作流运行不属于当前内容项目")

    candidates = metadata.get("project_memory_update_candidates")
    if not isinstance(candidates, list) or not candidates:
        return ApplyMemoryUpdatesResponse(assets=[])

    allowed_indexes = set(body.candidate_indexes) if body.candidate_indexes is not None else None
    created_assets: list[ProjectAsset] = []
    async with get_postgres_store().initialized_session() as session:
        service = ScenarioService(session)
        await service.get_project_model(project_id=project_id, workspace_id=workspace_id)
        for index, candidate in enumerate(candidates):
            if allowed_indexes is not None and index not in allowed_indexes:
                continue
            if not isinstance(candidate, dict):
                continue
            asset = await service.create_asset(
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=user_id,
                asset_type=str(candidate.get("asset_type") or "memory_note"),
                title=str(candidate.get("title") or f"记忆更新 {index + 1}"),
                content=candidate.get("content") or {},
                source_artifact_id=candidate.get("source_artifact_id"),
                metadata={
                    **(
                        candidate.get("metadata")
                        if isinstance(candidate.get("metadata"), dict)
                        else {}
                    ),
                    "workflow_run_id": body.workflow_run_id,
                    "candidate_index": index,
                },
            )
            if body.sync_to_knowledge:
                asset = await service.sync_asset_to_knowledge(
                    asset_id=asset.id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=role,
                )
            created_assets.append(asset)
    return ApplyMemoryUpdatesResponse(assets=created_assets)
