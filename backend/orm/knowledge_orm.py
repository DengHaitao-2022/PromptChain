"""知识库 SQLAlchemy ORM 模型。"""

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from core.time import utc_now_naive
from db.postgres_store import Base
from models.knowledge import (
    KnowledgeBaseStatus,
    KnowledgeDocumentLifecycleStatus,
    KnowledgeDocumentStatus,
    KnowledgeScope,
)

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - pgvector 依赖缺失时仍允许本地 hash 检索运行
    Vector = None


class KnowledgeBaseORM(Base):
    """知识库元数据表。"""

    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    workflow_run_id = Column(String(36), nullable=True, index=True)
    scope = Column(String(20), nullable=False, default=KnowledgeScope.WORKSPACE.value, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=KnowledgeBaseStatus.ACTIVE.value)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    documents = relationship(
        "KnowledgeDocumentORM",
        back_populates="knowledge_base",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class KnowledgeDocumentORM(Base):
    """知识库文档表。"""

    __tablename__ = "kb_documents"

    id = Column(String(36), primary_key=True)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    workflow_run_id = Column(String(36), nullable=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(40), nullable=False, index=True)
    storage_uri = Column(Text, nullable=True)
    checksum = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(
        String(20),
        nullable=False,
        default=KnowledgeDocumentLifecycleStatus.ACTIVE.value,
        index=True,
    )
    parse_status = Column(String(20), nullable=False, default=KnowledgeDocumentStatus.PENDING.value)
    index_status = Column(String(20), nullable=False, default=KnowledgeDocumentStatus.PENDING.value)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    knowledge_base = relationship("KnowledgeBaseORM", back_populates="documents")
    chunks = relationship(
        "KnowledgeChunkORM",
        back_populates="document",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class KnowledgeChunkORM(Base):
    """知识库 Chunk 表。"""

    __tablename__ = "kb_chunks"

    id = Column(String(36), primary_key=True)
    document_id = Column(String(36), ForeignKey("kb_documents.id"), nullable=False, index=True)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    workflow_run_id = Column(String(36), nullable=True, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    heading_path = Column(JSON, default=list)
    page_number = Column(Integer, nullable=True)
    metadata_json = Column(JSON, default=dict)
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)

    document = relationship("KnowledgeDocumentORM", back_populates="chunks")
    embeddings = relationship(
        "KnowledgeEmbeddingORM",
        back_populates="chunk",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class KnowledgeEmbeddingORM(Base):
    """知识库向量表。"""

    __tablename__ = "kb_embeddings"

    id = Column(String(36), primary_key=True)
    chunk_id = Column(String(36), ForeignKey("kb_chunks.id"), nullable=False, index=True)
    embedding_model = Column(String(120), nullable=False)
    vector_json = Column(JSON, nullable=False)
    # pgvector 列用于生产相似度索引；vector_json 保留为本地回退和测试可读格式。
    if Vector is not None:
        embedding_vector = Column(Vector(1536), nullable=True)
    dimension = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)

    chunk = relationship("KnowledgeChunkORM", back_populates="embeddings")


class KnowledgeRetrievalLogORM(Base):
    """知识检索日志表。"""

    __tablename__ = "kb_retrieval_logs"

    id = Column(String(36), primary_key=True)
    workflow_run_id = Column(String(36), nullable=True, index=True)
    node_run_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    query = Column(Text, nullable=False)
    rewritten_queries = Column(JSON, default=list)
    retrieval_scope = Column(JSON, default=list)
    retrieval_mode = Column(String(20), nullable=False)
    top_k = Column(Integer, nullable=False)
    min_score = Column(Float, nullable=False)
    retrieved_chunk_ids = Column(JSON, default=list)
    scores = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)
