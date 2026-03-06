"""
PostgreSQL 存储层

使用 SQLAlchemy 实现 Artifact 和 NodeRun 的持久化存储

注意：这是生产环境的存储实现，内存存储(artifact_store.py)用于开发调试
"""
from typing import Optional, List, Any
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, Boolean, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.future import select
import os
import json

from models.artifact import Artifact, ArtifactType, NodeRun, NodeRunStatus, WorkflowRun, WorkflowRunStatus


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


# ==================== ORM 模型定义 ====================

class ArtifactORM(Base):
    """Artifact ORM 模型"""
    __tablename__ = "artifacts"
    
    id = Column(String(36), primary_key=True)
    type = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    content_hash = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    parent_version = Column(String(36), nullable=True)
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id"), nullable=False)
    node_run_id = Column(String(36), ForeignKey("node_runs.id"), nullable=False)
    metadata_json = Column(JSON, default=dict)
    
    def to_model(self) -> Artifact:
        """转换为 Pydantic 模型"""
        return Artifact(
            id=self.id,
            type=ArtifactType(self.type),
            version=self.version,
            content=self.content,
            content_hash=self.content_hash,
            created_at=self.created_at,
            parent_version=self.parent_version,
            workflow_run_id=self.workflow_run_id,
            node_run_id=self.node_run_id,
            metadata=self.metadata_json or {}
        )
    
    @classmethod
    def from_model(cls, model: Artifact) -> "ArtifactORM":
        """从 Pydantic 模型创建"""
        return cls(
            id=model.id,
            type=model.type.value,
            version=model.version,
            content=model.content,
            content_hash=model.content_hash,
            created_at=model.created_at,
            parent_version=model.parent_version,
            workflow_run_id=model.workflow_run_id,
            node_run_id=model.node_run_id,
            metadata_json=model.metadata
        )


class NodeRunORM(Base):
    """NodeRun ORM 模型"""
    __tablename__ = "node_runs"
    
    id = Column(String(36), primary_key=True)
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id"), nullable=False)
    node_name = Column(String(100), nullable=False)
    node_type = Column(String(50), default="llm_call")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)
    input_artifact_ids = Column(JSON, default=list)
    output_artifact_ids = Column(JSON, default=list)
    llm_calls = Column(JSON, default=list)
    human_decision = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)
    is_rerun = Column(Boolean, default=False)
    rerun_from_node_run_id = Column(String(36), nullable=True)
    
    def to_model(self) -> NodeRun:
        """转换为 Pydantic 模型"""
        from models.artifact import LLMCallRecord, HumanDecision
        
        node_run = NodeRun(
            id=self.id,
            workflow_run_id=self.workflow_run_id,
            node_name=self.node_name,
            node_type=self.node_type,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_ms=self.duration_ms,
            status=NodeRunStatus(self.status),
            error_message=self.error_message,
            input_artifact_ids=self.input_artifact_ids or [],
            output_artifact_ids=self.output_artifact_ids or [],
            llm_calls=[LLMCallRecord(**call) for call in (self.llm_calls or [])],
            human_decision=HumanDecision(**self.human_decision) if self.human_decision else None,
            retry_count=self.retry_count,
            is_rerun=self.is_rerun,
            rerun_from_node_run_id=self.rerun_from_node_run_id
        )
        return node_run
    
    @classmethod
    def from_model(cls, model: NodeRun) -> "NodeRunORM":
        """从 Pydantic 模型创建"""
        return cls(
            id=model.id,
            workflow_run_id=model.workflow_run_id,
            node_name=model.node_name,
            node_type=model.node_type,
            started_at=model.started_at,
            completed_at=model.completed_at,
            duration_ms=model.duration_ms,
            status=model.status.value,
            error_message=model.error_message,
            input_artifact_ids=model.input_artifact_ids,
            output_artifact_ids=model.output_artifact_ids,
            llm_calls=[call.model_dump() for call in model.llm_calls],
            human_decision=model.human_decision.model_dump() if model.human_decision else None,
            retry_count=model.retry_count,
            is_rerun=model.is_rerun,
            rerun_from_node_run_id=model.rerun_from_node_run_id
        )


class WorkflowRunORM(Base):
    """WorkflowRun ORM 模型"""
    __tablename__ = "workflow_runs"
    
    id = Column(String(36), primary_key=True)
    workflow_name = Column(String(100), default="content_generation")
    workflow_version = Column(String(20), default="1.0.0")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")
    current_node = Column(String(100), nullable=True)
    user_input = Column(Text, nullable=False)
    final_artifact_id = Column(String(36), nullable=True)
    total_node_runs = Column(Integer, default=0)
    total_llm_calls = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    
    # 关系
    node_runs = relationship("NodeRunORM", backref="workflow_run", lazy="dynamic")
    artifacts = relationship("ArtifactORM", backref="workflow_run", lazy="dynamic")
    
    def to_model(self) -> WorkflowRun:
        """转换为 Pydantic 模型"""
        return WorkflowRun(
            id=self.id,
            workflow_name=self.workflow_name,
            workflow_version=self.workflow_version,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=WorkflowRunStatus(self.status),
            current_node=self.current_node,
            user_input=self.user_input,
            final_artifact_id=self.final_artifact_id,
            total_node_runs=self.total_node_runs,
            total_llm_calls=self.total_llm_calls,
            total_tokens=self.total_tokens,
            total_duration_ms=self.total_duration_ms,
            metadata=self.metadata_json or {}
        )
    
    @classmethod
    def from_model(cls, model: WorkflowRun) -> "WorkflowRunORM":
        """从 Pydantic 模型创建"""
        return cls(
            id=model.id,
            workflow_name=model.workflow_name,
            workflow_version=model.workflow_version,
            started_at=model.started_at,
            completed_at=model.completed_at,
            status=model.status.value,
            current_node=model.current_node,
            user_input=model.user_input,
            final_artifact_id=model.final_artifact_id,
            total_node_runs=model.total_node_runs,
            total_llm_calls=model.total_llm_calls,
            total_tokens=model.total_tokens,
            total_duration_ms=model.total_duration_ms,
            metadata_json=model.metadata
        )


# ==================== PostgreSQL 存储服务 ====================

class PostgresArtifactStore:
    """PostgreSQL 存储服务"""
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain"
        )
        self.engine = create_async_engine(self.database_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def init_db(self):
        """初始化数据库表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def create_artifact(
        self,
        type: ArtifactType,
        content: Any,
        workflow_run_id: str,
        node_run_id: str,
        parent_version_id: Optional[str] = None,
        metadata: dict = None
    ) -> Artifact:
        """创建新的 Artifact 版本"""
        import hashlib
        import json
        
        metadata = metadata or {}
        
        # 计算版本号
        async with self.async_session() as session:
            if parent_version_id:
                result = await session.execute(
                    select(ArtifactORM).where(ArtifactORM.id == parent_version_id)
                )
                parent = result.scalar_one_or_none()
                version = parent.version + 1 if parent else 1
            else:
                result = await session.execute(
                    select(ArtifactORM)
                    .where(ArtifactORM.workflow_run_id == workflow_run_id)
                    .where(ArtifactORM.type == type.value)
                    .order_by(ArtifactORM.version.desc())
                )
                latest = result.scalar_one_or_none()
                version = latest.version + 1 if latest else 1
            
            # 计算内容哈希
            content_str = json.dumps(content, sort_keys=True, default=str)
            content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]
            
            # 创建 Artifact
            artifact = Artifact(
                type=type,
                version=version,
                content=content,
                content_hash=content_hash,
                workflow_run_id=workflow_run_id,
                node_run_id=node_run_id,
                parent_version=parent_version_id,
                metadata=metadata
            )
            
            # 持久化
            orm = ArtifactORM.from_model(artifact)
            session.add(orm)
            await session.commit()
            
            return artifact
    
    async def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """获取指定 Artifact"""
        async with self.async_session() as session:
            result = await session.execute(
                select(ArtifactORM).where(ArtifactORM.id == artifact_id)
            )
            orm = result.scalar_one_or_none()
            return orm.to_model() if orm else None
    
    async def get_version_history(self, artifact_id: str) -> List[Artifact]:
        """获取 Artifact 的完整版本历史链"""
        history = []
        current = await self.get_artifact(artifact_id)
        
        while current:
            history.append(current)
            if current.parent_version:
                current = await self.get_artifact(current.parent_version)
            else:
                break
        
        return list(reversed(history))
    
    async def create_node_run(self, node_run: NodeRun) -> NodeRun:
        """创建节点运行记录"""
        async with self.async_session() as session:
            orm = NodeRunORM.from_model(node_run)
            session.add(orm)
            await session.commit()
            return node_run
    
    async def update_node_run(self, node_run: NodeRun) -> NodeRun:
        """更新节点运行记录"""
        async with self.async_session() as session:
            result = await session.execute(
                select(NodeRunORM).where(NodeRunORM.id == node_run.id)
            )
            orm = result.scalar_one_or_none()
            if orm:
                # 更新字段
                orm.completed_at = node_run.completed_at
                orm.duration_ms = node_run.duration_ms
                orm.status = node_run.status.value
                orm.error_message = node_run.error_message
                orm.output_artifact_ids = node_run.output_artifact_ids
                orm.llm_calls = [call.model_dump() for call in node_run.llm_calls]
                orm.human_decision = node_run.human_decision.model_dump() if node_run.human_decision else None
                await session.commit()
            return node_run
    
    async def get_node_run(self, node_run_id: str) -> Optional[NodeRun]:
        """获取节点运行记录"""
        async with self.async_session() as session:
            result = await session.execute(
                select(NodeRunORM).where(NodeRunORM.id == node_run_id)
            )
            orm = result.scalar_one_or_none()
            return orm.to_model() if orm else None
    
    async def get_node_runs_by_workflow(self, workflow_run_id: str) -> List[NodeRun]:
        """获取工作流的所有节点运行记录"""
        async with self.async_session() as session:
            result = await session.execute(
                select(NodeRunORM)
                .where(NodeRunORM.workflow_run_id == workflow_run_id)
                .order_by(NodeRunORM.started_at)
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]
    
    async def create_workflow_run(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """创建工作流运行记录"""
        async with self.async_session() as session:
            orm = WorkflowRunORM.from_model(workflow_run)
            session.add(orm)
            await session.commit()
            return workflow_run
    
    async def update_workflow_run(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """更新工作流运行记录"""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunORM).where(WorkflowRunORM.id == workflow_run.id)
            )
            orm = result.scalar_one_or_none()
            if orm:
                orm.completed_at = workflow_run.completed_at
                orm.status = workflow_run.status.value
                orm.current_node = workflow_run.current_node
                orm.final_artifact_id = workflow_run.final_artifact_id
                orm.total_node_runs = workflow_run.total_node_runs
                orm.total_llm_calls = workflow_run.total_llm_calls
                orm.total_tokens = workflow_run.total_tokens
                orm.total_duration_ms = workflow_run.total_duration_ms
                orm.metadata_json = workflow_run.metadata
                await session.commit()
            return workflow_run
    
    async def get_workflow_run(self, workflow_run_id: str) -> Optional[WorkflowRun]:
        """获取工作流运行记录"""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunORM).where(WorkflowRunORM.id == workflow_run_id)
            )
            orm = result.scalar_one_or_none()
            return orm.to_model() if orm else None
    
    async def get_all_workflow_runs(self) -> List[WorkflowRun]:
        """获取所有工作流运行记录"""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunORM).order_by(WorkflowRunORM.started_at.desc())
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]
    
    async def get_artifacts_by_workflow(self, workflow_run_id: str) -> List[Artifact]:
        """获取工作流的所有 Artifacts"""
        async with self.async_session() as session:
            result = await session.execute(
                select(ArtifactORM).where(ArtifactORM.workflow_run_id == workflow_run_id)
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]


# 全局实例
_postgres_store: Optional[PostgresArtifactStore] = None


def get_postgres_store() -> PostgresArtifactStore:
    """获取 PostgreSQL 存储服务单例"""
    global _postgres_store
    if _postgres_store is None:
        _postgres_store = PostgresArtifactStore()
    return _postgres_store


async def get_session() -> AsyncSession:
    """
    获取数据库会话
    
    用于依赖注入和路由层使用
    
    Returns:
        AsyncSession: SQLAlchemy 异步会话对象
    """
    store = get_postgres_store()
    async with store.async_session() as session:
        yield session
