"""
工作流定义ORM模型

用于持久化工作流定义到数据库
"""

import uuid
from datetime import datetime

from db.postgres_store import Base
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text


class WorkflowDefinitionORM(Base):
    """工作流定义表"""

    __tablename__ = "workflow_definitions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    version = Column(Integer, default=1)

    # 节点和边的JSON存储
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)

    # 关联
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 状态
    is_published = Column(Integer, default=0)  # 0=草稿, 1=已发布
    is_deleted = Column(Integer, default=0)

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": self.nodes,
            "edges": self.edges,
            "workspace_id": self.workspace_id,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_published": self.is_published,
        }


class WorkflowVersionORM(Base):
    """工作流版本历史表"""

    __tablename__ = "workflow_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflow_definitions.id"), nullable=False)
    version = Column(Integer, nullable=False)

    # 版本快照
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)

    # 元数据
    change_log = Column(Text, default="")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
