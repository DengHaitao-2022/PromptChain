"""Tool Factory 的稳定数据契约。"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.time import utc_now_naive


class ToolSourceType(StrEnum):
    """工具来源类型，命名对齐 issue #21 与 MCP/OpenAPI 后续扩展。"""

    INTERNAL = "internal"
    HTTP = "http"
    OPENAPI = "openapi"
    MCP = "mcp"
    LANGCHAIN = "langchain"
    WORKFLOW = "workflow"


class RiskLevel(StrEnum):
    """工具风险等级。"""

    READ_PUBLIC = "read_public"
    READ_PRIVATE = "read_private"
    WRITE_INTERNAL = "write_internal"
    EXTERNAL_ACTION = "external_action"
    DESTRUCTIVE = "destructive"


class ToolCallStatus(StrEnum):
    """工具调用状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    TIMEOUT = "timeout"


class ToolFailureStrategy(StrEnum):
    """工作流 tool 节点失败策略。"""

    TERMINATE = "terminate"
    SKIP = "skip"
    RETRY = "retry"
    ENTER_GATE = "enter_gate"


class ToolApprovalMode(StrEnum):
    """工作流 tool 节点审批策略。"""

    POLICY_DEFAULT = "policy_default"
    AUTO = "auto"
    GATE_REQUIRED = "gate_required"


class ToolSpec(BaseModel):
    """工具定义元数据，保留与 MCP tool schema 的字段映射。"""

    name: str = Field(..., pattern=r"^[a-zA-Z0-9_.:-]+$")
    title: str | None = None
    description: str
    category: str
    version: str = "1.0.0"
    source_type: ToolSourceType = ToolSourceType.INTERNAL
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.READ_PUBLIC
    permissions: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_policy: dict[str, Any] | None = None
    cost_policy: dict[str, Any] | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_mcp_tool(self) -> dict[str, Any]:
        """输出 MCP 兼容 tool 描述，方便后续 MCP server/client 适配。"""
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                **self.annotations,
                "riskLevel": self.risk_level.value,
                "sourceType": self.source_type.value,
                "category": self.category,
            },
        }
        if self.title:
            payload["title"] = self.title
        if self.output_schema is not None:
            payload["outputSchema"] = self.output_schema
        return payload


class ToolError(BaseModel):
    """结构化工具错误。"""

    code: str
    message: str
    details: dict[str, Any] | list[Any] | None = None


class ToolResult(BaseModel):
    """工具执行结果。"""

    success: bool = True
    output: Any = None
    summary: str | None = None
    state_patch: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_cost: int | None = None
    money_cost: float | None = None
    requires_approval: bool = False
    approval_request: dict[str, Any] | None = None
    error: ToolError | None = None


class ToolPolicyDecision(BaseModel):
    """策略引擎的判定结果。"""

    allowed: bool
    requires_approval: bool = False
    reason: str | None = None
    required_permissions: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    """工具调用审计记录。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str | None = None
    workflow_run_id: str | None = None
    node_run_id: str | None = None
    tool_name: str
    tool_version: str = "1.0.0"
    source_type: ToolSourceType = ToolSourceType.INTERNAL
    risk_level: RiskLevel = RiskLevel.READ_PUBLIC
    status: ToolCallStatus = ToolCallStatus.PENDING
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: Any = None
    error_message: str | None = None
    latency_ms: int | None = None
    token_cost: int | None = None
    money_cost: float | None = None
    requires_approval: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)
    metadata: dict[str, Any] = Field(default_factory=dict)


ToolApprovalAction = Literal["approve", "deny"]
