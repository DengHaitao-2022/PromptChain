"""
事实核查节点 (Chain of Verification - CoVe)

实现四步验证链：
1. 生成基线响应（已由其他节点完成）
2. 规划验证问题
3. 独立执行验证（Factored模式，避免确认偏误）
4. 生成最终修正

Source: Chain of Verification (CoVe) - Meta AI Research
"""

import json

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from core.time import utc_now_iso, utc_now_naive
from models import (
    ArtifactType,
    FactCheckReport,
    FactClaim,
    HumanDecision,
    LLMCallRecord,
    NodeRun,
    NodeRunStatus,
    VerificationResult,
)
from services import (
    get_artifact_store,
    get_current_model_info_for_workspace,
    get_llm_for_workspace,
    get_structured_llm_for_workspace,
    invoke_with_llm_retry,
)

# ==================== Prompt 模板 ====================

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

## 要求
1. 仅基于你的知识库回答
2. 如果不确定，请明确表示
3. 提供尽可能准确的答案

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


# ==================== 结构化输出模型 ====================


class ClaimList(BaseModel):
    """提取的事实声明列表"""

    claims: list[FactClaim] = Field(default_factory=list)


class VerificationEvaluation(BaseModel):
    """验证评估结果"""

    is_verified: bool
    confidence: float = Field(ge=0, le=1)
    risk_level: str = Field(pattern="^(low|medium|high)$")
    suggested_correction: str | None = None


def _now_iso() -> str:
    return utc_now_iso()


def _build_gate_questions(report: FactCheckReport) -> list[dict]:
    questions: list[dict] = []
    for result in report.results:
        if result.risk_level != "high":
            continue
        questions.append(
            {
                "claim_id": result.claim_id,
                "question": result.verification_question,
                "risk_level": result.risk_level,
                "suggested_correction": result.suggested_correction,
            }
        )
    return questions


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


def _apply_corrections_to_sections(
    sections: dict[str, str],
    corrections: dict[str, dict[str, str]],
) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    updated_sections = dict(sections)
    applied_corrections: dict[str, dict[str, str]] = {}
    failed_corrections: dict[str, dict[str, str]] = {}

    for correction in corrections.values():
        section_id = correction["section_id"]
        section_text = updated_sections.get(section_id)
        if not section_text:
            failed_corrections[correction["claim_id"]] = {
                **correction,
                "reason": "section_not_found",
            }
            continue

        original = correction["original"]
        replacement = correction["replacement"]
        if original not in section_text:
            failed_corrections[correction["claim_id"]] = {
                **correction,
                "reason": "original_text_not_found",
            }
            continue

        updated_sections[section_id] = section_text.replace(original, replacement, 1)
        applied_corrections[correction["claim_id"]] = correction

    return updated_sections, applied_corrections, failed_corrections


def _build_failed_correction_message(failed_corrections: dict[str, dict[str, str]]) -> str:
    parts = []
    for claim_id, correction in failed_corrections.items():
        parts.append(f"{claim_id}:{correction['reason']}")
    return ", ".join(parts)


def _mark_result_resolved(result: VerificationResult) -> None:
    result.is_verified = True
    result.risk_level = "low"


def _get_high_risk_claim_ids(report: FactCheckReport) -> list[str]:
    return [result.claim_id for result in report.results if result.risk_level == "high"]


def _get_missing_gate_decisions(
    report: FactCheckReport,
    decisions: dict[str, str],
) -> list[str]:
    return [
        claim_id for claim_id in _get_high_risk_claim_ids(report) if not decisions.get(claim_id)
    ]


def _build_final_content_payload(
    state: dict,
    updated_sections: dict[str, str],
    corrections: dict[str, dict[str, str]],
    fact_check_artifact_id: str,
) -> dict:
    compiled_sections: list[str] = []
    section_order: list[str] = []
    outline = state.get("outline")
    if outline is not None:
        for section in outline.get_flat_sections():
            content = updated_sections.get(section.id)
            if not content:
                continue
            section_order.append(section.id)
            compiled_sections.append(f"## {section.title}\n{content}")
    else:
        for section_id, content in updated_sections.items():
            section_order.append(section_id)
            compiled_sections.append(f"## {section_id}\n{content}")

    return {
        "sections": updated_sections,
        "section_order": section_order,
        "compiled_content": "\n\n".join(compiled_sections),
        "refinement_history": state.get("refinement_history", []),
        "fact_corrections": corrections,
        "fact_check_artifact_id": fact_check_artifact_id,
    }


# ==================== CoVe 四步验证链 ====================


async def extract_fact_claims(
    content: str,
    section_id: str,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_name: str | None = None,
) -> list[FactClaim]:
    """
    步骤1：从内容中提取事实性声明
    """
    llm = await get_structured_llm_for_workspace(
        ClaimList,
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
    )
    prompt = ChatPromptTemplate.from_template(EXTRACT_CLAIMS_PROMPT)
    chain = prompt | llm

    result: ClaimList = await invoke_with_llm_retry(lambda: chain.ainvoke({"content": content}))

    # 为每个claim设置section_id
    for claim in result.claims:
        claim.section_id = section_id

    return result.claims


async def generate_verification_question(
    claim: FactClaim,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_name: str | None = None,
) -> str:
    """
    步骤2：为声明生成验证问题
    """
    llm = await get_llm_for_workspace(
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
        temperature=0.3,
    )
    prompt = ChatPromptTemplate.from_template(GENERATE_VERIFICATION_QUESTIONS_PROMPT)
    chain = prompt | llm

    result = await invoke_with_llm_retry(
        lambda: chain.ainvoke({"claim_text": claim.text, "claim_category": claim.category})
    )

    return result.content.strip()


async def execute_verification(
    question: str,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_name: str | None = None,
) -> str:
    """
    步骤3：独立回答验证问题（Factored模式）

    关键：不提供原始声明作为上下文，避免确认偏误
    """
    llm = await get_llm_for_workspace(
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
        temperature=0.2,
    )  # 低温度以获得更确定的答案
    prompt = ChatPromptTemplate.from_template(EXECUTE_VERIFICATION_PROMPT)
    chain = prompt | llm

    result = await invoke_with_llm_retry(lambda: chain.ainvoke({"question": question}))

    return result.content.strip()


async def evaluate_claim_accuracy(
    claim: FactClaim,
    verification_question: str,
    verification_answer: str,
    workspace_id: str | None = None,
    model_provider_id: str | None = None,
    model_name: str | None = None,
) -> VerificationResult:
    """
    步骤4：评估声明准确性
    """
    llm = await get_structured_llm_for_workspace(
        VerificationEvaluation,
        workspace_id,
        model=model_name,
        model_provider_id=model_provider_id,
    )
    prompt = ChatPromptTemplate.from_template(EVALUATE_CLAIM_PROMPT)
    chain = prompt | llm

    evaluation: VerificationEvaluation = await invoke_with_llm_retry(
        lambda: chain.ainvoke(
            {
                "claim_text": claim.text,
                "verification_question": verification_question,
                "verification_answer": verification_answer,
            }
        )
    )

    return VerificationResult(
        claim_id=claim.id,
        is_verified=evaluation.is_verified,
        confidence=evaluation.confidence,
        risk_level=evaluation.risk_level,
        suggested_correction=evaluation.suggested_correction,
        verification_question=verification_question,
        verification_answer=verification_answer,
    )


# ==================== 主节点函数 ====================


async def check_facts(state: dict) -> dict:
    """
    事实核查节点 - 完整的 CoVe 验证链

    输入 state:
        - draft_sections: Dict[str, str] 或 final_content
        - workflow_run_id: str

    输出更新:
        - fact_check_report: FactCheckReport
        - fact_check_artifact_id: str
        - awaiting_fact_check_approval: bool (如有高风险项)
    """
    # 获取要核查的内容
    content_dict = state.get("final_content") or state.get("draft_sections", {})
    workflow_run_id = state["workflow_run_id"]
    workspace_id = state.get("workspace_id")
    model_provider_id = state.get("model_provider_id")
    model_name = state.get("model_name")
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="check_facts",
        node_type="checker",
        started_at=utc_now_naive(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id
            for artifact_id in [
                state.get("final_content_artifact_id"),
                *list(state.get("section_artifact_ids", {}).values()),
            ]
            if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        all_claims: list[FactClaim] = []
        all_results: list[VerificationResult] = []

        # 遍历每个章节提取并验证事实声明
        for section_id, content in content_dict.items():
            # 步骤1：提取事实声明
            start_time = utc_now_naive()
            claims = await extract_fact_claims(
                content,
                section_id,
                workspace_id,
                model_provider_id,
                model_name,
            )
            end_time = utc_now_naive()

            all_claims.extend(claims)

            # 记录LLM调用（动态获取模型配置）
            model_info = await get_current_model_info_for_workspace(
                workspace_id,
                model_provider_id=model_provider_id,
                model=model_name,
            )
            llm_call = LLMCallRecord(
                model=model_info["model"],
                provider=model_info["provider"],
                latency_ms=int((end_time - start_time).total_seconds() * 1000),
                prompt_preview=f"Extract claims from section {section_id}",
                response_preview=f"Found {len(claims)} claims",
            )
            node_run.llm_calls.append(llm_call)

            # 对每个声明执行 CoVe 验证
            for claim in claims:
                # 步骤2：生成验证问题
                start_time = utc_now_naive()
                question = await generate_verification_question(
                    claim,
                    workspace_id,
                    model_provider_id,
                    model_name,
                )

                # 步骤3：独立执行验证
                answer = await execute_verification(
                    question,
                    workspace_id,
                    model_provider_id,
                    model_name,
                )

                # 步骤4：评估准确性
                result = await evaluate_claim_accuracy(
                    claim,
                    question,
                    answer,
                    workspace_id,
                    model_provider_id,
                    model_name,
                )
                end_time = utc_now_naive()

                all_results.append(result)

                # 记录LLM调用
                model_info = await get_current_model_info_for_workspace(
                    workspace_id,
                    model_provider_id=model_provider_id,
                    model=model_name,
                )
                llm_call = LLMCallRecord(
                    model=model_info["model"],
                    provider=model_info["provider"],
                    latency_ms=int((end_time - start_time).total_seconds() * 1000),
                    prompt_preview=f"Verify: {claim.text[:50]}...",
                    response_preview=f"Verified: {result.is_verified}, Risk: {result.risk_level}",
                )
                node_run.llm_calls.append(llm_call)

        # 生成报告
        report = FactCheckReport(claims=all_claims, results=all_results)
        report.compute_stats()

        # 创建 Artifact
        artifact = await store.create_artifact(
            artifact_type=ArtifactType.FACT_CHECK_REPORT,
            content=report.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            metadata={
                "high_risk_count": report.high_risk_count,
                "awaiting_approval": report.has_high_risk_items(),
                "source_final_content_artifact_id": state.get("final_content_artifact_id"),
            },
        )
        node_run.output_artifact_ids.append(artifact.id)

        # 如果有高风险项，标记为需要用户确认
        if report.has_high_risk_items():
            gate_opened_at = _now_iso()
            await _update_gate_metadata(
                store,
                workflow_run_id,
                {
                    "gate_type": "fact_check",
                    "trigger_reason": "fact_risk",
                    "questions": _build_gate_questions(report),
                    "answers": None,
                    "opened_at": gate_opened_at,
                    "handled_at": None,
                    "resolution": None,
                },
            )
            node_run.complete(NodeRunStatus.INTERRUPTED)
            await store.update_node_run(node_run)

            return {
                **state,
                "fact_check_report": report,
                "fact_check_artifact_id": artifact.id,
                "awaiting_fact_check_approval": True,
                "fact_check_decisions": None,
                "manual_corrections": None,
            }

        # 无高风险项，直接完成
        await _update_gate_metadata(store, workflow_run_id, None)
        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "fact_check_report": report,
            "fact_check_artifact_id": artifact.id,
            "awaiting_fact_check_approval": False,
            "fact_check_decisions": None,
            "manual_corrections": None,
        }

    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise


async def approve_fact_check(state: dict) -> dict:
    """
    处理用户对事实核查结果的审批

    输入 state:
        - fact_check_report: FactCheckReport
        - fact_check_decisions: Dict[claim_id, decision]
          decision: "confirm" | "use_suggestion" | "manual"
        - manual_corrections: Dict[claim_id, correction_text]
    """
    report = FactCheckReport.model_validate(state["fact_check_report"])
    decisions = state.get("fact_check_decisions", {})
    manual_corrections = state.get("manual_corrections", {})
    workflow_run_id = state["workflow_run_id"]
    store = get_artifact_store()

    # 创建节点运行记录
    node_run = NodeRun(
        workflow_run_id=workflow_run_id,
        node_name="approve_fact_check",
        node_type="gate",
        started_at=utc_now_naive(),
        status=NodeRunStatus.RUNNING,
        input_artifact_ids=[
            artifact_id
            for artifact_id in [
                state.get("fact_check_artifact_id"),
                state.get("final_content_artifact_id"),
            ]
            if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        missing_decisions = _get_missing_gate_decisions(report, decisions)
        if missing_decisions:
            raise ValueError(
                f"Fact-check approval incomplete: missing_decisions={','.join(missing_decisions)}"
            )

        # 应用用户决策
        requested_corrections: dict[str, dict[str, str]] = {}
        failed_corrections: dict[str, dict[str, str]] = {}
        handled_at = _now_iso()

        for claim_id, decision in decisions.items():
            # 找到对应的结果
            result = next((r for r in report.results if r.claim_id == claim_id), None)
            claim = next((c for c in report.claims if c.id == claim_id), None)

            if not result or not claim:
                failed_corrections[claim_id] = {
                    "claim_id": claim_id,
                    "reason": "claim_or_result_not_found",
                }
                continue

            if decision == "confirm":
                # 用户确认无误，标记为已验证
                _mark_result_resolved(result)
            elif decision == "use_suggestion":
                # 采用系统建议的修正
                if not result.suggested_correction:
                    failed_corrections[claim_id] = {
                        "claim_id": claim_id,
                        "reason": "suggested_correction_missing",
                    }
                    continue
                requested_corrections[claim_id] = {
                    "claim_id": claim_id,
                    "section_id": claim.section_id,
                    "original": claim.text,
                    "replacement": result.suggested_correction,
                    "decision": decision,
                }
            elif decision == "manual":
                # 使用用户手动提供的修正
                replacement = manual_corrections.get(claim_id)
                if not replacement:
                    failed_corrections[claim_id] = {
                        "claim_id": claim_id,
                        "reason": "manual_correction_missing",
                    }
                    continue
                requested_corrections[claim_id] = {
                    "claim_id": claim_id,
                    "section_id": claim.section_id,
                    "original": claim.text,
                    "replacement": replacement,
                    "decision": decision,
                }
            else:
                failed_corrections[claim_id] = {
                    "claim_id": claim_id,
                    "reason": f"unsupported_decision:{decision}",
                }

        updated_final_content, applied_corrections, application_failures = (
            _apply_corrections_to_sections(
                state.get("final_content") or state.get("draft_sections", {}),
                requested_corrections,
            )
        )
        failed_corrections.update(application_failures)

        if failed_corrections:
            raise ValueError(
                "Fact-check corrections could not be applied: "
                f"{_build_failed_correction_message(failed_corrections)}"
            )

        for claim_id in applied_corrections:
            result = next((item for item in report.results if item.claim_id == claim_id), None)
            if result is not None:
                _mark_result_resolved(result)

        # 记录人工决策
        node_run.human_decision = HumanDecision(
            decision_type="modify" if applied_corrections else "approve",
            user_input=json.dumps(
                {
                    "decisions": decisions,
                    "manual_corrections": manual_corrections,
                },
                ensure_ascii=False,
            ),
            modified_content=applied_corrections or None,
        )

        # 更新报告
        report.compute_stats()

        # 创建新版本 Artifact
        report_artifact = await store.create_artifact(
            artifact_type=ArtifactType.FACT_CHECK_REPORT,
            content=report.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            parent_version_id=state.get("fact_check_artifact_id"),
            metadata={
                "gate_type": "fact_check",
                "user_decisions": decisions,
                "manual_corrections": manual_corrections,
                "corrections_requested": requested_corrections,
                "corrections_applied": applied_corrections,
                "handled_at": handled_at,
            },
        )
        node_run.output_artifact_ids.append(report_artifact.id)

        final_content_artifact = await store.create_artifact(
            artifact_type=ArtifactType.FINAL_CONTENT,
            content=_build_final_content_payload(
                state,
                updated_final_content,
                applied_corrections,
                report_artifact.id,
            ),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            parent_version_id=state.get("final_content_artifact_id"),
            metadata={
                "gate_type": "fact_check",
                "resolution": "approved_with_changes" if applied_corrections else "approved",
                "fact_check_artifact_id": report_artifact.id,
            },
        )
        node_run.output_artifact_ids.append(final_content_artifact.id)

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
                "gate_type": "fact_check",
                "trigger_reason": current_gate.get("trigger_reason") or "fact_risk",
                "questions": current_gate.get("questions") or _build_gate_questions(report),
                "answers": {
                    "decisions": decisions,
                    "manual_corrections": manual_corrections,
                },
                "opened_at": current_gate.get("opened_at") or handled_at,
                "handled_at": handled_at,
                "resolution": "approved_with_changes" if applied_corrections else "approved",
            },
        )

        node_run.complete(NodeRunStatus.COMPLETED)
        await store.update_node_run(node_run)

        return {
            **state,
            "fact_check_report": report,
            "fact_check_artifact_id": report_artifact.id,
            "awaiting_fact_check_approval": False,
            "fact_check_decisions": None,
            "manual_corrections": None,
            "fact_corrections": applied_corrections,
            "final_content": updated_final_content,
            "final_content_artifact_id": final_content_artifact.id,
        }

    except Exception as e:
        node_run.complete(NodeRunStatus.FAILED, str(e))
        await store.update_node_run(node_run)
        raise
