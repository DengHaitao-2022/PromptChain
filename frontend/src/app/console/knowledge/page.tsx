'use client';

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Archive,
  DatabaseZap,
  FileText,
  LibraryBig,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  TrendingUp,
  Upload,
} from 'lucide-react';

import { useAuth } from '@/contexts/AuthContext';
import {
  knowledgeApi,
  type EvidencePack,
  type KnowledgeBase,
  type KnowledgeDocument,
  type KnowledgeScope,
  type KnowledgeUsageStats,
} from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';
import styles from './knowledge.module.css';

const scopeLabels: Record<KnowledgeScope, string> = {
  workspace: '工作空间',
  personal: '个人',
  run_upload: '本次运行',
};

const statusLabels: Record<string, string> = {
  active: '启用',
  disabled: '停用',
  archived: '归档',
  pending: '排队中',
  processing: '处理中',
  ready: '可检索',
  failed: '失败',
};

function getStatusLabel(status: string) {
  return statusLabels[status] || status;
}

function getDocumentReadyCount(documents: KnowledgeDocument[]) {
  return documents.filter((document) => document.index_status === 'ready').length;
}

function hasIndexingDocuments(documents: KnowledgeDocument[]) {
  return documents.some(
    (document) =>
      document.parse_status === 'pending' ||
      document.parse_status === 'processing' ||
      document.index_status === 'pending' ||
      document.index_status === 'processing',
  );
}

export default function KnowledgePage() {
  const { user, workspace, hasPermission } = useAuth();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedKbId, setSelectedKbId] = useState('');
  const [loadingKb, setLoadingKb] = useState(true);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newScope, setNewScope] = useState<KnowledgeScope>('workspace');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchScopes, setSearchScopes] = useState<KnowledgeScope[]>(['workspace']);
  const [evidencePack, setEvidencePack] = useState<EvidencePack | null>(null);
  const [usageStats, setUsageStats] = useState<KnowledgeUsageStats | null>(null);

  // 个人知识库归当前用户所有，不应被工作空间级写权限误拦。
  const canCreateWorkspaceKnowledgeBase = hasPermission('knowledge_base', 'create');
  const canCreatePersonalKnowledgeBase = Boolean(workspace?.id && user?.id);
  const canCreateSelectedScope =
    newScope === 'personal' ? canCreatePersonalKnowledgeBase : canCreateWorkspaceKnowledgeBase;
  const canUpdate = hasPermission('knowledge_base', 'update');
  const canDelete = hasPermission('knowledge_base', 'delete');
  const selectedKnowledgeBase = useMemo(
    () => knowledgeBases.find((item) => item.id === selectedKbId) || null,
    [knowledgeBases, selectedKbId],
  );
  const ownsSelectedKnowledgeBase = Boolean(
    selectedKnowledgeBase?.owner_user_id && selectedKnowledgeBase.owner_user_id === user?.id,
  );
  const canManageSelectedKnowledgeBase = Boolean(
    selectedKnowledgeBase &&
      (selectedKnowledgeBase.scope === 'personal' ? ownsSelectedKnowledgeBase : canUpdate),
  );
  const canDeleteSelectedKnowledgeBase = Boolean(
    selectedKnowledgeBase &&
      (selectedKnowledgeBase.scope === 'personal' ? ownsSelectedKnowledgeBase : canDelete),
  );

  const activeCount = knowledgeBases.filter((item) => item.status === 'active').length;
  const personalCount = knowledgeBases.filter((item) => item.scope === 'personal').length;
  const readyDocumentCount = getDocumentReadyCount(documents);
  const shouldPollDocumentStatus = hasIndexingDocuments(documents);
  const averageChunksPerSearch = usageStats?.average_chunks_per_search ?? 0;

  const loadKnowledgeBases = useCallback(async () => {
    if (!workspace?.id) {
      setKnowledgeBases([]);
      setSelectedKbId('');
      setUsageStats(null);
      setLoadingKb(false);
      return;
    }

    setLoadingKb(true);
    setError('');

    try {
      const response = await knowledgeApi.list(workspace.id);
      const stats = await knowledgeApi.stats();
      const items = response.knowledge_bases || [];
      setKnowledgeBases(items);
      setUsageStats(stats);
      setSelectedKbId((current) => {
        if (current && items.some((item) => item.id === current)) {
          return current;
        }
        return items[0]?.id || '';
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '知识库列表加载失败');
    } finally {
      setLoadingKb(false);
    }
  }, [workspace?.id]);

  const loadDocuments = useCallback(async (knowledgeBaseId: string) => {
    if (!knowledgeBaseId) {
      setDocuments([]);
      return;
    }

    setLoadingDocs(true);
    setError('');

    try {
      const response = await knowledgeApi.listDocuments(knowledgeBaseId);
      setDocuments(response.documents || []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '文档列表加载失败');
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  useEffect(() => {
    void loadKnowledgeBases();
  }, [loadKnowledgeBases]);

  useEffect(() => {
    void loadDocuments(selectedKbId);
  }, [loadDocuments, selectedKbId]);

  useEffect(() => {
    if (!selectedKbId || !shouldPollDocumentStatus) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void loadDocuments(selectedKbId);
      void loadKnowledgeBases();
    }, 3000);

    return () => window.clearInterval(intervalId);
  }, [loadDocuments, loadKnowledgeBases, selectedKbId, shouldPollDocumentStatus]);

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!workspace?.id || !newName.trim() || isCreating || !canCreateSelectedScope) {
      return;
    }

    setIsCreating(true);
    setError('');
    setNotice('');

    try {
      const created = await knowledgeApi.create(workspace.id, {
        name: newName.trim(),
        description: newDescription.trim() || null,
        scope: newScope,
      });
      setNotice('知识库已创建');
      setNewName('');
      setNewDescription('');
      setKnowledgeBases((items) => [created, ...items]);
      setSelectedKbId(created.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '创建知识库失败');
    } finally {
      setIsCreating(false);
    }
  };

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedKbId || !uploadFile || isUploading) {
      return;
    }

    setIsUploading(true);
    setError('');
    setNotice('');

    try {
      const document = await knowledgeApi.uploadDocument(selectedKbId, uploadFile);
      setNotice(document.index_status === 'ready' ? '文档已入库并完成索引' : '文档已入库，正在后台索引');
      setUploadFile(null);
      setDocuments((items) => [document, ...items]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '上传文档失败');
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setUploadFile(event.target.files?.[0] || null);
  };

  const handleDeleteDocument = async (documentId: string) => {
    setError('');
    setNotice('');

    try {
      await knowledgeApi.deleteDocument(documentId);
      setNotice('文档已删除');
      setDocuments((items) => items.filter((item) => item.id !== documentId));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '删除文档失败');
    }
  };

  const handleUpdateDocumentStatus = async (
    documentId: string,
    status: 'active' | 'disabled' | 'archived',
  ) => {
    setError('');
    setNotice('');

    try {
      const updated = await knowledgeApi.updateDocument(documentId, { status });
      setNotice(
        status === 'active' ? '文档已启用' : status === 'disabled' ? '文档已停用' : '文档已归档',
      );
      setDocuments((items) => items.map((item) => (item.id === documentId ? updated : item)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '更新文档状态失败');
    }
  };

  const handleReindexDocument = async (documentId: string) => {
    setError('');
    setNotice('');

    try {
      const updated = await knowledgeApi.reindexDocument(documentId);
      setNotice(updated.index_status === 'ready' ? '文档索引已重建' : '文档已进入后台重建队列');
      setDocuments((items) => items.map((item) => (item.id === documentId ? updated : item)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '重建索引失败');
    }
  };

  const handleToggleStatus = async (knowledgeBase: KnowledgeBase) => {
    setError('');
    setNotice('');
    const nextStatus = knowledgeBase.status === 'active' ? 'disabled' : 'active';

    try {
      const updated = await knowledgeApi.update(knowledgeBase.id, { status: nextStatus });
      setNotice(nextStatus === 'active' ? '知识库已启用' : '知识库已停用');
      setKnowledgeBases((items) =>
        items.map((item) => (item.id === knowledgeBase.id ? updated : item)),
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '更新知识库状态失败');
    }
  };

  const handleDeleteKnowledgeBase = async (knowledgeBaseId: string) => {
    setError('');
    setNotice('');

    try {
      await knowledgeApi.delete(knowledgeBaseId);
      setNotice('知识库已删除');
      setKnowledgeBases((items) => {
        const nextItems = items.filter((item) => item.id !== knowledgeBaseId);
        setSelectedKbId(nextItems[0]?.id || '');
        return nextItems;
      });
      setDocuments([]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '删除知识库失败');
    }
  };

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!workspace?.id || !searchQuery.trim() || isSearching) {
      return;
    }

    setIsSearching(true);
    setError('');
    setEvidencePack(null);

    try {
      const response = await knowledgeApi.search({
        workspace_id: workspace.id,
        query: searchQuery.trim(),
        scopes: searchScopes,
        top_k: 6,
        min_score: 0.2,
        mode: 'hybrid',
      });
      setEvidencePack(response.evidence_pack);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '检索失败');
    } finally {
      setIsSearching(false);
    }
  };

  const toggleSearchScope = (scope: KnowledgeScope) => {
    setSearchScopes((current) => {
      if (current.includes(scope)) {
        const next = current.filter((item) => item !== scope);
        return next.length > 0 ? next : current;
      }
      return [...current, scope];
    });
  };

  return (
    <div className={styles.page}>
      <section className={styles.header}>
        <div>
          <span className={styles.eyebrow}>Knowledge Base</span>
          <h1 className={styles.title}>知识库</h1>
          <p className={styles.subtitle}>
            管理工作空间与个人资料，检索结果会作为 Evidence Artifact 进入生成、修订和事实核查链路。
          </p>
        </div>
        <button className={styles.refreshButton} type="button" onClick={loadKnowledgeBases}>
          <RefreshCw size={17} aria-hidden="true" />
          刷新
        </button>
      </section>

      <section className={styles.metricsGrid} aria-label="知识库统计">
        <article className={styles.metricCard}>
          <LibraryBig size={18} aria-hidden="true" />
          <span>知识库</span>
          <strong>{knowledgeBases.length}</strong>
        </article>
        <article className={styles.metricCard}>
          <ShieldCheck size={18} aria-hidden="true" />
          <span>启用中</span>
          <strong>{activeCount}</strong>
        </article>
        <article className={styles.metricCard}>
          <DatabaseZap size={18} aria-hidden="true" />
          <span>当前可检索文档</span>
          <strong>{readyDocumentCount}</strong>
        </article>
        <article className={styles.metricCard}>
          <Archive size={18} aria-hidden="true" />
          <span>个人库</span>
          <strong>{personalCount}</strong>
        </article>
        <article className={styles.metricCard}>
          <Search size={18} aria-hidden="true" />
          <span>检索次数</span>
          <strong>{usageStats?.total_searches ?? 0}</strong>
        </article>
        <article className={styles.metricCard}>
          <TrendingUp size={18} aria-hidden="true" />
          <span>平均命中</span>
          <strong>{averageChunksPerSearch.toFixed(1)}</strong>
        </article>
        <article className={styles.metricCard}>
          <ShieldCheck size={18} aria-hidden="true" />
          <span>冲突检索</span>
          <strong>{usageStats?.conflict_search_count ?? 0}</strong>
        </article>
        <article className={styles.metricCard}>
          <DatabaseZap size={18} aria-hidden="true" />
          <span>未验证检索</span>
          <strong>{usageStats?.unverified_search_count ?? 0}</strong>
        </article>
      </section>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}
      {notice ? <div className={styles.noticeBanner}>{notice}</div> : null}

      <div className={styles.grid}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>知识库列表</h2>
            <span>{loadingKb ? '加载中' : `${knowledgeBases.length} 个`}</span>
          </div>

          <div className={styles.kbList}>
            {knowledgeBases.map((knowledgeBase) => (
              <button
                key={knowledgeBase.id}
                type="button"
                className={`${styles.kbItem} ${
                  selectedKbId === knowledgeBase.id ? styles.kbItemActive : ''
                }`}
                onClick={() => setSelectedKbId(knowledgeBase.id)}
              >
                <span className={styles.kbName}>{knowledgeBase.name}</span>
                <span className={styles.kbMeta}>
                  {scopeLabels[knowledgeBase.scope]} / {getStatusLabel(knowledgeBase.status)}
                </span>
              </button>
            ))}

            {!loadingKb && knowledgeBases.length === 0 ? (
              <div className={styles.emptyState}>暂无知识库</div>
            ) : null}
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>创建知识库</h2>
            <span>{canCreateSelectedScope ? '可创建' : '只读'}</span>
          </div>

          <form className={styles.form} onSubmit={handleCreate}>
            <label>
              名称
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="例如：产品手册"
                disabled={!canCreateSelectedScope || isCreating}
              />
            </label>
            <label>
              描述
              <textarea
                value={newDescription}
                onChange={(event) => setNewDescription(event.target.value)}
                placeholder="资料用途、来源和维护规则"
                disabled={!canCreateSelectedScope || isCreating}
                rows={3}
              />
            </label>
            <div className={styles.segmentedControl} role="group" aria-label="知识库范围">
              {(['workspace', 'personal'] as KnowledgeScope[]).map((scope) => (
                <button
                  key={scope}
                  type="button"
                  className={newScope === scope ? styles.segmentActive : ''}
                  onClick={() => setNewScope(scope)}
                  disabled={
                    isCreating ||
                    (scope === 'personal'
                      ? !canCreatePersonalKnowledgeBase
                      : !canCreateWorkspaceKnowledgeBase)
                  }
                >
                  {scopeLabels[scope]}
                </button>
              ))}
            </div>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={!canCreateSelectedScope || isCreating}
            >
              {isCreating ? <Loader2 size={16} className={styles.spin} aria-hidden="true" /> : null}
              创建
            </button>
          </form>
        </section>
      </div>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <h2>{selectedKnowledgeBase?.name || '未选择知识库'}</h2>
            <p>
              {selectedKnowledgeBase
                ? `${scopeLabels[selectedKnowledgeBase.scope]} / ${getStatusLabel(selectedKnowledgeBase.status)}`
                : '请选择一个知识库后上传和检索文档'}
            </p>
          </div>
          {selectedKnowledgeBase ? (
            <div className={styles.panelActions}>
              {canManageSelectedKnowledgeBase ? (
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={() => handleToggleStatus(selectedKnowledgeBase)}
                >
                  {selectedKnowledgeBase.status === 'active' ? '停用' : '启用'}
                </button>
              ) : null}
              {canDeleteSelectedKnowledgeBase ? (
                <button
                  className={styles.dangerButton}
                  type="button"
                  onClick={() => handleDeleteKnowledgeBase(selectedKnowledgeBase.id)}
                >
                  <Trash2 size={15} aria-hidden="true" />
                  删除知识库
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <form className={styles.uploadRow} onSubmit={handleUpload}>
          <label className={styles.fileInput}>
            <Upload size={17} aria-hidden="true" />
            <span>{uploadFile?.name || '选择 PDF / DOCX / TXT / Markdown'}</span>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md,.markdown"
              onChange={handleFileChange}
              disabled={!selectedKbId || !canManageSelectedKnowledgeBase || isUploading}
            />
          </label>
          <button
            className={styles.primaryButton}
            type="submit"
            disabled={!selectedKbId || !uploadFile || !canManageSelectedKnowledgeBase || isUploading}
          >
            {isUploading ? <Loader2 size={16} className={styles.spin} aria-hidden="true" /> : null}
            上传并索引
          </button>
        </form>

        <div className={styles.documentTable}>
          <div className={styles.tableHead}>
            <span>文档</span>
            <span>解析</span>
            <span>索引</span>
            <span>状态</span>
            <span>版本</span>
            <span>更新时间</span>
            <span>操作</span>
          </div>
          {documents.map((document) => (
            <div key={document.id} className={styles.tableRow}>
              <span className={styles.documentName}>
                <FileText size={16} aria-hidden="true" />
                <span>
                  {document.file_name}
                  {document.error_message ? (
                    <small className={styles.documentError}>{document.error_message}</small>
                  ) : null}
                </span>
              </span>
              <span>{getStatusLabel(document.parse_status)}</span>
              <span>{getStatusLabel(document.index_status)}</span>
              <span>{getStatusLabel(document.status)}</span>
              <span>v{document.version}</span>
              <span>{formatAppDateTime(document.updated_at)}</span>
              <span className={styles.rowActions}>
                <button
                  type="button"
                  title="重建索引"
                  onClick={() => handleReindexDocument(document.id)}
                  disabled={!canManageSelectedKnowledgeBase}
                >
                  <RefreshCw size={15} aria-hidden="true" />
                </button>
                {document.status === 'active' ? (
                  <button
                    type="button"
                    title="停用文档"
                    onClick={() => handleUpdateDocumentStatus(document.id, 'disabled')}
                    disabled={!canManageSelectedKnowledgeBase}
                  >
                    停用
                  </button>
                ) : (
                  <button
                    type="button"
                    title="启用文档"
                    onClick={() => handleUpdateDocumentStatus(document.id, 'active')}
                    disabled={!canManageSelectedKnowledgeBase}
                  >
                    启用
                  </button>
                )}
                <button
                  type="button"
                  title="归档文档"
                  onClick={() => handleUpdateDocumentStatus(document.id, 'archived')}
                  disabled={!canManageSelectedKnowledgeBase || document.status === 'archived'}
                >
                  归档
                </button>
                <button
                  type="button"
                  title="删除文档"
                  onClick={() => handleDeleteDocument(document.id)}
                  disabled={!canDeleteSelectedKnowledgeBase}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              </span>
            </div>
          ))}
          {!loadingDocs && documents.length === 0 ? (
            <div className={styles.emptyState}>当前知识库还没有文档</div>
          ) : null}
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2>检索预览</h2>
          <span>Evidence Artifact</span>
        </div>

        <form className={styles.searchForm} onSubmit={handleSearch}>
          <div className={styles.searchBox}>
            <Search size={17} aria-hidden="true" />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="输入要验证或引用的问题"
            />
          </div>
          <div className={styles.scopeToggles}>
            {(['workspace', 'personal'] as KnowledgeScope[]).map((scope) => (
              <label key={scope}>
                <input
                  type="checkbox"
                  checked={searchScopes.includes(scope)}
                  onChange={() => toggleSearchScope(scope)}
                />
                {scopeLabels[scope]}
              </label>
            ))}
          </div>
          <button className={styles.primaryButton} type="submit" disabled={isSearching}>
            {isSearching ? <Loader2 size={16} className={styles.spin} aria-hidden="true" /> : null}
            检索
          </button>
        </form>

        {evidencePack ? (
          <div className={styles.evidenceList}>
            <div className={styles.evidenceSummary}>
              <strong>{evidencePack.chunks.length}</strong>
              <span>条命中 / {evidencePack.conflicts.length} 条冲突 / {evidencePack.unverified_points.length} 个未验证点</span>
            </div>
            {evidencePack.chunks.map((chunk) => (
              <article key={chunk.chunk_id} className={styles.evidenceItem}>
                <header>
                  <strong>{chunk.document_name}</strong>
                  <span>{scopeLabels[chunk.scope]} / {chunk.score.toFixed(3)}</span>
                </header>
                <p>{chunk.content}</p>
              </article>
            ))}
            {evidencePack.chunks.length === 0 ? (
              <div className={styles.emptyState}>未检索到满足阈值的证据</div>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
