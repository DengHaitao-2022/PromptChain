"""Tool Factory API 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import routes.workflow_helpers as workflow_helpers
from tools import (
    ToolApprovalMode,
    ToolCallStatus,
    ToolRuntime,
    get_tool_executor,
    get_tool_registry,
)

router = APIRouter(tags=["tools"])


class ExecuteToolRequest(BaseModel):
    """直接执行工具请求，主要供后端调试台和未来 Agent API 复用。"""

    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    workflow_run_id: str | None = None
    node_run_id: str | None = None
    approval_mode: ToolApprovalMode = ToolApprovalMode.POLICY_DEFAULT
    existing_tool_call_id: str | None = None


class ApproveToolCallRequest(BaseModel):
    """直接审批工具调用请求。"""

    action: str = Field(pattern="^(approve|deny)$")
    reason: str | None = None


def _dump_tool_call(call) -> dict[str, Any]:
    return call.model_dump(mode="json") if hasattr(call, "model_dump") else dict(call)


@router.get("/tools")
async def list_tools(
    request: Request,
    category: str | None = None,
    query: str | None = None,
    include_disabled: bool = False,
):
    """列出当前可用工具定义。"""
    await workflow_helpers.require_workspace_permission(request, "workflow", "read")
    registry = get_tool_registry()
    specs = registry.list_specs(
        category=category,
        query=query,
        enabled_only=not include_disabled,
    )
    return {
        "tools": [spec.model_dump(mode="json") for spec in specs],
        "categories": registry.categories(),
    }


@router.get("/tools/{tool_name:path}")
async def get_tool(tool_name: str, request: Request):
    """获取单个工具定义。"""
    await workflow_helpers.require_workspace_permission(request, "workflow", "read")
    try:
        spec = get_tool_registry().get_spec(tool_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "tool": spec.model_dump(mode="json"),
        "mcp_tool": spec.to_mcp_tool(),
    }


@router.post("/tools/execute")
async def execute_tool(request: Request, body: ExecuteToolRequest):
    """受控直接执行工具。"""
    user_id, workspace_id, role = await workflow_helpers.require_workspace_permission(
        request,
        "workflow",
        "execute",
    )
    if body.workflow_run_id:
        await workflow_helpers.require_workflow_run_access(
            request,
            body.workflow_run_id,
            resource="workflow",
            action="execute",
        )
    if body.existing_tool_call_id:
        from services import get_artifact_store

        store = get_artifact_store()
        existing_call = (
            await store.get_tool_call(body.existing_tool_call_id)
            if hasattr(store, "get_tool_call")
            else None
        )
        if existing_call is None:
            raise HTTPException(status_code=404, detail="工具调用记录不存在")
        if existing_call.workflow_run_id:
            await workflow_helpers.require_workflow_run_access(
                request,
                existing_call.workflow_run_id,
                resource="workflow",
                action="execute",
            )
        elif existing_call.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="无权执行该工具调用")
    runtime = ToolRuntime(
        user_id=user_id,
        workspace_id=workspace_id,
        workflow_run_id=body.workflow_run_id,
        node_run_id=body.node_run_id,
        graph_state={},
        node_config={},
        role=role.value if hasattr(role, "value") else str(role),
    )
    result = await get_tool_executor().execute(
        body.tool_name,
        body.input,
        runtime,
        approval_mode=body.approval_mode,
        existing_tool_call_id=body.existing_tool_call_id,
    )
    return result.model_dump(mode="json")


@router.post("/tool-calls/{tool_call_id}/approval")
async def approve_tool_call(tool_call_id: str, request: Request, body: ApproveToolCallRequest):
    """审批直接工具调用；工作流 Gate 恢复应使用 /workflow/{id}/approve-tool-call。"""
    user_id, workspace_id, _ = await workflow_helpers.require_workspace_permission(
        request,
        "workflow",
        "execute",
    )
    from services import get_artifact_store

    store = get_artifact_store()
    existing_call = (
        await store.get_tool_call(tool_call_id) if hasattr(store, "get_tool_call") else None
    )
    if existing_call is None:
        raise HTTPException(status_code=404, detail="工具调用记录不存在")
    if existing_call.status not in {ToolCallStatus.PENDING, ToolCallStatus.FAILED}:
        raise HTTPException(status_code=409, detail="该工具调用状态不允许审批")
    if existing_call.workflow_run_id:
        await workflow_helpers.require_workflow_run_access(
            request,
            existing_call.workflow_run_id,
            resource="workflow",
            action="execute",
        )
    elif existing_call.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="无权审批该工具调用")

    approved = body.action == "approve"
    call = await get_tool_executor().approve_tool_call(
        tool_call_id,
        approved_by=user_id,
        approved=approved,
        reason=body.reason,
    )
    return {"tool_call": _dump_tool_call(call)}


@router.get("/tool-calls")
async def list_tool_calls(
    request: Request,
    workflow_run_id: str = Query(...),
):
    """列出某个工作流运行的工具调用历史。"""
    workflow_run = await workflow_helpers.require_workflow_run_access(
        request,
        workflow_run_id,
    )
    from services import get_artifact_store

    store = get_artifact_store()
    calls = (
        await store.list_tool_calls_by_workflow(workflow_run.id)
        if hasattr(store, "list_tool_calls_by_workflow")
        else []
    )
    return {"tool_calls": [_dump_tool_call(call) for call in calls]}


@router.get("/tool-calls/{tool_call_id}")
async def get_tool_call(tool_call_id: str, request: Request):
    """读取单个工具调用记录。"""
    from services import get_artifact_store

    store = get_artifact_store()
    call = await store.get_tool_call(tool_call_id) if hasattr(store, "get_tool_call") else None
    if call is None:
        raise HTTPException(status_code=404, detail="工具调用记录不存在")
    if call.workflow_run_id:
        await workflow_helpers.require_workflow_run_access(request, call.workflow_run_id)
    else:
        _, workspace_id, _ = await workflow_helpers.require_workspace_permission(
            request,
            "workflow",
            "read",
        )
        if call.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="无权读取该工具调用")
    return {"tool_call": _dump_tool_call(call)}
