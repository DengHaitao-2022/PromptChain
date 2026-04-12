"""
内容工作流 API 工具函数

提供状态规范化、响应构建、Gate/Pause 状态处理等共享逻辑
"""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Request
from pydantic import BaseModel, Field

from core.errors.codes import (
    AUTH_UNAUTHENTICATED,
    TRACE_RESOURCE_NOT_FOUND,
    WORKFLOW_GATE_CONFLICT,
    WORKFLOW_NOT_FOUND,
    WORKFLOW_STATE_CONFLICT,
    WORKSPACE_ACCESS_DENIED,
    WORKSPACE_CONTEXT_REQUIRED,
)
from core.errors.exceptions import ApplicationError, DomainError
from models.auth_models import MemberRole

# ==================== 类型定义 ====================

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


# ==================== 请求/响应模型 ====================


class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""

    user_input: str
    workflow_definition_id: str | None = None
    workflow_version_id: str | None = None


class ApproveOutlineRequest(BaseModel):
    """提纲审批请求"""

    action: OutlineAction
    feedback: str | None = ""
    modified_outline: dict[str, Any] | None = None


class ClarifyRequest(BaseModel):
    """澄清回答请求"""

    clarifications: dict[str, str]  # {field: answer}


class ApproveFactCheckRequest(BaseModel):
    """事实核查审批请求"""

    decisions: dict[str, FactCheckDecision]
    manual_corrections: dict[str, str] = Field(default_factory=dict)


class PauseWorkflowRequest(BaseModel):
    """手动暂停工作流请求"""

    reason: str | None = None


class ResumeWorkflowRequest(BaseModel):
    """恢复手动暂停的工作流请求"""

    pass


class RerunRequest(BaseModel):
    """重跑请求"""

    from_node: str
    updated_input: dict[str, Any] | None = None
    reason: str | None = ""


class WorkflowResponse(BaseModel):
    """工作流响应"""

    workflow_run_id: str
    status: WorkflowStatus
    state: dict[str, Any]


class WorkflowRunListItem(BaseModel):
    """控制台运行记录列表项"""

    id: str
    workflow_name: str
    status: WorkflowStatus
    current_node: str | None = None
    user_input: str
    started_at: datetime
    completed_at: datetime | None = None
    total_duration_ms: int | None = None


class WorkflowRunListResponse(BaseModel):
    """控制台运行记录列表响应"""

    runs: list[WorkflowRunListItem]


# ==================== Gate 状态映射 ====================

_GATE_STATUS_TO_TYPE: dict[str, str] = {
    "needs_clarification": "clarification",
    "awaiting_outline_approval": "outline_approval",
    "awaiting_fact_check_approval": "fact_check",
}
_GATE_STATUSES = set(_GATE_STATUS_TO_TYPE)


# ==================== 状态规范化 ====================


def _normalize_status(value: Any) -> WorkflowStatus:
    """将任意状态值规范化为 WorkflowStatus 枚举"""
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
    """构建统一工作流响应"""
    return WorkflowResponse(
        workflow_run_id=workflow_run_id,
        status=status,
        state=_simplify_state(state, workflow_run=workflow_run, status=status),
    )


def _get_workflow_public_status(workflow_run: Any) -> WorkflowStatus:
    """优先返回持久化的公开状态，避免列表页只能看到原始 running/paused。"""
    raw_status = _get_workflow_run_status(workflow_run)
    if raw_status in {"paused", "completed", "failed"}:
        return _normalize_status(raw_status)

    metadata = _ensure_workflow_metadata(workflow_run)
    return _normalize_status(metadata.get("last_public_status") or raw_status)


def _build_workflow_run_list_response(workflow_runs: list[Any]) -> WorkflowRunListResponse:
    """构建控制台运行记录列表响应。"""
    runs = [
        WorkflowRunListItem(
            id=workflow_run.id,
            workflow_name=getattr(workflow_run, "workflow_name", "content_generation"),
            status=_get_workflow_public_status(workflow_run),
            current_node=getattr(workflow_run, "current_node", None),
            user_input=getattr(workflow_run, "user_input", ""),
            started_at=workflow_run.started_at,
            completed_at=getattr(workflow_run, "completed_at", None),
            total_duration_ms=getattr(workflow_run, "total_duration_ms", None),
        )
        for workflow_run in workflow_runs
    ]
    return WorkflowRunListResponse(runs=runs)


# ==================== 运行时上下文 ====================


async def _get_workflow_run_if_exists(workflow_run_id: str) -> Any | None:
    """尝试获取 WorkflowRun，不存在时返回 None"""
    from services import get_artifact_store

    store = get_artifact_store()
    return await store.get_workflow_run(workflow_run_id)


async def require_workspace_permission(
    request: Request, resource: str, action: str
) -> tuple[str, str, MemberRole]:
    """基于当前 access token 和工作空间上下文校验权限。"""
    from db.postgres_store import get_postgres_store
    from routes.auth_routes import get_current_user
    from services.permission_service import PermissionService

    user = await get_current_user(request)
    user_id = user.get("sub") or user.get("id")
    workspace_id = request.state.workspace_id if hasattr(request.state, "workspace_id") else None
    if not workspace_id:
        workspace_id = user.get("default_workspace_id") or user.get("workspace_id")

    if not user_id:
        raise ApplicationError(
            code=AUTH_UNAUTHENTICATED,
            message="未登录或登录已过期",
        )
    if not workspace_id:
        raise ApplicationError(
            code=WORKSPACE_CONTEXT_REQUIRED,
            message="请先选择工作空间",
        )

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        role = await permission_service.require_permission(user_id, workspace_id, resource, action)

    return user_id, workspace_id, role


async def annotate_workflow_run_ownership(
    workflow_run_id: str, user_id: str, workspace_id: str
) -> Any | None:
    """为运行记录补充最小归属信息。"""
    from services import get_artifact_store

    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if not workflow_run:
        return None

    metadata = _ensure_workflow_metadata(workflow_run)
    metadata["workspace_id"] = workspace_id
    metadata["user_id"] = user_id
    await store.update_workflow_run(workflow_run)
    return workflow_run


def _is_admin_role(role: Any) -> bool:
    """判断角色是否拥有跨用户访问能力。"""
    if isinstance(role, MemberRole):
        return role in {MemberRole.ADMIN, MemberRole.OWNER}

    role_value = str(role)
    return role_value in {MemberRole.ADMIN.value, MemberRole.OWNER.value}


async def require_workflow_run_access(
    request: Request,
    workflow_run_id: str,
    resource: str = "workflow_run",
    action: str = "read",
) -> Any:
    """校验当前用户对 WorkflowRun 的工作空间与用户归属访问。"""
    from services import get_artifact_store

    user_id, workspace_id, role = await require_workspace_permission(request, resource, action)
    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)

    if not workflow_run:
        raise DomainError(
            code=WORKFLOW_NOT_FOUND,
            message="工作流不存在",
        )

    metadata = _ensure_workflow_metadata(workflow_run)
    run_workspace_id = metadata.get("workspace_id")
    run_user_id = metadata.get("user_id")

    if not run_workspace_id or not run_user_id:
        raise DomainError(
            code=WORKSPACE_ACCESS_DENIED,
            message="该任务缺少归属信息，暂不允许访问",
        )
    if run_workspace_id != workspace_id:
        raise DomainError(
            code=WORKSPACE_ACCESS_DENIED,
            message="您无权访问该工作空间中的任务",
        )
    if not _is_admin_role(role) and run_user_id != user_id:
        raise DomainError(
            code=WORKSPACE_ACCESS_DENIED,
            message="您只能访问自己的任务",
        )

    return workflow_run


async def require_node_run_access(request: Request, node_run_id: str) -> Any:
    """通过 NodeRun 反查 WorkflowRun 后校验访问。"""
    from services import get_artifact_store

    store = get_artifact_store()
    node_run = await store.get_node_run(node_run_id)
    if not node_run:
        raise DomainError(
            code=TRACE_RESOURCE_NOT_FOUND,
            message="NodeRun 不存在",
        )

    await require_workflow_run_access(request, node_run.workflow_run_id)
    return node_run


async def require_artifact_access(request: Request, artifact_id: str) -> Any:
    """通过 Artifact 反查 WorkflowRun 后校验访问。"""
    from services import get_artifact_store

    store = get_artifact_store()
    artifact = await store.get_artifact(artifact_id)
    if not artifact:
        raise DomainError(
            code=TRACE_RESOURCE_NOT_FOUND,
            message="Artifact 不存在",
        )

    await require_workflow_run_access(request, artifact.workflow_run_id)
    return artifact


async def _load_runtime_context(workflow_run_id: str) -> tuple[Any, Any, Any, dict, WorkflowStatus]:
    """加载工作流运行时上下文（store, workflow, workflow_run, graph_state, status）"""
    from graph import get_workflow
    from services import get_artifact_store

    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if not workflow_run:
        raise DomainError(
            code=WORKFLOW_NOT_FOUND,
            message="工作流不存在",
        )

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
    """断言工作流状态，不满足时抛出统一工作流状态异常。"""

    if current_status == "paused":
        raise ApplicationError(
            code=WORKFLOW_STATE_CONFLICT,
            message=paused_detail,
        )
    if current_status not in allowed:
        code = (
            WORKFLOW_GATE_CONFLICT if current_status in _GATE_STATUSES else WORKFLOW_STATE_CONFLICT
        )
        raise ApplicationError(
            code=code,
            message=f"当前工作流状态为 {current_status}，不能执行{action}。",
        )


# ==================== 状态简化 ====================


def _simplify_state(
    state: dict, *, workflow_run: Any | None = None, status: WorkflowStatus | None = None
) -> dict:
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
                        "word_count": len(content),
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
    if not error and workflow_run is not None:
        metadata = _ensure_workflow_metadata(workflow_run)
        error = metadata.get("error")
    if error:
        simplified["error"] = error

    pause = _normalize_pause_state(workflow_run)
    if pause:
        simplified["pause"] = pause

    gate = _normalize_gate_state(status, state, workflow_run)
    if gate:
        simplified["gate"] = gate

    return simplified


# ==================== 图状态读取 ====================


async def _get_graph_state(workflow: Any, workflow_run_id: str) -> dict:
    """从图检查点读取最新状态，失败时返回空状态"""
    config = {"configurable": {"thread_id": workflow_run_id}}
    try:
        snapshot = await workflow.graph.aget_state(config)
        if snapshot and isinstance(snapshot.values, dict):
            return snapshot.values
    except Exception:
        pass
    return {}


def _extract_workflow_status(workflow: Any, workflow_run: Any, graph_state: dict) -> str:
    """优先使用图状态推导 Gate/终态，再回退到 WorkflowRun 持久化状态"""
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
    """获取 WorkflowRun 的原始状态字符串"""
    raw_status = getattr(workflow_run, "status", "running")
    if hasattr(raw_status, "value"):
        return str(raw_status.value)
    return str(raw_status)


# ==================== 元数据工具 ====================


def _ensure_workflow_metadata(workflow_run: Any) -> dict[str, Any]:
    """确保 workflow_run 有 metadata 字典，没有则创建"""
    metadata = getattr(workflow_run, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    metadata = {}
    workflow_run.metadata = metadata
    return metadata


def _coerce_iso(value: Any) -> str | None:
    """将日期/字符串转为 ISO 格式"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _now_iso() -> str:
    """获取当前 UTC 时间的 ISO 字符串"""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ==================== 澄清问题规范化 ====================


def _map_clarification_priority(value: Any) -> str:
    """把后端数值优先级映射为前端枚举优先级"""
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
    """统一澄清问题输出结构与优先级枚举"""
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


# ==================== Pause / Gate 状态构建 ====================


def _coerce_mapping(value: Any) -> dict[str, Any]:
    """将 Pydantic 模型或 dict 转为 dict"""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return value if isinstance(value, dict) else {}


def _normalize_pause_state(workflow_run: Any | None) -> dict[str, Any] | None:
    """从 WorkflowRun 元数据构建规范化的 pause 状态"""
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
    """构建提纲审批 Gate 的问题列表"""
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
    """构建事实核查 Gate 的高风险问题列表"""
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
    """构建规范化的 Gate 状态信息"""
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


# ==================== Trace 工具函数 ====================


def _normalize_trace_payload(
    trace: dict[str, Any],
    *,
    workflow_run: Any,
    graph_state: dict,
    status: WorkflowStatus,
) -> dict[str, Any]:
    """规范化 Trace 响应载荷"""
    workflow_payload = dict(trace.get("workflow") or {})
    workflow_payload["status"] = status

    current_node = (
        graph_state.get("current_node")
        or workflow_payload.get("current_node")
        or getattr(workflow_run, "current_node", None)
    )
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
    """为 timeline 补充 pause/gate 事件"""
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
                "timestamp": gate.get("opened_at")
                or _coerce_iso(getattr(workflow_run, "started_at", None))
                or _now_iso(),
                "event": "workflow_gate_waiting",
                "gate_type": gate["gate_type"],
                "questions": gate.get("questions", []),
                "current_node": current_node,
            }
        )

    events.sort(key=lambda event: event.get("timestamp") or "")
    return events
