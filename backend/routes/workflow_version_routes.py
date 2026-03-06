"""
工作流版本管理 API

提供工作流版本历史、版本对比和版本回滚功能，使用统一Result响应格式
"""
from typing import List, Optional
from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.workflow_orm import WorkflowDefinitionORM, WorkflowVersionORM
from models.result import Result
from routes.auth_routes import get_current_user
from db.postgres_store import get_session

router = APIRouter(prefix="/workflows", tags=["workflow-version"])


# ==================== 响应数据模型 ====================

class VersionInfo(BaseModel):
    """版本信息"""
    id: str
    version: int
    change_log: Optional[str] = ""
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class VersionDiff(BaseModel):
    """版本差异"""
    version_a: int
    version_b: int
    nodes_added: List[str]
    nodes_removed: List[str]
    nodes_modified: List[str]
    edges_added: List[str]
    edges_removed: List[str]


# ==================== 辅助函数 ====================

async def get_workspace_from_request(request: Request, user: dict) -> str:
    """从请求获取工作空间ID"""
    workspace_id = request.state.workspace_id if hasattr(request.state, 'workspace_id') else None
    if not workspace_id:
        workspace_id = user.get("default_workspace_id") or user.get("workspace_id")
    return workspace_id


# ==================== API 路由 ====================

@router.get("/{workflow_id}/versions")
async def list_versions(
    request: Request,
    workflow_id: str,
):
    """
    获取工作流的版本历史
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    if not workspace_id:
        return Result.bad_request(message="未指定工作空间")
    
    session = await get_session()
    
    # 获取当前工作流
    result = await session.execute(
        select(WorkflowDefinitionORM).where(
            WorkflowDefinitionORM.id == workflow_id,
            WorkflowDefinitionORM.workspace_id == workspace_id,
            WorkflowDefinitionORM.is_deleted == 0
        )
    )
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        return Result.not_found(message="工作流不存在")
    
    # 获取版本历史
    versions_result = await session.execute(
        select(WorkflowVersionORM)
        .where(WorkflowVersionORM.workflow_id == workflow_id)
        .order_by(WorkflowVersionORM.version.desc())
    )
    versions = versions_result.scalars().all()
    
    return Result.success(data={
        "workflow_id": workflow_id,
        "current_version": workflow.version,
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "change_log": v.change_log,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat() if v.created_at else None
            }
            for v in versions
        ]
    })


@router.get("/{workflow_id}/versions/{version_id}")
async def get_version(
    request: Request,
    workflow_id: str,
    version_id: str,
):
    """
    获取特定版本的工作流定义
    """
    user = await get_current_user(request)
    
    session = await get_session()
    
    result = await session.execute(
        select(WorkflowVersionORM).where(
            WorkflowVersionORM.id == version_id,
            WorkflowVersionORM.workflow_id == workflow_id
        )
    )
    version = result.scalar_one_or_none()
    
    if not version:
        return Result.not_found(message="版本不存在")
    
    return Result.success(data={
        "id": version.id,
        "workflow_id": version.workflow_id,
        "version": version.version,
        "nodes": version.nodes,
        "edges": version.edges,
        "change_log": version.change_log,
        "created_by": version.created_by,
        "created_at": version.created_at.isoformat() if version.created_at else None
    })


@router.get("/{workflow_id}/versions/compare")
async def compare_versions(
    request: Request,
    workflow_id: str,
    version_a: int,
    version_b: int,
):
    """
    对比两个版本的差异
    """
    user = await get_current_user(request)
    
    session = await get_session()
    
    # 获取两个版本
    result_a = await session.execute(
        select(WorkflowVersionORM).where(
            WorkflowVersionORM.workflow_id == workflow_id,
            WorkflowVersionORM.version == version_a
        )
    )
    version_a_data = result_a.scalar_one_or_none()
    
    result_b = await session.execute(
        select(WorkflowVersionORM).where(
            WorkflowVersionORM.workflow_id == workflow_id,
            WorkflowVersionORM.version == version_b
        )
    )
    version_b_data = result_b.scalar_one_or_none()
    
    # 如果版本B是当前版本，从工作流定义获取
    if not version_b_data:
        workflow_result = await session.execute(
            select(WorkflowDefinitionORM).where(
                WorkflowDefinitionORM.id == workflow_id
            )
        )
        workflow = workflow_result.scalar_one_or_none()
        if workflow and workflow.version == version_b:
            version_b_nodes = workflow.nodes or []
            version_b_edges = workflow.edges or []
        else:
            return Result.not_found(message=f"版本 {version_b} 不存在")
    else:
        version_b_nodes = version_b_data.nodes or []
        version_b_edges = version_b_data.edges or []
    
    if not version_a_data:
        return Result.not_found(message=f"版本 {version_a} 不存在")
    
    version_a_nodes = version_a_data.nodes or []
    version_a_edges = version_a_data.edges or []
    
    # 计算节点差异
    nodes_a_ids = {n.get('id') for n in version_a_nodes}
    nodes_b_ids = {n.get('id') for n in version_b_nodes}
    
    nodes_added = list(nodes_b_ids - nodes_a_ids)
    nodes_removed = list(nodes_a_ids - nodes_b_ids)
    
    # 检查修改的节点
    nodes_modified = []
    common_nodes = nodes_a_ids & nodes_b_ids
    nodes_a_map = {n.get('id'): n for n in version_a_nodes}
    nodes_b_map = {n.get('id'): n for n in version_b_nodes}
    
    for node_id in common_nodes:
        if nodes_a_map.get(node_id) != nodes_b_map.get(node_id):
            nodes_modified.append(node_id)
    
    # 计算边差异
    edges_a_ids = {e.get('id') for e in version_a_edges}
    edges_b_ids = {e.get('id') for e in version_b_edges}
    
    edges_added = list(edges_b_ids - edges_a_ids)
    edges_removed = list(edges_a_ids - edges_b_ids)
    
    return Result.success(data={
        "version_a": version_a,
        "version_b": version_b,
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_modified": nodes_modified,
        "edges_added": edges_added,
        "edges_removed": edges_removed
    })


@router.post("/{workflow_id}/versions/{version_id}/restore")
async def restore_version(
    request: Request,
    workflow_id: str,
    version_id: str,
):
    """
    回滚到指定版本
    
    创建新版本，内容为指定历史版本的内容
    """
    user = await get_current_user(request)
    workspace_id = await get_workspace_from_request(request, user)
    
    session = await get_session()
    
    # 获取要恢复的版本
    version_result = await session.execute(
        select(WorkflowVersionORM).where(
            WorkflowVersionORM.id == version_id,
            WorkflowVersionORM.workflow_id == workflow_id
        )
    )
    version = version_result.scalar_one_or_none()
    
    if not version:
        return Result.not_found(message="版本不存在")
    
    # 获取当前工作流
    workflow_result = await session.execute(
        select(WorkflowDefinitionORM).where(
            WorkflowDefinitionORM.id == workflow_id,
            WorkflowDefinitionORM.workspace_id == workspace_id,
            WorkflowDefinitionORM.is_deleted == 0
        )
    )
    workflow = workflow_result.scalar_one_or_none()
    
    if not workflow:
        return Result.not_found(message="工作流不存在")
    
    # 保存当前版本到历史
    current_version = WorkflowVersionORM(
        id=str(uuid.uuid4()),
        workflow_id=workflow.id,
        version=workflow.version,
        nodes=workflow.nodes,
        edges=workflow.edges,
        change_log=f"回滚前的版本 (v{workflow.version})",
        created_by=user.get("sub") or user.get("id"),
    )
    session.add(current_version)
    
    # 恢复到历史版本
    workflow.nodes = version.nodes
    workflow.edges = version.edges
    workflow.version += 1
    workflow.updated_at = datetime.utcnow()
    
    await session.commit()
    
    return Result.success(
        data={
            "workflow_id": workflow_id,
            "new_version": workflow.version,
            "restored_from_version": version.version
        },
        message=f"已回滚到版本 {version.version}"
    )
