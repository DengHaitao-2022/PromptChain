"""
基于 Prompt Chain 的自动化内容生成系统 - 数据模型

核心模型定义：
- Artifact: 节点产物（版本化存储）
- NodeRun: 节点运行记录
- WorkflowRun: 工作流运行记录
- LLMCallRecord: LLM调用记录
- HumanDecision: 人工决策记录
"""

import hashlib
import json
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.time import utc_now_naive


class ArtifactType(StrEnum):
    """产物类型枚举"""

    INTENT_CARD = "intent_card"
    OUTLINE = "outline"
    EVIDENCE_PACK = "evidence_pack"
    FACT_CHECK_REPORT = "fact_check_report"
    SECTION_CONTENT = "section_content"
    REFINEMENT_FEEDBACK = "refinement_feedback"
    FINAL_CONTENT = "final_content"
    SCENARIO_CHECK_REPORT = "scenario_check_report"
    PROJECT_MEMORY_UPDATE_CANDIDATES = "project_memory_update_candidates"
    AGENT_PLAN = "agent_plan"


class Artifact(BaseModel):
    """
    节点产物（版本化存储）

    设计原则：
    1. 每个节点每次执行都创建新版本
    2. 永不覆盖历史版本（Immutable）
    3. 通过 parent_version 链接版本历史
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # 类型与版本
    type: ArtifactType
    version: int = Field(..., ge=1, description="版本号，从1开始递增")

    # 内容（JSON序列化）
    content: Any = Field(..., description="产物内容，类型由type决定")
    content_hash: str = Field(default="", description="内容哈希，用于快速比对")

    # 时间戳
    created_at: datetime = Field(default_factory=utc_now_naive)

    # 版本链
    parent_version: str | None = Field(None, description="父版本ID（rerun时指向被替换的版本）")

    # 关联信息
    workflow_run_id: str = Field(..., description="所属工作流运行ID")
    node_run_id: str = Field(..., description="产生此产物的节点运行ID")

    # 元数据
    metadata: dict = Field(default_factory=dict, description="扩展元数据")

    def model_post_init(self, __context) -> None:
        """初始化后计算内容哈希"""
        if not self.content_hash and self.content:
            content_str = json.dumps(self.content, sort_keys=True, default=str)
            self.content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]


class NodeRunStatus(StrEnum):
    """节点运行状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"  # Human-in-the-Loop 中断


class LLMCallRecord(BaseModel):
    """LLM调用记录"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model: str
    provider: str = Field(default="openai", description="LLM提供商")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    latency_ms: int = Field(default=0)
    temperature: float = Field(default=0.7)
    # 可选：保存完整prompt/response用于调试
    prompt_preview: str | None = Field(None, description="Prompt前200字符")
    response_preview: str | None = Field(None, description="Response前200字符")
    created_at: datetime = Field(default_factory=utc_now_naive)


class HumanDecision(BaseModel):
    """人工决策记录"""

    decision_type: Literal["approve", "reject", "modify", "regenerate"]
    timestamp: datetime = Field(default_factory=utc_now_naive)
    user_input: str | None = None
    modified_content: Any | None = None


class NodeRun(BaseModel):
    """
    节点运行记录（追溯核心）

    记录每次节点执行的完整上下文，用于：
    1. Trace 回放：可视化展示执行过程
    2. 可复现：基于相同输入重现结果
    3. 调试：定位问题节点
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # 所属工作流
    workflow_run_id: str

    # 节点信息
    node_name: str = Field(..., description="节点名称，如 'parse_intent'")
    node_type: str = Field(default="llm_call", description="节点类型，如 'llm_call', 'validation'")

    # 执行时间
    started_at: datetime = Field(default_factory=utc_now_naive)
    completed_at: datetime | None = None
    duration_ms: int | None = None

    # 状态
    status: NodeRunStatus = NodeRunStatus.PENDING
    error_message: str | None = None

    # 输入输出 Artifact 版本关联（核心追溯能力）
    input_artifact_ids: list[str] = Field(default_factory=list, description="输入产物ID列表")
    output_artifact_ids: list[str] = Field(default_factory=list, description="输出产物ID列表")

    # LLM 调用详情（用于成本分析和调试）
    llm_calls: list[LLMCallRecord] = Field(default_factory=list, description="LLM调用记录")

    # 门控决策（Human-in-the-Loop）
    human_decision: HumanDecision | None = None

    # 重试信息
    retry_count: int = Field(default=0)
    is_rerun: bool = Field(default=False, description="是否为rerun产生的节点运行")
    rerun_from_node_run_id: str | None = Field(None, description="rerun来源的节点运行ID")

    def complete(self, status: NodeRunStatus = NodeRunStatus.COMPLETED, error: str | None = None):
        """标记节点完成"""
        self.completed_at = utc_now_naive()
        self.status = status
        self.error_message = error
        if self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)


class WorkflowRunStatus(StrEnum):
    """工作流运行状态"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"  # Human-in-the-Loop 暂停


class WorkflowRun(BaseModel):
    """
    工作流运行记录（顶层追溯入口）
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # 工作流定义
    workflow_name: str = Field(default="content_generation")
    workflow_version: str = Field(default="1.0.0")
    workflow_definition_id: str | None = Field(
        default=None,
        description="绑定的已发布工作流定义ID",
    )
    workflow_version_id: str | None = Field(
        default=None,
        description="绑定的已发布工作流版本ID",
    )

    # 时间
    started_at: datetime = Field(default_factory=utc_now_naive)
    completed_at: datetime | None = None

    # 状态
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING
    current_node: str | None = None

    # 原始输入
    user_input: str = Field(..., description="用户原始输入")

    # 最终输出 Artifact ID
    final_artifact_id: str | None = None

    # 统计
    total_node_runs: int = 0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0

    # 元数据（用于rerun追溯）
    metadata: dict = Field(default_factory=dict)

    def complete(self, status: WorkflowRunStatus = WorkflowRunStatus.COMPLETED):
        """标记工作流完成。

        注意：total_duration_ms 由运行态按节点耗时统一汇总，避免把 Gate/暂停等待时间混入。
        """
        self.completed_at = utc_now_naive()
        self.status = status
