"""
条件路由函数

LangGraph 图中用于决定工作流分支走向的条件判断函数
"""

from langgraph.graph import END

from graph.runtime_plan import runtime_feature_enabled
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
    if _has_tool_phase(state, "pre_finalize") and not _phase_completed(state, "pre_finalize"):
        return "run_pre_finalize_tools"
    return "finalize"


def should_run_self_refine(state: GraphState) -> str:
    """判断运行计划是否启用自检修订。"""
    if _has_tool_phase(state, "post_content") and not _phase_completed(state, "post_content"):
        return "run_post_content_tools"
    if runtime_feature_enabled(state, "self_refine", default=True):
        return "self_refine"
    return should_run_fact_check(state)


def should_run_fact_check(state: GraphState) -> str:
    """判断运行计划是否启用事实核查。"""
    if runtime_feature_enabled(state, "fact_check", default=True):
        return "check_facts"
    if _has_tool_phase(state, "pre_finalize") and not _phase_completed(state, "pre_finalize"):
        return "run_pre_finalize_tools"
    return "finalize"


def should_run_pre_outline_tools(state: GraphState) -> str:
    """知识检索后是否执行前置工具。"""
    if _has_tool_phase(state, "pre_outline") and not _phase_completed(state, "pre_outline"):
        return "run_pre_outline_tools"
    return "generate_outline"


def should_run_pre_finalize_tools(state: GraphState) -> str:
    """进入最终输出前是否执行收尾工具。"""
    if _has_tool_phase(state, "pre_finalize") and not _phase_completed(state, "pre_finalize"):
        return "run_pre_finalize_tools"
    return "finalize"


def should_continue_after_pre_outline_tools(state: GraphState) -> str:
    """前置工具结束后决定继续提纲生成或停在工具审批 Gate。"""
    if _tool_gate_or_error_waiting(state):
        return END
    return "generate_outline"


def should_continue_after_post_content_tools(state: GraphState) -> str:
    """正文后工具结束后决定继续自检、事实核查或停在工具审批 Gate。"""
    if _tool_gate_or_error_waiting(state):
        return END
    if runtime_feature_enabled(state, "self_refine", default=True):
        return "self_refine"
    return should_run_fact_check(state)


def should_continue_after_pre_finalize_tools(state: GraphState) -> str:
    """收尾工具结束后决定最终输出或停在工具审批 Gate。"""
    if _tool_gate_or_error_waiting(state):
        return END
    return "finalize"


def _tool_gate_or_error_waiting(state: dict) -> bool:
    """工具节点在审批或失败时必须停止，避免继续执行下游节点。"""
    return bool(state.get("awaiting_tool_approval") or state.get("error"))


def _has_tool_phase(state: dict, phase: str) -> bool:
    plan = state.get("runtime_plan")
    if not isinstance(plan, dict):
        return False
    tool_steps = plan.get("tool_steps")
    if not isinstance(tool_steps, list):
        return False
    return any(isinstance(step, dict) and step.get("phase") == phase for step in tool_steps)


def _phase_completed(state: dict, phase: str) -> bool:
    completed = state.get("tool_phase_completed")
    return isinstance(completed, dict) and completed.get(phase) is True
