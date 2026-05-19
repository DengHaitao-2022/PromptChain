"""
意图解析节点

功能：
1. 解析用户输入，生成结构化意图卡
2. 识别缺失信息，生成澄清问题
3. 创建 Artifact 版本
"""

import json
import re

from core.time import utc_now_iso, utc_now_naive
from models import (
    ArtifactType,
    Audience,
    HumanDecision,
    IntentCard,
    LLMCallRecord,
    NodeRun,
    NodeRunStatus,
    Tone,
    Uncertainty,
)
from services import (
    build_structured_chain_for_workspace,
    ensure_usage_metadata,
    get_artifact_store,
    get_current_model_info_for_workspace,
    invoke_structured_with_usage,
    invoke_with_llm_retry,
)

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
- uncertainties: 如果有重要信息不明确，添加澄清问题

## 字段合法性约束
- audience 只能输出："初学者"、"中级读者"、"专家"、"通用读者"
- 如果用户说“投资人”“客户”“管理层”“政府”“学校”等具体对象，请选择最接近的 audience，并把原始对象写入 must_include
- tone 只能输出："正式严谨"、"轻松活泼"、"学术专业"、"叙事性"
- 如果用户说“专业、严谨、数据驱动”“商业计划书”“投资分析”，tone 应输出 "正式严谨"
- length 必须是数字，范围 100 到 100000
- 如果用户要求超过 100000 字，请将 length 设为 100000，并在 must_include 记录原始字数需求
- uncertainties 必须是对象数组，不能是字符串数组
- 每个 uncertainty 必须包含 field、question、priority、default_assumption"""


def _now_iso() -> str:
    return utc_now_iso()


def _serialize_questions(questions: list[Uncertainty]) -> list[dict]:
    return [question.model_dump() for question in questions]


_NO_VALUE_ANSWERS = {"", "无", "暂无", "没有", "不需要", "无需", "否", "none", "null"}


def _coerce_list_answer(value) -> list[str]:
    """将澄清答案统一为字符串列表，避免单个文本破坏 IntentCard 校验。"""
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value).strip()
        if text.lower() in _NO_VALUE_ANSWERS:
            return []
        raw_items = re.split("[\n,，、;\uff1b]+", text)
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _merge_unique(items: list[str], additions: list[str]) -> list[str]:
    merged = list(items)
    existing = set(merged)
    for item in additions:
        if item not in existing:
            merged.append(item)
            existing.add(item)
    return merged


def _coerce_audience(value) -> str:
    text = str(value or "").strip()
    if not text:
        return Audience.GENERAL.value
    for audience in Audience:
        if text == audience.value:
            return audience.value

    lowered = text.lower()
    if any(keyword in lowered for keyword in ["初学", "新手", "入门", "beginner"]):
        return Audience.BEGINNER.value
    if any(keyword in lowered for keyword in ["专家", "资深", "架构师", "高级", "expert"]):
        return Audience.EXPERT.value
    if any(
        keyword in lowered
        for keyword in ["开发", "工程师", "技术", "程序员", "developer", "engineer", "中级"]
    ):
        return Audience.INTERMEDIATE.value
    return Audience.GENERAL.value


def _coerce_tone(value) -> str:
    text = str(value or "").strip()
    if not text:
        return Tone.CASUAL.value
    for tone in Tone:
        if text == tone.value:
            return tone.value

    lowered = text.lower()
    if any(
        keyword in lowered
        for keyword in [
            "正式",
            "严谨",
            "报告",
            "商业",
            "投资",
            "数据驱动",
            "计划书",
            "formal",
            "专业",
        ]
    ):
        return Tone.FORMAL.value
    if any(keyword in lowered for keyword in ["学术", "论文", "研究型", "academic"]):
        return Tone.ACADEMIC.value
    if any(keyword in lowered for keyword in ["故事", "叙事", "story"]):
        return Tone.STORYTELLING.value
    return Tone.CASUAL.value


def _coerce_length(value, fallback: int) -> int:
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else fallback


def _question_field(question) -> str | None:
    if isinstance(question, dict):
        return question.get("field")
    return getattr(question, "field", None)


def _normalize_uncertainty_item(item, index: int) -> dict:
    if isinstance(item, dict):
        question = (
            item.get("question")
            or item.get("text")
            or item.get("content")
            or item.get("description")
            or ""
        )
        try:
            priority = int(item.get("priority") or min(index + 1, 5))
        except (TypeError, ValueError):
            priority = min(index + 1, 5)
        return {
            "field": str(item.get("field") or "general"),
            "question": str(question),
            "priority": max(1, min(priority, 5)),
            "default_assumption": item.get("default_assumption"),
        }

    return {
        "field": "general",
        "question": str(item),
        "priority": min(index + 1, 5),
        "default_assumption": None,
    }


def _normalize_intent_card_payload(payload: dict) -> dict:
    data = dict(payload)

    raw_audience = data.get("audience")
    raw_tone = data.get("tone")
    raw_length = data.get("length")

    data["audience"] = _coerce_audience(raw_audience)
    data["tone"] = _coerce_tone(raw_tone)

    length = _coerce_length(raw_length, 1500)
    data["length"] = min(100000, max(100, length))

    uncertainties = data.get("uncertainties") or []
    if not isinstance(uncertainties, list):
        uncertainties = [uncertainties]
    data["uncertainties"] = [
        _normalize_uncertainty_item(item, index) for index, item in enumerate(uncertainties) if item
    ]

    for key in ("must_include", "must_exclude", "source_references"):
        value = data.get(key)
        if value is None:
            data[key] = []
        elif isinstance(value, str):
            data[key] = _coerce_list_answer(value)
        elif not isinstance(value, list):
            data[key] = [str(value)]

    preserved_constraints: list[str] = []
    valid_audience_values = {audience.value for audience in Audience}
    valid_tone_values = {tone.value for tone in Tone}

    if raw_audience and str(raw_audience).strip() not in valid_audience_values:
        preserved_constraints.append(f"目标受众：{raw_audience}")

    if raw_tone and str(raw_tone).strip() not in valid_tone_values:
        preserved_constraints.append(f"原始风格要求：{raw_tone}")

    if length > 100000:
        preserved_constraints.append(
            f"用户期望篇幅：{length} 字；当前单次生成上限为 100000 字，后续应按章节/分批扩展。"
        )

    if preserved_constraints:
        data["must_include"] = _merge_unique(
            data.get("must_include", []),
            preserved_constraints,
        )

    return data


def _apply_clarifications(intent_card: IntentCard, clarifications: dict) -> dict:
    updated_data = intent_card.model_dump()
    freeform_constraints: list[str] = []

    for field, answer in clarifications.items():
        if field == "audience":
            updated_data[field] = _coerce_audience(answer)
        elif field == "tone":
            updated_data[field] = _coerce_tone(answer)
        elif field == "length":
            updated_data[field] = _coerce_length(answer, updated_data.get("length", 1500))
        elif field in {"must_include", "must_exclude", "source_references"}:
            updated_data[field] = _merge_unique(
                updated_data.get(field, []),
                _coerce_list_answer(answer),
            )
        elif field in updated_data:
            normalized_answer = str(answer).strip()
            updated_data[field] = (
                None if normalized_answer.lower() in _NO_VALUE_ANSWERS else normalized_answer
            )
        else:
            values = _coerce_list_answer(answer)
            freeform_constraints.extend(f"{field}: {item}" for item in values)

    if freeform_constraints:
        updated_data["must_include"] = _merge_unique(
            updated_data.get("must_include", []),
            freeform_constraints,
        )

    updated_data["uncertainties"] = [
        u for u in updated_data.get("uncertainties", []) if _question_field(u) not in clarifications
    ]
    return updated_data


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
    workspace_id = state.get("workspace_id")
    model_provider_id = state.get("model_provider_id")
    model_provider_name = state.get("model_provider_name")
    model_name = state.get("model_name")
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="parse_intent",
        node_type="process",
        started_at=utc_now_naive(),
        status=NodeRunStatus.RUNNING,
    )
    await store.create_node_run(node_run)

    try:
        # 使用结构化输出的 LLM
        chain, _structured_runtime = await build_structured_chain_for_workspace(
            IntentCard,
            INTENT_EXTRACTION_PROMPT,
            workspace_id,
            model=model_name,
            model_provider_id=model_provider_id,
            model_provider_name=model_provider_name,
        )

        # 调用 LLM
        start_time = utc_now_naive()
        intent_card, usage = await invoke_with_llm_retry(
            lambda: invoke_structured_with_usage(
                chain,
                {"user_input": user_input},
                schema=IntentCard,
                normalizer=_normalize_intent_card_payload,
            )
        )
        end_time = utc_now_naive()
        usage = ensure_usage_metadata(
            usage,
            prompt_text=user_input,
            completion_text=str(intent_card.model_dump()),
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
            artifact_type=ArtifactType.INTENT_CARD,
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
    intent_card = IntentCard.model_validate(state["intent_card"])
    clarifications = state.get("user_clarifications", {})
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="clarify_intent",
        node_type="gate",
        started_at=utc_now_naive(),
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

        updated_intent_card = IntentCard.model_validate(
            _apply_clarifications(intent_card, clarifications)
        )

        # 创建新版本 Artifact
        parent_artifact_id = state.get("intent_card_artifact_id")
        artifact = await store.create_artifact(
            artifact_type=ArtifactType.INTENT_CARD,
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
