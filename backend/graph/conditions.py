"""
条件路由函数

LangGraph 图中用于决定工作流分支走向的条件判断函数
"""

from langgraph.graph import END

from graph.state import GraphState


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
    if state.get("user_decision") and not state.get("outline_approved", False):
        return "approve_outline"
    if not state.get("outline_approved", False):
        return "regenerate"
    return "generate_content"


def should_proceed_after_fact_check(state: GraphState) -> str:
    """判断事实核查后是否需要用户确认"""
    if state.get("awaiting_fact_check_approval", False):
        # 有高风险项，需要用户确认
        return END
    if state.get("fact_check_report") is not None and (
        state.get("fact_check_decisions") or state.get("manual_corrections")
    ):
        return "approve_fact_check"
    return "finalize"
