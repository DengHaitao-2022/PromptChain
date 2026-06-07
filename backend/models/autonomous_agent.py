"""
Autonomous Agent 运行态数据模型。

这些模型描述 Issue #15 中的目标驱动 Agent Runtime：目标卡、动态计划图、
步骤执行、工具调用、评估结果、记忆和重规划记录。
"""

import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.time import utc_now_naive


class AgentRunStatus(StrEnum):
    """自主 Agent 运行状态。"""

    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_GATE = "awaiting_gate"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentPlanStatus(StrEnum):
    """计划版本状态。"""

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStepStatus(StrEnum):
    """计划步骤执行状态。"""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class AgentStepType(StrEnum):
    """计划步骤类型。"""

    GOAL_INTERPRETATION = "goal_interpretation"
    PLANNING = "planning"
    MEMORY_RETRIEVAL = "memory_retrieval"
    TOOL_CALL = "tool_call"
    GENERATION = "generation"
    EVALUATION = "evaluation"
    REFLECTION = "reflection"
    REPLAN = "replan"
    FINALIZATION = "finalization"


class ToolRiskLevel(StrEnum):
    """工具风险等级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolCallStatus(StrEnum):
    """工具调用状态。"""

    PENDING = "pending"
    AWAITING_GATE = "awaiting_gate"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class EvaluationTargetType(StrEnum):
    """评估目标类型。"""

    STEP = "step"
    PLAN = "plan"
    FINAL_OUTPUT = "final_output"


class MemoryType(StrEnum):
    """Agent 记忆类型。"""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


AutonomyLevel = Literal["assistive", "supervised", "autonomous"]


class GoalCard(BaseModel):
    """目标卡：从开放式用户目标中抽取执行边界。"""

    goal: str
    task_type: str
    constraints: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    risk_boundaries: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    quality_dimensions: list[str] = Field(default_factory=list)
    uncertainty_questions: list[str] = Field(default_factory=list)


class PlanNode(BaseModel):
    """动态计划图节点。"""

    id: str
    title: str
    step_type: AgentStepType
    description: str
    depends_on: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    status: AgentStepStatus = AgentStepStatus.PENDING


class PlanEdge(BaseModel):
    """动态计划图边。"""

    source: str
    target: str
    condition: str | None = None


class PlanGraph(BaseModel):
    """动态任务图。"""

    nodes: list[PlanNode] = Field(default_factory=list)
    edges: list[PlanEdge] = Field(default_factory=list)
    quality_gates: list[dict[str, Any]] = Field(default_factory=list)
    max_steps: int = 12
    max_replans: int = 2


class ToolDefinition(BaseModel):
    """工具注册定义。"""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    permission: str = "workflow:execute"
    idempotent: bool = True


class AgentRun(BaseModel):
    """一次自主 Agent 运行。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    workspace_id: str
    goal: str
    status: AgentRunStatus = AgentRunStatus.PLANNING
    autonomy_level: AutonomyLevel = "supervised"
    budget_limit: dict[str, Any] = Field(default_factory=dict)
    current_plan_id: str | None = None
    current_step_id: str | None = None
    final_artifact_id: str | None = None
    gate: dict[str, Any] | None = None
    error_message: str | None = None
    queue_status: str = "idle"
    queued_at: Any | None = None
    claimed_at: Any | None = None
    lease_expires_at: Any | None = None
    heartbeat_at: Any | None = None
    worker_id: str | None = None
    lease_token: str | None = None
    attempt_count: int = 0
    last_worker_error: str | None = None
    created_at: Any = Field(default_factory=utc_now_naive)
    updated_at: Any = Field(default_factory=utc_now_naive)
    completed_at: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    """Agent 计划版本。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    version: int = 1
    status: AgentPlanStatus = AgentPlanStatus.DRAFT
    plan_graph: PlanGraph
    goal_card: GoalCard
    created_by: str = "planner"
    reason: str = "initial_plan"
    created_at: Any = Field(default_factory=utc_now_naive)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStep(BaseModel):
    """Agent 子任务执行记录。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    plan_id: str
    node_id: str
    parent_step_id: str | None = None
    step_type: AgentStepType
    title: str
    description: str
    status: AgentStepStatus = AgentStepStatus.PENDING
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    started_at: Any | None = None
    ended_at: Any | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """工具调用审计记录。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    step_id: str | None = None
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    error_message: str | None = None
    latency_ms: int | None = None
    cost: dict[str, Any] = Field(default_factory=dict)
    created_at: Any = Field(default_factory=utc_now_naive)
    completed_at: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    """步骤或最终输出的评估结果。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    step_id: str | None = None
    target_type: EvaluationTargetType
    score: float = Field(default=0, ge=0, le=1)
    passed: bool = False
    issues: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Any = Field(default_factory=utc_now_naive)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """长期/经验记忆记录。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    run_id: str | None = None
    memory_type: MemoryType
    content: str
    embedding_id: str | None = None
    source_trace_id: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)
    created_at: Any = Field(default_factory=utc_now_naive)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplanRecord(BaseModel):
    """重规划记录。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    old_plan_id: str
    new_plan_id: str
    trigger_reason: str
    failed_step_id: str | None = None
    reflection: dict[str, Any] = Field(default_factory=dict)
    created_at: Any = Field(default_factory=utc_now_naive)
    metadata: dict[str, Any] = Field(default_factory=dict)
