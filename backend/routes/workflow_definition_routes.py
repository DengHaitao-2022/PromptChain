"""
工作流定义 API 路由

提供工作流定义的 CRUD 接口，并补齐 RBAC 边界。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.postgres_store import get_session
from models.auth_models import MemberRole
from models.result import Result
from models.workflow_definition import WorkflowDefinitionCreate, WorkflowDefinitionUpdate
from routes.auth_routes import get_current_user
from services.permission_service import PermissionService
from services.workflow_definition_service import WorkflowDefinitionService

router = APIRouter(prefix="/workflows", tags=["workflow-definition"])


async def get_workflow_service(session: AsyncSession = Depends(get_session)) -> WorkflowDefinitionService:
    """获取工作流定义服务实例。"""
    return WorkflowDefinitionService(session)


async def get_workspace_from_request(request: Request, user: dict) -> str:
    """从请求与登录态中解析当前工作空间。"""
    workspace_id = getattr(request.state, "workspace_id", None) or user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="未指定工作空间")
    return workspace_id


async def require_workspace_permission(
    session: AsyncSession,
    user_id: str,
    workspace_id: str,
    resource: str,
    action: str,
) -> MemberRole:
    """校验用户在当前工作空间的资源权限。"""
    permission_service = PermissionService(session)
    return await permission_service.require_permission(user_id, workspace_id, resource, action)


async def require_workflow_write_access(
    session: AsyncSession,
    service: WorkflowDefinitionService,
    user_id: str,
    workspace_id: str,
    workflow_id: str,
    action: str,
):
    """编辑者只能维护自己创建的工作流，管理员和拥有者可跨作者维护。"""
    role = await require_workspace_permission(session, user_id, workspace_id, "workflow", action)
    workflow = await service.get_by_id(workflow_id, workspace_id)

    if not workflow:
        return role, None

    if role == MemberRole.EDITOR and workflow.created_by != user_id:
        raise HTTPException(status_code=403, detail="编辑者只能维护自己创建的工作流")

    return role, workflow


@router.get("")
async def list_workflows(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """获取当前工作空间的工作流列表。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    await require_workspace_permission(session, user_id, workspace_id, "workflow", "read")

    workflows = await service.list_by_workspace(workspace_id, limit, offset)
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
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """创建新的工作流定义。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    await require_workspace_permission(session, user_id, workspace_id, "workflow", "create")

    workflow = await service.create(workspace_id=workspace_id, user_id=user_id, data=data)
    return Result.success(data=workflow.model_dump(), message="工作流已创建")


@router.get("/{workflow_id}")
async def get_workflow(
    request: Request,
    workflow_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """获取工作流定义详情。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    await require_workspace_permission(session, user_id, workspace_id, "workflow", "read")

    workflow = await service.get_by_id(workflow_id, workspace_id)
    if not workflow:
        return Result.not_found(message="工作流不存在")

    return Result.success(data=workflow.model_dump())


@router.get("/{workflow_id}/definition")
async def get_workflow_definition(
    request: Request,
    workflow_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """获取工作流定义（用于编辑器加载）。"""
    return await get_workflow(request, workflow_id, user, session, service)


@router.put("/{workflow_id}")
async def update_workflow(
    request: Request,
    workflow_id: str,
    data: WorkflowDefinitionUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """更新工作流定义。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    _, workflow = await require_workflow_write_access(session, service, user_id, workspace_id, workflow_id, "update")

    if not workflow:
        return Result.not_found(message="工作流不存在")

    updated = await service.update(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        user_id=user_id,
        data=data,
    )
    return Result.success(data=updated.model_dump(), message="工作流已更新")


@router.put("/{workflow_id}/definition")
async def update_workflow_definition(
    request: Request,
    workflow_id: str,
    data: WorkflowDefinitionUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """更新工作流定义（用于编辑器保存）。"""
    return await update_workflow(request, workflow_id, data, user, session, service)


@router.delete("/{workflow_id}")
async def delete_workflow(
    request: Request,
    workflow_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """删除工作流定义（软删除）。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    role, workflow = await require_workflow_write_access(session, service, user_id, workspace_id, workflow_id, "delete")

    if not workflow:
        return Result.not_found(message="工作流不存在")

    if role == MemberRole.EDITOR and workflow.created_by != user_id:
        raise HTTPException(status_code=403, detail="编辑者只能删除自己创建的工作流")

    success = await service.delete(workflow_id, workspace_id)
    if not success:
        return Result.not_found(message="工作流不存在")

    return Result.success(message="工作流已删除")


@router.post("/{workflow_id}/validate")
async def validate_workflow(
    request: Request,
    workflow_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """验证工作流定义的合法性。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    _, workflow = await require_workflow_write_access(session, service, user_id, workspace_id, workflow_id, "update")

    if not workflow:
        return Result.not_found(message="工作流不存在")

    result = service.validate(workflow)
    return Result.success(data=result.model_dump())


@router.post("/{workflow_id}/compile")
async def compile_workflow(
    request: Request,
    workflow_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowDefinitionService = Depends(get_workflow_service),
):
    """编译工作流为 LangGraph 可执行图。"""
    user_id = user.get("sub") or user.get("id")
    workspace_id = await get_workspace_from_request(request, user)
    _, workflow = await require_workflow_write_access(session, service, user_id, workspace_id, workflow_id, "update")

    if not workflow:
        return Result.not_found(message="工作流不存在")

    result = service.compile(workflow)
    return Result.success(data=result.model_dump())
