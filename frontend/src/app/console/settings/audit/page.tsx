'use client';

/**
 * 审计日志页面
 */

import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
const PAGE_SIZE = 20;

interface AuditLog {
  id: string;
  user_id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

const actionLabels: Record<string, string> = {
  'user.login': '用户登录',
  'user.logout': '用户登出',
  'user.register': '用户注册',
  'workspace.create': '创建工作空间',
  'workspace.member_invite': '邀请成员',
  'workspace.member_remove': '移除成员',
  'workspace.member_role_change': '修改成员角色',
  'workflow.create': '创建工作流',
  'workflow.update': '更新工作流',
  'workflow.delete': '删除工作流',
  'workflow.run': '运行工作流',
  'model_provider.create': '添加模型供应商',
  'model_provider.update': '更新模型供应商',
  'model_provider.delete': '删除模型供应商',
  'secret.create': '添加密钥',
  'secret.delete': '删除密钥',
  'api_key.create': '创建 API Key',
  'api_key.revoke': '撤销 API Key',
};

function getActionTone(action: string) {
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

export default function AuditPage() {
  const { hasPermission } = useAuth();
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');

  const canReadAudit = hasPermission('audit_log', 'read');

  async function fetchLogs() {
    setLoading(true);
    setError('');

    try {
      const response = await fetch(
        `${API_BASE}/admin/audit-logs?page=${page}&page_size=${PAGE_SIZE}`,
        { credentials: 'include' },
      );

      if (!response.ok) {
        throw new Error('加载审计日志失败');
      }

      const data = (await response.json()) as { logs?: AuditLog[]; total?: number };
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载审计日志失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canReadAudit) {
      setLoading(false);
      return;
    }

    void fetchLogs();
  }, [canReadAudit, page]);

  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

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
            汇总系统关键操作、成员动作与工作流变更，便于追踪配置变动和排查异常路径。
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
            <span className={styles.summaryMeta}>后端累计返回的审计事件总量</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>当前页</span>
            <span className={styles.summaryValue}>{page}</span>
            <span className={styles.summaryMeta}>便于逐页回看最近的操作历史</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>总页数</span>
            <span className={styles.summaryValue}>{pageCount}</span>
            <span className={styles.summaryMeta}>按每页 {PAGE_SIZE} 条记录进行分页</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>本页载入</span>
            <span className={styles.summaryValue}>{logs.length}</span>
            <span className={styles.summaryMeta}>当前响应中实际返回的日志条数</span>
          </div>
        </div>
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
            <p className={styles.sectionDescription}>
              展示操作名称、目标对象、来源 IP 与时间戳。颜色标签仅用于帮助快速浏览，不改变审计语义。
            </p>
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
                    <th>目标</th>
                    <th>IP 地址</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td>
                        <span className={`${styles.pill} ${getActionTone(log.action)}`}>
                          {actionLabels[log.action] || log.action}
                        </span>
                      </td>
                      <td className={styles.tableMuted}>{log.target_type ? `${log.target_type}` : '-'}</td>
                      <td className={styles.tableMuted}>{log.ip_address || '-'}</td>
                      <td className={styles.tableMuted}>
                        {new Date(log.created_at).toLocaleString('zh-CN')}
                      </td>
                    </tr>
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
            <div className={styles.emptyText}>当成员操作、工作流变更或安全动作发生后，这里会按时间顺序持续累积记录。</div>
          </div>
        )}
      </section>
    </div>
  );
}
