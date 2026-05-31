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

        if step.step_type.value not in content_step_types and not issues:
            score = 0.82
        else:
            score = max(0.0, min(1.0, 0.55 + coverage * 0.45 - len(issues) * 0.18))
        return EvalResult(
            run_id=run.id,
            step_id=step.id,
            target_type=EvaluationTargetType.STEP,
            score=round(score, 3),
            passed=score >= 0.72 and not any(issue["severity"] == "high" for issue in issues),
            issues=issues,
            suggestions=suggestions,
            metadata={"goal_keyword_count": len(goal_keywords), "coverage": coverage},
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

        score = max(0.0, min(1.0, 0.45 + coverage * 0.55 - len(failed_evals) * 0.08))
        return EvalResult(
            run_id=run.id,
            step_id=None,
            target_type=EvaluationTargetType.FINAL_OUTPUT,
            score=round(score, 3),
            passed=score >= 0.75 and not any(issue["severity"] == "high" for issue in issues),
            issues=issues,
            suggestions=[{"action": "replan", "message": "围绕未覆盖目标插入补充生成步骤"}]
            if issues
            else [],
            metadata={"coverage": coverage, "step_eval_count": len(eval_results)},
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
