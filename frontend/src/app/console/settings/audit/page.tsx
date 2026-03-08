'use client';

/**
 * 审计日志页面
 */

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

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

export default function AuditPage() {
    const { hasPermission } = useAuth();
    const [logs, setLogs] = useState<AuditLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const canReadAuditLogs = hasPermission('audit_log', 'read');

    useEffect(() => {
        if (!canReadAuditLogs) {
            setLoading(false);
            return;
        }

        void fetchLogs();
    }, [page, canReadAuditLogs]);

    async function fetchLogs() {
        try {
            const response = await fetch(
                `${API_BASE}/admin/audit-logs?page=${page}&page_size=20`,
                { credentials: 'include' }
            );
            if (response.ok) {
                const data = await response.json();
                setLogs(data.logs || []);
                setTotal(data.total || 0);
            }
        } catch (err) {
            console.error('加载失败', err);
        } finally {
            setLoading(false);
        }
    }

    if (!canReadAuditLogs) {
        return (
            <div className={styles.container}>
                <h1 className={styles.title}>审计日志</h1>
                <p className={styles.subtitle}>暂无访问权限</p>
                <div className={styles.empty}>
                    <p>您当前的账号角色无法查看此页面配置。</p>
                    <p style={{ fontSize: 14, marginTop: 8 }}>
                        如需访问，请联系工作空间管理员为您分配权限。
                    </p>
                    <a href="/console" className={styles.button} style={{ marginTop: 16, display: 'inline-flex' }}>
                        返回控制台首页
                    </a>
                </div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <h1 className={styles.title}>审计日志</h1>
            <p className={styles.subtitle}>查看系统操作记录</p>

            <div className={styles.section}>
                {loading ? (
                    <div className={styles.loading}><div className={styles.spinner} /></div>
                ) : logs.length > 0 ? (
                    <>
                        <div style={{
                            background: 'white',
                            borderRadius: 12,
                            overflow: 'hidden',
                            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)'
                        }}>
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
                                                <span style={{
                                                    display: 'inline-block',
                                                    padding: '4px 10px',
                                                    borderRadius: 6,
                                                    fontSize: 12,
                                                    background: '#f3f4f6',
                                                }}>
                                                    {actionLabels[log.action] || log.action}
                                                </span>
                                            </td>
                                            <td style={{ color: '#6b7280' }}>
                                                {log.target_type ? `${log.target_type}` : '-'}
                                            </td>
                                            <td style={{ color: '#6b7280' }}>
                                                {log.ip_address || '-'}
                                            </td>
                                            <td style={{ color: '#6b7280' }}>
                                                {new Date(log.created_at).toLocaleString()}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* 分页 */}
                        <div style={{
                            display: 'flex',
                            justifyContent: 'center',
                            gap: 8,
                            marginTop: 24
                        }}>
                            <button
                                onClick={() => setPage(p => Math.max(1, p - 1))}
                                disabled={page === 1}
                                className={styles.button}
                                style={{ opacity: page === 1 ? 0.5 : 1 }}
                            >
                                上一页
                            </button>
                            <span style={{ padding: '10px 14px', color: '#6b7280' }}>
                                第 {page} 页 / 共 {Math.ceil(total / 20)} 页
                            </span>
                            <button
                                onClick={() => setPage(p => p + 1)}
                                disabled={page >= Math.ceil(total / 20)}
                                className={styles.button}
                                style={{ opacity: page >= Math.ceil(total / 20) ? 0.5 : 1 }}
                            >
                                下一页
                            </button>
                        </div>
                    </>
                ) : (
                    <div className={styles.empty}>
                        <p>暂无审计日志</p>
                    </div>
                )}
            </div>
        </div>
    );
}
