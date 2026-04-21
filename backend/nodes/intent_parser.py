"""
意图解析节点

功能：
1. 解析用户输入，生成结构化意图卡
2. 识别缺失信息，生成澄清问题
3. 创建 Artifact 版本
"""

import json
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate

from models import (
    ArtifactType,
    HumanDecision,
    IntentCard,
    LLMCallRecord,
    NodeRun,
    NodeRunStatus,
    Uncertainty,
)
from services import get_artifact_store, get_current_model_info, get_structured_llm

INTENT_EXTRACTION_PROMPT = """你是一个专业的内容规划助手。请根据用户的需求描述，提取结构化意图卡。

## 用户输入
{user_input}

## 任务
1. 提取所有明确表达的意图
2. 识别缺失的关键信息
3. 如发现冲突或模糊表述，添加到 uncertainties 列表
4. 仅对**高优先级**缺失信息生成澄清问题（最多3个）

## 输出要求
请仔细分析用户需求，生成完整的意图卡。对于用户未明确说明的字段：
- goal: 必须填写，概括用户的核心目标
- topic: 必须填写，提取文章的主题
- audience: 根据语境推断，默认为"通用读者"
- scenario: 如果用户提到了使用场景就填写，否则留空
- tone: 根据语境推断合适的风格
- length: 如果用户提到了字数要求就使用，否则默认1500
- must_include: 提取用户明确要求必须包含的内容
- must_exclude: 提取用户明确要求禁止的内容
- uncertainties: 如果有重要信息不明确，添加澄清问题"""


def _now_iso() -> str:
    return f"{datetime.utcnow().isoformat()}Z"


def _serialize_questions(questions: list[Uncertainty]) -> list[dict]:
    return [question.model_dump() for question in questions]


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


async def parse_intent(state: dict) -> dict:
    """
    解析用户意图，生成结构化意图卡

    输入 state:
        - user_input: str
        - workflow_run_id: str

    输出更新:
        - intent_card: IntentCard
        - needs_clarification: bool
        - clarification_questions: List[Uncertainty]
    """
    user_input = state["user_input"]
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="parse_intent",
        node_type="process",
        started_at=datetime.utcnow(),
        status=NodeRunStatus.RUNNING,
    )
    await store.create_node_run(node_run)

    try:
        # 使用结构化输出的 LLM
        llm = get_structured_llm(IntentCard)
        prompt = ChatPromptTemplate.from_template(INTENT_EXTRACTION_PROMPT)
        chain = prompt | llm

        # 调用 LLM
        start_time = datetime.utcnow()
        intent_card: IntentCard = await chain.ainvoke({"user_input": user_input})
        end_time = datetime.utcnow()

        # 记录 LLM 调用（动态获取模型配置）
        model_info = get_current_model_info()
        llm_call = LLMCallRecord(
            model=model_info["model"],
            provider=model_info["provider"],
            latency_ms=int((end_time - start_time).total_seconds() * 1000),
            prompt_preview=user_input[:200] if len(user_input) > 200 else user_input,
            response_preview=str(intent_card.model_dump())[:200],
        )
        node_run.llm_calls.append(llm_call)

        # 提取高优先级澄清问题
        clarification_questions = intent_card.get_high_priority_uncertainties(max_count=3)
        serialized_questions = _serialize_questions(clarification_questions)
        needs_clarification = len(clarification_questions) > 0

        # 创建 Artifact
        artifact = await store.create_artifact(
            type=ArtifactType.INTENT_CARD,
            content=intent_card.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            metadata={
                "needs_clarification": needs_clarification,
                "clarification_questions": serialized_questions,
            },
        )

        if needs_clarification:
            await _update_gate_metadata(
                store,
                workflow_run_id,
                {
                    "gate_type": "clarification",
                    "trigger_reason": "missing_information",
                    "questions": serialized_questions,
                    "answers": None,
                    "opened_at": _now_iso(),
                    "handled_at": None,
                    "resolution": None,
                },
            )
        else:
            await _update_gate_metadata(store, workflow_run_id, None)

        # 更新节点运行记录
        node_run.output_artifact_ids.append(artifact.id)
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "intent_card": intent_card,
            "intent_card_artifact_id": artifact.id,
            "needs_clarification": needs_clarification,
            "clarification_questions": serialized_questions,
        }

    except Exception as e:
        # 记录错误
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise


async def clarify_intent(state: dict) -> dict:
    """
    处理用户澄清，更新意图卡

    输入 state:
        - intent_card: IntentCard
        - user_clarifications: dict  # {field: answer}

    输出更新:
        - intent_card: IntentCard (更新后)
        - needs_clarification: False
    """
    intent_card = state["intent_card"]
    clarifications = state.get("user_clarifications", {})
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="clarify_intent",
        node_type="gate",
        started_at=datetime.utcnow(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id for artifact_id in [state.get("intent_card_artifact_id")] if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        node_run.human_decision = HumanDecision(
            decision_type="modify",
            user_input=json.dumps(clarifications, ensure_ascii=False),
            modified_content=clarifications,
        )

        # 应用用户澄清
        updated_data = intent_card.model_dump()
        for field, answer in clarifications.items():
            if field in updated_data:
                updated_data[field] = answer

        # 清除已解答的不确定点
        updated_data["uncertainties"] = [
            u for u in updated_data["uncertainties"] if u["field"] not in clarifications
        ]

        updated_intent_card = IntentCard.model_validate(updated_data)

        # 创建新版本 Artifact
        parent_artifact_id = state.get("intent_card_artifact_id")
        artifact = await store.create_artifact(
            type=ArtifactType.INTENT_CARD,
            content=updated_intent_card.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            parent_version_id=parent_artifact_id,
            metadata={
                "clarifications": clarifications,
                "remaining_uncertainties": updated_intent_card.model_dump().get(
                    "uncertainties", []
                ),
            },
        )

        workflow_run = await store.get_workflow_run(workflow_run_id)
        current_gate = {}
        if workflow_run and isinstance(workflow_run.metadata, dict):
            gate = workflow_run.metadata.get("gate")
            if isinstance(gate, dict):
                current_gate = dict(gate)

        await _update_gate_metadata(
            store,
            workflow_run_id,
            {
                "gate_type": "clarification",
                "trigger_reason": current_gate.get("trigger_reason") or "missing_information",
                "questions": current_gate.get("questions")
                or state.get("clarification_questions", []),
                "answers": clarifications,
                "opened_at": current_gate.get("opened_at") or _now_iso(),
                "handled_at": _now_iso(),
                "resolution": "answered",
            },
        )

        # 更新节点运行记录
        node_run.output_artifact_ids.append(artifact.id)
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "intent_card": updated_intent_card,
            "intent_card_artifact_id": artifact.id,
            "needs_clarification": False,
            "clarification_questions": [],
        }

    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise
