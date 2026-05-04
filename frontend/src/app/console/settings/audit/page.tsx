'use client';

/**
 * 审计日志页面
 */

import { Fragment, type FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCw, RotateCcw, Search, ShieldCheck } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { auditLogApi, type AuditLogEntry } from '@/lib/api';
import styles from '../settings.module.css';

const PAGE_SIZE = 20;

type AuditFilters = {
  action: string;
  outcome: string;
  userId: string;
  targetType: string;
  targetId: string;
  requestId: string;
  startTime: string;
  endTime: string;
};

const emptyFilters: AuditFilters = {
  action: '',
  outcome: '',
  userId: '',
  targetType: '',
  targetId: '',
  requestId: '',
  startTime: '',
  endTime: '',
};

const actionLabels: Record<string, string> = {
  'user.login': '用户登录',
  'user.logout': '用户登出',
  'user.register': '用户注册',
  'user.update': '用户更新',
  'user.password_reset': '密码重置',
  'workspace.create': '创建工作空间',
  'workspace.update': '更新工作空间',
  'workspace.switch': '切换工作空间',
  'workspace.member_invite': '邀请成员',
  'workspace.member_accept': '接受邀请',
  'workspace.member_remove': '移除成员',
  'workspace.member_role_change': '修改成员角色',
  'workflow.create': '创建工作流',
  'workflow.update': '保存工作流',
  'workflow.delete': '删除工作流',
  'workflow.publish': '发布工作流',
  'workflow.restore': '恢复版本',
  'workflow.run': '运行工作流',
  'workflow.pause': '暂停工作流',
  'workflow.resume': '恢复工作流',
  'workflow.approve': '处理审批',
  'workflow.clarify': '提交澄清',
  'workflow.rerun': '重跑工作流',
  'model_provider.create': '添加模型供应商',
  'model_provider.update': '更新模型供应商',
  'model_provider.delete': '删除模型供应商',
  'secret.create': '添加密钥',
  'secret.delete': '删除密钥',
  'api_key.create': '创建 API Key',
  'api_key.revoke': '撤销 API Key',
};

const outcomeLabels: Record<string, string> = {
  success: '成功',
  failure: '失败',
  unknown: '未知',
};

function getActionTone(action: string, outcome: string) {
  if (outcome === 'failure') {
    return styles.error;
  }
  if (action.startsWith('workflow.')) {
    return styles.info;
  }
  if (action.startsWith('workspace.member')) {
    return styles.warning;
  }
  if (action.endsWith('.delete') || action.endsWith('.revoke')) {
    return styles.error;
  }
  if (action.endsWith('.create') || action.endsWith('.login')) {
    return styles.success;
  }
  return styles.neutral;
}

function toIsoDateTime(value: string) {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}

function formatDateTime(value: string | null) {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(parsed);
}

function snapshotText(snapshot: Record<string, unknown>, fallback: string) {
  const displayName = snapshot.display_name;
  const email = snapshot.email;
  const name = snapshot.name;
  const id = snapshot.id;
  const value = displayName || email || name || id || fallback;
  return typeof value === 'string' ? value : fallback;
}

function compactId(value: string | null | undefined) {
  if (!value) {
    return '-';
  }
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function jsonPreview(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2);
}

export default function AuditPage() {
  const { hasPermission } = useAuth();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState<AuditFilters>(emptyFilters);
  const [draftFilters, setDraftFilters] = useState<AuditFilters>(emptyFilters);

  const canReadAudit = hasPermission('audit_log', 'read');
  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);
  const successCount = useMemo(
    () => logs.filter((log) => (log.outcome || 'success') === 'success').length,
    [logs],
  );
  const latestLog = logs[0];

  const fetchLogs = useCallback(async () => {
    if (!canReadAudit) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await auditLogApi.list({
        page,
        pageSize: PAGE_SIZE,
        action: filters.action || undefined,
        outcome: filters.outcome || undefined,
        userId: filters.userId || undefined,
        targetType: filters.targetType || undefined,
        targetId: filters.targetId || undefined,
        requestId: filters.requestId || undefined,
        startTime: toIsoDateTime(filters.startTime),
        endTime: toIsoDateTime(filters.endTime),
      });
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载审计日志失败');
    } finally {
      setLoading(false);
    }
  }, [canReadAudit, filters, page]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  function updateDraftFilter(key: keyof AuditFilters, value: string) {
    setDraftFilters((current) => ({ ...current, [key]: value }));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setFilters(draftFilters);
  }

  function resetFilters() {
    setDraftFilters(emptyFilters);
    setFilters(emptyFilters);
    setPage(1);
  }

  if (!canReadAudit) {
    return (
      <div className={styles.container}>
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <span className={styles.eyebrow}>Audit Stream</span>
            <h1 className={styles.title}>审计日志</h1>
            <p className={styles.subtitle}>您当前没有查看审计日志的权限，请联系管理员开放访问。</p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.eyebrow}>Audit Stream</span>
          <h1 className={styles.title}>审计日志</h1>
          <p className={styles.subtitle}>
            以结构化事件记录成员、配置、工作流与安全动作，保留请求链路、操作者快照和目标快照。
          </p>
        </div>

        <div className={styles.heroActions}>
          <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void fetchLogs()} type="button">
            <RefreshCw size={16} strokeWidth={2} />
            刷新日志
          </button>
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>记录总数</span>
            <span className={styles.summaryValue}>{total}</span>
            <span className={styles.summaryMeta}>匹配当前筛选条件的事件数量</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>当前页成功</span>
            <span className={styles.summaryValue}>{successCount}</span>
            <span className={styles.summaryMeta}>本页结果为成功的审计事件</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>最近事件</span>
            <span className={styles.summaryValue}>{latestLog ? actionLabels[latestLog.action] || latestLog.action : '-'}</span>
            <span className={styles.summaryMeta}>{latestLog ? formatDateTime(latestLog.created_at) : '暂无事件'}</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>页码</span>
            <span className={styles.summaryValue}>
              {page}/{pageCount}
            </span>
            <span className={styles.summaryMeta}>每页 {PAGE_SIZE} 条记录</span>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>筛选条件</h2>
            <p className={styles.sectionDescription}>按动作、结果、操作者、目标和请求链路定位审计事件。</p>
          </div>
        </div>

        <form className={styles.filterGrid} onSubmit={applyFilters}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>动作</span>
            <select className={styles.select} value={draftFilters.action} onChange={(event) => updateDraftFilter('action', event.target.value)}>
              <option value="">全部动作</option>
              {Object.entries(actionLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>结果</span>
            <select className={styles.select} value={draftFilters.outcome} onChange={(event) => updateDraftFilter('outcome', event.target.value)}>
              <option value="">全部结果</option>
              <option value="success">成功</option>
              <option value="failure">失败</option>
              <option value="unknown">未知</option>
            </select>
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>操作者 ID</span>
            <input className={styles.input} value={draftFilters.userId} onChange={(event) => updateDraftFilter('userId', event.target.value)} placeholder="user_id" />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>目标类型</span>
            <input className={styles.input} value={draftFilters.targetType} onChange={(event) => updateDraftFilter('targetType', event.target.value)} placeholder="workflow_run / user / secret" />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>目标 ID</span>
            <input className={styles.input} value={draftFilters.targetId} onChange={(event) => updateDraftFilter('targetId', event.target.value)} placeholder="target_id" />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>请求 ID</span>
            <input className={styles.input} value={draftFilters.requestId} onChange={(event) => updateDraftFilter('requestId', event.target.value)} placeholder="request_id / trace_id" />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>开始时间</span>
            <input className={styles.input} type="datetime-local" value={draftFilters.startTime} onChange={(event) => updateDraftFilter('startTime', event.target.value)} />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>结束时间</span>
            <input className={styles.input} type="datetime-local" value={draftFilters.endTime} onChange={(event) => updateDraftFilter('endTime', event.target.value)} />
          </label>
          <div className={styles.filterActions}>
            <button className={`${styles.button} ${styles.buttonSmall}`} type="submit">
              <Search size={16} strokeWidth={2} />
              应用筛选
            </button>
            <button className={`${styles.button} ${styles.buttonGhost} ${styles.buttonSmall}`} onClick={resetFilters} type="button">
              <RotateCcw size={16} strokeWidth={2} />
              清空
            </button>
          </div>
        </form>
      </section>

      {error ? (
        <div className={`${styles.notice} ${styles.noticeError}`} role="alert">
          {error}
        </div>
      ) : null}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>操作记录</h2>
            <p className={styles.sectionDescription}>事件详情包含请求链路、操作者快照、目标快照和脱敏后的结构化上下文。</p>
          </div>
          <div className={styles.metaRow}>
            <span className={`${styles.pill} ${styles.info}`}>
              <ShieldCheck size={14} strokeWidth={2} />
              结构化事件
            </span>
          </div>
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
          </div>
        ) : logs.length > 0 ? (
          <>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>操作</th>
                    <th>结果</th>
                    <th>操作者</th>
                    <th>目标</th>
                    <th>请求链路</th>
                    <th>来源</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <Fragment key={log.id}>
                      <tr>
                        <td>
                          <div className={styles.tableStack}>
                            <span className={`${styles.pill} ${getActionTone(log.action, log.outcome)}`}>
                              {actionLabels[log.action] || log.action}
                            </span>
                            <span className={styles.monoText}>{compactId(log.event_id)}</span>
                          </div>
                        </td>
                        <td>
                          <span className={`${styles.pill} ${log.outcome === 'failure' ? styles.error : styles.success}`}>
                            {outcomeLabels[log.outcome] || log.outcome || '成功'}
                          </span>
                        </td>
                        <td>
                          <div className={styles.tableStack}>
                            <span className={styles.tableStrong}>
                              {snapshotText(log.actor_snapshot, compactId(log.user_id))}
                            </span>
                            <span className={styles.tableMuted}>{compactId(log.user_id)}</span>
                          </div>
                        </td>
                        <td>
                          <div className={styles.tableStack}>
                            <span className={styles.tableStrong}>{log.target_type || '-'}</span>
                            <span className={styles.tableMuted}>
                              {snapshotText(log.target_snapshot, compactId(log.target_id))}
                            </span>
                          </div>
                        </td>
                        <td>
                          <div className={styles.tableStack}>
                            <span className={styles.monoText}>{compactId(log.request_id || log.trace_id)}</span>
                            <span className={styles.tableMuted}>{log.event_category || 'api'} / {log.event_type || 'info'}</span>
                          </div>
                        </td>
                        <td className={styles.tableMuted}>{log.ip_address || '-'}</td>
                        <td className={styles.tableMuted}>{formatDateTime(log.created_at)}</td>
                      </tr>
                      <tr className={styles.detailsRow}>
                        <td colSpan={7}>
                          <details className={styles.auditDetails}>
                            <summary>查看审计详情</summary>
                            <div className={styles.detailGrid}>
                              <div>
                                <span className={styles.detailTitle}>事件详情</span>
                                <pre className={styles.codeBlock}>{jsonPreview(log.detail)}</pre>
                              </div>
                              <div>
                                <span className={styles.detailTitle}>操作者快照</span>
                                <pre className={styles.codeBlock}>{jsonPreview(log.actor_snapshot)}</pre>
                              </div>
                              <div>
                                <span className={styles.detailTitle}>目标快照</span>
                                <pre className={styles.codeBlock}>{jsonPreview(log.target_snapshot)}</pre>
                              </div>
                              <div>
                                <span className={styles.detailTitle}>请求上下文</span>
                                <pre className={styles.codeBlock}>
                                  {jsonPreview({
                                    request_id: log.request_id,
                                    trace_id: log.trace_id,
                                    span_id: log.span_id,
                                    user_agent: log.user_agent,
                                    metadata: log.metadata,
                                    schema_version: log.schema_version,
                                  })}
                                </pre>
                              </div>
                            </div>
                          </details>
                        </td>
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            <div className={styles.pagination}>
              <button
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page === 1}
                className={`${styles.button} ${styles.buttonGhost} ${styles.buttonSmall}`}
                type="button"
              >
                <ChevronLeft size={16} strokeWidth={2} />
                上一页
              </button>
              <span className={styles.pageIndicator}>
                第 {page} 页 / 共 {pageCount} 页
              </span>
              <button
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                disabled={page >= pageCount}
                className={`${styles.button} ${styles.buttonGhost} ${styles.buttonSmall}`}
                type="button"
              >
                下一页
                <ChevronRight size={16} strokeWidth={2} />
              </button>
            </div>
          </>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>暂无审计日志</div>
            <div className={styles.emptyText}>当成员、配置、工作流或安全动作发生后，这里会按时间顺序持续累积记录。</div>
          </div>
        )}
      </section>
    </div>
  );
}
