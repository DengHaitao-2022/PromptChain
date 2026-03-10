"""
工作流定义 API 路由

提供工作流定义的CRUD接口，使用统一Result响应格式
"""
from typing import Optional, List, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from models.workflow_definition import (
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowValidationResult,
    WorkflowCompileResult,
)
from models.result import Result, PageResult
from services.workflow_definition_service import WorkflowDefinitionService
from routes.auth_routes import get_current_user
from db.postgres_store import get_session

router = APIRouter(prefix="/workflows", tags=["workflow-definition"])


# ==================== 辅助函数 ====================

async def get_workflow_service(request: Request) -> WorkflowDefinitionService:
    """获取工作流定义服务实例"""
    session = await get_session()
    return WorkflowDefinitionService(session)


async def get_workspace_from_request(request: Request, user: dict) -> str:
    """从请求获取工作空间ID"""
    workspace_id = request.state.workspace_id if hasattr(request.state, 'workspace_id') else None
    if not workspace_id:
        workspace_id = user.get("default_workspace_id") or user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="未指定工作空间")
    return workspace_id


# ==================== API 路由 ====================

@router.get("")
async def list_workflows(
    request: Request,
    limit: int = 50,
    offset: int = 0,
):
    """
    获取当前工作空间的工作流列表
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    workflows = await service.list_by_workspace(workspace_id, limit, offset)
    
    return Result.success(data={
        "workflows": [w.model_dump() for w in workflows],
        "total": len(workflows)
    })


@router.post("")
async def create_workflow(
    request: Request,
    data: WorkflowDefinitionCreate,
):
    """
    创建新的工作流定义
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    workflow = await service.create(
        workspace_id=workspace_id,
        user_id=user.get("sub") or user.get("id"),
        data=data
    )
    
    return Result.success(data=workflow.model_dump(), message="工作流已创建")


@router.get("/{workflow_id}")
async def get_workflow(
    request: Request,
    workflow_id: str,
):
    """
    获取工作流定义详情
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    workflow = await service.get_by_id(workflow_id, workspace_id)
    
    if not workflow:
        return Result.not_found(message="工作流不存在")
    
    return Result.success(data=workflow.model_dump())


@router.get("/{workflow_id}/definition")
async def get_workflow_definition(
    request: Request,
    workflow_id: str,
):
    """
    获取工作流定义（用于编辑器加载）
    
    与 GET /{workflow_id} 相同，提供语义化URL
    """
    return await get_workflow(request, workflow_id)


@router.put("/{workflow_id}")
async def update_workflow(
    request: Request,
    workflow_id: str,
    data: WorkflowDefinitionUpdate,
):
    """
    更新工作流定义
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    workflow = await service.update(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        user_id=user.get("sub") or user.get("id"),
        data=data
    )
    
    if not workflow:
        return Result.not_found(message="工作流不存在")
    
    return Result.success(data=workflow.model_dump(), message="工作流已更新")


@router.put("/{workflow_id}/definition")
async def update_workflow_definition(
    request: Request,
    workflow_id: str,
    data: WorkflowDefinitionUpdate,
):
    """
    更新工作流定义（用于编辑器保存）
    
    与 PUT /{workflow_id} 相同，提供语义化URL
    """
    return await update_workflow(request, workflow_id, data)


@router.delete("/{workflow_id}")
async def delete_workflow(
    request: Request,
    workflow_id: str,
):
    """
    删除工作流定义（软删除）
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    success = await service.delete(workflow_id, workspace_id)
    
    if not success:
        return Result.not_found(message="工作流不存在")
    
    return Result.success(message="工作流已删除")


@router.post("/{workflow_id}/validate")
async def validate_workflow(
    request: Request,
    workflow_id: str,
):
    """
    验证工作流定义的合法性
    
    检查：
    - 节点是否存在
    - 是否有输入/输出节点
    - 边的连接是否有效
    - 是否有孤立节点
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    workflow = await service.get_by_id(workflow_id, workspace_id)
    
    if not workflow:
        return Result.not_found(message="工作流不存在")
    
    result = service.validate(workflow)
    return Result.success(data=result.model_dump())


@router.post("/{workflow_id}/compile")
async def compile_workflow(
    request: Request,
    workflow_id: str,
):
    """
    编译工作流为LangGraph可执行图
    
    返回生成的代码预览
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    service = await get_workflow_service(request)
    workflow = await service.get_by_id(workflow_id, workspace_id)
    
    if not workflow:
        return Result.not_found(message="工作流不存在")
    
    result = service.compile(workflow)
    return Result.success(data=result.model_dump())
