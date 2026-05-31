"""
内容工作流 API 工具函数

提供状态规范化、响应构建、Gate/Pause 状态处理等共享逻辑
"""

import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Request
from pydantic import BaseModel, Field

from core.errors.codes import (
    AUTH_UNAUTHENTICATED,
    WORKFLOW_GATE_CONFLICT,
    WORKFLOW_NOT_FOUND,
    WORKFLOW_STATE_CONFLICT,
    WORKSPACE_ACCESS_DENIED,
    WORKSPACE_CONTEXT_REQUIRED,
)
from core.errors.exceptions import ApplicationError, DomainError
from core.time import to_utc_iso, to_utc_iso_or_none
from graph.runtime_plan import canonical_runtime_plan
from models.auth_models import MemberRole
from models.knowledge import RetrievalConfig

logger = logging.getLogger(__name__)

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
    model_provider_id: str | None = None
    model_name: str | None = None
    retrieval_config: RetrievalConfig | None = None


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
    final_artifact_id: str | None = None
    quality_metrics: dict[str, Any] | None = None
    state: dict[str, Any]


class WorkflowRunListItem(BaseModel):
    """控制台运行记录列表项"""

    id: str
    workflow_name: str
    status: WorkflowStatus
    current_node: str | None = None
    workflow_definition_id: str | None = None
    workflow_version_id: str | None = None
    final_artifact_id: str | None = None
    runtime_model: dict[str, Any] | None = None
    runtime_plan: dict[str, Any] | None = None
    runtime_progress: dict[str, Any] | None = None
    quality_metrics: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None
    pause: dict[str, Any] | None = None
    model_provider_id: str | None = None
    model_name: str | None = None
    error: str | None = None
    user_input: str
    started_at: str
    completed_at: str | None = None
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
_GATE_TYPE_ALIASES: dict[str, str] = {
    "fact_check_approval": "fact_check",
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
    viewer_user_id: str | None = None,
) -> WorkflowResponse:
    """构建统一工作流响应"""
    simplified_state = _simplify_state(
        state,
        workflow_run=workflow_run,
        status=status,
        viewer_user_id=viewer_user_id,
    )
    return WorkflowResponse(
        workflow_run_id=workflow_run_id,
        status=status,
        final_artifact_id=simplified_state.get("final_artifact_id"),
        quality_metrics=simplified_state.get("quality_metrics"),
        state=simplified_state,
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
    runs: list[WorkflowRunListItem] = []
    for workflow_run in workflow_runs:
        metadata = _ensure_workflow_metadata(workflow_run)
        status = _get_workflow_public_status(workflow_run)
        runtime_plan = _runtime_plan({}, workflow_run)
        runs.append(
            WorkflowRunListItem(
                id=workflow_run.id,
                workflow_name=getattr(workflow_run, "workflow_name", "content_generation"),
                status=status,
                current_node=getattr(workflow_run, "current_node", None),
                workflow_definition_id=getattr(workflow_run, "workflow_definition_id", None),
                workflow_version_id=getattr(workflow_run, "workflow_version_id", None),
                final_artifact_id=getattr(workflow_run, "final_artifact_id", None),
                runtime_model=metadata.get("runtime_model"),
                runtime_plan=runtime_plan,
                runtime_progress=_runtime_progress({}, workflow_run, status=status),
                quality_metrics=_quality_metrics(workflow_run),
                gate=_normalize_gate_state(status, {}, workflow_run),
                pause=_normalize_pause_state(workflow_run),
                model_provider_id=metadata.get("model_provider_id"),
                model_name=metadata.get("model_name"),
                error=metadata.get("error"),
                user_input=getattr(workflow_run, "user_input", ""),
                started_at=to_utc_iso(workflow_run.started_at),
                completed_at=to_utc_iso_or_none(getattr(workflow_run, "completed_at", None)),
                total_duration_ms=getattr(workflow_run, "total_duration_ms", None),
            )
        )
    return WorkflowRunListResponse(runs=runs)


def _runtime_plan(state: dict, workflow_run: Any | None = None) -> dict[str, Any]:
    """返回当前运行实例实际采用的受限运行计划。"""
    plan = state.get("runtime_plan")
    if isinstance(plan, dict):
        return plan

    if workflow_run is not None:
        metadata = _ensure_workflow_metadata(workflow_run)
        metadata_plan = metadata.get("runtime_plan")
        if isinstance(metadata_plan, dict):
            return metadata_plan

    return canonical_runtime_plan()


def _normalize_definition_plan(workflow_context: Any) -> dict[str, Any] | None:
    """从已发布工作流上下文提取前端可渲染的编排节点。"""
    context = _coerce_mapping(workflow_context)
    if not context:
        return None

    nodes = context.get("nodes")
    if not isinstance(nodes, list):
        nodes = []

    normalized_nodes: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        data = _coerce_mapping(node.get("data"))
        normalized_nodes.append(
            {
                "id": node.get("id"),
                "name": node.get("id"),
                "label": data.get("label") or node.get("id"),
                "type": node.get("type"),
            }
        )

    return {
        "workflow_definition_id": context.get("workflow_definition_id"),
        "workflow_version_id": context.get("workflow_version_id"),
        "definition_name": context.get("definition_name"),
        "definition_description": context.get("definition_description"),
        "version": context.get("version"),
        "nodes": normalized_nodes,
        "execution_mode": "published_dsl_runtime",
        "execution_note": "已发布编排定义会编译为当前引擎支持的受限运行计划；暂未支持的节点类型按五类运行时能力映射执行。",
    }


def _runtime_progress(
    state: dict,
    workflow_run: Any | None = None,
    *,
    status: WorkflowStatus | None = None,
) -> dict[str, Any]:
    """基于运行计划构建前端可直接消费的动态进度摘要。"""
    plan = _runtime_plan(state, workflow_run)
    steps = plan.get("steps")
    normalized_steps: list[dict[str, Any]] = []
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            normalized_steps.append(
                {
                    "id": step.get("id"),
                    "label": step.get("label") or step.get("name") or step.get("id"),
                    "runtime_type": step.get("runtime_type"),
                    "source_node_id": step.get("source_node_id"),
                    "source_node_label": step.get("source_node_label"),
                    "index": index,
                }
            )

    current_node = state.get("current_node") or getattr(workflow_run, "current_node", None)
    current_step_index = next(
        (
            step["index"]
            for step in normalized_steps
            if current_node is not None and step.get("id") == current_node
        ),
        None,
    )
    total_steps = len(normalized_steps)

    if status == "completed":
        completed_step_count = total_steps
    elif isinstance(current_step_index, int):
        completed_step_count = current_step_index
    else:
        completed_step_count = 0

    percent = (
        round((completed_step_count / total_steps) * 100)
        if total_steps > 0
        else (100 if status == "completed" else 0)
    )

    return {
        "execution_mode": plan.get("execution_mode"),
        "current_step_id": current_node,
        "current_step_index": current_step_index,
        "completed_step_count": completed_step_count,
        "total_steps": total_steps,
        "percent": max(0, min(100, percent)),
        "features": plan.get("features") if isinstance(plan.get("features"), dict) else {},
        "warnings": plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
        "steps": normalized_steps,
    }


def _quality_metrics(workflow_run: Any | None) -> dict[str, Any] | None:
    """读取运行质量指标；历史运行缺少聚合时返回最小统计兜底。"""
    if workflow_run is None:
        return None

    metadata = _ensure_workflow_metadata(workflow_run)
    metrics = metadata.get("quality_metrics")
    if isinstance(metrics, dict):
        return metrics

    return {
        "average_quality_score": None,
        "quality_score_count": 0,
        "revisions_requested": 0,
        "fact_check": None,
        "tokens": {
            "total": getattr(workflow_run, "total_tokens", 0),
            "llm_call_count": getattr(workflow_run, "total_llm_calls", 0),
        },
        "latency": {
            "total_node_duration_ms": getattr(workflow_run, "total_duration_ms", 0),
            "average_llm_latency_ms": None,
        },
        "final_artifact_id": getattr(workflow_run, "final_artifact_id", None),
        "final_content_hash": None,
    }


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
        raise ApplicationError(code=AUTH_UNAUTHENTICATED, message="未登录或登录已过期")
    if not workspace_id:
        raise ApplicationError(code=WORKSPACE_CONTEXT_REQUIRED, message="请先选择工作空间")

    store = get_postgres_store()
    async with store.async_session() as session:
        permission_service = PermissionService(session)
        role = await permission_service.require_permission(user_id, workspace_id, resource, action)

    request.state.auth_user_id = user_id
    request.state.workspace_id = workspace_id
    request.state.workspace_role = role
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
        raise DomainError(code=WORKFLOW_NOT_FOUND, message="工作流不存在")

    metadata = _ensure_workflow_metadata(workflow_run)
    run_workspace_id = metadata.get("workspace_id")
    run_user_id = metadata.get("user_id")

    if not run_workspace_id or not run_user_id:
        raise DomainError(
            code=WORKSPACE_ACCESS_DENIED,
            message="该任务缺少归属信息，暂不允许访问",
        )
    if run_workspace_id != workspace_id:
        raise DomainError(code=WORKSPACE_ACCESS_DENIED, message="您无权访问该工作空间中的任务")
    if not _is_admin_role(role) and run_user_id != user_id:
        raise DomainError(code=WORKSPACE_ACCESS_DENIED, message="您只能访问自己的任务")

    return workflow_run


async def require_node_run_access(request: Request, node_run_id: str) -> Any:
    """通过 NodeRun 反查 WorkflowRun 后校验访问。"""
    from services import get_artifact_store

    store = get_artifact_store()
    node_run = await store.get_node_run(node_run_id)
    if not node_run:
        raise DomainError(code=WORKFLOW_NOT_FOUND, message="节点运行记录不存在")

    await require_workflow_run_access(request, node_run.workflow_run_id)
    return node_run


async def require_artifact_access(request: Request, artifact_id: str) -> Any:
    """通过 Artifact 反查 WorkflowRun 后校验访问。"""
    from services import get_artifact_store

    store = get_artifact_store()
    artifact = await store.get_artifact(artifact_id)
    if not artifact:
        raise DomainError(code=WORKFLOW_NOT_FOUND, message="产物不存在")

    await require_workflow_run_access(request, artifact.workflow_run_id)
    return artifact


async def _load_runtime_context(workflow_run_id: str) -> tuple[Any, Any, Any, dict, WorkflowStatus]:
    """加载工作流运行时上下文（store, workflow, workflow_run, graph_state, status）"""
    from graph import get_workflow
    from services import get_artifact_store

    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if not workflow_run:
        raise DomainError(code=WORKFLOW_NOT_FOUND, message="工作流不存在")

    workflow = get_workflow()
    graph_state = await _get_graph_state(workflow, workflow_run_id)
    if graph_state.get("state_read_error"):
        # checkpoint 读取失败只记录诊断信息，不把一次读路径异常固化成终态失败。
        metadata = _ensure_workflow_metadata(workflow_run)
        metadata["error"] = graph_state.get("error")
        metadata["state_read_error"] = graph_state.get("state_read_error")
        workflow_run.metadata = metadata
        await store.update_workflow_run(workflow_run)
    status = _extract_workflow_status(workflow, workflow_run, graph_state)
    return store, workflow, workflow_run, graph_state, status


def _assert_status(
    current_status: WorkflowStatus,
    *,
    allowed: set[WorkflowStatus],
    action: str,
    paused_detail: str,
) -> None:
    """断言工作流状态，不满足时抛出 HTTPException"""
    if current_status == "paused":
        raise DomainError(code=WORKFLOW_GATE_CONFLICT, message=paused_detail)
    if current_status not in allowed:
        raise DomainError(
            code=WORKFLOW_STATE_CONFLICT,
            message=f"当前工作流状态为 {current_status}，不能执行{action}。",
        )


def get_request_user_id(request: Request) -> str | None:
    """读取已认证请求用户，用于响应脱敏等只读后处理。"""
    return getattr(request.state, "auth_user_id", None)


def _workflow_owner_user_id(workflow_run: Any | None) -> str | None:
    """读取运行发起人，优先使用归属元数据。"""
    if workflow_run is None:
        return None
    metadata = getattr(workflow_run, "metadata", None)
    if isinstance(metadata, dict):
        owner_user_id = metadata.get("user_id")
        if owner_user_id:
            return str(owner_user_id)
    owner_user_id = getattr(workflow_run, "user_id", None)
    return str(owner_user_id) if owner_user_id else None


def _should_redact_personal_evidence(
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> bool:
    """非运行发起人查看 Trace 时，不透出 personal scope 原文。"""
    owner_user_id = _workflow_owner_user_id(workflow_run)
    return bool(owner_user_id and viewer_user_id and owner_user_id != viewer_user_id)


def _redact_evidence_pack_for_viewer(
    evidence_pack: Any,
    *,
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> Any:
    """按当前查看者权限脱敏 Evidence Pack 中的个人知识库原文。"""
    if hasattr(evidence_pack, "model_dump"):
        data = evidence_pack.model_dump(mode="json")
    elif isinstance(evidence_pack, dict):
        data = deepcopy(evidence_pack)
    else:
        return evidence_pack

    if not _should_redact_personal_evidence(workflow_run, viewer_user_id):
        return data

    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        return data

    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        if str(chunk.get("scope")) != "personal":
            continue
        chunk["document_name"] = "个人知识库资料"
        chunk["content"] = "该证据来自运行发起人的个人知识库，当前账号无权查看原文。"
        chunk["heading_path"] = []
        chunk["page_number"] = None
        chunk["metadata"] = {}
        chunk["redacted"] = True

    return data


def _redact_artifact_payload_for_viewer(
    artifact_payload: dict[str, Any],
    *,
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> dict[str, Any]:
    """脱敏 Artifact 响应中的 Evidence Pack 内容。"""
    if artifact_payload.get("type") != "evidence_pack":
        return artifact_payload

    redacted = deepcopy(artifact_payload)
    redacted["content"] = _redact_evidence_pack_for_viewer(
        redacted.get("content"),
        workflow_run=workflow_run,
        viewer_user_id=viewer_user_id,
    )
    return redacted


def redact_trace_payload_for_viewer(
    payload: dict[str, Any],
    *,
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> dict[str, Any]:
    """脱敏 Trace 载荷中所有 Evidence Artifact。"""
    if not _should_redact_personal_evidence(workflow_run, viewer_user_id):
        return payload

    redacted = deepcopy(payload)
    artifacts = redacted.get("artifacts")
    if isinstance(artifacts, dict):
        for artifact_id, artifact_payload in list(artifacts.items()):
            if isinstance(artifact_payload, dict):
                artifacts[artifact_id] = _redact_artifact_payload_for_viewer(
                    artifact_payload,
                    workflow_run=workflow_run,
                    viewer_user_id=viewer_user_id,
                )
    return redacted


def redact_node_detail_for_viewer(
    detail: dict[str, Any],
    *,
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> dict[str, Any]:
    """脱敏节点详情中的输入、输出与版本历史 Artifact。"""
    if not _should_redact_personal_evidence(workflow_run, viewer_user_id):
        return detail

    redacted = deepcopy(detail)
    for collection_key in ("input_artifacts", "output_artifacts"):
        artifacts = redacted.get(collection_key)
        if not isinstance(artifacts, list):
            continue
        for index, artifact_payload in enumerate(artifacts):
            if not isinstance(artifact_payload, dict):
                continue
            artifacts[index] = _redact_artifact_payload_for_viewer(
                artifact_payload,
                workflow_run=workflow_run,
                viewer_user_id=viewer_user_id,
            )
            history = artifacts[index].get("version_history")
            if isinstance(history, list):
                artifacts[index]["version_history"] = [
                    _redact_artifact_payload_for_viewer(
                        item,
                        workflow_run=workflow_run,
                        viewer_user_id=viewer_user_id,
                    )
                    if isinstance(item, dict)
                    else item
                    for item in history
                ]
    return redacted


def redact_artifact_history_for_viewer(
    history: list[dict[str, Any]],
    *,
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> list[dict[str, Any]]:
    """脱敏 Artifact 历史响应中的 Evidence Pack 内容。"""
    if not _should_redact_personal_evidence(workflow_run, viewer_user_id):
        return history

    return [
        _redact_artifact_payload_for_viewer(
            item,
            workflow_run=workflow_run,
            viewer_user_id=viewer_user_id,
        )
        if isinstance(item, dict)
        else item
        for item in history
    ]


def redact_rerun_options_for_viewer(
    options: list[dict[str, Any]],
    *,
    workflow_run: Any | None,
    viewer_user_id: str | None,
) -> list[dict[str, Any]]:
    """脱敏重跑选项中随节点返回的 Evidence Artifact。"""
    if not _should_redact_personal_evidence(workflow_run, viewer_user_id):
        return options

    redacted = deepcopy(options)
    for option in redacted:
        if not isinstance(option, dict):
            continue
        artifacts = option.get("output_artifacts")
        if not isinstance(artifacts, list):
            continue
        option["output_artifacts"] = [
            _redact_artifact_payload_for_viewer(
                artifact,
                workflow_run=workflow_run,
                viewer_user_id=viewer_user_id,
            )
            if isinstance(artifact, dict)
            else artifact
            for artifact in artifacts
        ]
    return redacted


# ==================== 状态简化 ====================


def _simplify_state(
    state: dict,
    *,
    workflow_run: Any | None = None,
    status: WorkflowStatus | None = None,
    viewer_user_id: str | None = None,
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
        elif key == "evidence_pack":
            raw_value = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            simplified[key] = _redact_evidence_pack_for_viewer(
                raw_value,
                workflow_run=workflow_run,
                viewer_user_id=viewer_user_id,
            )
        elif key == "retrieval_config":
            if hasattr(value, "model_dump"):
                simplified[key] = value.model_dump(mode="json")
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

    simplified["runtime_plan"] = _runtime_plan(state, workflow_run)
    simplified["runtime_progress"] = _runtime_progress(state, workflow_run, status=status)
    if workflow_run is not None:
        metadata = _ensure_workflow_metadata(workflow_run)
        runtime_model = metadata.get("runtime_model")
        if isinstance(runtime_model, dict):
            simplified["runtime_model"] = runtime_model
        quality_metrics = _quality_metrics(workflow_run)
        if quality_metrics:
            simplified["quality_metrics"] = quality_metrics
    definition_plan = _normalize_definition_plan(state.get("workflow_context"))
    if definition_plan:
        simplified["definition_plan"] = definition_plan

    error = state.get("error")
    if not error and workflow_run is not None:
        metadata = _ensure_workflow_metadata(workflow_run)
        error = metadata.get("error")
    if error:
        simplified["error"] = error

    final_artifact_id = state.get("final_content_artifact_id") or getattr(
        workflow_run, "final_artifact_id", None
    )
    if final_artifact_id:
        simplified["final_content_artifact_id"] = final_artifact_id
        simplified["final_artifact_id"] = final_artifact_id

    pause = _normalize_pause_state(workflow_run, state=state)
    if pause:
        simplified["pause"] = pause

    gate = _normalize_gate_state(status, state, workflow_run)
    if gate:
        simplified["gate"] = gate

    return simplified


# ==================== 图状态读取 ====================


async def _get_graph_state(workflow: Any, workflow_run_id: str) -> dict:
    """从图检查点读取最新状态，失败时返回显式错误状态。"""
    config = {"configurable": {"thread_id": workflow_run_id}}
    try:
        snapshot = await workflow.graph.aget_state(config)
        if snapshot and isinstance(snapshot.values, dict):
            return snapshot.values
    except Exception as exc:
        logger.exception("读取工作流 checkpoint 状态失败: workflow_run_id=%s", workflow_run_id)
        return {
            "error": "工作流状态读取失败，请检查运行时 checkpoint 存储。",
            "state_read_error": {
                "type": exc.__class__.__name__,
                "source": "checkpoint",
            },
        }
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
        if graph_state.get("error") and not graph_state.get("state_read_error"):
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
        return to_utc_iso(value)
    return str(value)


def _duration_between_iso(start: str | None, end: str | None) -> int | None:
    """计算两个 ISO 时间之间的耗时，统一以毫秒返回。"""
    if not start or not end:
        return None

    def _parse(value: str) -> datetime:
        text = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    return int((_parse(end) - _parse(start)).total_seconds() * 1000)


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


def _normalize_pause_state(
    workflow_run: Any | None, *, state: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """从图状态和 WorkflowRun 元数据构建规范化的 pause 状态。"""
    state_pause = _coerce_mapping(state.get("pause")) if isinstance(state, dict) else {}
    metadata: dict[str, Any] = {}
    metadata_pause: dict[str, Any] = {}
    if workflow_run is not None:
        metadata = _ensure_workflow_metadata(workflow_run)
        metadata_pause = _coerce_mapping(metadata.get("pause"))

    if state_pause:
        # 图状态优先，但用持久化 metadata 补齐 resumed_at/source 等历史字段。
        pause_state = {**metadata_pause, **state_pause}
        return {
            "reason": pause_state.get("reason"),
            "paused_at": _coerce_iso(pause_state.get("paused_at")),
            "resumed_at": _coerce_iso(pause_state.get("resumed_at")),
            "source": pause_state.get("source") or "user",
        }

    if workflow_run is None:
        return None

    if metadata_pause:
        return {
            "reason": metadata_pause.get("reason"),
            "paused_at": _coerce_iso(metadata_pause.get("paused_at")),
            "resumed_at": _coerce_iso(metadata_pause.get("resumed_at")),
            "source": metadata_pause.get("source") or "user",
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
    raw_gate_type = gate_metadata.get("gate_type") or _GATE_STATUS_TO_TYPE[status]
    gate_type = _GATE_TYPE_ALIASES.get(str(raw_gate_type), str(raw_gate_type))

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

    opened_at = _coerce_iso(gate_metadata.get("opened_at"))
    handled_at = _coerce_iso(gate_metadata.get("handled_at"))

    return {
        "gate_type": gate_type,
        "trigger_reason": trigger_reason,
        "questions": questions,
        "answers": answers or gate_metadata.get("answers"),
        "opened_at": opened_at,
        "handled_at": handled_at,
        "waiting_duration_ms": _duration_between_iso(opened_at, handled_at),
        "resolution": gate_metadata.get("resolution"),
    }


# ==================== Trace 工具函数 ====================


def _normalize_trace_payload(
    trace: dict[str, Any],
    *,
    workflow_run: Any,
    graph_state: dict,
    status: WorkflowStatus,
    viewer_user_id: str | None = None,
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

    runtime_plan = _runtime_plan(graph_state, workflow_run)
    workflow_payload["runtime_plan"] = runtime_plan
    workflow_payload["runtime_progress"] = _runtime_progress(
        graph_state,
        workflow_run,
        status=status,
    )
    metadata = _ensure_workflow_metadata(workflow_run)
    runtime_model = metadata.get("runtime_model")
    if isinstance(runtime_model, dict):
        workflow_payload["runtime_model"] = runtime_model
    quality_metrics = _quality_metrics(workflow_run)
    if quality_metrics:
        workflow_payload["quality_metrics"] = quality_metrics

    final_artifact_id = graph_state.get("final_content_artifact_id") or getattr(
        workflow_run,
        "final_artifact_id",
        None,
    )
    if final_artifact_id:
        workflow_payload["final_artifact_id"] = final_artifact_id

    pause = _normalize_pause_state(workflow_run)
    if pause:
        workflow_payload["pause"] = pause

    gate = _normalize_gate_state(status, graph_state, workflow_run)
    if gate:
        workflow_payload["gate"] = gate

    error = graph_state.get("error")
    if error:
        workflow_payload["error"] = error

    payload = {
        **trace,
        "workflow": workflow_payload,
        "timeline": _enrich_timeline(trace.get("timeline", []), workflow_run, graph_state, status),
    }
    return redact_trace_payload_for_viewer(
        payload,
        workflow_run=workflow_run,
        viewer_user_id=viewer_user_id,
    )


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
    gate_opened_at = None
    if gate:
        gate_opened_at = gate.get("opened_at") or _infer_gate_opened_at_from_timeline(events)

    if gate and gate_opened_at and "workflow_gate_waiting" not in event_names:
        events.append(
            {
                "timestamp": gate_opened_at,
                "event": "workflow_gate_waiting",
                "gate_type": gate["gate_type"],
                "questions": gate.get("questions", []),
                "current_node": current_node,
            }
        )

    events.sort(key=_timeline_sort_key)
    return events


def _timeline_sort_key(event: dict[str, Any]) -> tuple[int, float]:
    """将 timeline 事件按真实时间排序，避免字符串排序导致时序漂移。"""
    raw_timestamp = event.get("timestamp")
    if not raw_timestamp:
        return (1, float("inf"))
    if isinstance(raw_timestamp, datetime):
        timestamp = raw_timestamp if raw_timestamp.tzinfo else raw_timestamp.replace(tzinfo=UTC)
        return (0, timestamp.timestamp())

    text = str(raw_timestamp)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return (0, parsed.timestamp())
    except ValueError:
        return (1, float("inf"))


def _infer_gate_opened_at_from_timeline(events: list[dict[str, Any]]) -> str | None:
    """兼容旧数据：缺少 opened_at 时，回退到最近一次节点完成时间。"""
    completed_events = [
        event
        for event in events
        if event.get("event") == "node_completed" and event.get("timestamp")
    ]
    if not completed_events:
        return None
    completed_events.sort(key=_timeline_sort_key)
    return str(completed_events[-1]["timestamp"])
