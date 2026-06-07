"""
PostgreSQL 存储层

使用 SQLAlchemy 实现 Artifact 和 NodeRun 的持久化存储

注意：这是生产环境的存储实现，内存存储(artifact_store.py)用于开发调试
"""

import asyncio
import base64
import importlib
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeVar

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    and_,
    text,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase, relationship

from core.time import utc_now_naive
from models.artifact import (
    Artifact,
    ArtifactType,
    NodeRun,
    NodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)

T = TypeVar("T")


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""

    pass


def _split_migration_statements(sql: str) -> list[str]:
    """把迁移 SQL 拆成单语句，避开 asyncpg prepared statement 的多语句限制。"""
    statements: list[str] = []
    current: list[str] = []
    index = 0
    quote: str | None = None
    dollar_quote: str | None = None
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if dollar_quote:
            current.append(char)
            if sql.startswith(dollar_quote, index):
                current.extend(sql[index + 1 : index + len(dollar_quote)])
                index += len(dollar_quote)
                dollar_quote = None
            else:
                index += 1
            continue

        if quote:
            current.append(char)
            if char == quote:
                quote = None
            elif char == "\\" and quote == "'" and next_char:
                current.append(next_char)
                index += 1
            index += 1
            continue

        if char == "-" and next_char == "-":
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(sql) and not (sql[index] == "*" and sql[index + 1] == "/"):
                index += 1
            index += 2
            continue

        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue

        if char == "$":
            end = sql.find("$", index + 1)
            if end > index:
                tag = sql[index : end + 1]
                if tag == "$$" or tag[1:-1].replace("_", "").isalnum():
                    dollar_quote = tag
                    current.append(tag)
                    index = end + 1
                    continue

        if char == ";":
            statement = "".join(current).strip()
            if statement and statement.upper() not in {"BEGIN", "COMMIT"}:
                statements.append(statement)
            current.clear()
            index += 1
            continue

        current.append(char)
        index += 1

    statement = "".join(current).strip()
    if statement and statement.upper() not in {"BEGIN", "COMMIT"}:
        statements.append(statement)
    return statements


def _runtime_schema_statements(database_url: str) -> list[str]:
    """返回 legacy 运行态表的幂等升级语句。

    这些语句已归属 Alembic baseline；这里只作为开发兼容路径保留。
    """
    if not database_url.startswith("postgresql"):
        return []

    return [
        'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',
        "CREATE EXTENSION IF NOT EXISTS vector",
    ]


def _runtime_upgrade_statements(database_url: str) -> list[str]:
    """返回模型建表后的幂等补丁语句，兼容未执行迁移的历史库。"""
    if not database_url.startswith("postgresql"):
        return []

    return [
        "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS workflow_definition_id VARCHAR(36)",
        "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS workflow_version_id VARCHAR(36)",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS queue_status VARCHAR(32) NOT NULL DEFAULT 'idle'",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS queued_at TIMESTAMPTZ",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(100)",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS lease_token VARCHAR(64)",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS last_worker_error TEXT",
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_queue_status ON agent_runs (queue_status)",
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_lease_expires_at ON agent_runs (lease_expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_worker_id ON agent_runs (worker_id)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_id VARCHAR(64)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(64)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS span_id VARCHAR(32)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_category VARCHAR(50)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_type VARCHAR(50)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_snapshot JSON",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_snapshot JSON",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS metadata_json JSON",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS schema_version VARCHAR(20)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_membership_user_workspace'
            ) AND EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'memberships'
                  AND indexname = 'uq_membership_user_workspace'
            ) THEN
                ALTER TABLE memberships
                    ADD CONSTRAINT uq_membership_user_workspace UNIQUE USING INDEX uq_membership_user_workspace;
            ELSIF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_membership_user_workspace'
            ) AND NOT EXISTS (
                SELECT 1
                FROM memberships
                GROUP BY user_id, workspace_id
                HAVING COUNT(*) > 1
            ) THEN
                ALTER TABLE memberships
                    ADD CONSTRAINT uq_membership_user_workspace UNIQUE (user_id, workspace_id);
            END IF;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_event_id ON audit_logs (event_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id ON audit_logs (request_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_trace_id ON audit_logs (trace_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_outcome ON audit_logs (outcome)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_target ON audit_logs (target_type, target_id)",
        """
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            owner_user_id VARCHAR(36) REFERENCES users(id),
            workflow_run_id VARCHAR(36),
            scope VARCHAR(20) NOT NULL DEFAULT 'workspace',
            name VARCHAR(160) NOT NULL,
            description TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_documents (
            id VARCHAR(36) PRIMARY KEY,
            kb_id VARCHAR(36) NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            owner_user_id VARCHAR(36) REFERENCES users(id),
            workflow_run_id VARCHAR(36),
            file_name VARCHAR(255) NOT NULL,
            file_type VARCHAR(40) NOT NULL,
            storage_uri TEXT,
            checksum VARCHAR(64) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            parse_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            index_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            error_message TEXT,
            metadata_json JSON DEFAULT '{}'::json,
            created_by VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36)",
        "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36)",
        "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'",
        "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS metadata_json JSON DEFAULT '{}'::json",
        """
        CREATE TABLE IF NOT EXISTS kb_chunks (
            id VARCHAR(36) PRIMARY KEY,
            document_id VARCHAR(36) NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
            kb_id VARCHAR(36) NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            owner_user_id VARCHAR(36) REFERENCES users(id),
            workflow_run_id VARCHAR(36),
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            heading_path JSON DEFAULT '[]'::json,
            page_number INTEGER,
            metadata_json JSON DEFAULT '{}'::json,
            content_hash VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36)",
        """
        CREATE TABLE IF NOT EXISTS kb_embeddings (
            id VARCHAR(36) PRIMARY KEY,
            chunk_id VARCHAR(36) NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
            embedding_model VARCHAR(120) NOT NULL,
            vector_json JSON NOT NULL,
            dimension INTEGER NOT NULL,
            embedding_vector vector(1536),
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "ALTER TABLE kb_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)",
        """
        CREATE TABLE IF NOT EXISTS kb_retrieval_logs (
            id VARCHAR(36) PRIMARY KEY,
            workflow_run_id VARCHAR(36),
            node_run_id VARCHAR(36),
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            query TEXT NOT NULL,
            rewritten_queries JSON DEFAULT '[]'::json,
            retrieval_scope JSON DEFAULT '[]'::json,
            retrieval_mode VARCHAR(20) NOT NULL,
            top_k INTEGER NOT NULL,
            min_score DOUBLE PRECISION NOT NULL,
            retrieved_chunk_ids JSON DEFAULT '[]'::json,
            scores JSON DEFAULT '[]'::json,
            metadata_json JSON DEFAULT '{}'::json,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_knowledge_bases_workspace_scope ON knowledge_bases (workspace_id, scope, status)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_bases_owner ON knowledge_bases (owner_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_bases_run_upload ON knowledge_bases (workspace_id, owner_user_id, workflow_run_id, scope)",
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_kb_status ON kb_documents (kb_id, index_status)",
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_index_claim ON kb_documents (index_status, updated_at, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_kb_lifecycle ON kb_documents (kb_id, status, version)",
        "CREATE INDEX IF NOT EXISTS ix_kb_documents_workspace ON kb_documents (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_kb ON kb_chunks (kb_id)",
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_workspace ON kb_chunks (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_run_upload ON kb_chunks (workspace_id, owner_user_id, workflow_run_id)",
        "CREATE INDEX IF NOT EXISTS ix_kb_embeddings_chunk ON kb_embeddings (chunk_id)",
        "CREATE INDEX IF NOT EXISTS ix_kb_retrieval_logs_workflow ON kb_retrieval_logs (workflow_run_id)",
        """
        CREATE TABLE IF NOT EXISTS kb_retrieval_evaluation_runs (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id),
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            evaluation_type VARCHAR(40) NOT NULL DEFAULT 'retrieval',
            request_json JSON NOT NULL DEFAULT '{}'::json,
            summary_json JSON NOT NULL DEFAULT '{}'::json,
            results_json JSON NOT NULL DEFAULT '[]'::json,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "ALTER TABLE kb_retrieval_evaluation_runs ADD COLUMN IF NOT EXISTS evaluation_type VARCHAR(40) NOT NULL DEFAULT 'retrieval'",
        "CREATE INDEX IF NOT EXISTS ix_kb_eval_runs_workspace_created ON kb_retrieval_evaluation_runs (workspace_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_kb_eval_runs_user_created ON kb_retrieval_evaluation_runs (user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_kb_eval_runs_type_created ON kb_retrieval_evaluation_runs (evaluation_type, created_at DESC)",
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                CREATE INDEX IF NOT EXISTS ix_kb_embeddings_vector_hnsw
                    ON kb_embeddings USING hnsw (embedding_vector vector_cosine_ops);
            END IF;
        END $$;
        """,
    ]


def _legacy_schema_init_enabled() -> bool:
    """是否允许应用启动时执行 legacy create_all/ALTER。

    生产环境应设置 DATABASE_AUTO_SCHEMA_INIT=false，并通过 Alembic 管理 schema 版本。
    """
    return os.getenv("DATABASE_AUTO_SCHEMA_INIT", "true").lower() in {"1", "true", "yes", "on"}


# ==================== ORM 模型定义 ====================


class ArtifactORM(Base):
    """Artifact ORM 模型"""

    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True)
    type = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    content_hash = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)
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
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: Artifact) -> ArtifactORM:
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
            metadata_json=model.metadata,
        )


class NodeRunORM(Base):
    """NodeRun ORM 模型"""

    __tablename__ = "node_runs"

    id = Column(String(36), primary_key=True)
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id"), nullable=False)
    node_name = Column(String(100), nullable=False)
    node_type = Column(String(50), default="llm_call")
    started_at = Column(DateTime, default=utc_now_naive)
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
        from models.artifact import HumanDecision, LLMCallRecord

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
            rerun_from_node_run_id=self.rerun_from_node_run_id,
        )
        return node_run

    @classmethod
    def from_model(cls, model: NodeRun) -> NodeRunORM:
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
            # 使用 mode='json' 确保 datetime 等非基础类型被序列化
            llm_calls=[call.model_dump(mode="json") for call in model.llm_calls],
            human_decision=model.human_decision.model_dump(mode="json")
            if model.human_decision
            else None,
            retry_count=model.retry_count,
            is_rerun=model.is_rerun,
            rerun_from_node_run_id=model.rerun_from_node_run_id,
        )


class WorkflowRunORM(Base):
    """WorkflowRun ORM 模型"""

    __tablename__ = "workflow_runs"

    id = Column(String(36), primary_key=True)
    workflow_name = Column(String(100), default="content_generation")
    workflow_version = Column(String(20), default="1.0.0")
    workflow_definition_id = Column(String(36), nullable=True)
    workflow_version_id = Column(String(36), nullable=True)
    started_at = Column(DateTime, default=utc_now_naive)
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
            workflow_definition_id=self.workflow_definition_id,
            workflow_version_id=self.workflow_version_id,
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
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: WorkflowRun) -> WorkflowRunORM:
        """从 Pydantic 模型创建"""
        return cls(
            id=model.id,
            workflow_name=model.workflow_name,
            workflow_version=model.workflow_version,
            workflow_definition_id=model.workflow_definition_id,
            workflow_version_id=model.workflow_version_id,
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
            metadata_json=model.metadata,
        )


class GraphCheckpointORM(Base):
    """LangGraph checkpoint 持久化表。"""

    __tablename__ = "graph_checkpoints"

    thread_id = Column(String(255), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(255), primary_key=True)
    parent_checkpoint_id = Column(String(255), nullable=True)
    checkpoint_type = Column(String(255), nullable=False)
    checkpoint_payload = Column(Text, nullable=False)
    metadata_type = Column(String(255), nullable=False)
    metadata_payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)


class GraphCheckpointWriteORM(Base):
    """LangGraph pending writes 持久化表。"""

    __tablename__ = "graph_checkpoint_writes"

    thread_id = Column(String(255), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(255), primary_key=True)
    task_id = Column(String(255), primary_key=True)
    write_index = Column(Integer, primary_key=True)
    channel = Column(String(255), nullable=False)
    task_path = Column(Text, default="")
    value_type = Column(String(255), nullable=False)
    value_payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)


# ==================== PostgreSQL 存储服务 ====================


class PostgresArtifactStore:
    """PostgreSQL 存储服务"""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/promptchain"
        )
        sql_echo = os.getenv("SQL_ECHO", "false").lower() == "true"
        pool_recycle_seconds = int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800"))
        # 连接池取连接前先做健康检查，并定期回收旧连接，避免拿到已失效的 asyncpg 连接。
        self.engine = create_async_engine(
            self.database_url,
            echo=sql_echo,
            pool_pre_ping=True,
            pool_recycle=pool_recycle_seconds,
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def _ensure_initialized(self):
        """懒初始化数据库表，避免调用方必须显式 init。"""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await self.init_db()
            self._initialized = True

    async def ensure_initialized(self) -> None:
        """公开的运行态表初始化入口，供直接使用 async_session 的路由调用。"""
        await self._ensure_initialized()

    async def init_db(self):
        """初始化数据库表。

        Alembic 是生产 schema 变更的唯一入口；这里仅保留开发兼容初始化。
        """
        for module_name in (
            "models.auth_orm",
            "models.admin_orm",
            "models.workflow_orm",
            "orm.knowledge_orm",
            "orm.autonomous_agent_orm",
        ):
            importlib.import_module(module_name)

        if not _legacy_schema_init_enabled():
            return

        async with self.engine.begin() as conn:
            for statement in _runtime_schema_statements(self.database_url):
                await conn.execute(text(statement))
            await conn.run_sync(Base.metadata.create_all)
            await self._run_migrations(conn)
            for statement in _runtime_upgrade_statements(self.database_url):
                await conn.execute(text(statement))

    async def _run_migrations(self, conn) -> None:
        """按文件名顺序执行 db/migrations 下的 SQL 迁移，并记录已执行版本。"""
        if not self.database_url.startswith("postgresql"):
            return

        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(120) PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
        )
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        if not migrations_dir.exists():
            return

        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied_versions = {row[0] for row in result.all()}
        for migration_file in sorted(migrations_dir.glob("*.sql")):
            version = migration_file.name
            if version in applied_versions:
                continue
            # 迁移文件由仓库维护，不拼接用户输入；保持原 SQL 便于 DB 自身事务处理。
            for statement in _split_migration_statements(
                migration_file.read_text(encoding="utf-8")
            ):
                await conn.execute(text(statement))
            await conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )

    @asynccontextmanager
    async def initialized_session(self) -> AsyncIterator[AsyncSession]:
        """返回已完成迁移初始化的短生命周期 session。"""
        await self._ensure_initialized()
        async with self.async_session() as session:
            yield session

    async def dispose(self) -> None:
        """在应用关闭或热重载时主动释放连接池中的底层连接。"""
        await self.engine.dispose()

    def _is_retryable_disconnect(self, exc: BaseException) -> bool:
        """识别可通过清理连接池后重试一次恢复的断连错误。"""
        if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
            return True

        message = str(exc).lower()
        return any(
            marker in message
            for marker in (
                "connection is closed",
                "connection was closed",
                "connection reset by peer",
                "server closed the connection unexpectedly",
            )
        )

    async def _run_with_session(
        self,
        operation: Callable[[AsyncSession], Awaitable[T]],
    ) -> T:
        """执行短生命周期数据库操作。

        写路径不能在断连后重放整个操作体，否则提交成功但响应丢失时会重复写入。
        断连恢复交给 SQLAlchemy 的 pool_pre_ping / pool_recycle 处理。
        """
        await self._ensure_initialized()

        async with self.async_session() as session:
            return await operation(session)

    async def create_artifact(
        self,
        artifact_type: ArtifactType | None = None,
        *,
        content: Any,
        workflow_run_id: str,
        node_run_id: str,
        parent_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Artifact:
        """创建新的 Artifact 版本"""
        import hashlib
        import json

        # 兼容旧调用：历史代码可能使用 `type=` 传参，这里统一归一为 artifact_type。
        if artifact_type is None:
            artifact_type = kwargs.get("type")
        if artifact_type is None:
            raise ValueError("artifact_type is required")
        metadata = metadata or {}

        async def _operation(session: AsyncSession) -> Artifact:
            # 计算版本号
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
                    .where(ArtifactORM.type == artifact_type.value)
                    .order_by(ArtifactORM.version.desc())
                    .limit(1)
                )
                latest = result.scalar_one_or_none()
                version = latest.version + 1 if latest else 1

            # 计算内容哈希
            content_str = json.dumps(content, sort_keys=True, default=str)
            content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]

            # 创建 Artifact
            artifact = Artifact(
                type=artifact_type,
                version=version,
                content=content,
                content_hash=content_hash,
                workflow_run_id=workflow_run_id,
                node_run_id=node_run_id,
                parent_version=parent_version_id,
                metadata=metadata,
            )

            # 持久化
            orm = ArtifactORM.from_model(artifact)
            session.add(orm)
            await session.commit()

            return artifact

        return await self._run_with_session(_operation)

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        """获取指定 Artifact"""

        async def _operation(session: AsyncSession) -> Artifact | None:
            result = await session.execute(select(ArtifactORM).where(ArtifactORM.id == artifact_id))
            orm = result.scalar_one_or_none()
            return orm.to_model() if orm else None

        return await self._run_with_session(_operation)

    async def get_version_history(self, artifact_id: str) -> list[Artifact]:
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

        async def _operation(session: AsyncSession) -> NodeRun:
            orm = NodeRunORM.from_model(node_run)
            session.add(orm)
            await session.commit()
            return node_run

        return await self._run_with_session(_operation)

    async def update_node_run(self, node_run: NodeRun) -> NodeRun:
        """更新节点运行记录"""

        async def _operation(session: AsyncSession) -> NodeRun:
            result = await session.execute(select(NodeRunORM).where(NodeRunORM.id == node_run.id))
            orm = result.scalar_one_or_none()
            if orm:
                # 更新字段
                orm.completed_at = node_run.completed_at
                orm.duration_ms = node_run.duration_ms
                orm.status = node_run.status.value
                orm.error_message = node_run.error_message
                orm.output_artifact_ids = node_run.output_artifact_ids
                # 使用 mode='json' 确保 datetime 等非基础类型被序列化
                orm.llm_calls = [call.model_dump(mode="json") for call in node_run.llm_calls]
                orm.human_decision = (
                    node_run.human_decision.model_dump(mode="json")
                    if node_run.human_decision
                    else None
                )
                await session.commit()
            return node_run

        return await self._run_with_session(_operation)

    async def get_node_run(self, node_run_id: str) -> NodeRun | None:
        """获取节点运行记录"""

        async def _operation(session: AsyncSession) -> NodeRun | None:
            result = await session.execute(select(NodeRunORM).where(NodeRunORM.id == node_run_id))
            orm = result.scalar_one_or_none()
            return orm.to_model() if orm else None

        return await self._run_with_session(_operation)

    async def get_node_runs_by_workflow(self, workflow_run_id: str) -> list[NodeRun]:
        """获取工作流的所有节点运行记录"""

        async def _operation(session: AsyncSession) -> list[NodeRun]:
            result = await session.execute(
                select(NodeRunORM)
                .where(NodeRunORM.workflow_run_id == workflow_run_id)
                .order_by(NodeRunORM.started_at)
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]

        return await self._run_with_session(_operation)

    async def get_latest_node_run(self, workflow_run_id: str) -> NodeRun | None:
        """获取工作流最近一次节点运行。"""

        async def _operation(session: AsyncSession) -> NodeRun | None:
            result = await session.execute(
                select(NodeRunORM)
                .where(NodeRunORM.workflow_run_id == workflow_run_id)
                .order_by(NodeRunORM.started_at.desc())
            )
            orm = result.scalars().first()
            return orm.to_model() if orm else None

        return await self._run_with_session(_operation)

    async def create_workflow_run(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """创建工作流运行记录"""

        async def _operation(session: AsyncSession) -> WorkflowRun:
            orm = WorkflowRunORM.from_model(workflow_run)
            session.add(orm)
            await session.commit()
            return workflow_run

        return await self._run_with_session(_operation)

    async def update_workflow_run(self, workflow_run: WorkflowRun) -> WorkflowRun:
        """更新工作流运行记录"""

        async def _operation(session: AsyncSession) -> WorkflowRun:
            result = await session.execute(
                select(WorkflowRunORM).where(WorkflowRunORM.id == workflow_run.id)
            )
            orm = result.scalar_one_or_none()
            if orm:
                orm.workflow_definition_id = workflow_run.workflow_definition_id
                orm.workflow_version_id = workflow_run.workflow_version_id
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

        return await self._run_with_session(_operation)

    async def get_workflow_run(self, workflow_run_id: str) -> WorkflowRun | None:
        """获取工作流运行记录"""

        async def _operation(session: AsyncSession) -> WorkflowRun | None:
            result = await session.execute(
                select(WorkflowRunORM).where(WorkflowRunORM.id == workflow_run_id)
            )
            orm = result.scalar_one_or_none()
            return orm.to_model() if orm else None

        return await self._run_with_session(_operation)

    async def list_workflow_runs(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
    ) -> list[WorkflowRun]:
        """按当前工作空间和用户范围返回可见的运行记录。"""
        filters = [WorkflowRunORM.metadata_json["workspace_id"].as_string() == workspace_id]
        if user_id is not None:
            filters.append(WorkflowRunORM.metadata_json["user_id"].as_string() == user_id)

        async def _operation(session: AsyncSession) -> list[WorkflowRun]:
            result = await session.execute(
                select(WorkflowRunORM)
                .where(and_(*filters))
                .order_by(WorkflowRunORM.started_at.desc())
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]

        return await self._run_with_session(_operation)

    async def get_all_workflow_runs(self) -> list[WorkflowRun]:
        """获取所有工作流运行记录"""

        async def _operation(session: AsyncSession) -> list[WorkflowRun]:
            result = await session.execute(
                select(WorkflowRunORM).order_by(WorkflowRunORM.started_at.desc())
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]

        return await self._run_with_session(_operation)

    async def get_artifacts_by_workflow(self, workflow_run_id: str) -> list[Artifact]:
        """获取工作流的所有 Artifacts"""

        async def _operation(session: AsyncSession) -> list[Artifact]:
            result = await session.execute(
                select(ArtifactORM).where(ArtifactORM.workflow_run_id == workflow_run_id)
            )
            orms = result.scalars().all()
            return [orm.to_model() for orm in orms]

        return await self._run_with_session(_operation)

    async def get_workflow_context(
        self,
        workflow_definition_id: str | None,
        workflow_version_id: str | None,
    ) -> dict | None:
        """加载已发布工作流上下文，供运行态恢复和回放使用。"""
        if not workflow_definition_id and not workflow_version_id:
            return None

        from models.workflow_orm import WorkflowDefinitionORM, WorkflowVersionORM

        async def _operation(session: AsyncSession) -> dict | None:
            version = None
            definition = None

            if workflow_version_id:
                version_result = await session.execute(
                    select(WorkflowVersionORM).where(WorkflowVersionORM.id == workflow_version_id)
                )
                version = version_result.scalar_one_or_none()
                if version is None:
                    return None

            if workflow_definition_id:
                definition_result = await session.execute(
                    select(WorkflowDefinitionORM).where(
                        WorkflowDefinitionORM.id == workflow_definition_id
                    )
                )
                definition = definition_result.scalar_one_or_none()
                if definition is None:
                    return None

            if definition is None and version is not None and version.workflow_id:
                definition_result = await session.execute(
                    select(WorkflowDefinitionORM).where(
                        WorkflowDefinitionORM.id == version.workflow_id
                    )
                )
                definition = definition_result.scalar_one_or_none()

            if (
                workflow_definition_id
                and version is not None
                and version.workflow_id != workflow_definition_id
            ):
                return None

            if (
                version is None
                and not workflow_version_id
                and definition is not None
                and definition.published_version_id
            ):
                version_result = await session.execute(
                    select(WorkflowVersionORM).where(
                        WorkflowVersionORM.id == definition.published_version_id
                    )
                )
                version = version_result.scalar_one_or_none()

            return {
                "workflow_definition_id": workflow_definition_id
                or getattr(version, "workflow_id", None),
                "workflow_version_id": workflow_version_id or getattr(version, "id", None),
                "definition_name": getattr(definition, "name", None),
                "definition_description": getattr(definition, "description", None),
                "version": getattr(version, "version", None),
                "nodes": getattr(version, "nodes", None),
                "edges": getattr(version, "edges", None),
            }

        return await self._run_with_session(_operation)


class PostgresGraphCheckpointSaver(BaseCheckpointSaver[str]):
    """使用 PostgreSQL 持久化 LangGraph checkpoint。"""

    def __init__(
        self,
        store: PostgresArtifactStore | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.store = store or get_postgres_store()

    def _encode_typed(self, value: Any) -> tuple[str, str]:
        value_type, payload = self.serde.dumps_typed(value)
        return value_type, base64.b64encode(payload).decode("ascii")

    def _decode_typed(self, value_type: str, payload: str) -> Any:
        raw = base64.b64decode(payload.encode("ascii"))
        return self.serde.loads_typed((value_type, raw))

    async def _get_checkpoint_row(
        self,
        session: AsyncSession,
        config: RunnableConfig,
    ) -> GraphCheckpointORM | None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)

        query = select(GraphCheckpointORM).where(
            GraphCheckpointORM.thread_id == thread_id,
            GraphCheckpointORM.checkpoint_ns == checkpoint_ns,
        )
        if checkpoint_id:
            query = query.where(GraphCheckpointORM.checkpoint_id == checkpoint_id)
        else:
            query = query.order_by(GraphCheckpointORM.created_at.desc())

        result = await session.execute(query)
        if checkpoint_id:
            return result.scalar_one_or_none()
        return result.scalars().first()

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        await self.store._ensure_initialized()
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")

        async with self.store.async_session() as session:
            checkpoint_row = await self._get_checkpoint_row(session, config)
            if checkpoint_row is None:
                return None

            writes_result = await session.execute(
                select(GraphCheckpointWriteORM)
                .where(
                    GraphCheckpointWriteORM.thread_id == checkpoint_row.thread_id,
                    GraphCheckpointWriteORM.checkpoint_ns == checkpoint_row.checkpoint_ns,
                    GraphCheckpointWriteORM.checkpoint_id == checkpoint_row.checkpoint_id,
                )
                .order_by(
                    GraphCheckpointWriteORM.task_id,
                    GraphCheckpointWriteORM.write_index,
                )
            )
            writes = writes_result.scalars().all()

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_row.checkpoint_id,
                    }
                },
                checkpoint=self._decode_typed(
                    checkpoint_row.checkpoint_type,
                    checkpoint_row.checkpoint_payload,
                ),
                metadata=self._decode_typed(
                    checkpoint_row.metadata_type,
                    checkpoint_row.metadata_payload,
                ),
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": checkpoint_row.parent_checkpoint_id,
                        }
                    }
                    if checkpoint_row.parent_checkpoint_id
                    else None
                ),
                pending_writes=[
                    (
                        write.task_id,
                        write.channel,
                        self._decode_typed(write.value_type, write.value_payload),
                    )
                    for write in writes
                ],
            )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        await self.store._ensure_initialized()
        async with self.store.async_session() as session:
            query = select(GraphCheckpointORM)
            if config is not None:
                query = query.where(
                    GraphCheckpointORM.thread_id == config["configurable"]["thread_id"],
                    GraphCheckpointORM.checkpoint_ns
                    == config["configurable"].get("checkpoint_ns", ""),
                )
                checkpoint_id = get_checkpoint_id(config)
                if checkpoint_id:
                    query = query.where(GraphCheckpointORM.checkpoint_id == checkpoint_id)
            if before is not None and get_checkpoint_id(before):
                query = query.where(GraphCheckpointORM.checkpoint_id < get_checkpoint_id(before))
            query = query.order_by(GraphCheckpointORM.created_at.desc())
            if limit is not None:
                query = query.limit(limit)

            result = await session.execute(query)
            rows = result.scalars().all()
            for row in rows:
                metadata = self._decode_typed(row.metadata_type, row.metadata_payload)
                if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                    continue
                yield (
                    await self.aget_tuple(
                        {
                            "configurable": {
                                "thread_id": row.thread_id,
                                "checkpoint_ns": row.checkpoint_ns,
                                "checkpoint_id": row.checkpoint_id,
                            }
                        }
                    )
                )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        del new_versions

        await self.store._ensure_initialized()
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_type, checkpoint_payload = self._encode_typed(checkpoint)
        metadata_type, metadata_payload = self._encode_typed(
            get_checkpoint_metadata(config, metadata)
        )

        async with self.store.async_session() as session:
            orm = GraphCheckpointORM(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint["id"],
                parent_checkpoint_id=config["configurable"].get("checkpoint_id"),
                checkpoint_type=checkpoint_type,
                checkpoint_payload=checkpoint_payload,
                metadata_type=metadata_type,
                metadata_payload=metadata_payload,
            )
            await session.merge(orm)
            await session.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self.store._ensure_initialized()
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        async with self.store.async_session() as session:
            for index, (channel, value) in enumerate(writes):
                value_type, value_payload = self._encode_typed(value)
                orm = GraphCheckpointWriteORM(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    task_id=task_id,
                    write_index=index,
                    channel=channel,
                    task_path=task_path,
                    value_type=value_type,
                    value_payload=value_payload,
                )
                await session.merge(orm)
            await session.commit()

    async def adelete_thread(self, thread_id: str) -> None:
        await self.store._ensure_initialized()
        async with self.store.async_session() as session:
            writes_result = await session.execute(
                select(GraphCheckpointWriteORM).where(
                    GraphCheckpointWriteORM.thread_id == thread_id
                )
            )
            for write in writes_result.scalars().all():
                await session.delete(write)

            checkpoints_result = await session.execute(
                select(GraphCheckpointORM).where(GraphCheckpointORM.thread_id == thread_id)
            )
            for checkpoint in checkpoints_result.scalars().all():
                await session.delete(checkpoint)
            await session.commit()


# 全局实例
_postgres_store: PostgresArtifactStore | None = None
_postgres_checkpoint_saver: PostgresGraphCheckpointSaver | None = None


def get_postgres_store() -> PostgresArtifactStore:
    """获取 PostgreSQL 存储服务单例"""
    global _postgres_store
    if _postgres_store is None:
        _postgres_store = PostgresArtifactStore()
    return _postgres_store


async def dispose_postgres_store() -> None:
    """若单例已创建，则主动释放其连接池。"""
    global _postgres_store
    if _postgres_store is None:
        return
    await _postgres_store.dispose()


def get_postgres_checkpoint_saver() -> PostgresGraphCheckpointSaver:
    """获取 LangGraph PostgreSQL checkpoint saver 单例。"""
    global _postgres_checkpoint_saver
    if _postgres_checkpoint_saver is None:
        _postgres_checkpoint_saver = PostgresGraphCheckpointSaver(store=get_postgres_store())
    return _postgres_checkpoint_saver


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    获取数据库会话

    用于依赖注入和路由层使用

    Returns:
        AsyncSession: SQLAlchemy 异步会话对象
    """
    store = get_postgres_store()
    await store._ensure_initialized()
    async with store.async_session() as session:
        yield session
