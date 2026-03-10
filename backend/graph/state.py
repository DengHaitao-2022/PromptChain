"""
工作流状态定义

GraphState 是 LangGraph 工作流的核心数据合约，
定义了在各节点之间传递的所有状态字段。
"""
from typing import TypedDict, Optional, List, Dict, Any

from models import IntentCard, Outline, Uncertainty, FactCheckReport


class GraphState(TypedDict, total=False):
    """工作流状态定义"""
    # 基础信息
    user_input: str
    workflow_run_id: str
    workflow_definition_id: Optional[str]
    workflow_version_id: Optional[str]
    workflow_context: Optional[Dict[str, Any]]
    is_paused: bool
    pause_reason: Optional[str]

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
