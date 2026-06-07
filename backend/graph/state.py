"""
工作流状态定义

GraphState 是 LangGraph 工作流的核心数据合约，
定义了在各节点之间传递的所有状态字段。
"""

from typing import Any, TypedDict

from models import EvidencePack, FactCheckReport, IntentCard, Outline, RetrievalConfig, Uncertainty


class GraphState(TypedDict, total=False):
    """工作流状态定义"""

    # 基础信息
    user_input: str
    workflow_run_id: str
    workspace_id: str | None
    user_id: str | None
    model_provider_id: str | None
    model_provider_name: str | None
    model_name: str | None
    workflow_definition_id: str | None
    workflow_version_id: str | None
    workflow_context: dict[str, Any] | None
    runtime_plan: dict[str, Any] | None
    retrieval_config: RetrievalConfig | dict[str, Any] | None
    is_paused: bool
    pause_reason: str | None
    rerun_from_node: str | None
    rerun_instruction: str | None
    scenario_code: str | None
    project_id: str | None
    edit_mode: str | None
    generation_mode: str | None
    target_asset_id: str | None
    project_memory_context: dict[str, Any] | None
    scenario_check_report: dict[str, Any] | None
    project_memory_update_candidates: list[dict[str, Any]]

    # 意图解析
    intent_card: IntentCard | None
    intent_card_artifact_id: str | None
    needs_clarification: bool
    clarification_questions: list[Uncertainty]
    user_clarifications: dict[str, str]

    # 知识检索
    evidence_pack: EvidencePack | dict[str, Any] | None
    evidence_artifact_id: str | None
    citations: list[dict[str, Any]]
    knowledge_conflicts: list[dict[str, Any]]
    unverified_points: list[str]

    # 提纲生成
    outline: Outline | None
    outline_artifact_id: str | None
    outline_node_run_id: str | None
    outline_feedback: str | None
    awaiting_outline_approval: bool
    outline_approved: bool
    user_decision: dict[str, Any] | None

    # 内容生成
    draft_sections: dict[str, str]
    section_artifact_ids: dict[str, str]
    generated_content: str

    # 章节重生成
    section_id_to_regenerate: str | None
    section_feedback: str | None

    # 自检修订
    final_content: dict[str, str]
    final_content_artifact_id: str | None
    refinement_history: list[dict]

    # 事实核查
    fact_check_report: FactCheckReport | None
    fact_check_artifact_id: str | None
    awaiting_fact_check_approval: bool
    fact_check_decisions: dict[str, str] | None
    manual_corrections: dict[str, str] | None
    fact_corrections: dict[str, dict[str, str]] | None

    # 错误处理
    error: str | None
