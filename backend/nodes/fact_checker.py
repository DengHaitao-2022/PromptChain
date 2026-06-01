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

from core.time import utc_now_iso, utc_now_naive
from graph.runtime_plan import runtime_feature_enabled
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
)
from services.cove_fact_check import (
    evaluate_claim_accuracy,
    execute_verification,
    extract_fact_claims,
    generate_verification_question,
)


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


def _format_evidence_context(state: dict, *, max_chunks: int = 10) -> str:
    """为事实核查准备证据上下文。"""
    evidence_pack = state.get("evidence_pack")
    if not evidence_pack:
        return "未启用知识库或未检索到可用证据。"

    chunks = getattr(evidence_pack, "chunks", None)
    if chunks is None and isinstance(evidence_pack, dict):
        chunks = evidence_pack.get("chunks")
    if not chunks:
        unverified = getattr(evidence_pack, "unverified_points", None)
        if unverified is None and isinstance(evidence_pack, dict):
            unverified = evidence_pack.get("unverified_points")
        if unverified:
            return f"未检索到足够证据；需标记未验证点：{', '.join(map(str, unverified))}"
        return "未启用知识库或未检索到可用证据。"

    lines: list[str] = []
    for index, chunk in enumerate(chunks[:max_chunks], start=1):
        document_name = getattr(chunk, "document_name", None)
        content = getattr(chunk, "content", None)
        score = getattr(chunk, "score", None)
        if isinstance(chunk, dict):
            document_name = chunk.get("document_name")
            content = chunk.get("content")
            score = chunk.get("score")
        if not content:
            continue
        lines.append(f"[{index}] 来源：{document_name or '未知文档'}；分数：{score}\n{content}")
    return "\n\n".join(lines) if lines else "未启用知识库或未检索到可用证据。"


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
    model_provider_name = state.get("model_provider_name")
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
                state.get("evidence_artifact_id"),
                *list(state.get("section_artifact_ids", {}).values()),
            ]
            if artifact_id
        ],
    )
    await store.create_node_run(node_run)

    try:
        all_claims: list[FactClaim] = []
        all_results: list[VerificationResult] = []
        evidence_context = _format_evidence_context(state)

        # 遍历每个章节提取并验证事实声明
        for section_id, content in content_dict.items():
            # 步骤1：提取事实声明
            start_time = utc_now_naive()
            claims, usage = await extract_fact_claims(
                content,
                section_id,
                workspace_id,
                model_provider_id,
                model_provider_name,
                model_name,
            )
            end_time = utc_now_naive()

            all_claims.extend(claims)

            # 记录LLM调用（动态获取模型配置）
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
                prompt_preview=f"Extract claims from section {section_id}",
                response_preview=f"Found {len(claims)} claims",
            )
            node_run.llm_calls.append(llm_call)

            # 对每个声明执行 CoVe 验证
            for claim in claims:
                # 步骤2：生成验证问题
                start_time = utc_now_naive()
                question, question_usage = await generate_verification_question(
                    claim,
                    workspace_id,
                    model_provider_id,
                    model_provider_name,
                    model_name,
                )

                # 步骤3：独立执行验证
                answer, answer_usage = await execute_verification(
                    question,
                    workspace_id,
                    model_provider_id,
                    model_provider_name,
                    model_name,
                    evidence_context,
                )

                # 步骤4：评估准确性
                result, evaluation_usage = await evaluate_claim_accuracy(
                    claim,
                    question,
                    answer,
                    workspace_id,
                    model_provider_id,
                    model_provider_name,
                    model_name,
                )
                end_time = utc_now_naive()

                all_results.append(result)

                # 记录LLM调用
                model_info = await get_current_model_info_for_workspace(
                    workspace_id,
                    model_provider_id=model_provider_id,
                    model_provider_name=model_provider_name,
                    model=model_name,
                )
                llm_call = LLMCallRecord(
                    model=model_info["model"],
                    provider=model_info["provider"],
                    prompt_tokens=(
                        question_usage["prompt_tokens"]
                        + answer_usage["prompt_tokens"]
                        + evaluation_usage["prompt_tokens"]
                    ),
                    completion_tokens=(
                        question_usage["completion_tokens"]
                        + answer_usage["completion_tokens"]
                        + evaluation_usage["completion_tokens"]
                    ),
                    total_tokens=(
                        question_usage["total_tokens"]
                        + answer_usage["total_tokens"]
                        + evaluation_usage["total_tokens"]
                    ),
                    latency_ms=int((end_time - start_time).total_seconds() * 1000),
                    prompt_preview=f"Verify: {claim.text[:50]}...",
                    response_preview=f"Verified: {result.is_verified}, Risk: {result.risk_level}",
                )
                node_run.llm_calls.append(llm_call)

        # 生成报告
        report = FactCheckReport(claims=all_claims, results=all_results)
        report.compute_stats()
        fact_check_gate_enabled = runtime_feature_enabled(
            state,
            "fact_check_gate",
            default=True,
        )
        awaiting_approval = report.has_high_risk_items() and fact_check_gate_enabled

        # 创建 Artifact
        artifact = await store.create_artifact(
            artifact_type=ArtifactType.FACT_CHECK_REPORT,
            content=report.model_dump(),
            workflow_run_id=workflow_run_id,
            node_run_id=node_run.id,
            metadata={
                "high_risk_count": report.high_risk_count,
                "awaiting_approval": awaiting_approval,
                "source_final_content_artifact_id": state.get("final_content_artifact_id"),
                "evidence_artifact_id": state.get("evidence_artifact_id"),
                "knowledge_conflicts": state.get("knowledge_conflicts", []),
                "unverified_points": state.get("unverified_points", []),
            },
        )
        node_run.output_artifact_ids.append(artifact.id)

        # 只有发布图启用了事实核查 Gate 时，高风险项才会暂停等待用户确认。
        if awaiting_approval:
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
