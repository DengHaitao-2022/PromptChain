"""
工作流定义模型

用于可视化编辑器保存/加载工作流定义
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ==================== 节点定义 ====================


class NodePosition(BaseModel):
    """节点位置"""

    x: float
    y: float


class NodeData(BaseModel):
    """节点数据"""

    label: str
    config: dict[str, Any] | None = None


class WorkflowNode(BaseModel):
    """工作流节点"""

    id: str
    # 前端编排器可以提交 richer taxonomy，例如 start/end/llm/tool/http/code/subflow。
    # 后端发布校验与编译预览会将这些扩展类型映射到当前运行时支持的
    # input/process/gate/checker/output 五大类别，以保持向后兼容。
    type: str
    position: NodePosition
    data: NodeData


# ==================== 边定义 ====================


class EdgeData(BaseModel):
    """边数据"""

    condition: str | None = None
    label: str | None = None


class WorkflowEdge(BaseModel):
    """工作流边（连接线）"""

    id: str
    source: str  # 源节点ID
    target: str  # 目标节点ID
    type: str | None = "default"
    data: EdgeData | None = None


# ==================== 工作流定义 ====================


class WorkflowDefinition(BaseModel):
    """
    工作流定义

    用于前端React Flow编辑器与后端的数据交换
    """

    id: str
    name: str
    description: str | None = ""
    version: int = 1
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    # 元数据
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    is_published: bool = False
    published_version_id: str | None = None
    published_version: int | None = None
    published_at: datetime | None = None
    published_by: str | None = None


# ==================== API请求/响应模型 ====================


class WorkflowDefinitionCreate(BaseModel):
    """创建工作流定义请求"""

    name: str
    description: str | None = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class WorkflowDefinitionUpdate(BaseModel):
    """更新工作流定义请求"""

    name: str | None = None
    description: str | None = None
    nodes: list[WorkflowNode] | None = None
    edges: list[WorkflowEdge] | None = None
    change_log: str | None = None


class WorkflowValidationMode(StrEnum):
    """工作流校验模式"""

    SAVE = "save"
    PUBLISH = "publish"


class WorkflowValidationResult(BaseModel):
    """工作流验证结果"""

    mode: WorkflowValidationMode = WorkflowValidationMode.SAVE
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowCompileResult(BaseModel):
    """工作流编译结果"""

    success: bool
    graph_code: str | None = None  # 生成的LangGraph代码预览
    errors: list[str] = Field(default_factory=list)
