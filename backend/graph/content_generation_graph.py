"""
内容生成工作流图定义

使用 LangGraph 构建有状态的工作流：
1. 意图解析 → 2. 提纲生成 → 3. 内容生成 → 4. 自检修订 → 5. 最终输出

支持：
- Human-in-the-Loop 中断
- 局部重跑/回溯
- 状态持久化
"""
from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from models import IntentCard, Outline, Uncertainty, WorkflowRun, WorkflowRunStatus, FactCheckReport
from nodes import (
    parse_intent,
    clarify_intent,
    generate_outline,
    approve_outline,
    generate_all_sections,
    self_refine_loop,
    check_facts,
    approve_fact_check,
)
from services import get_artifact_store


class GraphState(TypedDict, total=False):
    """工作流状态定义"""
    # 基础信息
    user_input: str
    workflow_run_id: str

    # 意图解析
    intent_card: Optional[IntentCard]
    intent_card_artifact_id: Optional[str]
    needs_clarification: bool
    clarification_questions: List[Uncertainty]
    user_clarifications: Dict[str, str]

    # 提纲生成
    outline: Optional[Outline]
    outline_artifact_id: Optional[str]
    outline_node_run_id: Optional[str]
    outline_feedback: Optional[str]
    awaiting_outline_approval: bool
    outline_approved: bool
    user_decision: Optional[Dict[str, Any]]

    # 内容生成
    draft_sections: Dict[str, str]
    section_artifact_ids: Dict[str, str]
    generated_content: str

    # 章节重生成
    section_id_to_regenerate: Optional[str]
    section_feedback: Optional[str]

    # 自检修订
    final_content: Dict[str, str]
    final_content_artifact_id: Optional[str]
    refinement_history: List[dict]

    # 事实核查
    fact_check_report: Optional[FactCheckReport]
    fact_check_artifact_id: Optional[str]
    awaiting_fact_check_approval: bool
    fact_check_decisions: Optional[Dict[str, str]]
    manual_corrections: Optional[Dict[str, str]]
    fact_corrections: Optional[Dict[str, Dict[str, str]]]

    # 错误处理
    error: Optional[str]


def should_clarify(state: GraphState) -> str:
    """判断是否需要澄清"""
    if state.get("needs_clarification", False):
        return "clarify"
    return "outline"


def should_regenerate_outline(state: GraphState) -> str:
    """判断是否需要重新生成提纲"""
    if state.get("awaiting_outline_approval", False):
        # 等待用户审批，工作流暂停
        return END
    if state.get("outline") is None:
        return "regenerate"
    if not state.get("outline_approved", False):
        return "regenerate"
    return "generate_content"


def should_proceed_after_fact_check(state: GraphState) -> str:
    """判断事实核查后是否需要用户确认"""
    if state.get("awaiting_fact_check_approval", False):
        # 有高风险项，需要用户确认
        return END
    return "finalize"


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
        "parse_intent",
        should_clarify,
        {
            "clarify": "clarify_intent",
            "outline": "generate_outline"
        }
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
            END: END  # 暂停等待用户审批
        }
    )

    # 提纲审批 → 条件分支
    graph.add_conditional_edges(
        "approve_outline",
        should_regenerate_outline,
        {
            "regenerate": "generate_outline",
            "generate_content": "generate_content",
            END: END
        }
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
            END: END  # 暂停等待用户确认高风险项
        }
    )

    # 事实核查审批 → 最终处理
    graph.add_edge("approve_fact_check", "finalize")

    # 最终处理 → 结束
    graph.add_edge("finalize", END)

    # 编译图，启用持久化
    memory = MemorySaver()
    return graph.compile(
        checkpointer=memory,
        # 在提纲生成和事实核查后中断，等待用户确认
        interrupt_after=["generate_outline", "check_facts"]
    )


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
            call.total_tokens
            for n in node_runs
            for call in n.llm_calls
        )

        workflow_run.complete()
        await store.update_workflow_run(workflow_run)

    return state


# ==================== 工作流执行器 ====================

class ContentGenerationWorkflow:
    """内容生成工作流执行器"""

    def __init__(self):
        self.graph = build_content_generation_graph()
        self.store = get_artifact_store()

    async def start(self, user_input: str) -> dict:
        """
        启动新的工作流

        Args:
            user_input: 用户输入

        Returns:
            工作流状态
        """
        # 创建工作流运行记录
        workflow_run = WorkflowRun(
            user_input=user_input,
            status=WorkflowRunStatus.RUNNING
        )
        await self.store.create_workflow_run(workflow_run)

        # 初始状态
        initial_state: GraphState = {
            "user_input": user_input,
            "workflow_run_id": workflow_run.id,
            "needs_clarification": False,
            "clarification_questions": [],
            "user_clarifications": {},
            "awaiting_outline_approval": False,
            "outline_approved": False,
            "draft_sections": {},
            "section_artifact_ids": {},
            "refinement_history": []
        }

        # 配置
        config = {
            "configurable": {
                "thread_id": workflow_run.id
            }
        }

        # 执行工作流(会在需要用户输入时暂停)
        result = await self.graph.ainvoke(initial_state, config)

        return {
            "workflow_run_id": workflow_run.id,
            "state": result,
            "status": self._get_workflow_status(result)
        }

    async def resume(
        self,
        workflow_run_id: str,
        user_input: dict
    ) -> dict:
        """
        恢复暂停的工作流

        Args:
            workflow_run_id: 工作流运行ID
            user_input: User input (e.g. approval decision, clarification)

        Returns:
            更新后的工作流状态
        """
        config = {
            "configurable": {
                "thread_id": workflow_run_id
            }
        }

        # 获取当前状态
        current_state = await self.graph.aget_state(config)

        # 更新状态
        updated_state = {**current_state.values, **user_input}

        # 继续执行
        result = await self.graph.ainvoke(updated_state, config)

        return {
            "workflow_run_id": workflow_run_id,
            "state": result,
            "status": self._get_workflow_status(result)
        }

    async def approve_outline(
        self,
        workflow_run_id: str,
        action: str,
        feedback: str = "",
        modified_outline: dict = None
    ) -> dict:
        """
        处理提纲审批

        Args:
            workflow_run_id: 工作流运行ID
            action: "approve" | "modify" | "regenerate"
            feedback: 用户反馈
            modified_outline: Modified outline (if action is modify)
        """
        user_decision = {
            "action": action,
            "feedback": feedback
        }
        if modified_outline:
            user_decision["modified_outline"] = modified_outline

        return await self.resume(workflow_run_id, {
            "user_decision": user_decision,
            "awaiting_outline_approval": False
        })

    def _get_workflow_status(self, state: dict) -> str:
        """获取工作流当前状态"""
        if state.get("awaiting_outline_approval"):
            return "awaiting_outline_approval"
        if state.get("awaiting_fact_check_approval"):
            return "awaiting_fact_check_approval"
        if state.get("needs_clarification"):
            return "needs_clarification"
        if state.get("final_content"):
            return "completed"
        return "running"


# 全局实例
_workflow: Optional[ContentGenerationWorkflow] = None


def get_workflow() -> ContentGenerationWorkflow:
    """获取工作流执行器单例"""
    global _workflow
    if _workflow is None:
        _workflow = ContentGenerationWorkflow()
    return _workflow
