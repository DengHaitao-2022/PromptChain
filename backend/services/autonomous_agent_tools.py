"""Autonomous Agent 工具注册与执行。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings
from core.time import utc_now_naive
from models.artifact import ArtifactType
from models.autonomous_agent import (
    AgentStep,
    ToolCall,
    ToolCallStatus,
    ToolDefinition,
    ToolRiskLevel,
)
from models.fact_check import FactCheckReport
from models.knowledge import KnowledgeScope, KnowledgeSearchRequest
from services.artifact_store import ArtifactStore
from services.autonomous_agent_store import AutonomousAgentStore
from services.knowledge_service import KnowledgeService

ToolHandler = Callable[[dict[str, Any], AgentStep | None], Awaitable[dict[str, Any]]]


def _optional_str(value: Any) -> str | None:
    """将可选 payload 字段归一为字符串。"""
    if value in (None, ""):
        return None
    return str(value)


async def _collect_artifact_evidence(
    *,
    artifact_store: ArtifactStore,
    workspace_id: str,
    user_id: str | None,
    workflow_run_id: str | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """收集当前运行和历史运行的 Artifact 线索，供长程上下文复用。"""
    workflow_ids = [workflow_run_id] if workflow_run_id else []
    try:
        workflow_runs = await artifact_store.list_workflow_runs(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        workflow_ids.extend(run.id for run in workflow_runs[:limit] if run.id not in workflow_ids)
    except Exception:
        # ArtifactStore 可能是测试内存实现或外部存储异常；证据检索失败不应中断 Agent。
        workflow_ids = [item for item in workflow_ids if item]

    evidence: list[dict[str, Any]] = []
    for current_workflow_id in workflow_ids:
        if not current_workflow_id:
            continue
        try:
            artifacts = await artifact_store.get_artifacts_by_workflow(current_workflow_id)
        except Exception:
            continue
        for artifact in artifacts[-limit:]:
            evidence.append(
                {
                    "artifact_id": artifact.id,
                    "workflow_run_id": artifact.workflow_run_id,
                    "node_run_id": artifact.node_run_id,
                    "type": artifact.type.value,
                    "version": artifact.version,
                    "content_preview": _preview(artifact.content),
                    "metadata": artifact.metadata,
                }
            )
            if len(evidence) >= limit:
                return evidence
    return evidence


async def _collect_trace_evidence(
    *,
    artifact_store: ArtifactStore,
    workspace_id: str,
    user_id: str | None,
    workflow_run_id: str | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """收集 NodeRun/Trace 线索，帮助 Agent 理解历史执行路径。"""
    workflow_ids = [workflow_run_id] if workflow_run_id else []
    try:
        workflow_runs = await artifact_store.list_workflow_runs(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        workflow_ids.extend(run.id for run in workflow_runs[:limit] if run.id not in workflow_ids)
    except Exception:
        workflow_ids = [item for item in workflow_ids if item]

    evidence: list[dict[str, Any]] = []
    for current_workflow_id in workflow_ids:
        if not current_workflow_id:
            continue
        try:
            node_runs = await artifact_store.get_node_runs_by_workflow(current_workflow_id)
        except Exception:
            continue
        for node_run in node_runs[-limit:]:
            evidence.append(
                {
                    "node_run_id": node_run.id,
                    "workflow_run_id": node_run.workflow_run_id,
                    "node_name": node_run.node_name,
                    "node_type": node_run.node_type,
                    "status": node_run.status.value,
                    "duration_ms": node_run.duration_ms,
                    "error_message": node_run.error_message,
                    "output_artifact_ids": node_run.output_artifact_ids,
                }
            )
            if len(evidence) >= limit:
                return evidence
    return evidence


async def _collect_tool_evidence(
    *,
    agent_store: AutonomousAgentStore,
    run_id: str | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """收集当前 AgentRun 的工具调用证据。"""
    if not run_id:
        return []
    try:
        tool_calls = await agent_store.list_tool_calls(run_id)
    except Exception:
        return []
    return [
        {
            "tool_call_id": call.id,
            "tool_name": call.tool_name,
            "status": call.status.value,
            "risk_level": call.risk_level.value,
            "latency_ms": call.latency_ms,
            "error_message": call.error_message,
            "output_preview": _preview(call.output),
        }
        for call in tool_calls[-limit:]
    ]


async def _retrieve_knowledge_evidence(
    *,
    agent_store: AutonomousAgentStore,
    workspace_id: str,
    user_id: str | None,
    workflow_run_id: str | None,
    node_run_id: str | None,
    query: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """复用知识库检索能力，失败时返回可审计错误而不中断主循环。"""
    if not user_id:
        return None, "缺少 user_id，已跳过知识库检索"
    if not query.strip():
        return None, "缺少 query，已跳过知识库检索"
    try:
        response = await KnowledgeService(agent_store.session).search(
            request=KnowledgeSearchRequest(
                query=query,
                scopes=[
                    KnowledgeScope.WORKSPACE,
                    KnowledgeScope.PERSONAL,
                    KnowledgeScope.RUN_UPLOAD,
                ],
                top_k=5,
                min_score=0.1,
                workflow_run_id=workflow_run_id,
                node_run_id=node_run_id,
            ),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return response.model_dump(mode="json"), None
    except (SQLAlchemyError, ValueError) as exc:
        return None, str(exc)


def _preview(value: Any, *, limit: int = 480) -> str:
    """把结构化证据压缩为短预览，避免工具输出过大。"""
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


async def _ensure_workflow_visible(
    *,
    artifact_store: ArtifactStore,
    workflow_run_id: str,
    workspace_id: str | None,
    user_id: str | None,
    resource_label: str = "Artifact",
) -> None:
    """校验工具读取的 WorkflowRun 仍在当前 Agent 可见范围内。"""
    workflow_run = await artifact_store.get_workflow_run(workflow_run_id)
    if workflow_run is None:
        raise ValueError(f"{resource_label} 所属运行不存在或不可访问")

    metadata = workflow_run.metadata or {}
    if workspace_id and metadata.get("workspace_id") != workspace_id:
        raise ValueError(f"{resource_label} 不属于当前工作空间")
    if user_id and metadata.get("user_id") and metadata.get("user_id") != user_id:
        raise ValueError(f"{resource_label} 不属于当前用户可见范围")


async def _ensure_artifact_visible(
    *,
    artifact_store: ArtifactStore,
    artifact_id: str,
    workspace_id: str | None,
    user_id: str | None,
) -> Any:
    """读取 Artifact 前先校验所属 WorkflowRun，防止跨空间枚举读取。"""
    artifact = await artifact_store.get_artifact(artifact_id)
    if artifact is None:
        return None
    await _ensure_workflow_visible(
        artifact_store=artifact_store,
        workflow_run_id=artifact.workflow_run_id,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    return artifact


def _wants_cove_fact_check(payload: dict[str, Any]) -> bool:
    """根据 payload 和配置判断是否运行 CoVe 核查链。"""
    mode = str(payload.get("mode") or "auto").strip().lower()
    if mode in {"lightweight", "keyword", "scan", "disabled"}:
        return False
    if mode == "cove":
        return True
    return get_settings().AUTONOMOUS_AGENT_COVE_FACT_CHECK_ENABLED


def _lightweight_fact_check(text: str) -> dict[str, Any]:
    """保留低成本关键词扫描，作为无模型或 CoVe 失败时的兜底。"""
    risky_terms = ["绝对", "唯一", "保证", "100%", "从不"]
    findings = [
        {"term": term, "risk": "medium", "suggestion": "改为更可验证的限定表述"}
        for term in risky_terms
        if term in text
    ]
    return {
        "passed": not findings,
        "findings": findings,
        "checked_length": len(text),
        "fact_check_mode": "lightweight",
    }


def _format_agent_fact_evidence(payload: dict[str, Any], *, limit: int = 6000) -> str:
    """把 Agent 工具 payload 中的证据压缩为 CoVe Evidence Context。"""
    explicit = payload.get("evidence_context")
    if explicit:
        text = str(explicit)
        return text[:limit]

    evidence: list[str] = []
    for key in ("knowledge_evidence", "artifact_evidence", "trace_evidence", "tool_evidence"):
        value = payload.get(key)
        if not value:
            continue
        evidence.append(f"## {key}\n{_preview(value, limit=1600)}")

    return "\n\n".join(evidence)[:limit] or "未启用知识库或未检索到可用证据。"


async def _run_cove_fact_check(payload: dict[str, Any], text: str) -> dict[str, Any]:
    """复用内容链路 CoVe 四步核查，生成可审计事实核查报告。"""
    from services.cove_fact_check import (
        evaluate_claim_accuracy,
        execute_verification,
        extract_fact_claims,
        generate_verification_question,
    )

    workspace_id = _optional_str(payload.get("workspace_id"))
    model_provider_id = _optional_str(payload.get("model_provider_id"))
    model_provider_name = _optional_str(payload.get("model_provider_name"))
    model_name = _optional_str(payload.get("model_name"))
    evidence_context = _format_agent_fact_evidence(payload)
    max_claims = max(1, min(int(payload.get("max_claims") or 8), 20))

    claims, usage = await extract_fact_claims(
        text,
        str(payload.get("section_id") or "agent_output"),
        workspace_id,
        model_provider_id,
        model_provider_name,
        model_name,
    )
    all_usage = dict(usage)

    async def _verify_claim(claim) -> tuple[Any, dict[str, Any], dict[str, int]]:
        """每条声明内部保持 CoVe 顺序，多条声明之间并发验证。"""
        question, question_usage = await generate_verification_question(
            claim,
            workspace_id,
            model_provider_id,
            model_provider_name,
            model_name,
        )
        answer, answer_usage = await execute_verification(
            question,
            workspace_id,
            model_provider_id,
            model_provider_name,
            model_name,
            evidence_context=evidence_context,
        )
        result, evaluation_usage = await evaluate_claim_accuracy(
            claim,
            question,
            answer,
            workspace_id,
            model_provider_id,
            model_provider_name,
            model_name,
        )
        trace_item = {
            "claim_id": claim.id,
            "claim": claim.text,
            "question": question,
            "answer": answer,
            "risk_level": result.risk_level,
            "is_verified": result.is_verified,
            "confidence": result.confidence,
            "suggested_correction": result.suggested_correction,
        }
        usage_item: dict[str, int] = {}
        for current_usage in (question_usage, answer_usage, evaluation_usage):
            for key, value in current_usage.items():
                usage_item[key] = int(usage_item.get(key, 0)) + int(value or 0)
        return result, trace_item, usage_item

    limited_claims = claims[:max_claims]
    verified_claims = await asyncio.gather(*(_verify_claim(claim) for claim in limited_claims))
    results = []
    trace: list[dict[str, Any]] = []
    for result, trace_item, usage_item in verified_claims:
        results.append(result)
        trace.append(trace_item)
        for key, value in usage_item.items():
            all_usage[key] = int(all_usage.get(key, 0)) + int(value or 0)

    report = FactCheckReport(claims=limited_claims, results=results)
    report.compute_stats()
    findings = [
        {
            "claim_id": item.claim_id,
            "risk": item.risk_level,
            "suggestion": item.suggested_correction or "补充证据或改写为限定表述",
        }
        for item in results
        if item.risk_level in {"medium", "high"} or not item.is_verified
    ]
    return {
        "passed": not report.has_high_risk_items(),
        "findings": findings,
        "checked_length": len(text),
        "fact_check_mode": "cove",
        "claim_count": len(report.claims),
        "report": report.model_dump(mode="json"),
        "verification_trace": trace,
        "llm_usage": all_usage,
        "evidence_context_preview": _preview(evidence_context, limit=1000),
    }


class ToolRegistry:
    """统一工具注册中心。"""

    def __init__(self):
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """注册工具定义和执行器。"""
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def get(self, name: str) -> ToolDefinition:
        """读取工具定义。"""
        if name not in self._definitions:
            raise ValueError(f"未注册工具: {name}")
        return self._definitions[name]

    def list_definitions(self) -> list[ToolDefinition]:
        """列出所有工具定义。"""
        return sorted(self._definitions.values(), key=lambda item: item.name)

    async def call(
        self, name: str, payload: dict[str, Any], step: AgentStep | None
    ) -> dict[str, Any]:
        """执行工具。"""
        if name not in self._handlers:
            raise ValueError(f"未注册工具执行器: {name}")
        return await self._handlers[name](payload, step)


class ToolExecutor:
    """负责工具参数校验、风险 Gate、执行和审计。"""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        store: AutonomousAgentStore,
        risk_gate_threshold: ToolRiskLevel = ToolRiskLevel.MEDIUM,
    ):
        self.registry = registry
        self.store = store
        self.risk_gate_threshold = risk_gate_threshold

    async def execute(
        self,
        *,
        run_id: str,
        tool_name: str,
        payload: dict[str, Any],
        step: AgentStep | None = None,
        force: bool = False,
        allowed_permissions: set[str] | None = None,
    ) -> ToolCall:
        """执行工具并写入 ToolCall。"""
        definition = self.registry.get(tool_name)
        tool_call = ToolCall(
            run_id=run_id,
            step_id=step.id if step else None,
            tool_name=tool_name,
            input=payload,
            status=ToolCallStatus.PENDING,
            risk_level=definition.risk_level,
            metadata={
                "permission": definition.permission,
                "idempotent": definition.idempotent,
            },
        )
        await self.store.create_tool_call(tool_call)

        permission_error = self._validate_permission(definition, allowed_permissions)
        if permission_error:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_message = permission_error
            tool_call.output = {"error": permission_error}
            tool_call.completed_at = utc_now_naive()
            await self.store.update_tool_call(tool_call)
            return tool_call

        validation_error = self._validate_payload(definition, payload)
        if validation_error:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_message = validation_error
            tool_call.output = {"error": validation_error}
            tool_call.completed_at = utc_now_naive()
            await self.store.update_tool_call(tool_call)
            return tool_call

        if self._requires_gate(definition.risk_level) and not force:
            tool_call.status = ToolCallStatus.AWAITING_GATE
            tool_call.output = {
                "gate_required": True,
                "reason": f"工具 {tool_name} 风险等级为 {definition.risk_level.value}",
            }
            tool_call.completed_at = utc_now_naive()
            await self.store.update_tool_call(tool_call)
            return tool_call

        return await self._run_tool_call(tool_call, step)

    async def approve_and_execute(
        self,
        *,
        tool_call: ToolCall,
        step: AgentStep | None = None,
        allowed_permissions: set[str] | None = None,
    ) -> ToolCall:
        """执行已经通过 Gate 审批的工具调用，并复用原审计记录。"""
        if tool_call.status != ToolCallStatus.AWAITING_GATE:
            raise ValueError("工具调用不处于 Gate 等待状态")
        definition = self.registry.get(tool_call.tool_name)
        permission_error = self._validate_permission(definition, allowed_permissions)
        if permission_error:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_message = permission_error
            tool_call.output = {"error": permission_error}
            tool_call.completed_at = utc_now_naive()
            await self.store.update_tool_call(tool_call)
            return tool_call
        return await self._run_tool_call(tool_call, step)

    async def _run_tool_call(self, tool_call: ToolCall, step: AgentStep | None) -> ToolCall:
        """执行工具并更新同一条 ToolCall 审计记录。"""
        started = time.perf_counter()
        tool_call.status = ToolCallStatus.RUNNING
        await self.store.update_tool_call(tool_call)
        try:
            tool_call.output = await self.registry.call(tool_call.tool_name, tool_call.input, step)
            tool_call.status = ToolCallStatus.COMPLETED
        except Exception as exc:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_message = str(exc)
            tool_call.output = {"error": str(exc)}
        finally:
            tool_call.latency_ms = int((time.perf_counter() - started) * 1000)
            if not tool_call.cost:
                tool_call.cost = {"amount": 1.0, "unit": "tool_call"}
            tool_call.completed_at = utc_now_naive()
            await self.store.update_tool_call(tool_call)
        return tool_call

    def _validate_permission(
        self,
        definition: ToolDefinition,
        allowed_permissions: set[str] | None,
    ) -> str | None:
        """校验工具声明权限；未提供 actor 权限时保持内部测试/离线运行兼容。"""
        if allowed_permissions is None:
            return None
        if definition.permission not in allowed_permissions:
            return f"工具 {definition.name} 需要权限 {definition.permission}"
        return None

    def _validate_payload(self, definition: ToolDefinition, payload: dict[str, Any]) -> str | None:
        """按工具声明的最小 JSON Schema 校验必填字段。"""
        required = definition.input_schema.get("required", [])
        if not isinstance(required, list):
            return "工具 input_schema.required 必须是数组"
        missing = [
            field for field in required if field not in payload or payload.get(field) in (None, "")
        ]
        if missing:
            return f"工具 {definition.name} 缺少必填参数: {', '.join(missing)}"
        return None

    def _requires_gate(self, risk_level: ToolRiskLevel) -> bool:
        order = {
            ToolRiskLevel.LOW: 0,
            ToolRiskLevel.MEDIUM: 1,
            ToolRiskLevel.HIGH: 2,
            ToolRiskLevel.CRITICAL: 3,
        }
        return order[risk_level] >= order[self.risk_gate_threshold]


def build_default_tool_registry(
    *,
    artifact_store: ArtifactStore,
    agent_store: AutonomousAgentStore,
) -> ToolRegistry:
    """注册 Issue #15 要求的首批工具。"""
    registry = ToolRegistry()

    async def retrieve_memory(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        workspace_id = payload.get("workspace_id")
        query = payload.get("query") or ""
        if not workspace_id:
            return {
                "memories": [],
                "knowledge_evidence": None,
                "artifact_evidence": [],
                "trace_evidence": [],
                "tool_evidence": [],
                "reason": "缺少 workspace_id",
            }
        memories = await agent_store.search_memories(workspace_id, query, limit=8)
        artifact_evidence = await _collect_artifact_evidence(
            artifact_store=artifact_store,
            workspace_id=str(workspace_id),
            user_id=_optional_str(payload.get("user_id")),
            workflow_run_id=_optional_str(payload.get("workflow_run_id")),
        )
        trace_evidence = await _collect_trace_evidence(
            artifact_store=artifact_store,
            workspace_id=str(workspace_id),
            user_id=_optional_str(payload.get("user_id")),
            workflow_run_id=_optional_str(payload.get("workflow_run_id")),
        )
        tool_evidence = await _collect_tool_evidence(
            agent_store=agent_store,
            run_id=_optional_str(payload.get("workflow_run_id")),
        )
        knowledge_evidence, knowledge_error = await _retrieve_knowledge_evidence(
            agent_store=agent_store,
            workspace_id=str(workspace_id),
            user_id=_optional_str(payload.get("user_id")),
            workflow_run_id=_optional_str(payload.get("workflow_run_id")),
            node_run_id=_optional_str(payload.get("node_run_id")),
            query=str(query),
        )
        return {
            "memories": [memory.model_dump(mode="json") for memory in memories],
            "knowledge_evidence": knowledge_evidence,
            "knowledge_error": knowledge_error,
            "artifact_evidence": artifact_evidence,
            "trace_evidence": trace_evidence,
            "tool_evidence": tool_evidence,
        }

    async def read_artifact(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        artifact_id = payload.get("artifact_id")
        workspace_id = _optional_str(payload.get("workspace_id"))
        user_id = _optional_str(payload.get("user_id"))
        if artifact_id:
            artifact = await _ensure_artifact_visible(
                artifact_store=artifact_store,
                artifact_id=str(artifact_id),
                workspace_id=workspace_id,
                user_id=user_id,
            )
            return {"artifact": artifact.model_dump(mode="json") if artifact else None}
        workflow_run_id = payload.get("workflow_run_id")
        if workflow_run_id:
            await _ensure_workflow_visible(
                artifact_store=artifact_store,
                workflow_run_id=str(workflow_run_id),
                workspace_id=workspace_id,
                user_id=user_id,
            )
            artifacts = await artifact_store.get_artifacts_by_workflow(str(workflow_run_id))
            return {
                "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
                "artifact_count": len(artifacts),
            }
        return {
            "artifact": None,
            "note": "未提供 artifact_id，当前步骤将基于目标和记忆继续执行。",
        }

    async def retrieve_trace(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        workflow_run_id = payload.get("workflow_run_id")
        workspace_id = _optional_str(payload.get("workspace_id"))
        user_id = _optional_str(payload.get("user_id"))
        if not workflow_run_id:
            return {
                "workflow_run_id": None,
                "node_run_count": 0,
                "trace_evidence": [],
                "reason": "缺少 workflow_run_id",
            }
        await _ensure_workflow_visible(
            artifact_store=artifact_store,
            workflow_run_id=str(workflow_run_id),
            workspace_id=workspace_id,
            user_id=user_id,
            resource_label="Trace",
        )
        try:
            limit = max(1, min(int(payload.get("limit") or 20), 50))
        except (TypeError, ValueError):
            limit = 20
        node_runs = await artifact_store.get_node_runs_by_workflow(str(workflow_run_id))
        return {
            "workflow_run_id": str(workflow_run_id),
            "node_run_count": len(node_runs),
            "trace_evidence": [
                {
                    "node_run_id": node_run.id,
                    "workflow_run_id": node_run.workflow_run_id,
                    "node_name": node_run.node_name,
                    "node_type": node_run.node_type,
                    "status": node_run.status.value,
                    "duration_ms": node_run.duration_ms,
                    "error_message": node_run.error_message,
                    "output_artifact_ids": node_run.output_artifact_ids,
                }
                for node_run in node_runs[-limit:]
            ],
        }

    async def write_artifact(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        if step is None:
            raise ValueError("write_artifact 需要关联 AgentStep")
        content = payload.get("content") or {}
        artifact = await artifact_store.create_artifact(
            artifact_type=ArtifactType.FINAL_CONTENT,
            content=content,
            workflow_run_id=payload.get("workflow_run_id") or step.run_id,
            node_run_id=payload.get("node_run_id") or step.id,
            metadata={
                "source": "autonomous_agent",
                "agent_run_id": step.run_id,
                "agent_step_id": step.id,
                **(payload.get("metadata") or {}),
            },
        )
        return {"artifact": artifact.model_dump(mode="json")}

    async def rollback_artifact(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        if step is None:
            raise ValueError("rollback_artifact 需要关联 AgentStep")
        artifact_id = payload.get("artifact_id")
        if not artifact_id:
            raise ValueError("rollback_artifact 缺少 artifact_id")
        source_artifact = await _ensure_artifact_visible(
            artifact_store=artifact_store,
            artifact_id=str(artifact_id),
            workspace_id=_optional_str(payload.get("workspace_id")),
            user_id=_optional_str(payload.get("user_id")),
        )
        if source_artifact is None:
            raise ValueError("待回滚 Artifact 不存在")
        rollback_artifact = await artifact_store.create_artifact(
            artifact_type=source_artifact.type,
            content=source_artifact.content,
            workflow_run_id=payload.get("workflow_run_id") or step.run_id,
            node_run_id=step.id,
            parent_version_id=source_artifact.id,
            metadata={
                "source": "autonomous_agent_rollback",
                "agent_run_id": step.run_id,
                "agent_step_id": step.id,
                "rollback_from_artifact_id": source_artifact.id,
                **(payload.get("metadata") or {}),
            },
        )
        return {
            "artifact": rollback_artifact.model_dump(mode="json"),
            "rolled_back_from": source_artifact.id,
        }

    async def fact_check(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        text = str(payload.get("text") or "")
        if not _wants_cove_fact_check(payload):
            return _lightweight_fact_check(text)
        try:
            return await _run_cove_fact_check(payload, text)
        except Exception as exc:
            fallback = _lightweight_fact_check(text)
            fallback["fact_check_mode"] = "lightweight_fallback"
            fallback["fallback_reason"] = str(exc)[:1000]
            return fallback

    async def export_docx(payload: dict[str, Any], step: AgentStep | None) -> dict[str, Any]:
        return {
            "export_ready": True,
            "format": "docx",
            "artifact_id": payload.get("artifact_id"),
            "note": "DOCX 导出复用现有 /api/workflow/{id}/exports/docx 能力。",
        }

    registry.register(
        ToolDefinition(
            name="retrieve_memory",
            description="检索当前工作空间的 Agent 长期记忆。",
            input_schema={"type": "object", "required": ["workspace_id", "query"]},
            output_schema={"type": "object", "properties": {"memories": {"type": "array"}}},
            risk_level=ToolRiskLevel.LOW,
            permission="workflow_run:read",
            idempotent=True,
        ),
        retrieve_memory,
    )
    registry.register(
        ToolDefinition(
            name="read_artifact",
            description="读取历史 Artifact 作为执行证据。",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.LOW,
            permission="workflow_run:read",
            idempotent=True,
        ),
        read_artifact,
    )
    registry.register(
        ToolDefinition(
            name="retrieve_trace",
            description="读取指定运行的 Trace/NodeRun 证据。",
            input_schema={"type": "object", "required": ["workflow_run_id"]},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.LOW,
            permission="workflow_run:read",
            idempotent=True,
        ),
        retrieve_trace,
    )
    registry.register(
        ToolDefinition(
            name="write_artifact",
            description="写入版本化 Artifact。",
            input_schema={"type": "object", "required": ["content"]},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.LOW,
            permission="workflow:execute",
            idempotent=False,
        ),
        write_artifact,
    )
    registry.register(
        ToolDefinition(
            name="rollback_artifact",
            description="从指定 Artifact 版本创建新的回滚版本。",
            input_schema={"type": "object", "required": ["artifact_id"]},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.MEDIUM,
            permission="workflow:execute",
            idempotent=False,
        ),
        rollback_artifact,
    )
    registry.register(
        ToolDefinition(
            name="fact_check",
            description="对文本进行 CoVe 事实核查；无模型或失败时回退轻量风险扫描。",
            input_schema={"type": "object", "required": ["text"]},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.LOW,
            permission="workflow:execute",
            idempotent=True,
        ),
        fact_check,
    )
    registry.register(
        ToolDefinition(
            name="export_docx",
            description="准备 DOCX 导出任务。",
            input_schema={"type": "object", "required": ["artifact_id"]},
            output_schema={"type": "object"},
            risk_level=ToolRiskLevel.MEDIUM,
            permission="workflow_run:export",
            idempotent=True,
        ),
        export_docx,
    )
    return registry
