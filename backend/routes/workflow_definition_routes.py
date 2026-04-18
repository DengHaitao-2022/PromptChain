"""
工作流定义 API 路由

提供工作流定义的 CRUD、校验、编译和显式发布接口。
"""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.errors.codes import (
    AUTH_UNAUTHENTICATED,
    WORKFLOW_NOT_FOUND,
    WORKFLOW_VALIDATION_FAILED,
    WORKSPACE_CONTEXT_REQUIRED,
)
from core.errors.exceptions import ApplicationError, DomainError
from db.postgres_store import get_postgres_store
from models.auth_models import MemberRole
from models.result import Result
from models.workflow_definition import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowValidationMode,
)
from routes.auth_routes import get_current_user
from services.permission_service import PermissionService
from services.workflow_definition_service import WorkflowDefinitionService

router = APIRouter(prefix="/workflows", tags=["workflow-definition"])


class PublishWorkflowRequest(BaseModel):
    """发布工作流请求。"""

    change_log: str = Field(default="", max_length=500)


def _get_user_id(user: dict[str, Any]) -> str:
    user_id = user.get("sub") or user.get("id")
    if not user_id:
        raise ApplicationError(code=AUTH_UNAUTHENTICATED, message="未识别用户身份")
    return user_id


async def _get_workspace_from_request(request: Request, user: dict[str, Any]) -> str:
    workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else None
    if not workspace_id:
        workspace_id = user.get("default_workspace_id") or user.get("workspace_id")
    if not workspace_id:
        raise ApplicationError(code=WORKSPACE_CONTEXT_REQUIRED, message="未指定工作空间")
    return workspace_id


def _raise_workflow_not_found() -> None:
    raise DomainError(code=WORKFLOW_NOT_FOUND, message="工作流不存在")


async def _require_workflow_role(
    request: Request,
    session,
    *,
    action: str,
) -> tuple[dict[str, Any], str, str, MemberRole]:
    user = await get_current_user(request)
    workspace_id = await _get_workspace_from_request(request, user)
    user_id = _get_user_id(user)

    permission_service = PermissionService(session)
    role = await permission_service.require_permission(
        user_id=user_id,
        workspace_id=workspace_id,
        resource="workflow",
        action=action,
    )
    return user, user_id, workspace_id, role


@router.get("")
async def list_workflows(
    request: Request,
    limit: int = 50,
    offset: int = 0,
):
    """获取当前工作空间的工作流列表。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, _, workspace_id, role = await _require_workflow_role(request, session, action="read")
        service = WorkflowDefinitionService(session)
        workflows = await service.list_by_workspace(
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
            published_only=role == MemberRole.VIEWER,
            use_published_snapshot=role == MemberRole.VIEWER,
        )

        return Result.success(
            data={
                "workflows": [workflow.model_dump() for workflow in workflows],
                "total": len(workflows),
            }
        )


@router.post("")
async def create_workflow(
    request: Request,
    data: WorkflowDefinitionCreate,
):
    """创建新的工作流定义。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, user_id, workspace_id, _ = await _require_workflow_role(
            request, session, action="create"
        )
        service = WorkflowDefinitionService(session)
        workflow = await service.create(
            workspace_id=workspace_id,
            user_id=user_id,
            data=data,
        )
        return Result.success(data=workflow.model_dump(), message="工作流已创建")


@router.get("/{workflow_id}")
async def get_workflow(
    request: Request,
    workflow_id: str,
):
    """获取工作流定义详情。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, _, workspace_id, role = await _require_workflow_role(request, session, action="read")
        service = WorkflowDefinitionService(session)
        workflow = await service.get_by_id(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            published_only=role == MemberRole.VIEWER,
            use_published_snapshot=role == MemberRole.VIEWER,
        )
        if not workflow:
            _raise_workflow_not_found()

        return Result.success(data=workflow.model_dump())


@router.get("/{workflow_id}/definition")
async def get_workflow_definition(
    request: Request,
    workflow_id: str,
):
    """获取工作流草稿定义，仅设计者及以上角色可访问。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, _, workspace_id, _ = await _require_workflow_role(request, session, action="update")
        service = WorkflowDefinitionService(session)
        workflow = await service.get_by_id(workflow_id=workflow_id, workspace_id=workspace_id)
        if not workflow:
            _raise_workflow_not_found()

        return Result.success(data=workflow.model_dump())


@router.put("/{workflow_id}")
async def update_workflow(
    request: Request,
    workflow_id: str,
    data: WorkflowDefinitionUpdate,
):
    """更新工作流草稿。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, user_id, workspace_id, _ = await _require_workflow_role(
            request, session, action="update"
        )
        service = WorkflowDefinitionService(session)
        workflow = await service.update(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            user_id=user_id,
            data=data,
        )
        if not workflow:
            _raise_workflow_not_found()

        return Result.success(data=workflow.model_dump(), message="工作流草稿已保存")


@router.put("/{workflow_id}/definition")
async def update_workflow_definition(
    request: Request,
    workflow_id: str,
    data: WorkflowDefinitionUpdate,
):
    """更新工作流定义，供编辑器保存使用。"""
    return await update_workflow(request, workflow_id, data)


@router.delete("/{workflow_id}")
async def delete_workflow(
    request: Request,
    workflow_id: str,
):
    """删除工作流定义（软删除）。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, _, workspace_id, _ = await _require_workflow_role(request, session, action="delete")
        service = WorkflowDefinitionService(session)
        success = await service.delete(workflow_id=workflow_id, workspace_id=workspace_id)
        if not success:
            _raise_workflow_not_found()

        return Result.success(message="工作流已删除")


@router.post("/{workflow_id}/validate")
async def validate_workflow(
    request: Request,
    workflow_id: str,
    mode: WorkflowValidationMode = WorkflowValidationMode.SAVE,
):
    """校验工作流草稿或发布可用性。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, _, workspace_id, _ = await _require_workflow_role(request, session, action="update")
        service = WorkflowDefinitionService(session)
        workflow = await service.get_by_id(workflow_id=workflow_id, workspace_id=workspace_id)
        if not workflow:
            _raise_workflow_not_found()

        result = service.validate(workflow, mode=mode)
        return Result.success(data=result.model_dump())


@router.post("/{workflow_id}/publish")
async def publish_workflow(
    request: Request,
    workflow_id: str,
    body: PublishWorkflowRequest,
):
    """显式发布工作流当前草稿。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, user_id, workspace_id, _ = await _require_workflow_role(
            request, session, action="update"
        )
        service = WorkflowDefinitionService(session)
        workflow, validation, snapshot = await service.publish(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            user_id=user_id,
            change_log=body.change_log,
        )

        if workflow is None:
            _raise_workflow_not_found()
        if not validation.is_valid or snapshot is None:
            raise ApplicationError(
                code=WORKFLOW_VALIDATION_FAILED,
                message="工作流未通过发布校验",
                details={"validation": validation.model_dump()},
            )

        return Result.success(
            data={
                "workflow": workflow.model_dump(),
                "validation": validation.model_dump(),
                "published_version_id": snapshot.id,
            },
            message="工作流已发布",
        )


@router.post("/{workflow_id}/compile")
async def compile_workflow(
    request: Request,
    workflow_id: str,
):
    """编译工作流为 LangGraph 可执行图预览。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, _, workspace_id, _ = await _require_workflow_role(request, session, action="update")
        service = WorkflowDefinitionService(session)
        workflow = await service.get_by_id(workflow_id=workflow_id, workspace_id=workspace_id)
        if not workflow:
            _raise_workflow_not_found()

        result = service.compile(workflow)
        return Result.success(data=result.model_dump())
