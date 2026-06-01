"""Smoke 验收专用 fake LLM。

该模型只在显式选择 fake provider 时使用，用于本地/CI smoke；不要把它作为生产模型回退。
"""

from __future__ import annotations

import json
from typing import Any, get_args, get_origin

from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field


class FakeSmokeChatModel(SimpleChatModel):
    """可预测的 LangChain ChatModel，用于 smoke harness 隔离真实 provider。"""

    model_name: str = Field(default="fake-smoke-model")

    @property
    def _llm_type(self) -> str:
        return "promptchain-fake-smoke"

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> str:
        last_text = _last_message_text(messages)
        return (
            "这是由 PromptChain fake provider 生成的 smoke 内容。"
            f"输入摘要：{last_text[:80] or '无'}。"
            "该内容仅用于验收链路，不代表真实模型输出。"
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ):
        text = self._call(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield ChatGenerationChunk(message=AIMessageChunk(content=text))

    def with_structured_output(
        self,
        schema: type[BaseModel],
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ):
        """返回与 LangChain `include_raw=True` 兼容的结构化结果。"""

        def _invoke(payload: Any) -> Any:
            parsed = _build_structured_payload(schema, payload)
            raw = _raw_message(parsed)
            if include_raw:
                return {"raw": raw, "parsed": parsed, "parsing_error": None}
            return parsed

        return RunnableLambda(_invoke)


def _last_message_text(messages: list[BaseMessage]) -> str:
    if not messages:
        return ""
    content = messages[-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _build_structured_payload(schema: type[BaseModel], payload: Any) -> BaseModel:
    schema_name = schema.__name__
    data = payload if isinstance(payload, dict) else {}

    if schema_name == "IntentCard":
        user_input = str(data.get("user_input") or "smoke 验收内容")
        return schema.model_validate(
            {
                "goal": "生成一篇用于 smoke 验收的内容",
                "topic": user_input[:80] or "PromptChain smoke 验收",
                "audience": "通用读者",
                "scenario": "验收环境",
                "tone": "正式严谨",
                "length": 600,
                "must_include": ["fake provider", "smoke harness"],
                "must_exclude": [],
                "source_references": [],
                "uncertainties": [],
            }
        )

    if schema_name == "Outline":
        topic = str(data.get("topic") or "PromptChain smoke 验收")
        return schema.model_validate(
            {
                "title": f"{topic}验收提纲",
                "abstract": "这是一份由 fake provider 生成的稳定提纲，用于验证工作流运行链路。",
                "sections": [
                    {
                        "id": "intro",
                        "title": "背景与目标",
                        "summary": "说明 smoke 验收的目标和边界。",
                        "target_words": 200,
                    },
                    {
                        "id": "flow",
                        "title": "执行链路",
                        "summary": "描述注册、发布、运行、Gate、重跑和导出路径。",
                        "target_words": 300,
                    },
                    {
                        "id": "result",
                        "title": "结果记录",
                        "summary": "记录可贴入 PR 的验收结果。",
                        "target_words": 100,
                    },
                ],
                "total_target_words": 600,
            }
        )

    if schema_name == "RefinementFeedback":
        return schema.model_validate(
            {
                "section_id": str(data.get("section_id") or "intro"),
                "issues": [],
                "suggestions": [],
                "quality_score": 9.0,
                "needs_revision": False,
            }
        )

    if schema_name == "ClaimList":
        return schema.model_validate({"claims": []})

    if schema_name == "VerificationEvaluation":
        return schema.model_validate(
            {
                "is_verified": True,
                "confidence": 0.99,
                "risk_level": "low",
                "suggested_correction": None,
            }
        )

    if schema_name == "LLMPlannerResponse":
        goal = str(data.get("goal") or "生成 Autonomous Agent 验收材料")
        return schema.model_validate(
            {
                "goal_card": {
                    "goal": goal,
                    "task_type": "research_report",
                    "constraints": ["由 fake provider 生成，需保留可审计链路"],
                    "deliverables": ["结构化调研报告"],
                    "risk_boundaries": ["中高风险工具调用必须进入 Gate"],
                    "success_criteria": ["覆盖目标", "包含证据", "通过最终评估"],
                    "quality_dimensions": ["目标覆盖度", "事实一致性", "产物完整性"],
                    "uncertainty_questions": [],
                },
                "plan_graph": {
                    "nodes": [
                        {
                            "id": "goal_interpretation",
                            "title": "目标理解",
                            "step_type": "goal_interpretation",
                            "description": "解析目标和交付物。",
                            "depends_on": [],
                            "tool_name": None,
                            "expected_output": "GoalCard",
                            "acceptance_criteria": ["目标字段完整"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "retrieve_memory",
                            "title": "检索记忆",
                            "step_type": "memory_retrieval",
                            "description": "检索历史记忆和证据。",
                            "depends_on": ["goal_interpretation"],
                            "tool_name": "retrieve_memory",
                            "expected_output": "记忆和证据",
                            "acceptance_criteria": ["输出来源信息"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "collect_trace",
                            "title": "读取 Trace",
                            "step_type": "tool_call",
                            "description": "读取当前运行 Trace 作为审计证据。",
                            "depends_on": ["retrieve_memory"],
                            "tool_name": "retrieve_trace",
                            "expected_output": "Trace 证据",
                            "acceptance_criteria": ["Trace 输出可审计"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "generate_content",
                            "title": "生成内容",
                            "step_type": "generation",
                            "description": "生成主体交付物。",
                            "depends_on": ["collect_trace"],
                            "tool_name": "write_artifact",
                            "expected_output": "结构化调研报告",
                            "acceptance_criteria": ["内容回应目标"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "fact_check_content",
                            "title": "事实核查",
                            "step_type": "tool_call",
                            "description": "核查事实风险。",
                            "depends_on": ["generate_content"],
                            "tool_name": "fact_check",
                            "expected_output": "事实核查结果",
                            "acceptance_criteria": ["输出风险项"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "evaluate_output",
                            "title": "质量评估",
                            "step_type": "evaluation",
                            "description": "评估产物质量。",
                            "depends_on": ["fact_check_content"],
                            "tool_name": None,
                            "expected_output": "评估结果",
                            "acceptance_criteria": ["评分达标"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "reflect_or_finalize",
                            "title": "反思收口",
                            "step_type": "reflection",
                            "description": "反思是否需要重规划。",
                            "depends_on": ["evaluate_output"],
                            "tool_name": None,
                            "expected_output": "完成判断",
                            "acceptance_criteria": ["明确下一步"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                        {
                            "id": "finalize",
                            "title": "最终交付",
                            "step_type": "finalization",
                            "description": "保存最终 Artifact。",
                            "depends_on": ["reflect_or_finalize"],
                            "tool_name": "write_artifact",
                            "expected_output": "最终 Artifact",
                            "acceptance_criteria": ["Artifact 已写入"],
                            "risk_level": "low",
                            "status": "pending",
                        },
                    ],
                    "edges": [
                        {"source": "goal_interpretation", "target": "retrieve_memory"},
                        {"source": "retrieve_memory", "target": "collect_trace"},
                        {"source": "collect_trace", "target": "generate_content"},
                        {"source": "generate_content", "target": "fact_check_content"},
                        {"source": "fact_check_content", "target": "evaluate_output"},
                        {"source": "evaluate_output", "target": "reflect_or_finalize"},
                        {"source": "reflect_or_finalize", "target": "finalize"},
                    ],
                    "quality_gates": [
                        {
                            "id": "fake_quality_gate",
                            "condition": "evaluation_score < 0.72",
                            "action": "reflect_and_replan",
                        }
                    ],
                    "max_steps": 12,
                    "max_replans": 2,
                },
                "selected_strategy": "fake_llm_dynamic_plan",
                "reasoning": "fake provider 生成动态 PlanGraph，用于验证 LLM Planner 通路。",
                "candidate_summaries": [
                    {"strategy": "trace_first", "reason": "优先验证证据链"},
                    {"strategy": "content_first", "reason": "优先生成产物"},
                ],
            }
        )

    return _build_generic_model(schema)


def _build_generic_model(schema: type[BaseModel]) -> BaseModel:
    values: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        values[name] = _fake_value_for_annotation(name, field.annotation)
    return schema.model_validate(values)


def _fake_value_for_annotation(name: str, annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is not None:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if origin is list:
            return []
        if origin is dict:
            return {}
        if args:
            return _fake_value_for_annotation(name, args[0])

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _build_generic_model(annotation)
    if annotation is bool:
        return False
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is dict:
        return {}
    return f"fake_{name}"


def _raw_message(parsed: BaseModel) -> AIMessage:
    content = json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False)
    prompt_tokens = max(1, len(content) // 4)
    completion_tokens = max(1, len(content) // 3)
    return AIMessage(
        content=content,
        response_metadata={
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
        },
    )
