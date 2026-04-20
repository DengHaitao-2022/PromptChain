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
from models import WorkflowRunStatus
from nodes import (
    approve_fact_check,
    approve_outline,
    check_facts,
    clarify_intent,
    generate_all_sections,
    generate_outline,
    parse_intent,
    self_refine_loop,
)
from services import get_artifact_store, get_postgres_checkpoint_saver

from graph.conditions import (
    should_clarify,
    should_proceed_after_fact_check,
    should_regenerate_outline,
)
from graph.state import GraphState


async def finalize_output(state: GraphState) -> GraphState:
    """最终处理节点"""
    store = get_artifact_store()
    workflow_run_id = state["workflow_run_id"]

    # 更新工作流状态
    workflow_run = await store.get_workflow_run(workflow_run_id)
    if workflow_run:
        workflow_run.status = WorkflowRunStatus.COMPLETED
        workflow_run.final_artifact_id = state.get("final_content_artifact_id")

        # 计算统计
        node_runs = await store.get_node_runs_by_workflow(workflow_run_id)
        workflow_run.total_node_runs = len(node_runs)
        workflow_run.total_llm_calls = sum(len(n.llm_calls) for n in node_runs)
        workflow_run.total_tokens = sum(
            call.total_tokens for n in node_runs for call in n.llm_calls
        )

        workflow_run.complete()
        await store.update_workflow_run(workflow_run)

    return state


def build_content_generation_graph():
    """构建内容生成工作流图"""

    graph = StateGraph(GraphState)

    # ==================== 添加节点 ====================

    # 意图解析
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("clarify_intent", clarify_intent)

    # 提纲生成
    graph.add_node("generate_outline", generate_outline)
    graph.add_node("approve_outline", approve_outline)

    # 内容生成
    graph.add_node("generate_content", generate_all_sections)

    # 自检修订
    graph.add_node("self_refine", self_refine_loop)

    # 事实核查
    graph.add_node("check_facts", check_facts)
    graph.add_node("approve_fact_check", approve_fact_check)

    # 最终处理
    graph.add_node("finalize", finalize_output)

    # ==================== 设置边 ====================

    # 入口
    graph.set_entry_point("parse_intent")

    # 意图解析 → 条件分支
    graph.add_conditional_edges(
        "parse_intent", should_clarify, {"clarify": "clarify_intent", "outline": "generate_outline"}
    )

    # 澄清后 → 提纲
    graph.add_edge("clarify_intent", "generate_outline")

    # 提纲生成 -> 条件分支(等待审批或继续)
    graph.add_conditional_edges(
        "generate_outline",
        should_regenerate_outline,
        {
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

    # 内容生成 → 自检修订 → 事实核查 → 条件分支
    graph.add_edge("generate_content", "self_refine")
    graph.add_edge("self_refine", "check_facts")

    # 事实核查 -> 条件分支(高风险项需要用户确认)
    graph.add_conditional_edges(
        "check_facts",
        should_proceed_after_fact_check,
        {
            "finalize": "finalize",
            END: END,  # 暂停等待用户确认高风险项
        },
    )

    # 事实核查审批 → 最终处理
    graph.add_edge("approve_fact_check", "finalize")

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
            "approve_fact_check",
            "finalize",
        ],
    )
