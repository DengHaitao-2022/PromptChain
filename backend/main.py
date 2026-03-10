"""
基于 Prompt Chain 的自动化内容生成系统 - FastAPI 入口

主要功能：
1. /api/workflow - 工作流 API（启动、恢复、审批）
2. /api/trace - Trace 回放 API
3. WebSocket - 实时状态推送
"""
from datetime import UTC, datetime
import os
from typing import Any, Dict, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# 创建 FastAPI 应用
app = FastAPI(
    title="PromptChain API",
    description="基于 Prompt Chain 的自动化内容生成系统",
    version="1.0.0"
)

# CORS 配置（开发环境允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 注册路由 ====================

# 认证路由
from routes.auth_routes import get_current_user, router as auth_router
app.include_router(auth_router, prefix="/api", tags=["auth"])

# 工作空间路由
from routes.workspace_routes import router as workspace_router
app.include_router(workspace_router, prefix="/api", tags=["workspace"])

# 后台管理路由
from routes.admin_routes import router as admin_router
app.include_router(admin_router, prefix="/api", tags=["admin"])

# 工作流定义路由
from routes.workflow_definition_routes import router as workflow_definition_router
app.include_router(workflow_definition_router, prefix="/api", tags=["workflow-definition"])

# WebSocket 路由
from routes.websocket_routes import router as ws_router
app.include_router(ws_router, tags=["websocket"])

# 版本管理路由
from routes.workflow_version_routes import router as version_router
app.include_router(version_router, prefix="/api", tags=["workflow-version"])


# ==================== 请求/响应模型 ====================

WorkflowStatus = Literal[
    "running",
    "paused",
    "needs_clarification",
    "awaiting_outline_approval",
    "awaiting_fact_check_approval",
    "completed",
    "failed",
]
OutlineAction = Literal["approve", "modify", "regenerate"]
FactCheckDecision = Literal["confirm", "use_suggestion", "manual"]


class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""
    user_input: str
    workflow_definition_id: Optional[str] = None
    workflow_version_id: Optional[str] = None


class ApproveOutlineRequest(BaseModel):
    """提纲审批请求"""
    action: OutlineAction
    feedback: Optional[str] = ""
    modified_outline: Optional[Dict[str, Any]] = None


class ClarifyRequest(BaseModel):
    """澄清回答请求"""
    clarifications: Dict[str, str]  # {field: answer}


class ApproveFactCheckRequest(BaseModel):
    """事实核查审批请求"""
    decisions: Dict[str, FactCheckDecision]
    manual_corrections: Dict[str, str] = Field(default_factory=dict)


class PauseWorkflowRequest(BaseModel):
    """手动暂停工作流请求"""
    reason: Optional[str] = None


class ResumeWorkflowRequest(BaseModel):
    """恢复手动暂停的工作流请求"""
    pass


class WorkflowResponse(BaseModel):
    """工作流响应"""
    workflow_run_id: str
    status: WorkflowStatus
    state: Dict[str, Any]


async def require_workspace_permission(user: dict, resource: str, action: str) -> tuple[str, str, Any]:
    """按当前 access_token 中的工作空间上下文校验权限。"""
    from db.postgres_store import get_postgres_store
    from services.permission_service import PermissionService

    user_id = user.get("sub") or user.get("id")
    workspace_id = user.get("workspace_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    if not workspace_id:
        raise HTTPException(status_code=400, detail="请先选择工作空间")

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        role = await permission_service.require_permission(user_id, workspace_id, resource, action)

    return user_id, workspace_id, role


async def annotate_workflow_run_ownership(workflow_run_id: str, user_id: str, workspace_id: str):
    """为新建运行记录补充最小归属元数据。"""
    from services import get_artifact_store

    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if not workflow_run:
        return None

    metadata = dict(workflow_run.metadata or {})
    metadata["workspace_id"] = workspace_id
    metadata["user_id"] = user_id
    workflow_run.metadata = metadata
    await store.update_workflow_run(workflow_run)
    return workflow_run


async def require_workflow_run_access(
    user: dict,
    workflow_run_id: str,
    resource: str = "workflow_run",
    action: str = "read",
):
    """校验工作流运行记录的工作空间和用户归属。"""
    from services import get_artifact_store
    from services.permission_service import is_admin_role

    user_id, workspace_id, role = await require_workspace_permission(user, resource, action)
    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)

    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow not found")

    metadata = workflow_run.metadata or {}
    run_workspace_id = metadata.get("workspace_id")
    run_user_id = metadata.get("user_id")

    if not run_workspace_id or not run_user_id:
        raise HTTPException(status_code=403, detail="该任务缺少归属信息，暂不允许访问")

    if run_workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="您无权访问该工作空间中的任务")

    if not is_admin_role(role) and run_user_id != user_id:
        raise HTTPException(status_code=403, detail="您只能访问自己的任务")

    return workflow_run


async def require_node_run_access(user: dict, node_run_id: str):
    """通过节点记录反查工作流归属后再校验。"""
    from services import get_artifact_store

    store = get_artifact_store()
    node_run = await store.get_node_run(node_run_id)
    if not node_run:
        raise HTTPException(status_code=404, detail="NodeRun not found")

    await require_workflow_run_access(user, node_run.workflow_run_id)
    return node_run


async def require_artifact_access(user: dict, artifact_id: str):
    """通过产物反查工作流归属后再校验。"""
    from services import get_artifact_store

    store = get_artifact_store()
    artifact = await store.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    await require_workflow_run_access(user, artifact.workflow_run_id)
    return artifact


# ==================== API 路由 ====================

@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "ok",
        "service": "PromptChain API",
        "version": "1.0.0"
    }


@app.post("/api/workflow/start", response_model=WorkflowResponse)
async def start_workflow(request: StartWorkflowRequest, user: dict = Depends(get_current_user)):
    """
    启动新的内容生成工作流

    工作流会在需要用户输入时暂停：
    - needs_clarification: 需要澄清信息
    - awaiting_outline_approval: 等待提纲审批
    """
    from graph import get_workflow

    try:
        user_id, workspace_id, _ = await require_workspace_permission(user, "workflow", "execute")
        workflow = get_workflow()
        result = await workflow.start(
            request.user_input,
            workflow_definition_id=request.workflow_definition_id,
            workflow_version_id=request.workflow_version_id,
        )
        workflow_run = await _get_workflow_run_if_exists(result["workflow_run_id"])
        workflow_run = await annotate_workflow_run_ownership(
            result["workflow_run_id"],
            user_id,
            workspace_id,
        ) or workflow_run
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


@app.post("/api/workflow/{workflow_run_id}/pause", response_model=WorkflowResponse)
async def pause_workflow(
    workflow_run_id: str,
    request: PauseWorkflowRequest,
    user: dict = Depends(get_current_user),
):
    """用户主动暂停工作流。"""
    try:
        await require_workflow_run_access(user, workflow_run_id, resource="workflow", action="execute")
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


@app.post("/api/workflow/{workflow_run_id}/resume", response_model=WorkflowResponse)
async def resume_workflow(
    workflow_run_id: str,
    _: ResumeWorkflowRequest,
    user: dict = Depends(get_current_user),
):
    """恢复用户手动暂停的工作流。"""
    try:
        await require_workflow_run_access(user, workflow_run_id, resource="workflow", action="execute")
        store, workflow, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)
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


@app.post("/api/workflow/{workflow_run_id}/approve-outline", response_model=WorkflowResponse)
async def approve_outline(
    workflow_run_id: str,
    request: ApproveOutlineRequest,
    user: dict = Depends(get_current_user),
):
    """
    处理提纲审批

    action 可选值：
    - approve: 确认提纲
    - modify: 修改提纲（需提供 modified_outline）
    - regenerate: 重新生成（可提供 feedback）
    """
    try:
        await require_workflow_run_access(user, workflow_run_id, resource="workflow", action="execute")
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


@app.post("/api/workflow/{workflow_run_id}/clarify", response_model=WorkflowResponse)
async def clarify_intent(
    workflow_run_id: str,
    request: ClarifyRequest,
    user: dict = Depends(get_current_user),
):
    """提供澄清回答"""
    try:
        await require_workflow_run_access(user, workflow_run_id, resource="workflow", action="execute")
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


@app.post("/api/workflow/{workflow_run_id}/approve-fact-check", response_model=WorkflowResponse)
async def approve_fact_check(
    workflow_run_id: str,
    request: ApproveFactCheckRequest,
    user: dict = Depends(get_current_user),
):
    """处理事实核查高风险项审批"""
    try:
        await require_workflow_run_access(user, workflow_run_id, resource="workflow", action="execute")
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


@app.get("/api/workflow/{workflow_run_id}", response_model=WorkflowResponse)
async def get_workflow_status(
    workflow_run_id: str,
    user: dict = Depends(get_current_user),
):
    """获取工作流状态"""
    await require_workflow_run_access(user, workflow_run_id)
    _, _, workflow_run, graph_state, status = await _load_runtime_context(workflow_run_id)
    return _build_workflow_response(
        workflow_run_id=workflow_run_id,
        status=status,
        state=graph_state,
        workflow_run=workflow_run,
    )


# ==================== Trace API ====================

@app.get("/api/trace/{workflow_run_id}")
async def get_workflow_trace(
    workflow_run_id: str,
    user: dict = Depends(get_current_user),
):
    """获取工作流完整追踪"""
    from services import get_trace_service
    from graph import get_workflow
    from services import get_artifact_store

    try:
        await require_workflow_run_access(user, workflow_run_id)
        trace_service = get_trace_service()
        trace = await trace_service.get_workflow_trace(workflow_run_id)
        store = get_artifact_store()
        workflow_run = await store.get_workflow_run(workflow_run_id)
        if not workflow_run:
            raise ValueError(f"WorkflowRun not found: {workflow_run_id}")

        workflow = get_workflow()
        graph_state = await _get_graph_state(workflow, workflow_run_id)
        status = _extract_workflow_status(workflow, workflow_run, graph_state)

        return _normalize_trace_payload(
            trace,
            workflow_run=workflow_run,
            graph_state=graph_state,
            status=status,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trace/node/{node_run_id}")
async def get_node_detail(node_run_id: str, user: dict = Depends(get_current_user)):
    """获取节点运行详情"""
    from services import get_trace_service

    try:
        await require_node_run_access(user, node_run_id)
        trace_service = get_trace_service()
        detail = await trace_service.get_node_detail(node_run_id)
        return detail
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artifact/{artifact_id}")
async def get_artifact(artifact_id: str, user: dict = Depends(get_current_user)):
    """获取 Artifact 详情"""
    artifact = await require_artifact_access(user, artifact_id)
    return artifact.model_dump()


@app.get("/api/artifact/{artifact_id}/history")
async def get_artifact_history(artifact_id: str, user: dict = Depends(get_current_user)):
    """获取 Artifact 版本历史"""
    from services import get_trace_service

    try:
        await require_artifact_access(user, artifact_id)
        trace_service = get_trace_service()
        history = await trace_service.get_artifact_history(artifact_id)
        return history
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/{workflow_run_id}/rerun-options")
async def get_rerun_options(
    workflow_run_id: str,
    user: dict = Depends(get_current_user),
):
    """获取可重跑的节点列表"""
    from services import get_rerun_service

    try:
        await require_workflow_run_access(user, workflow_run_id)
        rerun_service = get_rerun_service()
        options = await rerun_service.get_rerun_options(workflow_run_id)
        return {"options": options}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RerunRequest(BaseModel):
    """重跑请求"""
    from_node: str
    updated_input: Optional[Dict[str, Any]] = None
    reason: Optional[str] = ""


@app.post("/api/workflow/{workflow_run_id}/rerun")
async def rerun_workflow(
    workflow_run_id: str,
    request: RerunRequest,
    user: dict = Depends(get_current_user),
):
    """
    从指定节点重跑工作流

    创建新的工作流运行，保留指定节点之前的所有Artifact
    """
    from services import get_rerun_service
    from graph import get_workflow

    try:
        user_id, workspace_id, _ = await require_workspace_permission(user, "workflow", "execute")
        await require_workflow_run_access(user, workflow_run_id, resource="workflow", action="execute")
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
        await annotate_workflow_run_ownership(new_workflow_run.id, user_id, workspace_id)

        # 3. 使用新的工作流执行器恢复执行
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/{workflow_run_id}/rerun-history")
async def get_rerun_history(
    workflow_run_id: str,
    user: dict = Depends(get_current_user),
):
    """获取工作流的重跑历史"""
    from services import get_rerun_service

    try:
        await require_workflow_run_access(user, workflow_run_id)
        rerun_service = get_rerun_service()
        history = await rerun_service.get_rerun_history(workflow_run_id)
        return {"history": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 工具函数 ====================

_GATE_STATUS_TO_TYPE: dict[str, str] = {
    "needs_clarification": "clarification",
    "awaiting_outline_approval": "outline_approval",
    "awaiting_fact_check_approval": "fact_check",
}
_GATE_STATUSES = set(_GATE_STATUS_TO_TYPE)


def _normalize_status(value: Any) -> WorkflowStatus:
    normalized = str(value)
    if normalized not in {
        "running",
        "paused",
        "needs_clarification",
        "awaiting_outline_approval",
        "awaiting_fact_check_approval",
        "completed",
        "failed",
    }:
        return "running"
    return normalized  # type: ignore[return-value]


def _build_workflow_response(
    workflow_run_id: str,
    status: WorkflowStatus,
    state: dict,
    workflow_run: Any | None = None,
) -> WorkflowResponse:
    return WorkflowResponse(
        workflow_run_id=workflow_run_id,
        status=status,
        state=_simplify_state(state, workflow_run=workflow_run, status=status),
    )


async def _get_workflow_run_if_exists(workflow_run_id: str) -> Any | None:
    from services import get_artifact_store

    store = get_artifact_store()
    return await store.get_workflow_run(workflow_run_id)


async def _load_runtime_context(workflow_run_id: str) -> tuple[Any, Any, Any, dict, WorkflowStatus]:
    from graph import get_workflow
    from services import get_artifact_store

    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if not workflow_run:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = get_workflow()
    graph_state = await _get_graph_state(workflow, workflow_run_id)
    status = _extract_workflow_status(workflow, workflow_run, graph_state)
    return store, workflow, workflow_run, graph_state, status


def _assert_status(
    current_status: WorkflowStatus,
    *,
    allowed: set[WorkflowStatus],
    action: str,
    paused_detail: str,
) -> None:
    if current_status == "paused":
        raise HTTPException(status_code=409, detail=paused_detail)
    if current_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"当前工作流状态为 {current_status}，不能执行{action}。",
        )


def _simplify_state(state: dict, *, workflow_run: Any | None = None, status: WorkflowStatus | None = None) -> dict:
    """简化状态返回，移除大型对象"""
    simplified = {}

    for key, value in state.items():
        if key in ["intent_card", "outline"]:
            # Pydantic 模型转换为 dict
            if hasattr(value, "model_dump"):
                simplified[key] = value.model_dump()
            else:
                simplified[key] = value
        elif key in ["draft_sections", "final_content"]:
            # 仅返回章节ID和字数预览
            if isinstance(value, dict):
                simplified[key] = {
                    section_id: {
                        "preview": content[:100] + "..." if len(content) > 100 else content,
                        "word_count": len(content)
                    }
                    for section_id, content in value.items()
                }
            else:
                simplified[key] = value
        elif key in ["clarification_questions"]:
            # 转换 Uncertainty 对象
            if isinstance(value, list):
                simplified[key] = _normalize_clarification_questions(value)
            else:
                simplified[key] = value
        else:
            simplified[key] = value

    current_node = state.get("current_node") or getattr(workflow_run, "current_node", None)
    if current_node:
        simplified["current_node"] = current_node

    error = state.get("error")
    if error:
        simplified["error"] = error

    pause = _normalize_pause_state(workflow_run)
    if pause:
        simplified["pause"] = pause

    gate = _normalize_gate_state(status, state, workflow_run)
    if gate:
        simplified["gate"] = gate

    return simplified


async def _get_graph_state(workflow: Any, workflow_run_id: str) -> dict:
    """从图检查点读取最新状态，失败时返回空状态。"""
    config = {"configurable": {"thread_id": workflow_run_id}}
    try:
        snapshot = await workflow.graph.aget_state(config)
        if snapshot and isinstance(snapshot.values, dict):
            return snapshot.values
    except Exception:
        pass
    return {}


def _extract_workflow_status(workflow: Any, workflow_run: Any, graph_state: dict) -> str:
    """优先使用图状态推导 Gate/终态，再回退到 WorkflowRun 持久化状态。"""
    graph_status: str | None = None
    if graph_state:
        graph_status = workflow._get_workflow_status(graph_state)
        if graph_status in _GATE_STATUSES:
            return graph_status
        if graph_status in {"completed", "failed"}:
            return graph_status
        if graph_state.get("error"):
            return "failed"

    raw_status = _get_workflow_run_status(workflow_run)
    if raw_status == "paused":
        return "paused"
    if raw_status in {"completed", "failed"}:
        return raw_status
    if graph_status:
        return graph_status
    return "running"


def _get_workflow_run_status(workflow_run: Any) -> str:
    raw_status = getattr(workflow_run, "status", "running")
    if hasattr(raw_status, "value"):
        return str(raw_status.value)
    return str(raw_status)


def _ensure_workflow_metadata(workflow_run: Any) -> dict[str, Any]:
    metadata = getattr(workflow_run, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    metadata = {}
    setattr(workflow_run, "metadata", metadata)
    return metadata


def _coerce_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _map_clarification_priority(value: Any) -> str:
    """把后端数值优先级映射为前端枚举优先级。"""
    if isinstance(value, str):
        if value in {"high", "medium", "low"}:
            return value
        try:
            value = int(value)
        except ValueError:
            return "low"

    if isinstance(value, int):
        if value <= 2:
            return "high"
        if value == 3:
            return "medium"
        return "low"

    return "low"


def _normalize_clarification_questions(items: list[Any]) -> list[dict]:
    """统一澄清问题输出结构与优先级枚举。"""
    normalized: list[dict] = []
    for item in items:
        if hasattr(item, "model_dump"):
            question = item.model_dump()
        elif isinstance(item, dict):
            question = item
        else:
            continue

        normalized.append(
            {
                "field": question.get("field"),
                "question": question.get("question"),
                "priority": _map_clarification_priority(question.get("priority", 5)),
                "default_assumption": question.get("default_assumption"),
            }
        )
    return normalized


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return value if isinstance(value, dict) else {}


def _normalize_pause_state(workflow_run: Any | None) -> dict[str, Any] | None:
    if workflow_run is None:
        return None

    metadata = _ensure_workflow_metadata(workflow_run)
    pause_state = metadata.get("pause")
    if isinstance(pause_state, dict):
        return {
            "reason": pause_state.get("reason"),
            "paused_at": _coerce_iso(pause_state.get("paused_at")),
            "resumed_at": _coerce_iso(pause_state.get("resumed_at")),
            "source": pause_state.get("source") or "user",
        }

    legacy_reason = metadata.get("pause_reason")
    if legacy_reason is None and _get_workflow_run_status(workflow_run) != "paused":
        return None

    return {
        "reason": legacy_reason,
        "paused_at": None,
        "resumed_at": None,
        "source": "user",
    }


def _build_outline_gate_questions(state: dict) -> list[dict[str, Any]]:
    outline = _coerce_mapping(state.get("outline"))
    sections = outline.get("sections")
    question: dict[str, Any] = {
        "question": "请确认当前提纲是否可以进入正文生成。",
        "action_options": ["approve", "modify", "regenerate"],
    }
    if isinstance(sections, list):
        question["section_count"] = len(sections)
    if isinstance(outline.get("total_target_words"), int):
        question["target_words"] = outline["total_target_words"]
    return [question]


def _build_fact_check_gate_questions(state: dict) -> list[dict[str, Any]]:
    report = _coerce_mapping(state.get("fact_check_report"))
    results = report.get("results")
    if not isinstance(results, list):
        return []

    questions: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("risk_level") != "high":
            continue
        questions.append(
            {
                "claim_id": result.get("claim_id"),
                "question": result.get("verification_question"),
                "risk_level": result.get("risk_level"),
                "suggested_correction": result.get("suggested_correction"),
            }
        )
    return questions


def _normalize_gate_state(
    status: WorkflowStatus | None,
    state: dict,
    workflow_run: Any | None,
) -> dict[str, Any] | None:
    if status not in _GATE_STATUSES:
        return None

    metadata = _ensure_workflow_metadata(workflow_run) if workflow_run is not None else {}
    gate_metadata = metadata.get("gate") if isinstance(metadata.get("gate"), dict) else {}
    gate_type = gate_metadata.get("gate_type") or _GATE_STATUS_TO_TYPE[status]

    if gate_type == "clarification":
        questions = _normalize_clarification_questions(state.get("clarification_questions", []))
        answers = state.get("user_clarifications")
        trigger_reason = gate_metadata.get("trigger_reason") or "missing_information"
    elif gate_type == "outline_approval":
        questions = gate_metadata.get("questions") or _build_outline_gate_questions(state)
        answers = state.get("user_decision")
        trigger_reason = gate_metadata.get("trigger_reason") or "outline_review"
    else:
        questions = gate_metadata.get("questions") or _build_fact_check_gate_questions(state)
        answers = state.get("fact_check_decisions") or state.get("manual_corrections")
        trigger_reason = gate_metadata.get("trigger_reason") or "fact_risk"

    return {
        "gate_type": gate_type,
        "trigger_reason": trigger_reason,
        "questions": questions,
        "answers": answers or gate_metadata.get("answers"),
        "opened_at": _coerce_iso(gate_metadata.get("opened_at")),
        "handled_at": _coerce_iso(gate_metadata.get("handled_at")),
        "resolution": gate_metadata.get("resolution"),
    }


def _normalize_trace_payload(
    trace: dict[str, Any],
    *,
    workflow_run: Any,
    graph_state: dict,
    status: WorkflowStatus,
) -> dict[str, Any]:
    workflow_payload = dict(trace.get("workflow") or {})
    workflow_payload["status"] = status

    current_node = graph_state.get("current_node") or workflow_payload.get("current_node") or getattr(workflow_run, "current_node", None)
    if current_node:
        workflow_payload["current_node"] = current_node

    pause = _normalize_pause_state(workflow_run)
    if pause:
        workflow_payload["pause"] = pause

    gate = _normalize_gate_state(status, graph_state, workflow_run)
    if gate:
        workflow_payload["gate"] = gate

    error = graph_state.get("error")
    if error:
        workflow_payload["error"] = error

    return {
        **trace,
        "workflow": workflow_payload,
        "timeline": _enrich_timeline(trace.get("timeline", []), workflow_run, graph_state, status),
    }


def _enrich_timeline(
    timeline: list[dict[str, Any]],
    workflow_run: Any,
    graph_state: dict,
    status: WorkflowStatus,
) -> list[dict[str, Any]]:
    events = [dict(event) for event in timeline]
    event_names = {event.get("event") for event in events}
    current_node = graph_state.get("current_node") or getattr(workflow_run, "current_node", None)

    pause = _normalize_pause_state(workflow_run)
    if pause and pause.get("paused_at") and "workflow_paused" not in event_names:
        events.append(
            {
                "timestamp": pause["paused_at"],
                "event": "workflow_paused",
                "current_node": current_node,
                "reason": pause.get("reason"),
            }
        )
    if pause and pause.get("resumed_at") and "workflow_resumed" not in event_names:
        events.append(
            {
                "timestamp": pause["resumed_at"],
                "event": "workflow_resumed",
                "current_node": current_node,
            }
        )

    gate = _normalize_gate_state(status, graph_state, workflow_run)
    if gate and "workflow_gate_waiting" not in event_names:
        events.append(
            {
                "timestamp": gate.get("opened_at") or _coerce_iso(getattr(workflow_run, "started_at", None)) or _now_iso(),
                "event": "workflow_gate_waiting",
                "gate_type": gate["gate_type"],
                "questions": gate.get("questions", []),
                "current_node": current_node,
            }
        )

    events.sort(key=lambda event: event.get("timestamp") or "")
    return events


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    debug = os.getenv("DEBUG", "true").lower() == "true"

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug
    )
