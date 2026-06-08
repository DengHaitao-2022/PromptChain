"""Tool Factory API 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import routes.workflow_helpers as workflow_helpers
from db.postgres_store import get_postgres_store
from models.admin_models import AuditAction
from models.auth_models import MemberRole
from services.audit_log_service import AuditLogService
from services.permission_service import is_admin_role
from services.tool_policy_service import ToolPolicyService
from tools import (
    RiskLevel,
    ToolApprovalMode,
    ToolCallStatus,
    ToolRuntime,
    get_tool_executor,
    get_tool_registry,
)
from tools.redaction import redact_sensitive_payload

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


class ToolPolicyRequest(BaseModel):
    """Workspace 工具策略更新请求。"""

    auto_run_enabled: bool = False
    reason: str | None = None


def _dump_tool_call(call) -> dict[str, Any]:
    payload = call.model_dump(mode="json") if hasattr(call, "model_dump") else dict(call)
    if "input_json" in payload:
        payload["input_json"] = redact_sensitive_payload(payload["input_json"])
    if "output_json" in payload:
        payload["output_json"] = redact_sensitive_payload(payload["output_json"])
    if "metadata" in payload:
        payload["metadata"] = redact_sensitive_payload(payload["metadata"])
    return payload


def _dump_tool_policy(policy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "workspace_id": policy.workspace_id,
        "tool_name": policy.tool_name,
        "auto_run_enabled": bool(policy.auto_run_enabled),
        "created_by": policy.created_by,
        "updated_by": policy.updated_by,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
        "metadata": policy.metadata_json or {},
    }


def _coerce_member_role(value: Any) -> MemberRole | None:
    """兼容测试替身或旧调用传入字符串角色的情况。"""
    if isinstance(value, MemberRole):
        return value
    if isinstance(value, str):
        try:
            return MemberRole(value)
        except ValueError:
            return None
    return None


async def _record_tool_audit(
    request: Request,
    *,
    actor_user_id: str,
    workspace_id: str,
    action: AuditAction,
    tool_name: str,
    outcome: str,
    detail: dict[str, Any],
) -> None:
    store = get_postgres_store()
    async with store.async_session() as session:
        await AuditLogService(session).record(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            request=request,
            outcome=outcome,  # type: ignore[arg-type]
            target_type="tool",
            target_id=tool_name,
            detail=detail,
        )
        await session.commit()


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


@router.get("/tool-policies")
async def list_tool_policies(request: Request):
    """列出当前 workspace 的工具 auto-run 策略。"""
    _, workspace_id, _ = await workflow_helpers.require_workspace_permission(
        request,
        "workflow",
        "manage",
    )
    store = get_postgres_store()
    async with store.initialized_session() as session:
        policies = await ToolPolicyService(session).list_policies(workspace_id)
        return {"policies": [_dump_tool_policy(policy) for policy in policies]}


@router.put("/tool-policies/{tool_name:path}")
async def update_tool_policy(tool_name: str, request: Request, body: ToolPolicyRequest):
    """更新单个工具在当前 workspace 的显式 auto-run 授权。"""
    user_id, workspace_id, _ = await workflow_helpers.require_workspace_permission(
        request,
        "workflow",
        "manage",
    )
    try:
        spec = get_tool_registry().get_spec(tool_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if body.auto_run_enabled and spec.risk_level == RiskLevel.DESTRUCTIVE:
        await _record_tool_audit(
            request,
            actor_user_id=user_id,
            workspace_id=workspace_id,
            action=AuditAction.TOOL_POLICY_UPDATE,
            tool_name=tool_name,
            outcome="failure",
            detail={"reason": "destructive_tool_auto_run_forbidden"},
        )
        raise HTTPException(status_code=403, detail="破坏性工具不允许配置自动执行")
    if body.auto_run_enabled and spec.requires_approval:
        await _record_tool_audit(
            request,
            actor_user_id=user_id,
            workspace_id=workspace_id,
            action=AuditAction.TOOL_POLICY_UPDATE,
            tool_name=tool_name,
            outcome="failure",
            detail={"reason": "tool_requires_explicit_approval"},
        )
        raise HTTPException(status_code=403, detail="该工具声明必须审批，不能配置自动执行")
    if body.auto_run_enabled and spec.risk_level != RiskLevel.EXTERNAL_ACTION:
        await _record_tool_audit(
            request,
            actor_user_id=user_id,
            workspace_id=workspace_id,
            action=AuditAction.TOOL_POLICY_UPDATE,
            tool_name=tool_name,
            outcome="failure",
            detail={"reason": "auto_run_only_for_external_action"},
        )
        raise HTTPException(status_code=400, detail="仅 external_action 工具支持显式自动执行策略")

    store = get_postgres_store()
    async with store.initialized_session() as session:
        policy = await ToolPolicyService(session).upsert_policy(
            workspace_id=workspace_id,
            tool_name=tool_name,
            auto_run_enabled=body.auto_run_enabled,
            actor_user_id=user_id,
            metadata={
                "reason": body.reason,
                "risk_level": spec.risk_level.value,
                "requires_approval": spec.requires_approval,
            },
        )
        await AuditLogService(session).record(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditAction.TOOL_POLICY_UPDATE,
            request=request,
            target_type="tool",
            target_id=tool_name,
            detail={
                "auto_run_enabled": body.auto_run_enabled,
                "risk_level": spec.risk_level.value,
                "has_reason": bool(body.reason),
            },
        )
        await session.commit()
        return {"policy": _dump_tool_policy(policy)}


@router.post("/tools/execute")
async def execute_tool(request: Request, body: ExecuteToolRequest):
    """受控直接执行工具。"""
    user_id, workspace_id, role = await workflow_helpers.require_workspace_permission(
        request,
        "workflow",
        "execute",
    )
    try:
        spec = get_tool_registry().get_spec(body.tool_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    role_value = _coerce_member_role(role)
    if not is_admin_role(role_value):
        await _record_tool_audit(
            request,
            actor_user_id=user_id,
            workspace_id=workspace_id,
            action=AuditAction.TOOL_EXECUTE,
            tool_name=body.tool_name,
            outcome="failure",
            detail={"reason": "direct_tool_execute_requires_admin"},
        )
        raise HTTPException(status_code=403, detail="直接工具执行仅允许管理员或拥有者")
    if spec.risk_level == RiskLevel.DESTRUCTIVE:
        await _record_tool_audit(
            request,
            actor_user_id=user_id,
            workspace_id=workspace_id,
            action=AuditAction.TOOL_EXECUTE,
            tool_name=body.tool_name,
            outcome="failure",
            detail={"reason": "destructive_tool_direct_execute_forbidden"},
        )
        raise HTTPException(status_code=403, detail="破坏性工具只能通过工作流 Gate 执行")

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
        role=role_value.value if role_value is not None else str(role),
    )
    result = await get_tool_executor().execute(
        body.tool_name,
        body.input,
        runtime,
        approval_mode=body.approval_mode,
        existing_tool_call_id=body.existing_tool_call_id,
    )
    return redact_sensitive_payload(result.model_dump(mode="json"))


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
