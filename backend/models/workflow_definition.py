"""
工作流定义模型

用于可视化编辑器保存/加载工作流定义
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 节点定义 ====================

class NodePosition(BaseModel):
    """节点位置"""
    x: float
    y: float


class NodeData(BaseModel):
    """节点数据"""
    label: str
    config: Optional[Dict[str, Any]] = None


class WorkflowNode(BaseModel):
    """工作流节点"""
    id: str
    type: str  # input, process, gate, checker, output
    position: NodePosition
    data: NodeData


# ==================== 边定义 ====================

class EdgeData(BaseModel):
    """边数据"""
    condition: Optional[str] = None
    label: Optional[str] = None


class WorkflowEdge(BaseModel):
    """工作流边（连接线）"""
    id: str
    source: str  # 源节点ID
    target: str  # 目标节点ID
    type: Optional[str] = "default"
    data: Optional[EdgeData] = None


# ==================== 工作流定义 ====================

class WorkflowDefinition(BaseModel):
    """
    工作流定义

    用于前端React Flow编辑器与后端的数据交换
    """
    id: str
    name: str
    description: Optional[str] = ""
    version: int = 1
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)

    # 元数据
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    is_published: bool = False
    published_version_id: Optional[str] = None
    published_version: Optional[int] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None


# ==================== API请求/响应模型 ====================

class WorkflowDefinitionCreate(BaseModel):
    """创建工作流定义请求"""
    name: str
    description: Optional[str] = ""
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)


class WorkflowDefinitionUpdate(BaseModel):
    """更新工作流定义请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[WorkflowNode]] = None
    edges: Optional[List[WorkflowEdge]] = None
    change_log: Optional[str] = None


class WorkflowValidationMode(str, Enum):
    """工作流校验模式"""

    SAVE = "save"
    PUBLISH = "publish"


class WorkflowValidationResult(BaseModel):
    """工作流验证结果"""
    mode: WorkflowValidationMode = WorkflowValidationMode.SAVE
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class WorkflowCompileResult(BaseModel):
    """工作流编译结果"""
    success: bool
    graph_code: Optional[str] = None  # 生成的LangGraph代码预览
    errors: List[str] = Field(default_factory=list)
