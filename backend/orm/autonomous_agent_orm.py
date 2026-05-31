"""Autonomous Agent 运行态 ORM。"""

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from core.time import utc_now_naive
from db.postgres_store import Base
from models.autonomous_agent import (
    AgentPlan,
    AgentPlanStatus,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    EvalResult,
    EvaluationTargetType,
    GoalCard,
    MemoryRecord,
    MemoryType,
    PlanGraph,
    ReplanRecord,
    ToolCall,
    ToolCallStatus,
    ToolRiskLevel,
)


class AgentRunORM(Base):
    """Agent 运行表。"""

    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    autonomy_level = Column(String(32), nullable=False, default="supervised")
    budget_limit = Column(JSON, default=dict)
    current_plan_id = Column(String(36), nullable=True)
    current_step_id = Column(String(36), nullable=True)
    final_artifact_id = Column(String(36), nullable=True)
    gate = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    completed_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> AgentRun:
        """转换为 Pydantic 模型。"""
        return AgentRun(
            id=self.id,
            user_id=self.user_id or "",
            workspace_id=self.workspace_id,
            goal=self.goal,
            status=AgentRunStatus(self.status),
            autonomy_level=self.autonomy_level,
            budget_limit=self.budget_limit or {},
            current_plan_id=self.current_plan_id,
            current_step_id=self.current_step_id,
            final_artifact_id=self.final_artifact_id,
            gate=self.gate,
            error_message=self.error_message,
            created_at=self.created_at,
            updated_at=self.updated_at,
            completed_at=self.completed_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: AgentRun) -> AgentRunORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            user_id=model.user_id,
            workspace_id=model.workspace_id,
            goal=model.goal,
            status=model.status.value,
            autonomy_level=model.autonomy_level,
            budget_limit=model.budget_limit,
            current_plan_id=model.current_plan_id,
            current_step_id=model.current_step_id,
            final_artifact_id=model.final_artifact_id,
            gate=model.gate,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
            metadata_json=model.metadata,
        )


class AgentPlanORM(Base):
    """Agent 计划版本表。"""

    __tablename__ = "agent_plans"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False)
    plan_json = Column(JSON, nullable=False)
    goal_card = Column(JSON, nullable=False)
    created_by = Column(String(64), nullable=False, default="planner")
    reason = Column(Text, nullable=False, default="initial_plan")
    created_at = Column(DateTime, default=utc_now_naive)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> AgentPlan:
        """转换为 Pydantic 模型。"""
        return AgentPlan(
            id=self.id,
            run_id=self.run_id,
            version=self.version,
            status=AgentPlanStatus(self.status),
            plan_graph=PlanGraph(**(self.plan_json or {})),
            goal_card=GoalCard(**(self.goal_card or {})),
            created_by=self.created_by,
            reason=self.reason,
            created_at=self.created_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: AgentPlan) -> AgentPlanORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            run_id=model.run_id,
            version=model.version,
            status=model.status.value,
            plan_json=model.plan_graph.model_dump(mode="json"),
            goal_card=model.goal_card.model_dump(mode="json"),
            created_by=model.created_by,
            reason=model.reason,
            created_at=model.created_at,
            metadata_json=model.metadata,
        )


class AgentStepORM(Base):
    """Agent 步骤表。"""

    __tablename__ = "agent_steps"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("agent_plans.id"), nullable=False, index=True)
    node_id = Column(String(100), nullable=False)
    parent_step_id = Column(String(36), nullable=True)
    step_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(32), nullable=False, index=True)
    input_json = Column(JSON, default=dict)
    output_json = Column(JSON, default=dict)
    artifact_ids = Column(JSON, default=list)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> AgentStep:
        """转换为 Pydantic 模型。"""
        return AgentStep(
            id=self.id,
            run_id=self.run_id,
            plan_id=self.plan_id,
            node_id=self.node_id,
            parent_step_id=self.parent_step_id,
            step_type=AgentStepType(self.step_type),
            title=self.title,
            description=self.description,
            status=AgentStepStatus(self.status),
            input=self.input_json or {},
            output=self.output_json or {},
            artifact_ids=self.artifact_ids or [],
            started_at=self.started_at,
            ended_at=self.ended_at,
            error_message=self.error_message,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: AgentStep) -> AgentStepORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            run_id=model.run_id,
            plan_id=model.plan_id,
            node_id=model.node_id,
            parent_step_id=model.parent_step_id,
            step_type=model.step_type.value,
            title=model.title,
            description=model.description,
            status=model.status.value,
            input_json=model.input,
            output_json=model.output,
            artifact_ids=model.artifact_ids,
            started_at=model.started_at,
            ended_at=model.ended_at,
            error_message=model.error_message,
            metadata_json=model.metadata,
        )


class ToolCallORM(Base):
    """工具调用审计表。"""

    __tablename__ = "tool_calls"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_id = Column(String(36), nullable=True, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    input_json = Column(JSON, default=dict)
    output_json = Column(JSON, default=dict)
    status = Column(String(32), nullable=False, index=True)
    risk_level = Column(String(32), nullable=False)
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    cost = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)
    completed_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> ToolCall:
        """转换为 Pydantic 模型。"""
        return ToolCall(
            id=self.id,
            run_id=self.run_id,
            step_id=self.step_id,
            tool_name=self.tool_name,
            input=self.input_json or {},
            output=self.output_json or {},
            status=ToolCallStatus(self.status),
            risk_level=ToolRiskLevel(self.risk_level),
            error_message=self.error_message,
            latency_ms=self.latency_ms,
            cost=self.cost or {},
            created_at=self.created_at,
            completed_at=self.completed_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: ToolCall) -> ToolCallORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            run_id=model.run_id,
            step_id=model.step_id,
            tool_name=model.tool_name,
            input_json=model.input,
            output_json=model.output,
            status=model.status.value,
            risk_level=model.risk_level.value,
            error_message=model.error_message,
            latency_ms=model.latency_ms,
            cost=model.cost,
            created_at=model.created_at,
            completed_at=model.completed_at,
            metadata_json=model.metadata,
        )


class EvalResultORM(Base):
    """评估结果表。"""

    __tablename__ = "eval_results"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_id = Column(String(36), nullable=True, index=True)
    target_type = Column(String(32), nullable=False)
    score = Column(Float, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    issues_json = Column(JSON, default=list)
    suggestions_json = Column(JSON, default=list)
    created_at = Column(DateTime, default=utc_now_naive)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> EvalResult:
        """转换为 Pydantic 模型。"""
        return EvalResult(
            id=self.id,
            run_id=self.run_id,
            step_id=self.step_id,
            target_type=EvaluationTargetType(self.target_type),
            score=self.score,
            passed=bool(self.passed),
            issues=self.issues_json or [],
            suggestions=self.suggestions_json or [],
            created_at=self.created_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: EvalResult) -> EvalResultORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            run_id=model.run_id,
            step_id=model.step_id,
            target_type=model.target_type.value,
            score=model.score,
            passed=1 if model.passed else 0,
            issues_json=model.issues,
            suggestions_json=model.suggestions,
            created_at=model.created_at,
            metadata_json=model.metadata,
        )


class MemoryRecordORM(Base):
    """Agent 记忆表。"""

    __tablename__ = "agent_memories"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    memory_type = Column(String(32), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding_id = Column(String(100), nullable=True)
    source_trace_id = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=False, default=0.8)
    created_at = Column(DateTime, default=utc_now_naive)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> MemoryRecord:
        """转换为 Pydantic 模型。"""
        return MemoryRecord(
            id=self.id,
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            memory_type=MemoryType(self.memory_type),
            content=self.content,
            embedding_id=self.embedding_id,
            source_trace_id=self.source_trace_id,
            confidence=self.confidence,
            created_at=self.created_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: MemoryRecord) -> MemoryRecordORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            workspace_id=model.workspace_id,
            run_id=model.run_id,
            memory_type=model.memory_type.value,
            content=model.content,
            embedding_id=model.embedding_id,
            source_trace_id=model.source_trace_id,
            confidence=model.confidence,
            created_at=model.created_at,
            metadata_json=model.metadata,
        )


class ReplanRecordORM(Base):
    """重规划记录表。"""

    __tablename__ = "replan_records"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    old_plan_id = Column(String(36), nullable=False)
    new_plan_id = Column(String(36), nullable=False)
    trigger_reason = Column(Text, nullable=False)
    failed_step_id = Column(String(36), nullable=True)
    reflection = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)
    metadata_json = Column(JSON, default=dict)

    def to_model(self) -> ReplanRecord:
        """转换为 Pydantic 模型。"""
        return ReplanRecord(
            id=self.id,
            run_id=self.run_id,
            old_plan_id=self.old_plan_id,
            new_plan_id=self.new_plan_id,
            trigger_reason=self.trigger_reason,
            failed_step_id=self.failed_step_id,
            reflection=self.reflection or {},
            created_at=self.created_at,
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: ReplanRecord) -> ReplanRecordORM:
        """从 Pydantic 模型创建 ORM。"""
        return cls(
            id=model.id,
            run_id=model.run_id,
            old_plan_id=model.old_plan_id,
            new_plan_id=model.new_plan_id,
            trigger_reason=model.trigger_reason,
            failed_step_id=model.failed_step_id,
            reflection=model.reflection,
            created_at=model.created_at,
            metadata_json=model.metadata,
        )
