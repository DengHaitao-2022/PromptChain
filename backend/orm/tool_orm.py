"""Tool Factory ORM 模型。"""

import uuid

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from core.time import utc_now_naive
from db.postgres_store import Base
from tools.schemas import RiskLevel, ToolCall, ToolCallStatus, ToolSourceType


class ToolCallORM(Base):
    """工具调用审计表。"""

    __tablename__ = "tool_calls"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=True)
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id"), nullable=True)
    node_run_id = Column(String(36), ForeignKey("node_runs.id"), nullable=True)
    tool_name = Column(String(160), nullable=False)
    tool_version = Column(String(40), nullable=False, default="1.0.0")
    source_type = Column(String(40), nullable=False, default=ToolSourceType.INTERNAL.value)
    risk_level = Column(String(40), nullable=False, default=RiskLevel.READ_PUBLIC.value)
    status = Column(String(20), nullable=False, default=ToolCallStatus.PENDING.value)
    input_json = Column(JSON, nullable=False, default=dict)
    output_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    token_cost = Column(Integer, nullable=True)
    money_cost = Column(Float, nullable=True)
    requires_approval = Column(Integer, nullable=False, default=0)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> ToolCall:
        return ToolCall(
            id=self.id,
            workspace_id=self.workspace_id,
            workflow_run_id=self.workflow_run_id,
            node_run_id=self.node_run_id,
            tool_name=self.tool_name,
            tool_version=self.tool_version,
            source_type=ToolSourceType(self.source_type),
            risk_level=RiskLevel(self.risk_level),
            status=ToolCallStatus(self.status),
            input_json=self.input_json or {},
            output_json=self.output_json,
            error_message=self.error_message,
            latency_ms=self.latency_ms,
            token_cost=self.token_cost,
            money_cost=self.money_cost,
            requires_approval=bool(self.requires_approval),
            approved_by=self.approved_by,
            approved_at=self.approved_at,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: ToolCall) -> ToolCallORM:
        return cls(
            id=model.id,
            workspace_id=model.workspace_id,
            workflow_run_id=model.workflow_run_id,
            node_run_id=model.node_run_id,
            tool_name=model.tool_name,
            tool_version=model.tool_version,
            source_type=model.source_type.value,
            risk_level=model.risk_level.value,
            status=model.status.value,
            input_json=model.input_json,
            output_json=model.output_json,
            error_message=model.error_message,
            latency_ms=model.latency_ms,
            token_cost=model.token_cost,
            money_cost=model.money_cost,
            requires_approval=1 if model.requires_approval else 0,
            approved_by=model.approved_by,
            approved_at=model.approved_at,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            metadata_json=model.metadata,
        )
