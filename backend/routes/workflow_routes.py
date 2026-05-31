"""
内容工作流 API 路由

提供工作流的启动、暂停、恢复、审批、重跑等接口
"""

import asyncio
import inspect
import json
import logging
import time
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

import routes.workflow_helpers as workflow_helpers
from core.errors.codes import (
    WORKFLOW_GATE_CONFLICT,
    WORKFLOW_NOT_FOUND,
    WORKFLOW_STATE_CONFLICT,
    WORKSPACE_CONTEXT_REQUIRED,
)
from core.errors.context import resolve_request_id
from core.errors.exceptions import ApplicationError, DomainError, PromptChainError
from core.errors.mapping import map_exception
from db.postgres_store import get_postgres_store
from models.admin_models import AuditAction
from models.knowledge import RetrievalConfig
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
    _get_workflow_run_if_exists,
    _is_admin_role,
    _load_runtime_context,
    _normalize_status,
    _normalize_trace_payload,
    _simplify_state,
)
from services.audit_log_service import AuditLogService
from services.workflow_event_bus import get_workflow_event_bus
from services.workflow_export_service import build_docx, build_workflow_export_payload

# 由 app.py 统一补齐 /api 前缀，这里只保留资源级前缀，避免重复拼接
router = APIRouter(prefix="/workflow", tags=["workflow"])
logger = logging.getLogger(__name__)
INTERNAL_SERVER_ERROR = "Internal server error"
MAX_RUN_UPLOAD_FILES = 5
MAX_RUN_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _format_sse_event(event: str, data: dict, event_id: str | None = None) -> str:
    """把 Python 字典编码为标准 SSE 事件，保留中文内容不转义。"""
    lines = [f"event: {event}"]
    if event_id:
        lines.append(f"id: {event_id}")
    payload = json.dumps(data, ensure_ascii=False, default=str)
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _format_sse_app_error_event(
    exc: Exception,
    *,
    request: Request,
    workflow_run_id: str,
) -> str:
    """复用统一错误映射输出 SSE 应用错误，避免使用 EventSource 保留的 error 事件名。"""

    mapped = map_exception(
        exc,
        request_id=resolve_request_id(request),
        path=str(request.url.path),
        method=request.method,
    )
    payload = mapped.envelope.model_dump(mode="json")
    payload["status"] = mapped.http_status
    payload["workflow_run_id"] = workflow_run_id
    return _format_sse_event("app_error", payload)


async def _build_workflow_event_snapshot(workflow_run_id: str) -> dict:
    """构建详情页 SSE 快照，包含运行状态和完整 trace/artifacts。"""
    from services import get_trace_service

    _, _, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)
    workflow_response = _build_workflow_response(
        workflow_run_id=workflow_run_id,
        status=status,
        state=graph_state,
        workflow_run=workflow_run,
    )
    trace = await get_trace_service().get_workflow_trace(workflow_run_id)

    return {
        "workflow": workflow_response.model_dump(mode="json"),
        "trace": _normalize_trace_payload(
            trace,
            workflow_run=workflow_run,
            graph_state=graph_state,
            status=status,
        ),
    }


def _workflow_run_snapshot(workflow_run) -> dict:
    """构建审计用运行记录快照，避免把完整输入内容重复写入审计表。"""
    if workflow_run is None:
        return {}
    status = getattr(workflow_run, "status", None)
    return {
        "id": getattr(workflow_run, "id", None),
        "workflow_name": getattr(workflow_run, "workflow_name", None),
        "workflow_definition_id": getattr(workflow_run, "workflow_definition_id", None),
        "workflow_version_id": getattr(workflow_run, "workflow_version_id", None),
        "status": status.value if hasattr(status, "value") else status,
        "current_node": getattr(workflow_run, "current_node", None),
    }


async def _audit_actor_context(request: Request, workflow_run) -> tuple[str, str]:
    from routes.auth_routes import get_current_user

    user = await get_current_user(request)
    user_id = user.get("sub") or user.get("id")
    metadata = workflow_helpers._ensure_workflow_metadata(workflow_run) if workflow_run else {}
    workspace_id = metadata.get("workspace_id") or user.get("workspace_id")
    if not user_id or not workspace_id:
        raise ApplicationError(
            code=WORKSPACE_CONTEXT_REQUIRED,
            message="缺少审计所需的用户或工作空间上下文",
        )
    return user_id, workspace_id


async def _record_workflow_audit(
    request: Request,
    *,
    actor_user_id: str,
    workspace_id: str,
    action: AuditAction,
    workflow_run_id: str,
    detail: dict | None = None,
    workflow_run=None,
) -> None:
    store = get_postgres_store()
    async with store.async_session() as session:
        await AuditLogService(session).record(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            request=request,
            target_type="workflow_run",
            target_id=workflow_run_id,
            detail=detail or {},
            target_snapshot=_workflow_run_snapshot(workflow_run),
        )
        await session.commit()


async def _start_workflow_run(
    request: Request,
    body: StartWorkflowRequest,
    *,
    run_upload_documents: list[dict] | None = None,
) -> WorkflowResponse:
    """启动工作流的共享实现，JSON 与带上传文件入口保持一致。"""
    from graph import get_workflow

    user_id, workspace_id, _ = await workflow_helpers.require_workspace_permission(
        request, "workflow", "execute"
    )
    workflow = get_workflow()
    start_kwargs = {
        "workflow_definition_id": body.workflow_definition_id,
        "workflow_version_id": body.workflow_version_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "model_provider_id": body.model_provider_id,
        "model_name": body.model_name,
        "retrieval_config": body.retrieval_config,
        "run_upload_documents": run_upload_documents,
    }
    supported_parameters = set(inspect.signature(workflow.start).parameters)
    compatible_kwargs = {
        key: value for key, value in start_kwargs.items() if key in supported_parameters
    }
    result = await workflow.start(body.user_input, **compatible_kwargs)
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
    await _record_workflow_audit(
        request,
        actor_user_id=user_id,
        workspace_id=workspace_id,
        action=AuditAction.WORKFLOW_RUN,
        workflow_run_id=result["workflow_run_id"],
        detail={
            "workflow_definition_id": body.workflow_definition_id,
            "workflow_version_id": body.workflow_version_id,
            "retrieval_enabled": (
                body.retrieval_config.enabled if body.retrieval_config else False
            ),
            "run_upload_document_count": len(run_upload_documents or []),
            "input_length": len(body.user_input),
            "status": status,
        },
        workflow_run=workflow_run,
    )
    return _build_workflow_response(
        workflow_run_id=result["workflow_run_id"],
        status=status,
        state=result["state"],
        workflow_run=workflow_run,
    )


def _parse_retrieval_config_json(raw_config: str | None) -> RetrievalConfig | None:
    """解析 multipart 表单中的检索配置。"""
    if not raw_config:
        return None
    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="retrieval_config 不是合法 JSON") from exc
    try:
        return RetrievalConfig.model_validate(parsed)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="retrieval_config 字段不合法") from exc


async def _read_run_upload_documents(files: list[UploadFile] | None) -> list[dict]:
    """读取本次运行上传文件，并在进入图执行前完成大小与数量校验。"""
    uploads = files or []
    if len(uploads) > MAX_RUN_UPLOAD_FILES:
        raise HTTPException(
            status_code=413, detail=f"本次运行最多上传 {MAX_RUN_UPLOAD_FILES} 个文件"
        )

    documents: list[dict] = []
    total_bytes = 0
    for upload in uploads:
        chunks: list[bytes] = []
        while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
            total_bytes += len(chunk)
            if total_bytes > MAX_RUN_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="本次运行上传资料总大小超过 20MB")
            chunks.append(chunk)
        content = b"".join(chunks)
        if not content:
            continue
        documents.append(
            {
                "file_name": upload.filename or "untitled.txt",
                "content": content,
                "metadata": {"source": "run_upload"},
            }
        )
    return documents


@router.post("/start", response_model=WorkflowResponse)
async def start_workflow(request: Request, body: StartWorkflowRequest):
    """
    启动新的内容生成工作流

    工作流会在需要用户输入时暂停：
    - needs_clarification: 需要澄清信息
    - awaiting_outline_approval: 等待提纲审批
    """
    try:
        return await _start_workflow_run(request, body)
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("启动工作流失败")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/start-with-uploads", response_model=WorkflowResponse)
async def start_workflow_with_uploads(
    request: Request,
    user_input: str = Form(...),
    workflow_definition_id: str | None = Form(None),
    workflow_version_id: str | None = Form(None),
    model_provider_id: str | None = Form(None),
    model_name: str | None = Form(None),
    retrieval_config: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
) -> WorkflowResponse:
    """启动工作流并先索引本次运行上传资料。"""
    try:
        documents = await _read_run_upload_documents(files)
        config = _parse_retrieval_config_json(retrieval_config)
        if documents:
            base_config = config or RetrievalConfig()
            config = base_config.model_copy(update={"enabled": True, "use_run_upload": True})
        body = StartWorkflowRequest(
            user_input=user_input,
            workflow_definition_id=workflow_definition_id,
            workflow_version_id=workflow_version_id,
            model_provider_id=model_provider_id,
            model_name=model_name,
            retrieval_config=config,
        )
        return await _start_workflow_run(request, body, run_upload_documents=documents)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("启动带运行资料的工作流失败")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/{workflow_run_id}/pause", response_model=WorkflowResponse)
async def pause_workflow(workflow_run_id: str, request: Request, body: PauseWorkflowRequest):
    """用户主动暂停工作流"""
    try:
        access_workflow_run = await workflow_helpers.require_workflow_run_access(
            request, workflow_run_id, resource="workflow", action="execute"
        )
        _, workflow, workflow_run, graph_state, status = await _load_runtime_context(
            workflow_run_id
        )

        if status in _GATE_STATUSES:
            raise DomainError(
                code=WORKFLOW_GATE_CONFLICT,
                message="当前工作流正在等待人工 Gate，请使用对应审批接口继续。",
            )
        if status in {"completed", "failed"}:
            raise DomainError(
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
        actor_user_id, workspace_id = await _audit_actor_context(request, access_workflow_run)
        await _record_workflow_audit(
            request,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            action=AuditAction.WORKFLOW_PAUSE,
            workflow_run_id=workflow_run_id,
            detail={"reason": body.reason, "current_node": refreshed_workflow_run.current_node},
            workflow_run=refreshed_workflow_run,
        )
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as exc:
        logger.exception("暂停工作流失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/{workflow_run_id}/resume", response_model=WorkflowResponse)
async def resume_workflow(workflow_run_id: str, request: Request, _: ResumeWorkflowRequest):
    """恢复用户手动暂停的工作流"""
    try:
        access_workflow_run = await workflow_helpers.require_workflow_run_access(
            request, workflow_run_id, resource="workflow", action="execute"
        )
        _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
        from routes.workflow_helpers import _get_workflow_run_status

        raw_status = _get_workflow_run_status(workflow_run)

        if status in _GATE_STATUSES:
            raise DomainError(
                code=WORKFLOW_GATE_CONFLICT,
                message="当前工作流处于 Gate 等待态，请使用澄清或审批接口继续。",
            )
        if status != "paused" and raw_status != "paused":
            raise DomainError(
                code=WORKFLOW_STATE_CONFLICT,
                message="当前工作流未处于手动暂停状态。",
            )

        result = await workflow.resume_paused(workflow_run_id)
        refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
        actor_user_id, workspace_id = await _audit_actor_context(request, access_workflow_run)
        await _record_workflow_audit(
            request,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            action=AuditAction.WORKFLOW_RESUME,
            workflow_run_id=workflow_run_id,
            detail={"current_node": refreshed_workflow_run.current_node},
            workflow_run=refreshed_workflow_run,
        )

        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as exc:
        logger.exception("恢复工作流失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/{workflow_run_id}/approve-outline", response_model=WorkflowResponse)
async def approve_outline(workflow_run_id: str, request: Request, body: ApproveOutlineRequest):
    """
    处理提纲审批

    action 可选值：
    - approve: 确认提纲
    - modify: 修改提纲（需提供 modified_outline）
    - regenerate: 重新生成（可提供 feedback）
    """
    try:
        access_workflow_run = await workflow_helpers.require_workflow_run_access(
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
        actor_user_id, workspace_id = await _audit_actor_context(request, access_workflow_run)
        await _record_workflow_audit(
            request,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            action=AuditAction.WORKFLOW_APPROVE,
            workflow_run_id=workflow_run_id,
            detail={
                "gate_type": "outline_approval",
                "decision": body.action,
                "has_feedback": bool(body.feedback),
                "has_modified_outline": body.modified_outline is not None,
            },
            workflow_run=refreshed_workflow_run,
        )
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("提纲审批失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/{workflow_run_id}/clarify", response_model=WorkflowResponse)
async def clarify_intent(workflow_run_id: str, request: Request, body: ClarifyRequest):
    """提供澄清回答"""
    try:
        access_workflow_run = await workflow_helpers.require_workflow_run_access(
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
        actor_user_id, workspace_id = await _audit_actor_context(request, access_workflow_run)
        await _record_workflow_audit(
            request,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            action=AuditAction.WORKFLOW_CLARIFY,
            workflow_run_id=workflow_run_id,
            detail={
                "answered_fields": sorted(body.clarifications.keys()),
                "answer_count": len(body.clarifications),
            },
            workflow_run=refreshed_workflow_run,
        )
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("澄清提交失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/{workflow_run_id}/approve-fact-check", response_model=WorkflowResponse)
async def approve_fact_check(workflow_run_id: str, request: Request, body: ApproveFactCheckRequest):
    """处理事实核查高风险项审批"""
    try:
        access_workflow_run = await workflow_helpers.require_workflow_run_access(
            request, workflow_run_id, resource="workflow", action="execute"
        )
        _, workflow, workflow_run, _, status = await _load_runtime_context(workflow_run_id)
        _assert_status(
            status,
            allowed={"awaiting_fact_check_approval"},
            action="事实核查审批",
            paused_detail="当前工作流已手动暂停，请先恢复后再处理事实核查审批。",
        )
        result = await workflow.approve_fact_check(
            workflow_run_id=workflow_run_id,
            decisions=body.decisions,
            manual_corrections=body.manual_corrections,
        )
        refreshed_workflow_run = await _get_workflow_run_if_exists(workflow_run_id) or workflow_run
        actor_user_id, workspace_id = await _audit_actor_context(request, access_workflow_run)
        await _record_workflow_audit(
            request,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            action=AuditAction.WORKFLOW_APPROVE,
            workflow_run_id=workflow_run_id,
            detail={
                "gate_type": "fact_check",
                "decision_count": len(body.decisions),
                "manual_correction_count": len(body.manual_corrections),
            },
            workflow_run=refreshed_workflow_run,
        )
        return _build_workflow_response(
            workflow_run_id=result["workflow_run_id"],
            status=_normalize_status(result["status"]),
            state=result["state"],
            workflow_run=refreshed_workflow_run,
        )
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("事实核查审批失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/runs", response_model=WorkflowRunListResponse)
async def list_workflow_runs(request: Request):
    """获取当前用户在当前工作空间可见的运行记录列表。"""
    from services import get_artifact_store

    try:
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
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取工作流运行列表失败")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/{workflow_run_id}/events")
async def stream_workflow_events(workflow_run_id: str, request: Request):
    """通过 SSE 向详情页推送运行状态和 trace 快照。"""
    await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
    event_bus = get_workflow_event_bus()
    event_queue = event_bus.subscribe(workflow_run_id)

    async def event_stream():
        last_payload_signature: str | None = None
        event_index = 0
        heartbeat_ticks = 0
        next_snapshot_at = time.monotonic()

        try:
            while not await request.is_disconnected():
                # 先按固定节奏发送 snapshot，避免高频 token 事件把快照饿死。
                if time.monotonic() >= next_snapshot_at:
                    try:
                        snapshot = await _build_workflow_event_snapshot(workflow_run_id)
                    except PromptChainError as exc:
                        yield _format_sse_app_error_event(
                            exc,
                            request=request,
                            workflow_run_id=workflow_run_id,
                        )
                        break
                    except HTTPException as exc:
                        yield _format_sse_app_error_event(
                            exc,
                            request=request,
                            workflow_run_id=workflow_run_id,
                        )
                        break
                    except Exception as exc:
                        logger.exception(
                            "工作流 SSE 快照生成失败: workflow_run_id=%s", workflow_run_id
                        )
                        yield _format_sse_app_error_event(
                            exc,
                            request=request,
                            workflow_run_id=workflow_run_id,
                        )
                        break

                    signature = json.dumps(snapshot, sort_keys=True, default=str)
                    if signature != last_payload_signature:
                        event_index += 1
                        heartbeat_ticks = 0
                        last_payload_signature = signature
                        yield _format_sse_event("snapshot", snapshot, event_id=str(event_index))
                    else:
                        heartbeat_ticks += 1
                        if heartbeat_ticks >= 10:
                            heartbeat_ticks = 0
                            yield _format_sse_event(
                                "heartbeat",
                                {"workflow_run_id": workflow_run_id},
                                event_id=f"{event_index}:heartbeat",
                            )

                    workflow_payload = snapshot.get("workflow", {})
                    if workflow_payload.get("status") in {"completed", "failed"}:
                        yield _format_sse_event(
                            "done",
                            {
                                "workflow_run_id": workflow_run_id,
                                "status": workflow_payload.get("status"),
                            },
                            event_id=f"{event_index}:done",
                        )
                        break

                    next_snapshot_at = time.monotonic() + 1.0
                    continue

                # 在两次 snapshot 之间，优先把节点级增量事件透传给前端。
                timeout = max(next_snapshot_at - time.monotonic(), 0.05)
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=timeout)
                except TimeoutError:
                    continue

                payload = {
                    "workflow_run_id": event.workflow_run_id,
                    "timestamp": event.timestamp,
                    **event.data,
                }
                yield _format_sse_event(event.type, payload, event_id=event.event_id)
        finally:
            event_bus.unsubscribe(workflow_run_id, event_queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

    try:
        await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
        rerun_service = get_rerun_service()
        options = await rerun_service.get_rerun_options(workflow_run_id)
        return {"options": options}
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取重跑选项失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.post("/{workflow_run_id}/rerun")
async def rerun_workflow(workflow_run_id: str, request: Request, body: RerunRequest):
    """
    从指定节点重跑工作流

    创建新的工作流运行，保留指定节点之前的所有 Artifact
    """
    from graph import get_workflow
    from services import get_rerun_service

    try:
        user_id, workspace_id, _ = await workflow_helpers.require_workspace_permission(
            request, "workflow", "execute"
        )
        await workflow_helpers.require_workflow_run_access(
            request, workflow_run_id, resource="workflow", action="execute"
        )
        rerun_service = get_rerun_service()

        # 1. 准备重跑状态
        preserved_state = await rerun_service.prepare_rerun_state(
            workflow_run_id, body.from_node, body.updated_input
        )

        # 2. 创建新的 WorkflowRun
        updated_user_input = None
        if body.updated_input and isinstance(body.updated_input.get("user_input"), str):
            updated_user_input = body.updated_input["user_input"]

        new_workflow_run = await rerun_service.create_rerun_workflow(
            workflow_run_id,
            body.from_node,
            body.reason or "",
            updated_user_input=updated_user_input,
        )
        await workflow_helpers.annotate_workflow_run_ownership(
            new_workflow_run.id, user_id, workspace_id
        )

        # 3. 像 start/resume 一样走后台调度，避免重跑请求被节点执行时间阻塞。
        workflow = get_workflow()
        if hasattr(workflow, "start_rerun_from_node"):
            result = await workflow.start_rerun_from_node(
                new_workflow_run.id,
                from_node=body.from_node,
                preserved_state=preserved_state,
            )
        else:
            result = await workflow.rerun_from_node(
                new_workflow_run.id,
                from_node=body.from_node,
                preserved_state=preserved_state,
            )

        simplified_state = _simplify_state(result["state"])
        refreshed_new_workflow_run = (
            await _get_workflow_run_if_exists(new_workflow_run.id) or new_workflow_run
        )
        await _record_workflow_audit(
            request,
            actor_user_id=user_id,
            workspace_id=workspace_id,
            action=AuditAction.WORKFLOW_RERUN,
            workflow_run_id=new_workflow_run.id,
            detail={
                "original_workflow_run_id": workflow_run_id,
                "from_node": body.from_node,
                "has_updated_input": body.updated_input is not None,
                "reason": body.reason,
            },
            workflow_run=refreshed_new_workflow_run,
        )

        return {
            "original_workflow_run_id": workflow_run_id,
            "new_workflow_run_id": new_workflow_run.id,
            "rerun_from_node": body.from_node,
            "status": result["status"],
            "state": simplified_state,
        }
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as exc:
        logger.exception("重跑工作流失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/{workflow_run_id}/rerun-history")
async def get_rerun_history(workflow_run_id: str, request: Request):
    """获取工作流的重跑历史"""
    from services import get_rerun_service

    try:
        await workflow_helpers.require_workflow_run_access(request, workflow_run_id)
        rerun_service = get_rerun_service()
        history = await rerun_service.get_rerun_history(workflow_run_id)
        return {"history": history}
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取重跑历史失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR) from exc


@router.get("/{workflow_run_id}/exports/docx")
async def export_workflow_docx(workflow_run_id: str, request: Request):
    """导出已完成工作流的最终产物 DOCX。"""
    from services import get_trace_service

    try:
        await workflow_helpers.require_workflow_run_access(
            request, workflow_run_id, resource="workflow_run", action="export"
        )
        _, _, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)

        if status != "completed":
            raise DomainError(
                code=WORKFLOW_STATE_CONFLICT,
                message="仅已完成的工作流支持导出 DOCX。",
            )

        trace = await get_trace_service().get_workflow_trace(workflow_run_id)
        payload = build_workflow_export_payload(
            graph_state,
            trace,
            workflow_name=getattr(workflow_run, "workflow_name", None),
        )
        if not payload.sections:
            raise DomainError(
                code=WORKFLOW_NOT_FOUND,
                message="当前工作流没有可导出的最终产物。",
            )

        buffer = build_docx(payload)
        filename = f"PromptChain-{workflow_run_id[:8]}-最终产物.docx"
        encoded_filename = quote(filename)

        return StreamingResponse(
            buffer,
            media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            headers={
                "Content-Disposition": (
                    f'attachment; filename="PromptChain-{workflow_run_id[:8]}.docx"; '
                    f"filename*=UTF-8''{encoded_filename}"
                )
            },
        )
    except PromptChainError:
        raise
    except HTTPException:
        raise
    except ImportError as exc:
        logger.exception("DOCX 导出依赖缺失: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(
            status_code=500, detail="DOCX 导出依赖缺失，请先同步后端依赖。"
        ) from exc
    except Exception as exc:
        logger.exception("导出 DOCX 失败: workflow_run_id=%s", workflow_run_id)
        raise HTTPException(status_code=500, detail="导出 DOCX 失败。") from exc
