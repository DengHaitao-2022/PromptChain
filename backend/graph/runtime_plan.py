"""
工作流 DSL 运行计划编译

把已发布的可视化工作流定义编译为当前内容生成引擎可执行的受限运行计划。
"""

from __future__ import annotations

from typing import Any

_RUNTIME_NODE_TYPE_ALIASES: dict[str, str] = {
    "start": "input",
    "prompt": "input",
    "end": "output",
    "task": "process",
    "llm": "process",
    "agent_step": "process",
    "tool": "process",
    "tool_call": "process",
    "knowledge": "process",
    "rag_retrieve": "process",
    "rerank": "process",
    "output_parser": "process",
    "memory_read": "process",
    "memory_write": "process",
    "http": "process",
    "sql": "process",
    "function": "process",
    "webhook": "process",
    "queue_publish": "process",
    "email": "process",
    "slack": "process",
    "im": "process",
    "file_loader": "process",
    "code": "process",
    "delay": "process",
    "subflow": "process",
    "switch": "gate",
    "condition": "gate",
    "if_else": "gate",
    "loop": "gate",
    "parallel": "gate",
    "merge": "gate",
    "retry_gate": "gate",
    "approval": "gate",
    "review": "gate",
    "edit": "gate",
    "assign": "gate",
    "human_approval": "gate",
    "fact_check": "checker",
}

_CANONICAL_STEP_DEFINITIONS: dict[str, dict[str, str]] = {
    "parse_intent": {
        "id": "parse_intent",
        "name": "parse_intent",
        "label": "意图解析",
        "runtime_type": "process",
    },
    "generate_outline": {
        "id": "generate_outline",
        "name": "generate_outline",
        "label": "提纲生成",
        "runtime_type": "process",
    },
    "approve_outline": {
        "id": "approve_outline",
        "name": "approve_outline",
        "label": "提纲审批",
        "runtime_type": "gate",
    },
    "generate_content": {
        "id": "generate_content",
        "name": "generate_content",
        "label": "内容生成",
        "runtime_type": "process",
    },
    "self_refine": {
        "id": "self_refine",
        "name": "self_refine",
        "label": "自检修订",
        "runtime_type": "process",
    },
    "check_facts": {
        "id": "check_facts",
        "name": "check_facts",
        "label": "事实核查",
        "runtime_type": "checker",
    },
    "approve_fact_check": {
        "id": "approve_fact_check",
        "name": "approve_fact_check",
        "label": "事实核查审批",
        "runtime_type": "gate",
    },
    "finalize": {
        "id": "finalize",
        "name": "finalize",
        "label": "最终输出",
        "runtime_type": "output",
    },
}

_DEFAULT_CANONICAL_ORDER: tuple[str, ...] = (
    "parse_intent",
    "generate_outline",
    "approve_outline",
    "generate_content",
    "self_refine",
    "check_facts",
    "approve_fact_check",
    "finalize",
)


def canonical_runtime_plan() -> dict[str, Any]:
    """返回未绑定可视化定义时的默认运行计划。"""
    return {
        "execution_mode": "canonical_runtime",
        "steps": [_step(step_id) for step_id in _DEFAULT_CANONICAL_ORDER],
        "features": {
            "outline_gate": True,
            "self_refine": True,
            "fact_check": True,
            "fact_check_gate": True,
        },
        "warnings": [],
    }


def compile_workflow_runtime_plan(workflow_context: dict[str, Any] | None) -> dict[str, Any]:
    """把已发布工作流上下文编译成当前执行器可消费的运行计划。"""
    if not workflow_context:
        return canonical_runtime_plan()

    nodes = [node for node in workflow_context.get("nodes") or [] if isinstance(node, dict)]
    edges = [edge for edge in workflow_context.get("edges") or [] if isinstance(edge, dict)]
    if not nodes:
        plan = canonical_runtime_plan()
        plan["warnings"] = ["已发布工作流缺少节点定义，已回退到默认内容生成链路。"]
        return _with_context_metadata(plan, workflow_context)

    ordered_nodes = _topological_nodes(nodes, edges)
    typed_nodes = [_normalize_node(node, index) for index, node in enumerate(ordered_nodes)]
    input_nodes = [node for node in typed_nodes if node["runtime_type"] == "input"]
    process_nodes = [node for node in typed_nodes if node["runtime_type"] == "process"]
    gate_nodes = [node for node in typed_nodes if node["runtime_type"] == "gate"]
    checker_nodes = [node for node in typed_nodes if node["runtime_type"] == "checker"]
    output_nodes = [node for node in typed_nodes if node["runtime_type"] == "output"]

    checker_index = checker_nodes[0]["order"] if checker_nodes else None
    outline_gate = _first_gate(gate_nodes, before_index=checker_index)
    fact_gate = (
        _first_gate(gate_nodes, after_index=checker_index) if checker_index is not None else None
    )

    steps: list[dict[str, Any]] = [
        _step("parse_intent", source_node=(input_nodes[0] if input_nodes else None)),
        _step("generate_outline", source_node=(process_nodes[0] if process_nodes else None)),
    ]

    if outline_gate is not None:
        steps.append(_step("approve_outline", source_node=outline_gate))

    self_refine_node = process_nodes[1] if len(process_nodes) > 1 else None
    steps.append(
        _step("generate_content", source_node=(process_nodes[0] if process_nodes else None))
    )
    if self_refine_node is not None:
        steps.append(_step("self_refine", source_node=self_refine_node))

    if checker_nodes:
        steps.append(_step("check_facts", source_node=checker_nodes[0]))
        if fact_gate is not None:
            steps.append(_step("approve_fact_check", source_node=fact_gate))

    steps.append(_step("finalize", source_node=(output_nodes[0] if output_nodes else None)))

    warnings = _build_warnings(typed_nodes, checker_nodes, outline_gate, fact_gate)
    plan = {
        "execution_mode": "published_dsl_runtime",
        "steps": steps,
        "features": {
            "outline_gate": outline_gate is not None,
            "self_refine": self_refine_node is not None,
            "fact_check": bool(checker_nodes),
            "fact_check_gate": fact_gate is not None,
        },
        "source_nodes": typed_nodes,
        "warnings": warnings,
    }
    return _with_context_metadata(plan, workflow_context)


def runtime_feature_enabled(
    state: dict[str, Any],
    feature: str,
    *,
    default: bool = True,
) -> bool:
    """读取运行计划开关，缺省保持旧链路行为。"""
    plan = state.get("runtime_plan")
    if not isinstance(plan, dict):
        return default
    features = plan.get("features")
    if not isinstance(features, dict):
        return default
    value = features.get(feature)
    return value if isinstance(value, bool) else default


def _with_context_metadata(plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(plan)
    enriched.update(
        {
            "workflow_definition_id": context.get("workflow_definition_id"),
            "workflow_version_id": context.get("workflow_version_id"),
            "definition_name": context.get("definition_name"),
            "definition_description": context.get("definition_description"),
            "version": context.get("version"),
        }
    )
    return enriched


def _resolve_runtime_type(node_type: str) -> str:
    normalized = str(node_type or "").strip().lower().replace("-", "_")
    return _RUNTIME_NODE_TYPE_ALIASES.get(normalized, normalized)


def _normalize_node(node: dict[str, Any], order: int) -> dict[str, Any]:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return {
        "id": node.get("id"),
        "name": node.get("id"),
        "label": data.get("label") or node.get("id"),
        "type": node.get("type"),
        "runtime_type": _resolve_runtime_type(str(node.get("type") or "")),
        "order": order,
    }


def _topological_nodes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    node_by_id = {node.get("id"): node for node in nodes if node.get("id")}
    original_order = {node_id: index for index, node_id in enumerate(node_by_id)}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
    indegree: dict[str, int] = dict.fromkeys(node_by_id, 0)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_by_id or target not in node_by_id:
            continue
        outgoing[source].append(target)
        indegree[target] += 1

    queue = sorted(
        [node_id for node_id, degree in indegree.items() if degree == 0],
        key=lambda node_id: original_order[node_id],
    )
    ordered_ids: list[str] = []
    while queue:
        node_id = queue.pop(0)
        ordered_ids.append(node_id)
        for target in sorted(outgoing[node_id], key=lambda item: original_order[item]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort(key=lambda item: original_order[item])

    if len(ordered_ids) < len(node_by_id):
        remaining = [
            node_id
            for node_id in sorted(node_by_id, key=lambda item: original_order[item])
            if node_id not in ordered_ids
        ]
        ordered_ids.extend(remaining)

    return [node_by_id[node_id] for node_id in ordered_ids]


def _first_gate(
    gate_nodes: list[dict[str, Any]],
    *,
    before_index: int | None = None,
    after_index: int | None = None,
) -> dict[str, Any] | None:
    for node in gate_nodes:
        if before_index is not None and node["order"] >= before_index:
            continue
        if after_index is not None and node["order"] <= after_index:
            continue
        return node
    return None


def _step(step_id: str, source_node: dict[str, Any] | None = None) -> dict[str, Any]:
    step = dict(_CANONICAL_STEP_DEFINITIONS[step_id])
    if source_node is not None:
        step.update(
            {
                "source_node_id": source_node.get("id"),
                "source_node_label": source_node.get("label"),
                "source_node_type": source_node.get("type"),
            }
        )
    return step


def _build_warnings(
    typed_nodes: list[dict[str, Any]],
    checker_nodes: list[dict[str, Any]],
    outline_gate: dict[str, Any] | None,
    fact_gate: dict[str, Any] | None,
) -> list[str]:
    warnings: list[str] = []
    mapped_nodes = [
        node
        for node in typed_nodes
        if node.get("type") and node.get("type") != node.get("runtime_type")
    ]
    for node in mapped_nodes:
        warnings.append(
            f"节点 {node.get('label')} 的类型 {node.get('type')} 已按 {node.get('runtime_type')} 运行。"
        )
    if outline_gate is None:
        warnings.append("发布图未包含事实核查前的 Gate，提纲生成后将自动进入正文生成。")
    if checker_nodes and fact_gate is None:
        warnings.append("发布图未包含事实核查后的 Gate，高风险事实不会暂停等待人工确认。")
    if not checker_nodes:
        warnings.append("发布图未包含核查节点，本次运行将跳过事实核查。")
    if len([node for node in typed_nodes if node.get("runtime_type") == "process"]) < 2:
        warnings.append("发布图未包含第二个处理节点，本次运行将跳过自检修订。")
    return warnings
