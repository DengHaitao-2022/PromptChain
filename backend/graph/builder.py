"""
内容生成工作流图构建

使用 LangGraph 构建有状态的工作流：
1. 意图解析 → 2. 提纲生成 → 3. 内容生成 → 4. 自检修订 → 5. 最终输出

支持：
- Human-in-the-Loop 中断
- 局部重跑/回溯
- 状态持久化
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from core.time import utc_now_naive
from graph.conditions import (
    should_clarify,
    should_continue_after_post_content_tools,
    should_continue_after_pre_finalize_tools,
    should_continue_after_pre_outline_tools,
    should_proceed_after_fact_check,
    should_regenerate_outline,
    should_run_fact_check,
    should_run_pre_finalize_tools,
    should_run_pre_outline_tools,
    should_run_self_refine,
)
from graph.state import GraphState
from models import ArtifactType, WorkflowRunStatus
from nodes import (
    approve_fact_check,
    approve_outline,
    check_facts,
    clarify_intent,
    generate_all_sections,
    generate_outline,
    parse_intent,
    retrieve_knowledge,
    run_post_content_tools,
    run_pre_finalize_tools,
    run_pre_outline_tools,
    self_refine_loop,
)
from services import get_artifact_store, get_postgres_checkpoint_saver


async def finalize_output(state: GraphState) -> GraphState:
    """最终处理节点"""
    store = get_artifact_store()
    workflow_run_id = state["workflow_run_id"]
    final_artifact_id = state.get("final_content_artifact_id")

    if not final_artifact_id:
        draft_sections = state.get("draft_sections")
        if isinstance(draft_sections, dict) and draft_sections:
            node_runs = await store.get_node_runs_by_workflow(workflow_run_id)
            latest_node_run = max(node_runs, key=lambda run: run.started_at, default=None)
            section_artifact_ids = state.get("section_artifact_ids")
            artifact = await store.create_artifact(
                artifact_type=ArtifactType.FINAL_CONTENT,
                content={
                    "sections": draft_sections,
                    "section_order": list(draft_sections.keys()),
                    "compiled_content": state.get("generated_content") or "",
                    "refinement_history": state.get("refinement_history") or [],
                    "total_iterations": len(state.get("refinement_history") or []),
                    "refinement_skipped_reason": "runtime_plan_disabled_self_refine",
                },
                workflow_run_id=workflow_run_id,
                node_run_id=latest_node_run.id if latest_node_run else workflow_run_id,
                metadata={
                    "section_artifact_ids": (
                        section_artifact_ids if isinstance(section_artifact_ids, dict) else {}
                    ),
                    "refinement_skipped": True,
                    "refinement_skipped_reason": "runtime_plan_disabled_self_refine",
                },
            )
            final_artifact_id = artifact.id
            state["final_content"] = draft_sections
            state["final_content_artifact_id"] = artifact.id

    # 更新工作流状态
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if workflow_run:
        workflow_run.status = WorkflowRunStatus.COMPLETED
        workflow_run.final_artifact_id = final_artifact_id

        # 计算统计
        node_runs = await store.get_node_runs_by_workflow(workflow_run_id)
        workflow_run.total_node_runs = len(node_runs)
        workflow_run.total_llm_calls = sum(len(n.llm_calls) for n in node_runs)
        workflow_run.total_tokens = sum(
            call.total_tokens for n in node_runs for call in n.llm_calls
        )
        workflow_run.completed_at = utc_now_naive()
        workflow_run.total_duration_ms = sum(node.duration_ms or 0 for node in node_runs)
        await store.update_workflow_run(workflow_run)

    return state


def build_content_generation_graph():
    """构建内容生成工作流图"""

    graph = StateGraph(GraphState)

    # ==================== 添加节点 ====================

    # 意图解析
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("clarify_intent", clarify_intent)

    # 知识检索
    graph.add_node("retrieve_knowledge", retrieve_knowledge)

    # 提纲生成
    graph.add_node("run_pre_outline_tools", run_pre_outline_tools)
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("approve_outline", approve_outline)

    # 内容生成
    graph.add_node("generate_content", generate_all_sections)
    graph.add_node("run_post_content_tools", run_post_content_tools)

    # 自检修订
    graph.add_node("self_refine", self_refine_loop)

    # 事实核查
    graph.add_node("check_facts", check_facts)
    graph.add_node("approve_fact_check", approve_fact_check)

    # 最终处理
    graph.add_node("run_pre_finalize_tools", run_pre_finalize_tools)
    graph.add_node("finalize", finalize_output)

    # ==================== 设置边 ====================

    # 入口
    graph.set_entry_point("parse_intent")

    # 意图解析 → 条件分支
    graph.add_conditional_edges(
        "parse_intent",
        should_clarify,
        {"clarify": "clarify_intent", "outline": "retrieve_knowledge"},
    )

    # 澄清后 → 提纲
    graph.add_edge("clarify_intent", "retrieve_knowledge")
    graph.add_conditional_edges(
        "retrieve_knowledge",
        should_run_pre_outline_tools,
        {
            "run_pre_outline_tools": "run_pre_outline_tools",
            "generate_outline": "generate_outline",
        },
    )
    graph.add_conditional_edges(
        "run_pre_outline_tools",
        should_continue_after_pre_outline_tools,
        {"generate_outline": "generate_outline", END: END},
    )

    # 提纲生成 -> 条件分支(等待审批或继续)
    graph.add_conditional_edges(
        "generate_outline",
        should_regenerate_outline,
        {
            "approve_outline": "approve_outline",
            "regenerate": "generate_outline",
            "generate_content": "generate_content",
            END: END,  # 暂停等待用户审批
        },
    )

    # 提纲审批 → 条件分支
    graph.add_conditional_edges(
        "approve_outline",
        should_regenerate_outline,
        {"regenerate": "generate_outline", "generate_content": "generate_content", END: END},
    )

    # 内容生成 → 按运行计划决定是否进入自检修订
    graph.add_conditional_edges(
        "generate_content",
        should_run_self_refine,
        {
            "self_refine": "self_refine",
            "run_post_content_tools": "run_post_content_tools",
            "check_facts": "check_facts",
            "run_pre_finalize_tools": "run_pre_finalize_tools",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "run_post_content_tools",
        should_continue_after_post_content_tools,
        {
            "self_refine": "self_refine",
            "check_facts": "check_facts",
            "run_pre_finalize_tools": "run_pre_finalize_tools",
            "finalize": "finalize",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "self_refine",
        should_run_fact_check,
        {
            "check_facts": "check_facts",
            "run_pre_finalize_tools": "run_pre_finalize_tools",
            "finalize": "finalize",
        },
    )

    # 事实核查 -> 条件分支(高风险项需要用户确认)
    graph.add_conditional_edges(
        "check_facts",
        should_proceed_after_fact_check,
        {
            "approve_fact_check": "approve_fact_check",
            "run_pre_finalize_tools": "run_pre_finalize_tools",
            "finalize": "finalize",
            END: END,  # 暂停等待用户确认高风险项
        },
    )

    # 事实核查审批 → 按计划进入收尾工具或最终处理
    graph.add_conditional_edges(
        "approve_fact_check",
        should_run_pre_finalize_tools,
        {"run_pre_finalize_tools": "run_pre_finalize_tools", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "run_pre_finalize_tools",
        should_continue_after_pre_finalize_tools,
        {"finalize": "finalize", END: END},
    )

    # 最终处理 → 结束
    graph.add_edge("finalize", END)

    # 编译图，启用持久化
    try:
        checkpointer = get_postgres_checkpoint_saver()
    except Exception:
        checkpointer = MemorySaver()

    return graph.compile(
        checkpointer=checkpointer,
        # 每个节点后都产生静态 checkpoint，便于手动暂停与 Gate 恢复。
        interrupt_after=[
            "parse_intent",
            "clarify_intent",
            "generate_outline",
            "approve_outline",
            "generate_content",
            "self_refine",
            "check_facts",
            "retrieve_knowledge",
            "run_pre_outline_tools",
            "run_post_content_tools",
            "run_pre_finalize_tools",
            "approve_fact_check",
            "finalize",
        ],
    )
