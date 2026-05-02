"""
工作流版本管理 API

提供版本历史、版本对比和版本恢复接口。
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from db.postgres_store import get_postgres_store
from models.admin_models import AuditAction
from models.auth_models import MemberRole
from models.result import Result
from routes.auth_routes import get_current_user
from services.audit_log_service import AuditLogService
from services.permission_service import PermissionService
from services.workflow_definition_service import WorkflowDefinitionService

router = APIRouter(prefix="/workflows", tags=["workflow-version"])


class RestoreVersionRequest(BaseModel):
    """恢复版本请求。"""

    change_log: str = Field(default="", max_length=500)


def _get_user_id(user: dict[str, Any]) -> str:
    user_id = user.get("sub") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未识别用户身份")
    return user_id


async def _get_workspace_from_request(request: Request, user: dict[str, Any]) -> str:
    workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else None
    if not workspace_id:
        workspace_id = user.get("default_workspace_id") or user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="未指定工作空间")
    return workspace_id


async def _require_workflow_role(
    request: Request,
    session,
) -> tuple[str, str, MemberRole]:
    return await _require_permission(request, session, action="update")


async def _require_workflow_read(
    request: Request,
    session,
) -> tuple[str, str, MemberRole]:
    return await _require_permission(request, session, action="read")


async def _require_permission(
    request: Request,
    session,
    *,
    action: str,
) -> tuple[str, str, MemberRole]:
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
    return user_id, workspace_id, role


@router.get("/{workflow_id}/versions")
async def list_versions(
    request: Request,
    workflow_id: str,
):
    """获取工作流的版本历史。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, workspace_id, role = await _require_workflow_read(request, session)
        service = WorkflowDefinitionService(session)
        workflow, versions = await service.get_version_history(workflow_id, workspace_id)
        if workflow is None:
            return Result.not_found(message="工作流不存在")

        current_version = workflow.version
        visible_versions = versions
        if role == MemberRole.VIEWER:
            if not workflow.is_published:
                return Result.not_found(message="工作流不存在")

            published_snapshot = await service._get_published_snapshot(workflow)
            if published_snapshot is None:
                return Result.not_found(message="工作流不存在")

            current_version = published_snapshot.version
            visible_versions = [published_snapshot]

        return Result.success(
            data={
                "workflow_id": workflow_id,
                "current_version": current_version,
                "is_published": bool(workflow.is_published),
                "published_version_id": workflow.published_version_id,
                "published_at": workflow.published_at.isoformat()
                if workflow.published_at
                else None,
                "versions": [
                    service.version_to_dict(
                        version,
                        published_version_id=workflow.published_version_id,
                    )
                    for version in visible_versions
                ],
            }
        )


@router.get("/public/{workflow_id}/versions")
async def list_public_versions(
    workflow_id: str,
):
    """获取首页匿名可见工作流的已发布版本。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        service = WorkflowDefinitionService(session)
        workflow, published_snapshot = await service.get_public_published_version(workflow_id)
        if workflow is None or published_snapshot is None:
            return Result.not_found(message="工作流不存在")

        return Result.success(
            data={
                "workflow_id": workflow_id,
                "current_version": published_snapshot.version,
                "is_published": True,
                "published_version_id": workflow.published_version_id,
                "published_at": workflow.published_at.isoformat()
                if workflow.published_at
                else None,
                "versions": [
                    service.version_to_dict(
                        published_snapshot,
                        published_version_id=workflow.published_version_id,
                    )
                ],
            }
        )


@router.get("/{workflow_id}/versions/compare")
async def compare_versions(
    request: Request,
    workflow_id: str,
    version_a: int,
    version_b: int,
):
    """对比两个版本的差异。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, workspace_id, _ = await _require_workflow_role(request, session)
        service = WorkflowDefinitionService(session)
        workflow = await service.get_by_id(workflow_id=workflow_id, workspace_id=workspace_id)
        if workflow is None:
            return Result.not_found(message="工作流不存在")

        diff = await service.compare_versions(workflow_id, workspace_id, version_a, version_b)
        if diff is None:
            return Result.not_found(message="待比较的版本不存在")

        return Result.success(data=diff)


@router.get("/{workflow_id}/versions/{version_id}")
async def get_version(
    request: Request,
    workflow_id: str,
    version_id: str,
):
    """获取特定版本的工作流快照。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        _, workspace_id, _ = await _require_workflow_role(request, session)
        service = WorkflowDefinitionService(session)
        workflow, version = await service.get_version_by_id(workflow_id, workspace_id, version_id)
        if workflow is None:
            return Result.not_found(message="工作流不存在")
        if version is None:
            return Result.not_found(message="版本不存在")

        return Result.success(
            data=service.version_to_dict(
                version,
                published_version_id=workflow.published_version_id,
            )
        )


@router.post("/{workflow_id}/versions/{version_id}/restore")
async def restore_version(
    request: Request,
    workflow_id: str,
    version_id: str,
    body: RestoreVersionRequest,
):
    """恢复指定版本到新的草稿。"""
    store = get_postgres_store()
    async with store.async_session() as session:
        user_id, workspace_id, _ = await _require_workflow_role(request, session)
        service = WorkflowDefinitionService(session)
        workflow, version = await service.restore(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            user_id=user_id,
            version_id=version_id,
            change_log=body.change_log,
        )
        if workflow is None or version is None:
            return Result.not_found(message="工作流或版本不存在")

        await AuditLogService(session).record(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditAction.WORKFLOW_RESTORE,
            request=request,
            target_type="workflow",
            target_id=workflow_id,
            detail={
                "restored_from_version_id": version.id,
                "restored_from_version": version.version,
                "change_log": body.change_log,
            },
            target_snapshot=workflow.model_dump(),
        )
        await session.commit()
        return Result.success(
            data={
                "workflow": workflow.model_dump(),
                "restored_from_version_id": version.id,
                "restored_from_version": version.version,
                "restore_source_snapshot_type": version.snapshot_type,
            },
            message=f"已恢复版本 v{version.version} 到新草稿",
        )
