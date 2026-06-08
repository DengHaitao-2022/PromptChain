"""工作流 tool 节点执行器。"""

from __future__ import annotations

from typing import Any

from core.time import utc_now_iso
from graph.state import GraphState
from models import ArtifactType, NodeRun, NodeRunStatus
from services import get_artifact_store
from tools import ToolApprovalMode, ToolFailureStrategy, ToolRuntime, get_tool_executor
from tools.redaction import is_sensitive_field_name

ALLOWED_STATE_MAPPING_ROOTS = {
    "citations",
    "draft_sections",
    "evidence_artifact_id",
    "evidence_pack",
    "fact_check_artifact_id",
    "fact_check_report",
    "fact_corrections",
    "final_content",
    "final_content_artifact_id",
    "generated_content",
    "intent_card",
    "intent_card_artifact_id",
    "knowledge_conflicts",
    "manual_corrections",
    "outline",
    "outline_artifact_id",
    "outline_feedback",
    "refinement_history",
    "section_artifact_ids",
    "section_feedback",
    "tool_results",
    "unverified_points",
    "user_clarifications",
    "user_input",
}

ALLOWED_CONFIG_MAPPING_ROOTS = {
    "approvalMode",
    "approval_mode",
    "executionPhase",
    "execution_phase",
    "failureStrategy",
    "failure_strategy",
    "input",
    "inputMapping",
    "input_mapping",
    "maxAttempts",
    "max_attempts",
    "metadata",
    "outputMapping",
    "output_mapping",
    "toolName",
    "tool_name",
}


async def run_pre_outline_tools(state: GraphState) -> GraphState:
    """执行提纲生成前的工具节点。"""
    return await _run_tool_phase(state, "pre_outline", "run_pre_outline_tools")


async def run_post_content_tools(state: GraphState) -> GraphState:
    """执行正文生成后的工具节点。"""
    return await _run_tool_phase(state, "post_content", "run_post_content_tools")


async def run_pre_finalize_tools(state: GraphState) -> GraphState:
    """执行最终输出前的工具节点。"""
    return await _run_tool_phase(state, "pre_finalize", "run_pre_finalize_tools")


async def _run_tool_phase(state: GraphState, phase: str, node_name: str) -> GraphState:
    store = get_artifact_store()
    workflow_run_id = state["workflow_run_id"]
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name=node_name,
        node_type="tool",
        status=NodeRunStatus.RUNNING,
    )
    await store.create_node_run(node_run)

    tool_steps = _tool_steps_for_phase(state, phase)
    tool_results = dict(state.get("tool_results") or {})
    tool_call_ids = list(state.get("tool_call_ids") or [])
    output_artifact_ids: list[str] = []

    try:
        for step in tool_steps:
            step_id = str(step.get("id") or step.get("source_node_id") or step.get("tool_name"))
            existing = (
                tool_results.get(step_id) if isinstance(tool_results.get(step_id), dict) else {}
            )
            if existing.get("status") == "succeeded":
                continue

            tool_input = _resolve_tool_input(step, state)
            approval_mode = _coerce_approval_mode(step.get("approval_mode"))
            existing_tool_call_id = _approved_tool_call_id(existing, state)
            runtime = ToolRuntime(
                user_id=state.get("user_id"),
                workspace_id=state.get("workspace_id"),
                workflow_run_id=workflow_run_id,
                node_run_id=node_run.id,
                graph_state=dict(state),
                node_config=step.get("config") if isinstance(step.get("config"), dict) else {},
                store=store,
                role=state.get("workspace_role"),
                approval_context={
                    "phase": phase,
                    "node_name": node_name,
                    "tool_step_id": step_id,
                },
            )
            strategy = _coerce_failure_strategy(step.get("failure_strategy"))
            attempts = _resolve_step_attempts(step) if strategy == ToolFailureStrategy.RETRY else 1
            result = None
            for attempt in range(attempts):
                result = await get_tool_executor().execute(
                    str(step["tool_name"]),
                    tool_input,
                    runtime,
                    approval_mode=approval_mode,
                    existing_tool_call_id=existing_tool_call_id if attempt == 0 else None,
                )
                attempt_tool_call_id = str(result.metadata.get("tool_call_id") or "")
                if attempt_tool_call_id and attempt_tool_call_id not in tool_call_ids:
                    tool_call_ids.append(attempt_tool_call_id)
                if result.success or result.requires_approval:
                    break
                if result.error and result.error.code == "TOOL_APPROVAL_DENIED":
                    break
            assert result is not None
            tool_call_id = str(result.metadata.get("tool_call_id") or "")
            if tool_call_id and tool_call_id not in tool_call_ids:
                tool_call_ids.append(tool_call_id)

            if result.requires_approval and result.approval_request:
                tool_results[step_id] = {
                    "status": "pending_approval",
                    "tool_name": step.get("tool_name"),
                    "tool_call_id": result.approval_request.get("tool_call_id"),
                    "approval_request": result.approval_request,
                    "phase": phase,
                }
                state["tool_results"] = tool_results
                state["tool_call_ids"] = tool_call_ids
                state["awaiting_tool_approval"] = True
                await _update_tool_gate_metadata(
                    workflow_run_id,
                    {
                        "gate_type": "tool_approval",
                        "trigger_reason": "tool_risk",
                        "resume_node": node_name,
                        "resume_from_node": _tool_phase_predecessor(phase, state),
                        "tool_step_id": step_id,
                        "tool_call_id": result.approval_request.get("tool_call_id"),
                        "tool_name": step.get("tool_name"),
                        "risk_level": result.approval_request.get("risk_level"),
                        "questions": [
                            {
                                "question": "请确认是否允许执行该工具调用。",
                                "tool_name": step.get("tool_name"),
                                "tool_call_id": result.approval_request.get("tool_call_id"),
                                "risk_level": result.approval_request.get("risk_level"),
                                "input_preview": result.approval_request.get("input_preview"),
                                "action_options": ["approve", "deny"],
                            }
                        ],
                        "opened_at": utc_now_iso(),
                    },
                )
                node_run.complete(NodeRunStatus.INTERRUPTED)
                node_run.output_artifact_ids = output_artifact_ids
                await store.update_node_run(node_run)
                return state

            if not result.success:
                tool_results[step_id] = {
                    "status": "failed",
                    "tool_name": step.get("tool_name"),
                    "tool_call_id": tool_call_id or None,
                    "error": result.error.model_dump(mode="json") if result.error else None,
                    "phase": phase,
                }
                if strategy == ToolFailureStrategy.SKIP:
                    continue
                if strategy == ToolFailureStrategy.ENTER_GATE and (
                    not result.error or result.error.code != "TOOL_APPROVAL_DENIED"
                ):
                    return await _enter_tool_failure_gate(
                        state=state,
                        workflow_run_id=workflow_run_id,
                        node_run=node_run,
                        node_name=node_name,
                        phase=phase,
                        step=step,
                        step_id=step_id,
                        result=result,
                        tool_results=tool_results,
                        tool_call_ids=tool_call_ids,
                        output_artifact_ids=output_artifact_ids,
                    )
                raise RuntimeError(result.summary or "工具调用失败")

            output_artifact_ids.extend(
                await _apply_tool_result(step, result.output, state, node_run.id)
            )
            if result.state_patch:
                state.update(result.state_patch)
            tool_results[step_id] = {
                "status": "succeeded",
                "tool_name": step.get("tool_name"),
                "tool_call_id": tool_call_id or None,
                "summary": result.summary,
                "output": result.output,
                "artifact_ids": result.artifact_ids,
                "phase": phase,
            }
            output_artifact_ids.extend(result.artifact_ids)

        completed = dict(state.get("tool_phase_completed") or {})
        completed[phase] = True
        state["tool_phase_completed"] = completed
        state["tool_results"] = tool_results
        state["tool_call_ids"] = tool_call_ids
        state["awaiting_tool_approval"] = False
        await _update_tool_gate_metadata(workflow_run_id, None)
        node_run.output_artifact_ids = list(dict.fromkeys(output_artifact_ids))
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)
        return state
    except Exception as exc:
        node_run.output_artifact_ids = list(dict.fromkeys(output_artifact_ids))
        node_run.complete(NodeRunStatus.FAILED, error=str(exc))
        await store.update_node_run(node_run)
        state["error"] = str(exc)
        return state


async def _enter_tool_failure_gate(
    *,
    state: GraphState,
    workflow_run_id: str,
    node_run: NodeRun,
    node_name: str,
    phase: str,
    step: dict[str, Any],
    step_id: str,
    result: Any,
    tool_results: dict[str, Any],
    tool_call_ids: list[str],
    output_artifact_ids: list[str],
) -> GraphState:
    """将工具失败升级为 Gate，允许人工确认是否重试该工具节点。"""
    tool_call_id = str(result.metadata.get("tool_call_id") or "")
    error_payload = result.error.model_dump(mode="json") if result.error else None
    tool_results[step_id] = {
        "status": "pending_failure_gate",
        "tool_name": step.get("tool_name"),
        "tool_call_id": tool_call_id or None,
        "error": error_payload,
        "phase": phase,
    }
    state["tool_results"] = tool_results
    state["tool_call_ids"] = tool_call_ids
    state["awaiting_tool_approval"] = True
    await _update_tool_gate_metadata(
        workflow_run_id,
        {
            "gate_type": "tool_approval",
            "trigger_reason": "tool_failure",
            "resume_node": node_name,
            "resume_from_node": _tool_phase_predecessor(phase, state),
            "tool_step_id": step_id,
            "tool_call_id": tool_call_id or None,
            "tool_name": step.get("tool_name"),
            "risk_level": result.metadata.get("risk_level"),
            "questions": [
                {
                    "question": "工具执行失败，请确认是否允许从该工具调用重试。",
                    "tool_name": step.get("tool_name"),
                    "tool_call_id": tool_call_id or None,
                    "error": error_payload,
                    "action_options": ["approve", "deny"],
                }
            ],
            "opened_at": utc_now_iso(),
        },
    )
    node_run.complete(NodeRunStatus.INTERRUPTED)
    node_run.output_artifact_ids = output_artifact_ids
    await get_artifact_store().update_node_run(node_run)
    return state


def _tool_steps_for_phase(state: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    plan = state.get("runtime_plan")
    if not isinstance(plan, dict):
        return []
    steps = plan.get("tool_steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict) and step.get("phase") == phase]


def _resolve_tool_input(step: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    static_input = step.get("input") if isinstance(step.get("input"), dict) else {}
    tool_input = dict(static_input)
    mapping = step.get("input_mapping")
    if isinstance(mapping, dict):
        for field, source in mapping.items():
            tool_input[str(field)] = _resolve_mapping_value(source, state, step)
    if not tool_input:
        tool_name = str(step.get("tool_name") or "")
        if tool_name == "retrieval.query_workspace_knowledge":
            tool_input["query"] = state.get("user_input") or ""
        elif tool_name in {"content.style_check", "fact.check_claims"}:
            tool_input["content"] = state.get("generated_content") or _join_sections(state)
        elif tool_name == "content.outline_consistency_check" and state.get("outline"):
            outline = state["outline"]
            tool_input["outline"] = (
                outline.model_dump(mode="json") if hasattr(outline, "model_dump") else outline
            )
    return tool_input


def _resolve_mapping_value(source: Any, state: dict[str, Any], step: dict[str, Any]) -> Any:
    if isinstance(source, dict):
        source_type = source.get("source") or "state"
        path = source.get("path")
        if source_type == "literal":
            return source.get("value")
        _assert_mapping_path_allowed(str(source_type), str(path or ""))
        if source_type == "config":
            return _resolve_path(step.get("config"), str(path or ""))
        if source_type == "state":
            return _resolve_path(state, str(path or ""))
        raise ValueError(f"不支持的工具输入映射来源: {source_type}")
    if isinstance(source, str):
        if source.startswith("$"):
            source = source[1:]
        if source.startswith("state."):
            path = source[6:]
            _assert_mapping_path_allowed("state", path)
            return _resolve_path(state, path)
        if source.startswith("config."):
            path = source[7:]
            _assert_mapping_path_allowed("config", path)
            return _resolve_path(step.get("config"), path)
        _assert_mapping_path_allowed("state", source)
        return _resolve_path(state, source)
    return source


def _assert_mapping_path_allowed(source_type: str, path: str) -> None:
    parts = [item for item in path.split(".") if item]
    if not parts:
        raise ValueError("工具输入映射必须指定明确路径")
    if any(is_sensitive_field_name(part) for part in parts):
        raise ValueError("工具输入映射禁止读取敏感字段")

    root = parts[0]
    if source_type == "state" and root not in ALLOWED_STATE_MAPPING_ROOTS:
        raise ValueError(f"工具输入映射不允许读取 state.{root}")
    if source_type == "config" and root not in ALLOWED_CONFIG_MAPPING_ROOTS:
        raise ValueError(f"工具输入映射不允许读取 config.{root}")


def _resolve_path(root: Any, path: str) -> Any:
    value = root
    for part in [item for item in path.split(".") if item]:
        if is_sensitive_field_name(part):
            raise ValueError("工具输入映射禁止读取敏感字段")
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


async def _apply_tool_result(
    step: dict[str, Any],
    output: Any,
    state: dict[str, Any],
    node_run_id: str,
) -> list[str]:
    mapping = step.get("output_mapping")
    if not isinstance(mapping, dict):
        return []
    state_key = mapping.get("stateKey") or mapping.get("state_key")
    if isinstance(state_key, str) and state_key:
        state[state_key] = output
    state_fields = mapping.get("stateFields") or mapping.get("state_fields")
    if isinstance(state_fields, dict):
        for target_key, output_path in state_fields.items():
            state[str(target_key)] = _resolve_path(output, str(output_path))
    if not (mapping.get("persistArtifact") or mapping.get("persist_artifact")):
        return []

    store = get_artifact_store()
    artifact = await store.create_artifact(
        artifact_type=_artifact_type(mapping.get("artifactType") or mapping.get("artifact_type")),
        content=output,
        workflow_run_id=state["workflow_run_id"],
        node_run_id=node_run_id,
        metadata={
            "source": "tool_output_mapping",
            "tool_name": step.get("tool_name"),
            "source_node_id": step.get("source_node_id"),
        },
    )
    return [artifact.id]


def _artifact_type(value: Any) -> ArtifactType:
    try:
        return ArtifactType(str(value or ArtifactType.TOOL_RESULT.value))
    except ValueError:
        return ArtifactType.TOOL_RESULT


def _join_sections(state: dict[str, Any]) -> str:
    sections = state.get("draft_sections")
    if isinstance(sections, dict):
        return "\n\n".join(str(value) for value in sections.values())
    return ""


def _tool_phase_predecessor(phase: str, state: dict[str, Any]) -> str:
    """返回恢复工具节点时应标记的上游节点，确保审批后会重新执行工具节点。"""
    if phase == "pre_outline":
        return "retrieve_knowledge"
    if phase == "post_content":
        return "generate_content"
    if state.get("fact_check_decisions") or state.get("manual_corrections"):
        return "approve_fact_check"
    if state.get("fact_check_report") is not None:
        return "check_facts"
    if state.get("refinement_history"):
        return "self_refine"
    return "generate_content"


def _approved_tool_call_id(existing: dict[str, Any], state: dict[str, Any]) -> str | None:
    tool_call_id = existing.get("tool_call_id")
    approvals = state.get("tool_approvals")
    if not tool_call_id or not isinstance(approvals, dict):
        return None
    decision = approvals.get(str(tool_call_id))
    return str(tool_call_id) if decision in {"approve", "approved", "deny", "denied"} else None


def _coerce_approval_mode(value: Any) -> ToolApprovalMode:
    try:
        return ToolApprovalMode(str(value or ToolApprovalMode.POLICY_DEFAULT.value))
    except ValueError:
        return ToolApprovalMode.POLICY_DEFAULT


def _coerce_failure_strategy(value: Any) -> ToolFailureStrategy:
    try:
        return ToolFailureStrategy(str(value or ToolFailureStrategy.TERMINATE.value))
    except ValueError:
        return ToolFailureStrategy.TERMINATE


def _resolve_step_attempts(step: dict[str, Any]) -> int:
    """解析 tool 节点级重试次数，避免失败策略 retry 退化为单次执行。"""
    config = step.get("config") if isinstance(step.get("config"), dict) else {}
    raw_attempts = (
        step.get("max_attempts")
        or config.get("maxAttempts")
        or config.get("max_attempts")
        or config.get("retryAttempts")
        or config.get("retry_attempts")
        or 2
    )
    try:
        attempts = int(raw_attempts)
    except (TypeError, ValueError):
        attempts = 2
    return max(1, min(attempts, 5))


async def _update_tool_gate_metadata(workflow_run_id: str, gate_payload: dict | None) -> None:
    store = get_artifact_store()
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if workflow_run is None:
        return
    metadata = dict(workflow_run.metadata or {})
    if gate_payload is None:
        metadata.pop("gate", None)
    else:
        metadata["gate"] = gate_payload
    workflow_run.metadata = metadata
    await store.update_workflow_run(workflow_run)
