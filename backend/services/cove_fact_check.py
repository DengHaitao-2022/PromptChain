"""CoVe 事实核查公共服务。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.fact_check import FactClaim, VerificationResult
from services.llm_provider import build_structured_chain_for_workspace, get_llm_for_workspace
from services.llm_retry import invoke_with_llm_retry
from services.llm_usage import (
    ensure_usage_metadata,
    extract_usage_metadata,
    invoke_structured_with_usage,
)

EXTRACT_CLAIMS_PROMPT = """从以下文章内容中提取所有事实性声明。

事实性声明包括：
- 数字/统计数据（如"增长了50%"）
- 日期/时间（如"2024年发布"）
- 引用/来源（如"根据XXX研究"）
- 政策/规定（如"按照XXX规定"）
- 具体事件（如"XXX公司推出了XXX产品"）

## 文章内容
{content}

## 要求
1. 仅提取需要核实的事实性声明
2. 不要提取主观观点或常识性内容
3. 每个声明应该是独立可验证的

请输出JSON格式的事实声明列表。"""


GENERATE_VERIFICATION_QUESTIONS_PROMPT = """为以下事实声明生成验证问题。

## 事实声明
{claim_text}

## 声明类型
{claim_category}

## 要求
生成一个可用于验证此声明真伪的具体问题。
问题应该：
1. 具体且可回答
2. 不包含原声明中的结论
3. 能够独立验证声明的准确性

请只输出一个验证问题（纯文本，不需要其他格式）。"""


EXECUTE_VERIFICATION_PROMPT = """请回答以下问题。

## 问题
{question}

## Evidence Artifact
{evidence_context}

## 要求
1. 如果 Evidence Artifact 提供了相关内容，必须优先基于证据回答
2. 如果不确定，请明确表示
3. 提供尽可能准确的答案
4. 如果证据不足，请直接说明“当前证据不足”

请直接回答问题。"""


EVALUATE_CLAIM_PROMPT = """评估以下事实声明的准确性。

## 原始声明
{claim_text}

## 验证问题
{verification_question}

## 验证答案
{verification_answer}

## 要求
请评估原始声明与验证答案是否一致，输出：
1. is_verified: 声明是否准确（true/false）
2. confidence: 置信度（0-1之间的小数）
3. risk_level: 风险等级（"low"/"medium"/"high"）
4. suggested_correction: 如果声明不准确，提供建议修正（可为null）

请输出JSON格式。"""


class ClaimList(BaseModel):
    """提取的事实声明列表。"""

    claims: list[FactClaim] = Field(default_factory=list)


class VerificationEvaluation(BaseModel):
    """验证评估结果。"""

    is_verified: bool
    confidence: float = Field(ge=0, le=1)
    risk_level: str = Field(pattern="^(low|medium|high)$")
    suggested_correction: str | None = None


async def extract_fact_claims(
    content: str,
    section_id: str,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    model_name: str | None = None,
) -> tuple[list[FactClaim], dict[str, int]]:
    """步骤1：从内容中提取事实性声明。"""
    chain, _structured_runtime = await build_structured_chain_for_workspace(
        ClaimList,
        EXTRACT_CLAIMS_PROMPT,
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
        model_provider_name=model_provider_name,
    )

    result, usage = await invoke_with_llm_retry(
        lambda: invoke_structured_with_usage(chain, {"content": content})
    )

    for claim in result.claims:
        claim.section_id = section_id

    usage = ensure_usage_metadata(
        usage,
        prompt_text=content,
        completion_text=str(result.model_dump()),
    )
    return result.claims, usage


async def generate_verification_question(
    claim: FactClaim,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    model_name: str | None = None,
) -> tuple[str, dict[str, int]]:
    """步骤2：为声明生成验证问题。"""
    llm = await get_llm_for_workspace(
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
        model_provider_name=model_provider_name,
        temperature=0.3,
    )
    prompt = ChatPromptTemplate.from_template(GENERATE_VERIFICATION_QUESTIONS_PROMPT)
    chain = prompt | llm

    result = await invoke_with_llm_retry(
        lambda: chain.ainvoke({"claim_text": claim.text, "claim_category": claim.category})
    )

    question = result.content.strip()
    usage = ensure_usage_metadata(
        extract_usage_metadata(result),
        prompt_text=claim.text,
        completion_text=question,
    )
    return question, usage


async def execute_verification(
    question: str,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    model_name: str | None = None,
    evidence_context: str | None = None,
) -> tuple[str, dict[str, int]]:
    """步骤3：独立回答验证问题，避免确认偏误。"""
    llm = await get_llm_for_workspace(
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
        model_provider_name=model_provider_name,
        temperature=0.2,
    )
    prompt = ChatPromptTemplate.from_template(EXECUTE_VERIFICATION_PROMPT)
    chain = prompt | llm

    result = await invoke_with_llm_retry(
        lambda: chain.ainvoke(
            {
                "question": question,
                "evidence_context": evidence_context or "未启用知识库或未检索到可用证据。",
            }
        )
    )

    answer = result.content.strip()
    usage = ensure_usage_metadata(
        extract_usage_metadata(result),
        prompt_text=question,
        completion_text=answer,
    )
    return answer, usage


async def evaluate_claim_accuracy(
    claim: FactClaim,
    verification_question: str,
    verification_answer: str,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_provider_name: str | None = None,
    model_name: str | None = None,
) -> tuple[VerificationResult, dict[str, int]]:
    """步骤4：评估声明准确性。"""
    chain, _structured_runtime = await build_structured_chain_for_workspace(
        VerificationEvaluation,
        EVALUATE_CLAIM_PROMPT,
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
        model_provider_name=model_provider_name,
    )

    evaluation, usage = await invoke_with_llm_retry(
        lambda: invoke_structured_with_usage(
            chain,
            {
                "claim_text": claim.text,
                "verification_question": verification_question,
                "verification_answer": verification_answer,
            },
        )
    )

    usage = ensure_usage_metadata(
        usage,
        prompt_text=f"{claim.text}\n{verification_question}\n{verification_answer}",
        completion_text=str(evaluation.model_dump()),
    )
    return (
        VerificationResult(
            claim_id=claim.id,
            is_verified=evaluation.is_verified,
            confidence=evaluation.confidence,
            risk_level=evaluation.risk_level,
            suggested_correction=evaluation.suggested_correction,
            verification_question=verification_question,
            verification_answer=verification_answer,
        ),
        usage,
    )
