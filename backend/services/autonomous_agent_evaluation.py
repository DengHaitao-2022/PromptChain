"""Evaluator / Reflector / Memory Manager。"""

from __future__ import annotations

from typing import Any

from models.autonomous_agent import (
    AgentRun,
    AgentStep,
    EvalResult,
    EvaluationTargetType,
    MemoryRecord,
    MemoryType,
)
from services.autonomous_agent_store import AutonomousAgentStore


class AgentEvaluator:
    """评估步骤和最终产物是否满足目标。"""

    def evaluate_step(self, run: AgentRun, step: AgentStep) -> EvalResult:
        """评估单个步骤输出。"""
        issues: list[dict[str, Any]] = []
        suggestions: list[dict[str, Any]] = []

        if step.error_message:
            issues.append({"code": "STEP_ERROR", "message": step.error_message, "severity": "high"})
        if not step.output:
            issues.append(
                {"code": "EMPTY_OUTPUT", "message": "步骤未产生输出", "severity": "medium"}
            )
            suggestions.append(
                {"action": "retry_or_replan", "message": "补充输入后重新执行或局部重规划"}
            )

        output_text = _flatten_text(step.output)
        self._evaluate_plan_validity(step, issues, suggestions)
        self._evaluate_tool_result(step, issues, suggestions)
        self._evaluate_evidence_sufficiency(step, issues, suggestions)
        self._evaluate_fact_check_result(step, issues, suggestions)

        goal_keywords = _keywords(run.goal)
        coverage = _coverage_score(output_text, goal_keywords)
        content_step_types = {"generation", "finalization"}
        if coverage < 0.45 and step.step_type.value in content_step_types:
            issues.append(
                {
                    "code": "LOW_GOAL_COVERAGE",
                    "message": "步骤输出对目标关键词覆盖不足",
                    "severity": "medium",
                    "coverage": coverage,
                }
            )
            suggestions.append(
                {"action": "collect_more_evidence", "message": "补充证据后重写该步骤"}
            )

        penalty = sum(_issue_penalty(issue) for issue in issues)
        if step.step_type.value not in content_step_types:
            score = max(0.0, min(1.0, 0.86 - penalty))
        else:
            score = max(0.0, min(1.0, 0.55 + coverage * 0.45 - penalty))
        return EvalResult(
            run_id=run.id,
            step_id=step.id,
            target_type=EvaluationTargetType.STEP,
            score=round(score, 3),
            passed=score >= 0.72 and not _has_blocking_issue(issues),
            issues=issues,
            suggestions=suggestions,
            metadata={
                "goal_keyword_count": len(goal_keywords),
                "coverage": coverage,
                "evaluator_version": "agent-step-evaluator-v2",
            },
        )

    def evaluate_final_output(
        self,
        run: AgentRun,
        steps: list[AgentStep],
        eval_results: list[EvalResult],
    ) -> EvalResult:
        """评估最终输出是否达成目标。"""
        final_text = "\n".join(_flatten_text(step.output) for step in steps)
        goal_keywords = _keywords(run.goal)
        coverage = _coverage_score(final_text, goal_keywords)
        failed_evals = [item for item in eval_results if not item.passed]
        issues: list[dict[str, Any]] = []

        if coverage < 0.55:
            issues.append(
                {
                    "code": "FINAL_GOAL_COVERAGE_LOW",
                    "message": "最终输出未充分覆盖用户目标",
                    "severity": "high",
                    "coverage": coverage,
                }
            )
        if failed_evals:
            issues.append(
                {
                    "code": "UNRESOLVED_STEP_ISSUES",
                    "message": "仍存在未通过的步骤评估",
                    "severity": "medium",
                    "count": len(failed_evals),
                }
            )
        fact_risk = _latest_fact_check_risk(steps)
        if fact_risk["high_risk_count"] > 0:
            issues.append(
                {
                    "code": "FINAL_FACTUAL_RISK_UNRESOLVED",
                    "message": "最终交付仍存在未关闭的事实核查高风险项",
                    "severity": "high",
                    **fact_risk,
                }
            )
        if not _has_final_artifact(steps):
            issues.append(
                {
                    "code": "FINAL_ARTIFACT_MISSING",
                    "message": "最终交付缺少版本化 Artifact",
                    "severity": "high",
                }
            )

        penalty = len(failed_evals) * 0.08 + sum(_issue_penalty(issue) for issue in issues)
        score = max(0.0, min(1.0, 0.45 + coverage * 0.55 - penalty))
        return EvalResult(
            run_id=run.id,
            step_id=None,
            target_type=EvaluationTargetType.FINAL_OUTPUT,
            score=round(score, 3),
            passed=score >= 0.75 and not _has_blocking_issue(issues),
            issues=issues,
            suggestions=[{"action": "replan", "message": "围绕未覆盖目标插入补充生成步骤"}]
            if issues
            else [],
            metadata={
                "coverage": coverage,
                "step_eval_count": len(eval_results),
                "fact_risk": fact_risk,
                "evaluator_version": "agent-final-evaluator-v2",
            },
        )

    def _evaluate_plan_validity(
        self,
        step: AgentStep,
        issues: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
    ) -> None:
        if step.step_type.value != "planning":
            return
        plan_graph = step.output.get("plan_graph")
        if not isinstance(plan_graph, dict):
            return
        nodes = plan_graph.get("nodes") or []
        edges = plan_graph.get("edges") or []
        if not nodes:
            issues.append(
                {"code": "PLAN_GRAPH_EMPTY", "message": "计划图没有节点", "severity": "high"}
            )
        node_ids = {str(node.get("id")) for node in nodes if isinstance(node, dict)}
        missing_dependencies = [
            dependency
            for node in nodes
            if isinstance(node, dict)
            for dependency in node.get("depends_on", [])
            if str(dependency) not in node_ids
        ]
        if missing_dependencies:
            issues.append(
                {
                    "code": "PLAN_DEPENDENCY_MISSING",
                    "message": "计划图存在不存在的依赖节点",
                    "severity": "high",
                    "dependencies": missing_dependencies[:8],
                }
            )
        if nodes and not edges:
            suggestions.append(
                {"action": "repair_plan_graph", "message": "补齐计划边，便于前端展示和审计"}
            )

    def _evaluate_tool_result(
        self,
        step: AgentStep,
        issues: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
    ) -> None:
        if step.step_type.value != "tool_call":
            return
        if "error" in step.output:
            issues.append(
                {
                    "code": "TOOL_RESULT_ERROR",
                    "message": str(step.output.get("error")),
                    "severity": "high",
                }
            )
            suggestions.append(
                {"action": "replace_tool_or_retry", "message": "更换工具、修正输入后重试"}
            )
        if step.output.get("gate_required"):
            issues.append(
                {
                    "code": "TOOL_GATE_REQUIRED",
                    "message": "工具需要人工 Gate 审批",
                    "severity": "medium",
                }
            )

    def _evaluate_evidence_sufficiency(
        self,
        step: AgentStep,
        issues: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
    ) -> None:
        if step.node_id not in {"retrieve_memory", "collect_evidence", "collect_trace"}:
            return
        if step.output.get("knowledge_error") and not step.output.get("knowledge_evidence"):
            suggestions.append(
                {
                    "action": "collect_more_evidence",
                    "message": "知识库检索失败，需补充 Artifact/Trace 证据",
                }
            )
        evidence_count = int(step.output.get("artifact_count") or 0)
        evidence_count += len(step.output.get("artifact_evidence") or [])
        evidence_count += len(step.output.get("trace_evidence") or [])
        evidence_count += len(step.output.get("memories") or [])
        if evidence_count == 0:
            issues.append(
                {
                    "code": "EVIDENCE_INSUFFICIENT",
                    "message": "证据收集步骤没有返回可用来源",
                    "severity": "high",
                }
            )
            suggestions.append(
                {
                    "action": "collect_more_evidence",
                    "message": "插入补充检索或读取历史 Trace 的步骤",
                }
            )

    def _evaluate_fact_check_result(
        self,
        step: AgentStep,
        issues: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
    ) -> None:
        if step.node_id != "fact_check_content" and step.output.get("fact_check_mode") is None:
            return
        report = step.output.get("report") if isinstance(step.output, dict) else None
        high_risk_count = 0
        if isinstance(report, dict):
            high_risk_count = int(report.get("high_risk_count") or 0)
        findings = step.output.get("findings") or []
        has_high_risk_finding = any(
            str(finding.get("risk")).lower() == "high"
            for finding in findings
            if isinstance(finding, dict)
        )
        failed = step.output.get("passed") is False
        if failed or high_risk_count > 0:
            issues.append(
                {
                    "code": "FACT_CHECK_FAILED",
                    "message": "事实核查未通过或存在高风险事实项",
                    "severity": "high" if high_risk_count > 0 or has_high_risk_finding else "low",
                    "high_risk_count": high_risk_count,
                    "finding_count": len(findings),
                    "fact_check_mode": step.output.get("fact_check_mode"),
                }
            )
            suggestions.append(
                {
                    "action": "collect_evidence_and_recheck",
                    "message": "补充证据、改写不确定表述后再次事实核查",
                }
            )
        if step.output.get("fact_check_mode") == "lightweight_fallback":
            suggestions.append(
                {
                    "action": "rerun_cove_fact_check",
                    "message": "CoVe 核查失败，建议修正模型或证据上下文后重跑",
                }
            )


class AgentReflector:
    """对失败或低质量结果进行原因归纳。"""

    def reflect(self, *, run: AgentRun, step: AgentStep, eval_result: EvalResult) -> dict[str, Any]:
        """生成可执行的反思记录。"""
        primary_issue = eval_result.issues[0] if eval_result.issues else {}
        code = primary_issue.get("code", "QUALITY_BELOW_THRESHOLD")
        repair_action = "补充证据并重写当前步骤输出"
        if code == "EMPTY_OUTPUT":
            repair_action = "检查输入和工具输出，重新执行当前步骤"
        if code == "LOW_GOAL_COVERAGE":
            repair_action = "插入目标覆盖补充步骤，补齐缺失关键词和交付标准"
        if code == "EVIDENCE_INSUFFICIENT":
            repair_action = "插入补充证据检索步骤，优先读取 Artifact、Trace 和知识库证据"
        if code == "FACT_CHECK_FAILED":
            repair_action = "补充证据、改写不确定事实表述，并重新执行事实核查"
        if code == "TOOL_RESULT_ERROR":
            repair_action = "更换工具或修正工具输入后重新执行"
        if code.startswith("PLAN_"):
            repair_action = "修正计划图依赖、节点和边后重新评估计划"

        return {
            "summary": f"步骤 {step.title} 未通过评估：{code}",
            "root_cause": code,
            "repair_action": repair_action,
            "failed_step_id": step.id,
            "failed_node_id": step.node_id,
            "score": eval_result.score,
            "issues": eval_result.issues,
            "goal": run.goal,
        }


class MemoryManager:
    """Agent 记忆读写。"""

    def __init__(self, store: AutonomousAgentStore):
        self.store = store

    async def retrieve(self, workspace_id: str, query: str) -> list[MemoryRecord]:
        """检索长期/经验记忆。"""
        return await self.store.search_memories(
            workspace_id,
            query,
            memory_types=[MemoryType.EPISODIC, MemoryType.SEMANTIC, MemoryType.PROCEDURAL],
            limit=8,
        )

    async def build_context_window(
        self,
        *,
        run: AgentRun,
        recent_step_limit: int = 4,
    ) -> dict[str, Any]:
        """构建长程任务上下文窗口：近期完整、历史摘要、长期记忆按需检索。"""
        steps = await self.store.list_steps(run.id)
        recent_steps = steps[-recent_step_limit:]
        summarized_steps = steps[: max(0, len(steps) - recent_step_limit)]
        memories = await self.retrieve(run.workspace_id, run.goal)

        return {
            "working_memory": [
                {
                    "step_id": step.id,
                    "node_id": step.node_id,
                    "title": step.title,
                    "status": step.status.value,
                    "output": step.output,
                    "artifact_ids": step.artifact_ids,
                }
                for step in recent_steps
            ],
            "compressed_history": [
                {
                    "step_id": step.id,
                    "node_id": step.node_id,
                    "title": step.title,
                    "status": step.status.value,
                    "artifact_count": len(step.artifact_ids),
                    "has_error": bool(step.error_message),
                }
                for step in summarized_steps
            ],
            "long_term_memory": [memory.model_dump(mode="json") for memory in memories],
        }

    async def remember_run_lesson(
        self,
        *,
        run: AgentRun,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        confidence: float = 0.8,
    ) -> MemoryRecord:
        """沉淀一次运行经验。"""
        memory = MemoryRecord(
            workspace_id=run.workspace_id,
            run_id=run.id,
            memory_type=memory_type,
            content=content,
            confidence=confidence,
            source_trace_id=run.id,
            metadata={"goal": run.goal},
        )
        return await self.store.create_memory(memory)


def _keywords(text: str) -> list[str]:
    normalized = (
        text.replace("，", " ")
        .replace("。", " ")
        .replace("、", " ")
        .replace(",", " ")
        .replace(".", " ")
    )
    return [token.lower() for token in normalized.split() if len(token.strip()) >= 2]


def _coverage_score(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.7 if text else 0.0
    lowered = text.lower()
    unique_keywords = set(keywords)
    covered = sum(1 for keyword in unique_keywords if keyword in lowered)
    return covered / len(unique_keywords)


def _issue_penalty(issue: dict[str, Any]) -> float:
    severity = str(issue.get("severity") or "medium").lower()
    return {"high": 0.28, "medium": 0.14, "low": 0.06}.get(severity, 0.1)


def _has_blocking_issue(issues: list[dict[str, Any]]) -> bool:
    return any(str(issue.get("severity")).lower() == "high" for issue in issues)


def _latest_fact_check_risk(steps: list[AgentStep]) -> dict[str, int]:
    for step in reversed(steps):
        if step.output.get("fact_check_mode") is None:
            continue
        report = step.output.get("report")
        if isinstance(report, dict):
            return {
                "high_risk_count": int(report.get("high_risk_count") or 0),
                "unverified_count": int(report.get("unverified_count") or 0),
                "total_claims": int(report.get("total_claims") or 0),
            }
        findings = step.output.get("findings") or []
        return {
            "high_risk_count": sum(
                1 for finding in findings if str(finding.get("risk")).lower() == "high"
            ),
            "unverified_count": 0 if step.output.get("passed") else len(findings),
            "total_claims": int(step.output.get("claim_count") or 0),
        }
    return {"high_risk_count": 0, "unverified_count": 0, "total_claims": 0}


def _has_final_artifact(steps: list[AgentStep]) -> bool:
    for step in reversed(steps):
        if step.step_type.value != "finalization":
            continue
        if step.artifact_ids or step.output.get("artifact_id") or step.output.get("artifact"):
            return True
    return False


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)
