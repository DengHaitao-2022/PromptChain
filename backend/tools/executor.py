"""工具统一执行入口。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from tools.audit import ToolAuditService
from tools.base import ToolExecutionError, tool_failure_result
from tools.factory import ToolFactory
from tools.policy import ToolPolicyEngine
from tools.runtime import ToolRuntime
from tools.schemas import (
    ToolApprovalMode,
    ToolCallStatus,
    ToolError,
    ToolResult,
)


class ToolExecutor:
    """统一处理解析、策略、审批、执行、重试和审计。"""

    def __init__(
        self,
        *,
        factory: ToolFactory | None = None,
        policy_engine: ToolPolicyEngine | None = None,
        audit_service: ToolAuditService | None = None,
    ):
        self.factory = factory or ToolFactory()
        self.policy_engine = policy_engine or ToolPolicyEngine()
        self.audit_service = audit_service or ToolAuditService()

    async def execute(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        runtime: ToolRuntime,
        *,
        approval_mode: ToolApprovalMode = ToolApprovalMode.POLICY_DEFAULT,
        existing_tool_call_id: str | None = None,
    ) -> ToolResult:
        try:
            tool = self.factory.create(tool_name)
            spec = tool.spec
        except Exception as exc:
            return tool_failure_result("TOOL_NOT_FOUND", str(exc))

        decision = await self.policy_engine.evaluate(
            spec,
            runtime,
            approval_mode=approval_mode,
        )
        if not decision.allowed:
            call = await self.audit_service.create_call(
                spec,
                input_data,
                runtime,
                status=ToolCallStatus.DENIED,
                requires_approval=decision.requires_approval,
                metadata={"policy_reason": decision.reason},
            )
            return ToolResult(
                success=False,
                summary=decision.reason,
                metadata={"tool_call_id": call.id},
                error=ToolError(
                    code="TOOL_POLICY_DENIED",
                    message=decision.reason or "工具策略拒绝调用",
                    details={"required_permissions": decision.required_permissions},
                ),
            )

        # 失败进入 Gate 的工具可能本身不需要风险审批，也要允许复用已批准的调用记录重试。
        approved_call = await self._load_approved_call(existing_tool_call_id)
        if approved_call is not None:
            if approved_call.tool_name != spec.name:
                return ToolResult(
                    success=False,
                    summary="工具审批记录与当前工具不匹配",
                    metadata={"tool_call_id": approved_call.id},
                    error=ToolError(
                        code="TOOL_APPROVAL_MISMATCH",
                        message="工具审批记录与当前工具不匹配",
                        details={
                            "approved_tool_name": approved_call.tool_name,
                            "requested_tool_name": spec.name,
                        },
                    ),
                )
            if approved_call.input_json != input_data:
                return ToolResult(
                    success=False,
                    summary="工具审批记录与当前输入不匹配",
                    metadata={"tool_call_id": approved_call.id},
                    error=ToolError(
                        code="TOOL_APPROVAL_INPUT_MISMATCH",
                        message="工具审批记录与当前输入不匹配",
                    ),
                )
            if approved_call.status == ToolCallStatus.DENIED:
                return ToolResult(
                    success=False,
                    summary="工具调用已被拒绝",
                    metadata={"tool_call_id": approved_call.id},
                    error=ToolError(code="TOOL_APPROVAL_DENIED", message="工具调用已被拒绝"),
                )
            call = approved_call
            await self.audit_service.update_call(call, status=ToolCallStatus.RUNNING)
        elif decision.requires_approval:
            call = await self.audit_service.create_call(
                spec,
                input_data,
                runtime,
                status=ToolCallStatus.PENDING,
                requires_approval=True,
                metadata={"required_permissions": decision.required_permissions},
            )
            return ToolResult(
                success=False,
                summary="工具调用需要人工审批",
                requires_approval=True,
                approval_request={
                    "tool_call_id": call.id,
                    "tool_name": spec.name,
                    "title": spec.title or spec.name,
                    "risk_level": spec.risk_level.value,
                    "required_permissions": decision.required_permissions,
                    "input_preview": input_data,
                },
                metadata={"tool_call_id": call.id},
            )
        else:
            call = await self.audit_service.create_call(
                spec,
                input_data,
                runtime,
                status=ToolCallStatus.RUNNING,
                requires_approval=False,
                metadata={"required_permissions": decision.required_permissions},
            )

        runtime = runtime.with_tool_call_id(call.id)
        attempts = self._resolve_attempts(spec.retry_policy)
        timeout_seconds = self._resolve_timeout(spec.timeout_seconds)
        start = time.perf_counter()
        last_error: ToolError | None = None
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(tool(input_data, runtime), timeout=timeout_seconds)
                latency_ms = int((time.perf_counter() - start) * 1000)
                result.metadata = {
                    **result.metadata,
                    "tool_call_id": call.id,
                    "attempt": attempt + 1,
                }
                await self.audit_service.update_call(
                    call,
                    status=ToolCallStatus.SUCCEEDED if result.success else ToolCallStatus.FAILED,
                    output=result.output,
                    error_message=result.error.message if result.error else None,
                    latency_ms=latency_ms,
                    token_cost=result.token_cost,
                    money_cost=result.money_cost,
                    metadata=result.metadata,
                )
                return result
            except TimeoutError:
                last_error = ToolError(code="TOOL_TIMEOUT", message="工具调用超时")
                break
            except ToolExecutionError as exc:
                last_error = ToolError(code=exc.code, message=str(exc), details=exc.details)
                break
            except Exception as exc:
                last_error = ToolError(
                    code="TOOL_EXECUTION_ERROR",
                    message=str(exc) or exc.__class__.__name__,
                )
                if attempt + 1 >= attempts:
                    break
                await asyncio.sleep(min(2**attempt, 5))

        latency_ms = int((time.perf_counter() - start) * 1000)
        status = (
            ToolCallStatus.TIMEOUT
            if last_error and last_error.code == "TOOL_TIMEOUT"
            else ToolCallStatus.FAILED
        )
        await self.audit_service.update_call(
            call,
            status=status,
            error_message=last_error.message if last_error else "工具调用失败",
            latency_ms=latency_ms,
        )
        return ToolResult(
            success=False,
            summary=last_error.message if last_error else "工具调用失败",
            metadata={"tool_call_id": call.id},
            error=last_error,
        )

    async def approve_tool_call(
        self,
        tool_call_id: str,
        *,
        approved_by: str,
        approved: bool,
        reason: str | None = None,
    ):
        return await self.audit_service.approve_call(
            tool_call_id,
            approved_by=approved_by,
            approved=approved,
            reason=reason,
        )

    async def _load_approved_call(self, tool_call_id: str | None):
        if not tool_call_id:
            return None
        call = await self.audit_service.get_call(tool_call_id)
        if call is None:
            return None
        return call if call.status in {ToolCallStatus.APPROVED, ToolCallStatus.DENIED} else None

    @staticmethod
    def _resolve_attempts(retry_policy: dict[str, Any] | None) -> int:
        if not retry_policy:
            return 1
        try:
            attempts = int(retry_policy.get("max_attempts", 1))
        except (TypeError, ValueError):
            attempts = 1
        return max(1, min(attempts, 5))

    @staticmethod
    def _resolve_timeout(timeout_seconds: int | None) -> int:
        return max(1, min(int(timeout_seconds or 30), 300))


_tool_executor: ToolExecutor | None = None


def get_tool_executor() -> ToolExecutor:
    """获取工具执行器单例。"""
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ToolExecutor()
    return _tool_executor
