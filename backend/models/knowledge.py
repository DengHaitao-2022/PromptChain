"""知识库领域模型。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.time import utc_now_naive


class KnowledgeScope(StrEnum):
    """知识库可见范围。"""

    WORKSPACE = "workspace"
    PERSONAL = "personal"
    RUN_UPLOAD = "run_upload"


class KnowledgeBaseStatus(StrEnum):
    """知识库状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class KnowledgeDocumentStatus(StrEnum):
    """文档解析或索引状态。"""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class KnowledgeDocumentLifecycleStatus(StrEnum):
    """文档参与检索的业务状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class RetrievalMode(StrEnum):
    """检索模式。"""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class KnowledgeBase(BaseModel):
    """知识库读模型。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    owner_user_id: str | None = None
    workflow_run_id: str | None = None
    scope: KnowledgeScope = KnowledgeScope.WORKSPACE
    name: str
    description: str | None = None
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE
    created_by: str
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)


class KnowledgeDocument(BaseModel):
    """知识库文档读模型。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kb_id: str
    workspace_id: str
    owner_user_id: str | None = None
    workflow_run_id: str | None = None
    file_name: str
    file_type: str
    storage_uri: str | None = None
    checksum: str
    version: int = 1
    status: KnowledgeDocumentLifecycleStatus = KnowledgeDocumentLifecycleStatus.ACTIVE
    parse_status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PENDING
    index_status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PENDING
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime = Field(default_factory=utc_now_naive)
    updated_at: datetime = Field(default_factory=utc_now_naive)


class KnowledgeChunk(BaseModel):
    """知识库 Chunk 读模型。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    kb_id: str
    workspace_id: str
    owner_user_id: str | None = None
    workflow_run_id: str | None = None
    chunk_index: int
    content: str
    token_count: int
    heading_path: list[str] = Field(default_factory=list)
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    created_at: datetime = Field(default_factory=utc_now_naive)


class KnowledgeSearchRequest(BaseModel):
    """知识检索请求。"""

    workspace_id: str | None = None
    query: str = Field(..., min_length=1)
    scopes: list[KnowledgeScope] = Field(default_factory=lambda: [KnowledgeScope.WORKSPACE])
    top_k: int = Field(default=8, ge=1, le=30)
    min_score: float = Field(default=0.55, ge=0, le=1)
    mode: RetrievalMode = RetrievalMode.HYBRID
    filters: dict[str, Any] = Field(default_factory=dict)
    enable_query_rewrite: bool = True
    enable_multi_query: bool = True
    enable_rerank: bool = True
    enable_context_compression: bool = True
    enable_conflict_detection: bool = True
    workflow_run_id: str | None = None
    node_run_id: str | None = None


class EvidenceChunk(BaseModel):
    """Evidence Artifact 中的命中片段。"""

    chunk_id: str
    document_id: str
    knowledge_base_id: str
    document_name: str
    scope: KnowledgeScope
    page_number: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None
    rerank_score: float | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeConflict(BaseModel):
    """证据冲突提示。"""

    topic: str
    chunk_ids: list[str]
    reason: str


class EvidencePack(BaseModel):
    """Prompt Chain 使用的证据包。"""

    query: str
    rewritten_queries: list[str] = Field(default_factory=list)
    scopes: list[KnowledgeScope] = Field(default_factory=list)
    chunks: list[EvidenceChunk] = Field(default_factory=list)
    conflicts: list[KnowledgeConflict] = Field(default_factory=list)
    unverified_points: list[str] = Field(default_factory=list)
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID
    generated_at: datetime = Field(default_factory=utc_now_naive)


class KnowledgeSearchResponse(BaseModel):
    """知识检索响应。"""

    evidence_pack: EvidencePack
    retrieval_log_id: str | None = None


class RetrievalEvaluationCase(BaseModel):
    """单条检索评测用例。"""

    id: str | None = None
    query: str = Field(..., min_length=1)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)


class RetrievalEvaluationRequest(BaseModel):
    """检索质量评测请求。"""

    cases: list[RetrievalEvaluationCase] = Field(..., min_length=1, max_length=50)
    scopes: list[KnowledgeScope] = Field(default_factory=lambda: [KnowledgeScope.WORKSPACE])
    top_k: int = Field(default=8, ge=1, le=30)
    min_score: float = Field(default=0.0, ge=0, le=1)
    mode: RetrievalMode = RetrievalMode.HYBRID
    filters: dict[str, Any] = Field(default_factory=dict)
    enable_query_rewrite: bool = True
    enable_multi_query: bool = True
    enable_rerank: bool = True
    enable_context_compression: bool = True
    enable_conflict_detection: bool = False


class RetrievalEvaluationResult(BaseModel):
    """单条检索评测结果。"""

    case_id: str | None = None
    query: str
    expected_document_ids: list[str]
    expected_chunk_ids: list[str]
    retrieved_document_ids: list[str]
    retrieved_chunk_ids: list[str]
    hit: bool
    first_relevant_rank: int | None = None
    reciprocal_rank: float = 0.0
    precision_at_k: float = 0.0


class RetrievalEvaluationSummary(BaseModel):
    """检索评测汇总指标。"""

    total_cases: int
    hit_count: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_precision_at_k: float
    empty_expected_count: int = 0


class RetrievalEvaluationResponse(BaseModel):
    """检索评测响应。"""

    summary: RetrievalEvaluationSummary
    results: list[RetrievalEvaluationResult]


class RetrievalConfig(BaseModel):
    """工作流运行时知识检索配置。"""

    enabled: bool = False
    use_workspace_kb: bool = True
    use_personal_kb: bool = False
    use_run_upload: bool = True
    top_k: int = Field(default=8, ge=1, le=30)
    min_score: float = Field(default=0.55, ge=0, le=1)
    mode: RetrievalMode = RetrievalMode.HYBRID
    enable_query_rewrite: bool = True
    enable_multi_query: bool = True
    enable_rerank: bool = True
    enable_context_compression: bool = True
    enable_conflict_detection: bool = True

    @classmethod
    def from_raw(cls, value: Any) -> RetrievalConfig:
        """从运行态 metadata/API 入参中安全恢复检索配置。"""
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls.model_validate(value)
        return cls()

    def to_scopes(self) -> list[KnowledgeScope]:
        """把开关转换成检索 scope 列表。"""
        scopes: list[KnowledgeScope] = []
        if self.use_workspace_kb:
            scopes.append(KnowledgeScope.WORKSPACE)
        if self.use_personal_kb:
            scopes.append(KnowledgeScope.PERSONAL)
        if self.use_run_upload:
            scopes.append(KnowledgeScope.RUN_UPLOAD)
        return scopes
