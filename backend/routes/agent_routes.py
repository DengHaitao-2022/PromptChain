"""Autonomous Agent API 路由。"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import routes.workflow_helpers as workflow_helpers
from db.postgres_store import get_postgres_store
from models.auth_models import MemberRole
from models.autonomous_agent import AgentRunStatus
from routes.auth_routes import get_current_user
from services import get_artifact_store
from services.autonomous_agent_runtime import AutonomousAgentRuntime
from services.autonomous_agent_store import AutonomousAgentStore
from services.autonomous_agent_worker import get_agent_worker_queue
from services.permission_service import get_role_permissions, is_admin_role

router = APIRouter(prefix="/agents", tags=["autonomous-agent"])
logger = logging.getLogger(__name__)
INTERNAL_SERVER_ERROR = "Internal server error"
GATE_TOOL_PERMISSIONS = {
    "export_docx": ("workflow_run", "export"),
    "write_artifact": ("workflow", "execute"),
    "rollback_artifact": ("workflow", "execute"),
    "fact_check": ("workflow", "execute"),
    "read_artifact": ("workflow_run", "read"),
    "retrieve_memory": ("workflow_run", "read"),
    "retrieve_trace": ("workflow_run", "read"),
}


class StartAgentRunRequest(BaseModel):
    """启动 Autonomous Agent 请求。"""

    goal: str = Field(..., min_length=1, max_length=8000)
    autonomy_level: str = Field(default="supervised")
    budget_limit: dict[str, Any] = Field(default_factory=dict)
    auto_execute: bool = True
    planner_mode: str = Field(default="auto")
    generation_mode: str = Field(default="auto")
    fact_check_mode: str = Field(default="cove")
    model_provider_id: str | None = None
    model_provider_name: str | None = None
    model_name: str | None = None


class AgentGateDecisionRequest(BaseModel):
    """Agent Gate 审批请求。"""

    approved: bool
    note: str = ""


class AgentRunControlRequest(BaseModel):
    """Agent 运行控制请求。"""

    reason: str = ""


class AgentGoalClarificationRequest(BaseModel):
    """Planner 澄清请求。"""

    clarification: str = Field(..., min_length=1, max_length=8000)


class UpdateAgentPlanRequest(BaseModel):
    """人工修改 Agent 计划请求。"""

    plan_graph: dict[str, Any]
    reason: str = "human_plan_edit"


class SkipAgentNodeRequest(BaseModel):
    """人工跳过动态计划节点请求。"""

    node_id: str = Field(..., min_length=1, max_length=200)
    reason: str = "human_skip_node"


def _get_user_id(user: dict[str, Any]) -> str:
    user_id = user.get("sub") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未识别用户身份")
    return user_id


def _allowed_tool_permissions_for_role(role: Any) -> list[str]:
    """把工作空间角色权限转换为 ToolDefinition.permission 使用的字符串集合。"""
    if not isinstance(role, MemberRole):
        try:
            role = MemberRole(str(role))
        except ValueError:
            return []
    return sorted(
        f"{resource}:{action}"
        for resource, actions in get_role_permissions(role).items()
        for action in actions
    )


async def _refresh_run_tool_permissions(
    agent_store: AutonomousAgentStore,
    run: Any,
    role: Any,
) -> Any:
    """执行前刷新 actor 当前工具权限，避免角色变化后沿用旧授权。"""
    run.metadata["allowed_tool_permissions"] = _allowed_tool_permissions_for_role(role)
    return await agent_store.update_run(run)


async def _actor_context(request: Request, resource: str, action: str) -> tuple[str, str, str]:
    user_id, workspace_id, role = await workflow_helpers.require_workspace_permission(
        request, resource, action
    )
    return user_id, workspace_id, role


async def _require_agent_run_access(
    request: Request,
    run_id: str,
    *,
    action: str = "read",
) -> tuple[Any, str, str]:
    """校验 AgentRun 访问权限和工作空间归属。"""
    user = await get_current_user(request)
    user_id = _get_user_id(user)
    workspace_id = user.get("workspace_id") or user.get("default_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="未指定工作空间")

    store = get_postgres_store()
    await store.ensure_initialized()
    async with store.async_session() as session:
        agent_store = AutonomousAgentStore(session)
        run = await agent_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AgentRun 不存在")
        _, _, role = await workflow_helpers.require_workspace_permission(
            request, "workflow_run", action
        )
        if run.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="无权访问该 AgentRun")
        if not is_admin_role(role) and run.user_id != user_id:
            raise HTTPException(status_code=403, detail="无权访问其他用户的 AgentRun")
        return run, user_id, workspace_id


async def _require_gate_tool_permission(request: Request, run: Any) -> None:
    """按 Gate 关联工具补充校验具体权限。"""
    gate = run.gate or {}
    tool_name = gate.get("tool_name")
    permission = GATE_TOOL_PERMISSIONS.get(str(tool_name))
    if not permission:
        return
    resource, action = permission
    await workflow_helpers.require_workspace_permission(request, resource, action)


@router.post("/runs")
async def start_agent_run(request: Request, body: StartAgentRunRequest):
    """启动目标驱动 Autonomous Agent 运行。"""
    try:
        user_id, workspace_id, role = await _actor_context(request, "workflow", "execute")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            agent_store = AutonomousAgentStore(session)
            runtime = AutonomousAgentRuntime(
                store=agent_store,
                artifact_store=get_artifact_store(),
            )
            run = await runtime.start(
                goal=body.goal,
                user_id=user_id,
                workspace_id=workspace_id,
                autonomy_level=body.autonomy_level,
                budget_limit=body.budget_limit,
                auto_execute=body.auto_execute,
                allowed_tool_permissions=_allowed_tool_permissions_for_role(role),
                planner_mode=body.planner_mode,
                generation_mode=body.generation_mode,
                fact_check_mode=body.fact_check_mode,
                inline_execute=False,
                model_provider_id=body.model_provider_id,
                model_provider_name=body.model_provider_name,
                model_name=body.model_name,
            )
            if body.auto_execute and run.status == AgentRunStatus.RUNNING:
                await get_agent_worker_queue().enqueue(run.id)
            detail = await runtime.get_detail(run.id)
            return detail
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("启动 Autonomous Agent 失败")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/runs")
async def list_agent_runs(request: Request):
    """列出当前工作空间可见的 Autonomous Agent 运行。"""
    try:
        user_id, workspace_id, role = await _actor_context(request, "workflow_run", "read")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            agent_store = AutonomousAgentStore(session)
            runs = await agent_store.list_runs(
                workspace_id=workspace_id,
                user_id=None if is_admin_role(role) else user_id,
            )
            return {"runs": [run.model_dump(mode="json") for run in runs]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取 Autonomous Agent 运行列表失败")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str, request: Request):
    """获取 Autonomous Agent 运行详情。"""
    try:
        await _require_agent_run_access(request, run_id)
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("获取 Autonomous Agent 运行详情失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/runs/{run_id}/resume")
async def resume_agent_run(run_id: str, request: Request):
    """继续执行未完成的 Autonomous Agent 运行。"""
    try:
        run, _, _ = await _require_agent_run_access(request, run_id, action="create")
        _, _, role = await workflow_helpers.require_workspace_permission(
            request, "workflow", "execute"
        )
        if run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            raise HTTPException(status_code=409, detail="当前 AgentRun 已结束，无法继续执行")
        if run.status == AgentRunStatus.AWAITING_GATE:
            raise HTTPException(status_code=409, detail="当前 AgentRun 正在等待 Gate 审批")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            run = await _refresh_run_tool_permissions(runtime.store, run, role)
            await runtime.prepare_for_worker(run_id, reason="resume", run=run)
            await get_agent_worker_queue().enqueue(run_id)
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("继续执行 Autonomous Agent 失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/runs/{run_id}/pause")
async def pause_agent_run(run_id: str, request: Request, body: AgentRunControlRequest):
    """人工暂停长程 Autonomous Agent 运行。"""
    try:
        await _require_agent_run_access(request, run_id, action="create")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            await runtime.pause_run(run_id, reason=body.reason)
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("暂停 Autonomous Agent 失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str, request: Request, body: AgentRunControlRequest):
    """取消未完成的 Autonomous Agent 运行。"""
    try:
        await _require_agent_run_access(request, run_id, action="create")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            await runtime.cancel_run(run_id, reason=body.reason)
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("取消 Autonomous Agent 失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.put("/runs/{run_id}/plan")
async def update_agent_plan(run_id: str, request: Request, body: UpdateAgentPlanRequest):
    """人工修改 planning 状态下的动态计划图。"""
    try:
        run, _, _ = await _require_agent_run_access(request, run_id, action="create")
        if run.status != AgentRunStatus.PLANNING:
            raise HTTPException(
                status_code=409, detail="只有 planning 状态的 AgentRun 可以修改计划"
            )
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            await runtime.replace_plan(
                run_id,
                plan_graph_payload=body.plan_graph,
                reason=body.reason,
            )
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("修改 Autonomous Agent 计划失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/runs/{run_id}/gate")
async def approve_agent_gate(run_id: str, request: Request, body: AgentGateDecisionRequest):
    """审批高风险工具调用 Gate。"""
    try:
        run, _, _ = await _require_agent_run_access(request, run_id, action="create")
        await _require_gate_tool_permission(request, run)
        _, _, role = await workflow_helpers.require_workspace_permission(
            request, "workflow", "execute"
        )
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            await _refresh_run_tool_permissions(runtime.store, run, role)
            run = await runtime.approve_gate(
                run_id,
                approved=body.approved,
                note=body.note,
                inline_execute=False,
            )
            if run.status == AgentRunStatus.RUNNING:
                await get_agent_worker_queue().enqueue(run.id)
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("审批 Autonomous Agent Gate 失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/runs/{run_id}/skip-node")
async def skip_agent_node(run_id: str, request: Request, body: SkipAgentNodeRequest):
    """人工跳过当前计划中的未执行节点。"""
    try:
        await _require_agent_run_access(request, run_id, action="create")
        await workflow_helpers.require_workspace_permission(request, "workflow", "execute")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            await runtime.skip_node(run_id, node_id=body.node_id, reason=body.reason)
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("跳过 Autonomous Agent 节点失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/runs/{run_id}/clarify")
async def clarify_agent_goal(run_id: str, request: Request, body: AgentGoalClarificationRequest):
    """补充 Planner 失败时缺失的目标信息。"""
    try:
        run, _, _ = await _require_agent_run_access(request, run_id, action="create")
        _, _, role = await workflow_helpers.require_workspace_permission(
            request, "workflow", "execute"
        )
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            await _refresh_run_tool_permissions(runtime.store, run, role)
            run = await runtime.clarify_goal(
                run_id,
                body.clarification,
                inline_execute=False,
            )
            if run.status == AgentRunStatus.RUNNING:
                await get_agent_worker_queue().enqueue(run.id)
            return await runtime.get_detail(run_id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("补充 Autonomous Agent 目标失败: run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/tools")
async def list_agent_tools(request: Request):
    """列出 Autonomous Agent 可用工具定义。"""
    try:
        await _actor_context(request, "workflow_run", "read")
        store = get_postgres_store()
        await store.ensure_initialized()
        async with store.async_session() as session:
            runtime = AutonomousAgentRuntime(
                store=AutonomousAgentStore(session),
                artifact_store=get_artifact_store(),
            )
            return {
                "tools": [
                    tool.model_dump(mode="json")
                    for tool in runtime.tool_executor.registry.list_definitions()
                ]
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取 Autonomous Agent 工具列表失败")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc
