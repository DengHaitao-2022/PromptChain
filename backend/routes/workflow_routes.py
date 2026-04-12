"""
内容工作流 API 路由

提供工作流的启动、暂停、恢复、审批、重跑等接口
"""

from fastapi import APIRouter, Request

import routes.workflow_helpers as workflow_helpers
from core.errors.codes import COMMON_BAD_REQUEST, WORKFLOW_GATE_CONFLICT, WORKFLOW_STATE_CONFLICT
from core.errors.exceptions import ApplicationError
from routes.workflow_helpers import (
    _GATE_STATUSES,
    ApproveFactCheckRequest,
    ApproveOutlineRequest,
    ClarifyRequest,
    PauseWorkflowRequest,
    RerunRequest,
    ResumeWorkflowRequest,
    StartWorkflowRequest,
    WorkflowResponse,
    WorkflowRunListResponse,
    _assert_status,
    _build_workflow_response,
    _build_workflow_run_list_response,
    _ensure_workflow_metadata,
    _get_workflow_run_if_exists,
    _is_admin_role,
    _load_runtime_context,
    _normalize_status,
    _now_iso,
    _simplify_state,
)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/start", response_model=WorkflowResponse)
async def start_workflow(request: Request, body: StartWorkflowRequest):
    """
    启动新的内容生成工作流

    工作流会在需要用户输入时暂停:
    - needs_clarification: 需要澄清信息
    - awaiting_outline_approval: 等待提纲审批
    """
    from graph import get_workflow

    user_id, workspace_id, _ = await workflow_helpers.require_workspace_permission(
        request, "workflow", "execute"
    )
    workflow = get_workflow()
    result = await workflow.start(
        body.user_input,
        workflow_definition_id=body.workflow_definition_id,
        workflow_version_id=body.workflow_version_id,
    )
    workflow_run = await _get_workflow_run_if_exists(result["workflow_run_id"])
    workflow_run = (
        await workflow_helpers.annotate_workflow_run_ownership(
            result["workflow_run_id"],
            user_id,
            workspace_id,
        )
        or workflow_run
    )
    status = _normalize_status(result["status"])
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=status,
        state=result["state"],
        workflow_run=workflow_run,
    )


@router.post("/{workflow_run_id}/pause", response_model=WorkflowResponse)
async def pause_workflow(workflow_run_id: str, request: Request, body: PauseWorkflowRequest):
    """用户主动暂停工作流"""
    await workflow_helpers.require_workflow_run_access(
        request, workflow_run_id, resource="workflow", action="execute"
    )
    store, workflow, workflow_run, graph_state, status = await _load_runtime_context(
        workflow_run_id
    )

    if status in _GATE_STATUSES:
        raise ApplicationError(
            code=WORKFLOW_GATE_CONFLICT,
            message="当前工作流正在等待人工 Gate，请使用对应审批接口继续。",
        )
    if status in {"completed", "failed"}:
        raise ApplicationError(
            code=WORKFLOW_STATE_CONFLICT,
            message="当前工作流已结束，无法暂停。",
        )
    if status == "paused":
        return _build_workflow_response(
            workflow_run_id=workflow_run_id,
            status="paused",
            state=graph_state,
            workflow_run=workflow_run,
        )

    result = await workflow.pause(
        workflow_run_id=workflow_run_id,
        reason=body.reason or "",
    )

    refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
    metadata = _ensure_workflow_metadata(refreshed_workflow_run)
    previous_pause = metadata.get("pause") if isinstance(metadata.get("pause"), dict) else {}
    paused_at = previous_pause.get("paused_at")
    if paused_at is None or previous_pause.get("resumed_at") is not None:
        paused_at = _now_iso()
    metadata["pause"] = {
        "reason": body.reason,
        "paused_at": paused_at,
        "resumed_at": None,
        "source": "user",
    }
    await store.update_workflow_run(refreshed_workflow_run)
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=_normalize_status(result["status"]),
        state=result["state"],
        workflow_run=refreshed_workflow_run,
    )


@router.post("/{workflow_run_id}/resume", response_model=WorkflowResponse)
async def resume_workflow(workflow_run_id: str, request: Request, _: ResumeWorkflowRequest):
    """恢复用户手动暂停的工作流"""
    await workflow_helpers.require_workflow_run_access(
        request, workflow_run_id, resource="workflow", action="execute"
    )
    store, workflow, workflow_run, _graph_state, status = await _load_runtime_context(
        workflow_run_id
    )
    from routes.workflow_helpers import _get_workflow_run_status

    raw_status = _get_workflow_run_status(workflow_run)

    if status in _GATE_STATUSES:
        raise ApplicationError(
            code=WORKFLOW_GATE_CONFLICT,
            message="当前工作流处于 Gate 等待态，请使用澄清或审批接口继续。",
        )
    if status != "paused" and raw_status != "paused":
        raise ApplicationError(
            code=WORKFLOW_STATE_CONFLICT,
            message="当前工作流未处于手动暂停状态。",
        )

    result = await workflow.resume_paused(workflow_run_id)
    refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
    metadata = _ensure_workflow_metadata(refreshed_workflow_run)
    previous_pause = metadata.get("pause") if isinstance(metadata.get("pause"), dict) else {}
    metadata["pause"] = {
        "reason": previous_pause.get("reason"),
        "paused_at": previous_pause.get("paused_at") or _now_iso(),
        "resumed_at": _now_iso(),
        "source": previous_pause.get("source") or "user",
    }
    await store.update_workflow_run(refreshed_workflow_run)

    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=_normalize_status(result["status"]),
        state=result["state"],
        workflow_run=refreshed_workflow_run,
    )


@router.post("/{workflow_run_id}/approve-outline", response_model=WorkflowResponse)
async def approve_outline(workflow_run_id: str, request: Request, body: ApproveOutlineRequest):
    """
    处理提纲审批

    action 可选值:
    - approve: 确认提纲
    - modify: 修改提纲（需提供 modified_outline）
    - regenerate: 重新生成（可提供 feedback）
    """
    await workflow_helpers.require_workflow_run_access(
        request, workflow_run_id, resource="workflow", action="execute"
    )
    _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
    _assert_status(
        status,
        allowed={"awaiting_outline_approval"},
        action="提纲审批",
        paused_detail="当前工作流已手动暂停，请先恢复后再处理提纲审批。",
    )
    result = await workflow.approve_outline(
        workflow_run_id=workflow_run_id,
        action=body.action,
        feedback=body.feedback or "",
        modified_outline=body.modified_outline,
    )
    refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=_normalize_status(result["status"]),
        state=result["state"],
        workflow_run=refreshed_workflow_run,
    )


@router.post("/{workflow_run_id}/clarify", response_model=WorkflowResponse)
async def clarify_intent(workflow_run_id: str, request: Request, body: ClarifyRequest):
    """提供澄清回答"""
    await workflow_helpers.require_workflow_run_access(
        request, workflow_run_id, resource="workflow", action="execute"
    )
    _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
    _assert_status(
        status,
        allowed={"needs_clarification"},
        action="澄清提交",
        paused_detail="当前工作流已手动暂停，请先恢复后再提交澄清回答。",
    )
    result = await workflow.resume(
        workflow_run_id=workflow_run_id, user_input={"user_clarifications": body.clarifications}
    )
    refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=_normalize_status(result["status"]),
        state=result["state"],
        workflow_run=refreshed_workflow_run,
    )


@router.post("/{workflow_run_id}/approve-fact-check", response_model=WorkflowResponse)
async def approve_fact_check(workflow_run_id: str, request: Request, body: ApproveFactCheckRequest):
    """处理事实核查高风险项审批"""
    await workflow_helpers.require_workflow_run_access(
        request, workflow_run_id, resource="workflow", action="execute"
    )
    _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
    _assert_status(
        status,
        allowed={"awaiting_fact_check_approval"},
        action="事实核查审批",
        paused_detail="当前工作流已手动暂停，请先恢复后再处理事实核查审批。",
    )
    result = await workflow.resume(
        workflow_run_id=workflow_run_id,
        user_input={
            "fact_check_decisions": body.decisions,
            "manual_corrections": body.manual_corrections,
            "awaiting_fact_check_approval": False,
        },
    )
    refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=_normalize_status(result["status"]),
        state=result["state"],
        workflow_run=refreshed_workflow_run,
    )


@router.get("/runs", response_model=WorkflowRunListResponse)
async def list_workflow_runs(request: Request):
    """获取当前用户在当前工作空间可见的运行记录列表。"""
    from services import get_artifact_store

    user_id, workspace_id, role = await workflow_helpers.require_workspace_permission(
        request,
        "workflow_run",
        "read",
    )
    store = get_artifact_store()
    # 静态列表接口按可见范围过滤，避免退回为全局 runs 列表。
    visible_user_id = None if _is_admin_role(role) else user_id
    workflow_runs = await store.list_workflow_runs(
        workspace_id=workspace_id,
        user_id=visible_user_id,
    )
    return _build_workflow_run_list_response(workflow_runs)


@router.get("/{workflow_run_id}", response_model=WorkflowResponse)
async def get_workflow_status(workflow_run_id: str, request: Request):
    """获取工作流状态"""
    await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
    _, _, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)
    return _build_workflow_response(
        workflow_run_id=workflow_run_id,
        status=status,
        state=graph_state,
        workflow_run=workflow_run,
    )


@router.get("/{workflow_run_id}/rerun-options")
async def get_rerun_options(workflow_run_id: str, request: Request):
    """获取可重跑的节点列表"""
    from services import get_rerun_service

    await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
    rerun_service = get_rerun_service()
    options = await rerun_service.get_rerun_options(workflow_run_id)
    return {"options": options}


@router.post("/{workflow_run_id}/rerun")
async def rerun_workflow(workflow_run_id: str, request: Request, body: RerunRequest):
    """
    从指定节点重跑工作流

    创建新的工作流运行，保留指定节点之前的所有 Artifact
    """
    from graph import get_workflow
    from services import get_rerun_service

    user_id, workspace_id, _ = await workflow_helpers.require_workspace_permission(
        request, "workflow", "execute"
    )
    await workflow_helpers.require_workflow_run_access(
        request, workflow_run_id, resource="workflow", action="execute"
    )
    rerun_service = get_rerun_service()

    try:
        # 1. 准备重跑状态
        preserved_state = await rerun_service.prepare_rerun_state(
            workflow_run_id, body.from_node, body.updated_input
        )

        # 2. 创建新的 WorkflowRun
        new_workflow_run = await rerun_service.create_rerun_workflow(
            workflow_run_id, body.from_node, body.reason or ""
        )
    except ValueError as exc:
        raise ApplicationError(
            code=COMMON_BAD_REQUEST,
            message=str(exc),
        ) from exc

    await workflow_helpers.annotate_workflow_run_ownership(
        new_workflow_run.id, user_id, workspace_id
    )

    # 3. 使用工作流执行器恢复执行
    workflow = get_workflow()
    result = await workflow.resume(new_workflow_run.id, preserved_state)

    simplified_state = _simplify_state(result["state"])

    return {
        "original_workflow_run_id": workflow_run_id,
        "new_workflow_run_id": new_workflow_run.id,
        "rerun_from_node": body.from_node,
        "status": result["status"],
        "state": simplified_state,
    }


@router.get("/{workflow_run_id}/rerun-history")
async def get_rerun_history(workflow_run_id: str, request: Request):
    """获取工作流的重跑历史"""
    from services import get_rerun_service

    await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
    rerun_service = get_rerun_service()
    history = await rerun_service.get_rerun_history(workflow_run_id)
    return {"history": history}
