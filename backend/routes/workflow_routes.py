"""
内容工作流 API 路由

提供工作流的启动、暂停、恢复、审批、重跑等接口
"""
from fastapi import APIRouter, HTTPException

from routes.workflow_helpers import (
    ApproveFactCheckRequest,
    ApproveOutlineRequest,
    ClarifyRequest,
    PauseWorkflowRequest,
    RerunRequest,
    ResumeWorkflowRequest,
    StartWorkflowRequest,
    WorkflowResponse,
    _assert_status,
    _build_workflow_response,
    _ensure_workflow_metadata,
    _GATE_STATUSES,
    _get_workflow_run_if_exists,
    _load_runtime_context,
    _normalize_status,
    _now_iso,
    _simplify_state,
)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/start", response_model=WorkflowResponse)
async def start_workflow(request: StartWorkflowRequest):
    """
    启动新的内容生成工作流

    工作流会在需要用户输入时暂停：
    - needs_clarification: 需要澄清信息
    - awaiting_outline_approval: 等待提纲审批
    """
    from graph import get_workflow

    try:
        workflow = get_workflow()
        result = await workflow.start(
            request.user_input,
            workflow_definition_id=request.workflow_definition_id,
            workflow_version_id=request.workflow_version_id,
        )
        workflow_run = await _get_workflow_run_if_exists(result["workflow_run_id"])
        status = _normalize_status(result["status"])
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=status,
            state=result["state"],
            workflow_run=workflow_run,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_run_id}/pause", response_model=WorkflowResponse)
async def pause_workflow(workflow_run_id: str, request: PauseWorkflowRequest):
    """用户主动暂停工作流"""
    try:
        store, workflow, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)

        if status in _GATE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="当前工作流正在等待人工 Gate，请使用对应审批接口继续。",
            )
        if status in {"completed", "failed"}:
            raise HTTPException(status_code=409, detail="当前工作流已结束，无法暂停。")
        if status == "paused":
            return _build_workflow_response(
                workflow_run_id=workflow_run_id,
                status="paused",
                state=graph_state,
                workflow_run=workflow_run,
            )

        result = await workflow.pause(
            workflow_run_id=workflow_run_id,
            reason=request.reason or "",
        )

        refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
        metadata = _ensure_workflow_metadata(refreshed_workflow_run)
        previous_pause = metadata.get("pause") if isinstance(metadata.get("pause"), dict) else {}
        paused_at = previous_pause.get("paused_at")
        if paused_at is None or previous_pause.get("resumed_at") is not None:
            paused_at = _now_iso()
        metadata["pause"] = {
            "reason": request.reason,
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
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_run_id}/resume", response_model=WorkflowResponse)
async def resume_workflow(workflow_run_id: str, _: ResumeWorkflowRequest):
    """恢复用户手动暂停的工作流"""
    try:
        store, workflow, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)
        from routes.workflow_helpers import _get_workflow_run_status
        raw_status = _get_workflow_run_status(workflow_run)

        if status in _GATE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="当前工作流处于 Gate 等待态，请使用澄清或审批接口继续。",
            )
        if status != "paused" and raw_status != "paused":
            raise HTTPException(status_code=409, detail="当前工作流未处于手动暂停状态。")

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
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_run_id}/approve-outline", response_model=WorkflowResponse)
async def approve_outline(workflow_run_id: str, request: ApproveOutlineRequest):
    """
    处理提纲审批

    action 可选值：
    - approve: 确认提纲
    - modify: 修改提纲（需提供 modified_outline）
    - regenerate: 重新生成（可提供 feedback）
    """
    try:
        _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
        _assert_status(
            status,
            allowed={"awaiting_outline_approval"},
            action="提纲审批",
            paused_detail="当前工作流已手动暂停，请先恢复后再处理提纲审批。",
        )
        result = await workflow.approve_outline(
            workflow_run_id=workflow_run_id,
            action=request.action,
            feedback=request.feedback or "",
            modified_outline=request.modified_outline
        )
        refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_run_id}/clarify", response_model=WorkflowResponse)
async def clarify_intent(workflow_run_id: str, request: ClarifyRequest):
    """提供澄清回答"""
    try:
        _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
        _assert_status(
            status,
            allowed={"needs_clarification"},
            action="澄清提交",
            paused_detail="当前工作流已手动暂停，请先恢复后再提交澄清回答。",
        )
        result = await workflow.resume(
            workflow_run_id=workflow_run_id,
            user_input={"user_clarifications": request.clarifications}
        )
        refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_run_id}/approve-fact-check", response_model=WorkflowResponse)
async def approve_fact_check(workflow_run_id: str, request: ApproveFactCheckRequest):
    """处理事实核查高风险项审批"""
    try:
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
                "fact_check_decisions": request.decisions,
                "manual_corrections": request.manual_corrections,
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_run_id}", response_model=WorkflowResponse)
async def get_workflow_status(workflow_run_id: str):
    """获取工作流状态"""
    _, _, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)
    return _build_workflow_response(
        workflow_run_id=workflow_run_id,
        status=status,
        state=graph_state,
        workflow_run=workflow_run,
    )


@router.get("/{workflow_run_id}/rerun-options")
async def get_rerun_options(workflow_run_id: str):
    """获取可重跑的节点列表"""
    from services import get_rerun_service

    try:
        rerun_service = get_rerun_service()
        options = await rerun_service.get_rerun_options(workflow_run_id)
        return {"options": options}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_run_id}/rerun")
async def rerun_workflow(workflow_run_id: str, request: RerunRequest):
    """
    从指定节点重跑工作流

    创建新的工作流运行，保留指定节点之前的所有 Artifact
    """
    from services import get_rerun_service
    from graph import get_workflow

    try:
        rerun_service = get_rerun_service()

        # 1. 准备重跑状态
        preserved_state = await rerun_service.prepare_rerun_state(
            workflow_run_id,
            request.from_node,
            request.updated_input
        )

        # 2. 创建新的 WorkflowRun
        new_workflow_run = await rerun_service.create_rerun_workflow(
            workflow_run_id,
            request.from_node,
            request.reason or ""
        )

        # 3. 使用工作流执行器恢复执行
        workflow = get_workflow()
        result = await workflow.resume(
            new_workflow_run.id,
            preserved_state
        )

        simplified_state = _simplify_state(result["state"])

        return {
            "original_workflow_run_id": workflow_run_id,
            "new_workflow_run_id": new_workflow_run.id,
            "rerun_from_node": request.from_node,
            "status": result["status"],
            "state": simplified_state
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_run_id}/rerun-history")
async def get_rerun_history(workflow_run_id: str):
    """获取工作流的重跑历史"""
    from services import get_rerun_service

    try:
        rerun_service = get_rerun_service()
        history = await rerun_service.get_rerun_history(workflow_run_id)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
