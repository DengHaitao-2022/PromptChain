"""
提纲生成节点

功能：
1. 基于意图卡生成文章提纲
2. 支持 Human-in-the-Loop 确认
3. 创建 Artifact 版本
"""

import json

from core.time import utc_now_iso, utc_now_naive
from graph.runtime_plan import runtime_feature_enabled
from models import (
    ArtifactType,
    HumanDecision,
    IntentCard,
    LLMCallRecord,
    NodeRun,
    NodeRunStatus,
    Outline,
)
from services import (
    build_structured_chain_for_workspace,
    ensure_usage_metadata,
    get_artifact_store,
    get_current_model_info_for_workspace,
    invoke_structured_with_usage,
    invoke_with_llm_retry,
)

OUTLINE_GENERATION_PROMPT = """基于以下意图卡，生成一份结构清晰、逻辑连贯的文章提纲。

## 意图卡
目标: {goal}
主题: {topic}
受众: {audience}
风格: {tone}
目标字数: {length}
必须包含: {must_include}
禁止内容: {must_exclude}

## 要求
1. 提纲应包含3-7个主要章节
2. 每个章节应有明确的目标和字数分配
3. 章节之间应有逻辑递进关系
4. 确保覆盖所有"必须包含"的项目
5. 避免"禁止内容"中的项目
6. 总字数分配应接近目标字数

## 输出格式
请生成完整的提纲结构，包括：
- title: 文章标题
- abstract: 概述/导语（50-100字的内容摘要）
- sections: 章节列表，每个章节包含 id, title, summary, target_words
- total_target_words: 总目标字数"""


def _now_iso() -> str:
    return utc_now_iso()


def _build_outline_gate_questions(outline: Outline) -> list[dict]:
    return [
        {
            "question": "请确认当前提纲是否可以进入正文生成。",
            "action_options": ["approve", "modify", "regenerate"],
            "section_count": len(outline.get_flat_sections()),
            "target_words": outline.total_target_words,
        }
    ]


async def _update_gate_metadata(store, workflow_run_id: str, gate_payload: dict | None) -> None:
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


async def generate_outline(state: dict) -> dict:
    """
    生成提纲

    输入 state:
        - intent_card: IntentCard
        - workflow_run_id: str
        - outline_feedback: Optional[str]  # 用户反馈（用于重新生成）

    输出更新:
        - outline: Outline
        - outline_artifact_id: str
        - awaiting_outline_approval: bool
    """
    intent_card: IntentCard = state["intent_card"]
    workflow_run_id = state["workflow_run_id"]
    workspace_id = state.get("workspace_id")
    model_provider_id = state.get("model_provider_id")
    model_provider_name = state.get("model_provider_name")
    model_name = state.get("model_name")
    outline_feedback = state.get("outline_feedback", "")
    rerun_instruction = state.get("rerun_instruction", "")
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="generate_outline",
        node_type="process",
        started_at=utc_now_naive(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id for artifact_id in [state.get("intent_card_artifact_id")] if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        # 构建 prompt
        prompt_template = OUTLINE_GENERATION_PROMPT
        if outline_feedback:
            prompt_template += f"\n\n## 用户反馈（请根据此反馈调整提纲）\n{outline_feedback}"
        if rerun_instruction:
            prompt_template += f"\n\n## 重跑修订要求\n{rerun_instruction}"

        chain, _structured_runtime = await build_structured_chain_for_workspace(
            Outline,
            prompt_template,
            workspace_id,
            model=model_name,
            model_provider_id=model_provider_id,
            model_provider_name=model_provider_name,
        )

        # 调用 LLM
        start_time = utc_now_naive()
        outline, usage = await invoke_with_llm_retry(
            lambda: invoke_structured_with_usage(
                chain,
                {
                    "goal": intent_card.goal,
                    "topic": intent_card.topic,
                    "audience": intent_card.audience.value,
                    "tone": intent_card.tone.value,
                    "length": intent_card.length,
                    "must_include": ", ".join(intent_card.must_include) or "无特殊要求",
                    "must_exclude": ", ".join(intent_card.must_exclude) or "无",
                },
            )
        )
        end_time = utc_now_naive()
        usage = ensure_usage_metadata(
            usage,
            prompt_text=intent_card.topic,
            completion_text=outline.title,
        )

        # 记录 LLM 调用（动态获取模型配置）
        model_info = await get_current_model_info_for_workspace(
            workspace_id,
            model_provider_id=model_provider_id,
            model_provider_name=model_provider_name,
            model=model_name,
        )
        llm_call = LLMCallRecord(
            model=model_info["model"],
            provider=model_info["provider"],
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            latency_ms=int((end_time - start_time).total_seconds() * 1000),
            prompt_preview=intent_card.topic[:100],
            response_preview=outline.title[:100],
        )
        node_run.llm_calls.append(llm_call)

        outline_gate_enabled = runtime_feature_enabled(state, "outline_gate", default=True)

        # 创建 Artifact
        parent_artifact_id = state.get("outline_artifact_id")  # 如果是重新生成
        artifact = await store.create_artifact(
            artifact_type=ArtifactType.OUTLINE,
            content=outline.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            parent_version_id=parent_artifact_id,
            metadata={
                "feedback": outline_feedback,
                "rerun_instruction": rerun_instruction,
                "section_count": len(outline.get_flat_sections()),
                "awaiting_approval": outline_gate_enabled,
            },
        )

        node_run.output_artifact_ids.append(artifact.id)
        if not outline_gate_enabled:
            await _update_gate_metadata(store, workflow_run_id, None)
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)

            return {
                **state,
                "outline": outline,
                "outline_artifact_id": artifact.id,
                "outline_node_run_id": node_run.id,
                "awaiting_outline_approval": False,
                "outline_approved": True,
                "user_decision": None,
                "outline_feedback": None,  # 清除反馈
            }

        gate_opened_at = _now_iso()
        await _update_gate_metadata(
            store,
            workflow_run_id,
            {
                "gate_type": "outline_approval",
                "trigger_reason": "outline_review",
                "questions": _build_outline_gate_questions(outline),
                "answers": None,
                "opened_at": gate_opened_at,
                "handled_at": None,
                "resolution": None,
            },
        )

        # 更新节点运行记录（标记为中断，等待用户确认）
        node_run.complete(NodeRunStatus.INTERRUPTED)
        await store.update_node_run(node_run)

        return {
            **state,
            "outline": outline,
            "outline_artifact_id": artifact.id,
            "outline_node_run_id": node_run.id,
            "awaiting_outline_approval": True,
            "outline_approved": False,
            "user_decision": None,
            "outline_feedback": None,  # 清除反馈
        }

    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise


async def approve_outline(state: dict) -> dict:
    """
    处理用户对提纲的审批决策

    输入 state:
        - outline: Outline
        - user_decision: dict  # {action: "approve"|"modify"|"regenerate", ...}

    输出更新:
        - outline: Outline (如果修改)
        - outline_approved: bool
        - outline_feedback: str (如果需要重新生成)
    """
    outline = Outline.model_validate(state["outline"])
    user_decision = state.get("user_decision", {"action": "approve"})
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    action = user_decision.get("action", "approve")
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="approve_outline",
        node_type="gate",
        started_at=utc_now_naive(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id for artifact_id in [state.get("outline_artifact_id")] if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    node_run.human_decision = HumanDecision(
        decision_type=action,
        user_input=json.dumps(user_decision, ensure_ascii=False),
        modified_content=user_decision.get("modified_outline"),
    )
    handled_at = _now_iso()

    workflow_run = await store.get_workflow_run(workflow_run_id)
    current_gate = {}
    if workflow_run and isinstance(workflow_run.metadata, dict):
        gate = workflow_run.metadata.get("gate")
        if isinstance(gate, dict):
            current_gate = dict(gate)

    try:
        if action == "approve":
            approved_outline = outline.model_copy(deep=True)
            approved_outline.version += 1
            approved_outline.is_approved = True

            artifact = await store.create_artifact(
                artifact_type=ArtifactType.OUTLINE,
                content=approved_outline.model_dump(),
                workflow_run_id=workflow_run_id,
                node_run_id=node_run.id,
                parent_version_id=state.get("outline_artifact_id"),
                metadata={
                    "gate_type": "outline_approval",
                    "decision": "approve",
                    "feedback": user_decision.get("feedback", ""),
                    "handled_at": handled_at,
                },
            )
            node_run.output_artifact_ids.append(artifact.id)
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)

            await _update_gate_metadata(
                store,
                workflow_run_id,
                {
                    "gate_type": "outline_approval",
                    "trigger_reason": current_gate.get("trigger_reason") or "outline_review",
                    "questions": current_gate.get("questions")
                    or _build_outline_gate_questions(approved_outline),
                    "answers": user_decision,
                    "opened_at": current_gate.get("opened_at") or handled_at,
                    "handled_at": handled_at,
                    "resolution": "approve",
                },
            )

            return {
                **state,
                "outline": approved_outline,
                "outline_artifact_id": artifact.id,
                "outline_approved": True,
                "awaiting_outline_approval": False,
                "user_decision": None,
            }

        if action == "modify":
            modified_data = user_decision.get("modified_outline", outline.model_dump())
            modified_outline = Outline.model_validate(modified_data)
            modified_outline.version = outline.version + 1
            modified_outline.is_approved = True

            artifact = await store.create_artifact(
                artifact_type=ArtifactType.OUTLINE,
                content=modified_outline.model_dump(),
                workflow_run_id=workflow_run_id,
                node_run_id=node_run.id,
                parent_version_id=state.get("outline_artifact_id"),
                metadata={
                    "gate_type": "outline_approval",
                    "decision": "modify",
                    "feedback": user_decision.get("feedback", ""),
                    "handled_at": handled_at,
                },
            )
            node_run.output_artifact_ids.append(artifact.id)
            node_run.complete(NodeRunStatus.COMPLETED)
            await store.update_node_run(node_run)

            await _update_gate_metadata(
                store,
                workflow_run_id,
                {
                    "gate_type": "outline_approval",
                    "trigger_reason": current_gate.get("trigger_reason") or "outline_review",
                    "questions": current_gate.get("questions")
                    or _build_outline_gate_questions(modified_outline),
                    "answers": user_decision,
                    "opened_at": current_gate.get("opened_at") or handled_at,
                    "handled_at": handled_at,
                    "resolution": "modify",
                },
            )

            return {
                **state,
                "outline": modified_outline,
                "outline_artifact_id": artifact.id,
                "outline_approved": True,
                "awaiting_outline_approval": False,
                "user_decision": None,
            }

        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)
        await _update_gate_metadata(
            store,
            workflow_run_id,
            {
                "gate_type": "outline_approval",
                "trigger_reason": current_gate.get("trigger_reason") or "outline_review",
                "questions": current_gate.get("questions")
                or _build_outline_gate_questions(outline),
                "answers": user_decision,
                "opened_at": current_gate.get("opened_at") or handled_at,
                "handled_at": handled_at,
                "resolution": "regenerate",
            },
        )

        return {
            **state,
            "outline": None,
            "outline_approved": False,
            "awaiting_outline_approval": False,
            "user_decision": None,
            "outline_feedback": user_decision.get("feedback", "请重新生成提纲"),
        }
    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise
