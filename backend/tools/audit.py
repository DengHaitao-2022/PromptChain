"""工具调用审计服务。"""

from __future__ import annotations

from typing import Any

from core.time import utc_now
from tools.redaction import redact_sensitive_payload, sensitive_payload_fingerprint
from tools.runtime import ToolRuntime
from tools.schemas import ToolCall, ToolCallStatus, ToolSpec

TERMINAL_TOOL_CALL_STATUSES = {
    ToolCallStatus.DENIED,
    ToolCallStatus.SUCCEEDED,
    ToolCallStatus.FAILED,
    ToolCallStatus.TIMEOUT,
}


class ToolAuditService:
    """把工具调用写入 tool_calls，作为审计与回放事实源。"""

    def __init__(self, store: Any | None = None):
        if store is None:
            # 延迟导入，避免 services.artifact_store 导入 ToolCall schema 时形成循环依赖。
            from services import get_artifact_store

            store = get_artifact_store()
        self.store = store

    async def create_call(
        self,
        spec: ToolSpec,
        input_data: dict[str, Any],
        runtime: ToolRuntime,
        *,
        status: ToolCallStatus,
        requires_approval: bool,
        metadata: dict[str, Any] | None = None,
    ) -> ToolCall:
        safe_metadata = dict(metadata or {})
        safe_metadata["input_fingerprint"] = sensitive_payload_fingerprint(input_data)
        safe_metadata["runtime_context"] = {
            "workflow_run_id": runtime.workflow_run_id,
            "node_run_id": runtime.node_run_id,
            "approval_context": runtime.approval_context or {},
        }
        call = ToolCall(
            workspace_id=runtime.workspace_id,
            workflow_run_id=runtime.workflow_run_id,
            node_run_id=runtime.node_run_id,
            tool_name=spec.name,
            tool_version=spec.version,
            source_type=spec.source_type,
            risk_level=spec.risk_level,
            status=status,
            input_json=redact_sensitive_payload(input_data),
            requires_approval=requires_approval,
            created_by=runtime.user_id,
            metadata=redact_sensitive_payload(safe_metadata),
        )
        if status in TERMINAL_TOOL_CALL_STATUSES:
            call.completed_at = call.updated_at
        if hasattr(self.store, "create_tool_call"):
            return await self.store.create_tool_call(call)
        return call

    async def update_call(
        self,
        call: ToolCall,
        *,
        status: ToolCallStatus,
        output: Any = None,
        error_message: str | None = None,
        latency_ms: int | None = None,
        token_cost: int | None = None,
        money_cost: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolCall:
        call.status = status
        call.output_json = redact_sensitive_payload(output)
        call.error_message = error_message
        call.latency_ms = latency_ms
        call.token_cost = token_cost
        call.money_cost = money_cost
        call.updated_at = utc_now()
        if status in TERMINAL_TOOL_CALL_STATUSES:
            call.completed_at = call.updated_at
        if metadata:
            call.metadata = redact_sensitive_payload({**(call.metadata or {}), **metadata})
        if hasattr(self.store, "update_tool_call"):
            return await self.store.update_tool_call(call)
        return call

    async def get_call(self, tool_call_id: str) -> ToolCall | None:
        if hasattr(self.store, "get_tool_call"):
            return await self.store.get_tool_call(tool_call_id)
        return None

    async def approve_call(
        self,
        tool_call_id: str,
        *,
        approved_by: str,
        approved: bool,
        reason: str | None = None,
    ) -> ToolCall | None:
        call = await self.get_call(tool_call_id)
        if call is None:
            return None
        call.status = ToolCallStatus.APPROVED if approved else ToolCallStatus.DENIED
        call.approved_by = approved_by
        call.approved_at = utc_now()
        call.updated_at = call.approved_at
        if not approved:
            call.completed_at = call.updated_at
        metadata = dict(call.metadata or {})
        metadata["approval_reason"] = reason
        call.metadata = metadata
        if hasattr(self.store, "update_tool_call"):
            return await self.store.update_tool_call(call)
        return call
