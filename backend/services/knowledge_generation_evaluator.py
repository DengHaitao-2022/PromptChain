"""知识库 RAG 生成忠实性评测。"""

from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel, Field

from core.config import get_settings
from models.knowledge import (
    EvidencePack,
    GenerationFaithfulnessCase,
    GenerationFaithfulnessEvaluationResult,
)
from services.llm_provider import get_structured_llm_for_workspace
from services.llm_retry import invoke_with_llm_retry

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
CLAIM_SPLIT_PATTERN = re.compile(r"[。！？!?；;\n]+")

FAITHFULNESS_JUDGE_PROMPT = """你是 RAG 生成忠实性评测器。请只判断回答是否被给定证据支持。

## 用户问题
{query}

## 回答
{answer}

## 证据上下文
{contexts}

## 要求
1. 不评价文风，只评价回答中的事实性内容是否能由证据支持。
2. 若回答包含证据没有支持的事实，faithfulness_score 应降低。
3. unsupported_claims 只列出没有证据支持的关键声明。
4. reason 使用简短中文说明。"""


class _FaithfulnessJudgeOutput(BaseModel):
    """LLM judge 结构化输出。"""

    faithfulness_score: float = Field(ge=0, le=1)
    reason: str
    unsupported_claims: list[str] = Field(default_factory=list)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _collect_contexts(case: GenerationFaithfulnessCase) -> list[str]:
    contexts = [context.strip() for context in case.contexts if context.strip()]
    if case.evidence_pack:
        contexts.extend(_contexts_from_evidence_pack(case.evidence_pack))
    return contexts


def _contexts_from_evidence_pack(evidence_pack: EvidencePack) -> list[str]:
    return [chunk.content.strip() for chunk in evidence_pack.chunks if chunk.content.strip()]


def _extract_claims(answer: str) -> list[str]:
    claims = [part.strip() for part in CLAIM_SPLIT_PATTERN.split(answer) if part.strip()]
    return claims or [answer.strip()]


def _keyword_recall(claim: str, contexts: list[str]) -> float:
    claim_terms = Counter(_tokenize(claim))
    if not claim_terms:
        return 1.0
    context_terms = Counter(_tokenize("\n".join(contexts)))
    matched = sum(min(count, context_terms.get(term, 0)) for term, count in claim_terms.items())
    return matched / max(1, sum(claim_terms.values()))


class GenerationFaithfulnessEvaluator:
    """按配置执行 heuristic / LLM / Ragas 生成忠实性评测。"""

    def __init__(self, *, workspace_id: str | None = None, provider: str | None = None) -> None:
        settings = get_settings()
        self.workspace_id = workspace_id
        self.provider = provider or settings.KNOWLEDGE_GENERATION_EVAL_PROVIDER

    async def evaluate_case(
        self,
        case: GenerationFaithfulnessCase,
    ) -> GenerationFaithfulnessEvaluationResult:
        """评测单条生成结果。"""
        if self.provider == "ragas":
            return await self._evaluate_with_ragas(case)
        if self.provider == "llm":
            return await self._evaluate_with_llm(case)
        return self._evaluate_with_heuristic(case)

    def _evaluate_with_heuristic(
        self,
        case: GenerationFaithfulnessCase,
    ) -> GenerationFaithfulnessEvaluationResult:
        contexts = _collect_contexts(case)
        claims = _extract_claims(case.answer)
        if not contexts:
            return GenerationFaithfulnessEvaluationResult(
                case_id=case.id,
                query=case.query,
                faithfulness_score=0.0,
                passed=False,
                provider="heuristic",
                reason="缺少证据上下文，无法证明回答忠实于证据。",
                unsupported_claims=claims,
            )

        claim_scores = [_keyword_recall(claim, contexts) for claim in claims]
        unsupported_claims = [
            claim for claim, score in zip(claims, claim_scores, strict=False) if score < 0.35
        ]
        score = round(sum(claim_scores) / max(1, len(claim_scores)), 4)
        return GenerationFaithfulnessEvaluationResult(
            case_id=case.id,
            query=case.query,
            faithfulness_score=score,
            passed=score >= 0.7 and not unsupported_claims,
            provider="heuristic",
            reason="基于回答声明与证据上下文的关键词覆盖率估算。",
            unsupported_claims=unsupported_claims,
        )

    async def _evaluate_with_llm(
        self,
        case: GenerationFaithfulnessCase,
    ) -> GenerationFaithfulnessEvaluationResult:
        settings = get_settings()
        if not settings.KNOWLEDGE_GENERATION_EVAL_ALLOW_EXTERNAL_JUDGE:
            raise ValueError(
                "LLM judge 可能外发内容，需显式开启 KNOWLEDGE_GENERATION_EVAL_ALLOW_EXTERNAL_JUDGE"
            )

        from langchain_core.prompts import ChatPromptTemplate

        contexts = _collect_contexts(case)
        llm = await get_structured_llm_for_workspace(
            _FaithfulnessJudgeOutput,
            workspace_id=self.workspace_id,
            temperature=0,
        )
        chain = ChatPromptTemplate.from_template(FAITHFULNESS_JUDGE_PROMPT) | llm
        output = await invoke_with_llm_retry(
            lambda: chain.ainvoke(
                {
                    "query": case.query,
                    "answer": case.answer,
                    "contexts": "\n\n".join(contexts) or "无可用证据上下文。",
                }
            )
        )
        parsed = output.get("parsed") if isinstance(output, dict) else output
        if not isinstance(parsed, _FaithfulnessJudgeOutput):
            parsed = _FaithfulnessJudgeOutput.model_validate(parsed)
        return GenerationFaithfulnessEvaluationResult(
            case_id=case.id,
            query=case.query,
            faithfulness_score=round(parsed.faithfulness_score, 4),
            passed=parsed.faithfulness_score >= 0.7 and not parsed.unsupported_claims,
            provider="llm",
            reason=parsed.reason,
            unsupported_claims=parsed.unsupported_claims,
        )

    async def _evaluate_with_ragas(
        self,
        case: GenerationFaithfulnessCase,
    ) -> GenerationFaithfulnessEvaluationResult:
        settings = get_settings()
        if not settings.KNOWLEDGE_GENERATION_EVAL_ALLOW_EXTERNAL_JUDGE:
            raise ValueError(
                "Ragas 评测可能外发内容，需显式开启 KNOWLEDGE_GENERATION_EVAL_ALLOW_EXTERNAL_JUDGE"
            )

        contexts = _collect_contexts(case)
        try:
            from openai import AsyncOpenAI
            from ragas.llms import llm_factory
            from ragas.metrics.collections import Faithfulness
        except ImportError as exc:  # pragma: no cover - 可选依赖只在 ragas 模式触发
            raise RuntimeError("Ragas 评测需要安装 ragas 及 openai 依赖") from exc

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or None)
        metric = Faithfulness(llm=llm_factory(settings.KNOWLEDGE_RAGAS_MODEL, client=client))
        result = await metric.ascore(
            user_input=case.query,
            response=case.answer,
            retrieved_contexts=contexts,
        )
        score = float(getattr(result, "value", result))
        return GenerationFaithfulnessEvaluationResult(
            case_id=case.id,
            query=case.query,
            faithfulness_score=round(score, 4),
            passed=score >= 0.7,
            provider="ragas",
            reason="Ragas Faithfulness 指标评测结果。",
            unsupported_claims=[],
        )
