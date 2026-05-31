-- 004: 生产版知识库与 Evidence Artifact 基础表
-- 目标：支持工作空间/个人/运行态资料的 RAG 检索、pgvector 索引和检索日志。

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

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
);

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
    created_by VARCHAR(36) NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

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
);

CREATE TABLE IF NOT EXISTS kb_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    chunk_id VARCHAR(36) NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
    embedding_model VARCHAR(120) NOT NULL,
    vector_json JSON NOT NULL,
    dimension INTEGER NOT NULL,
    embedding_vector vector(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

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
);

ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36);
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36);
ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36);
ALTER TABLE kb_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);

CREATE INDEX IF NOT EXISTS ix_knowledge_bases_workspace_scope
    ON knowledge_bases (workspace_id, scope, status);
CREATE INDEX IF NOT EXISTS ix_knowledge_bases_owner
    ON knowledge_bases (owner_user_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_bases_run_upload
    ON knowledge_bases (workspace_id, owner_user_id, workflow_run_id, scope);
CREATE INDEX IF NOT EXISTS ix_kb_documents_kb_status
    ON kb_documents (kb_id, index_status);
CREATE INDEX IF NOT EXISTS ix_kb_documents_kb_lifecycle
    ON kb_documents (kb_id, status, version);
CREATE INDEX IF NOT EXISTS ix_kb_documents_workspace
    ON kb_documents (workspace_id);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_kb
    ON kb_chunks (kb_id);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_workspace
    ON kb_chunks (workspace_id);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_run_upload
    ON kb_chunks (workspace_id, owner_user_id, workflow_run_id);
CREATE INDEX IF NOT EXISTS ix_kb_embeddings_chunk
    ON kb_embeddings (chunk_id);
CREATE INDEX IF NOT EXISTS ix_kb_retrieval_logs_workflow
    ON kb_retrieval_logs (workflow_run_id);
CREATE INDEX IF NOT EXISTS ix_kb_embeddings_vector_hnsw
    ON kb_embeddings USING hnsw (embedding_vector vector_cosine_ops);

COMMIT;
