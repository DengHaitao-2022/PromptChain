'use client';

/**
 * 控制台 Dashboard 页面
 */

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getRoleLabel } from '@/lib/auth';
import styles from './dashboard.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

interface DashboardData {
    today_runs: number;
    today_success_runs: number;
    today_failed_runs: number;
    today_avg_duration_ms: number;
    total_runs: number;
    total_members: number;
    recent_runs: Array<{
        id: string;
        workflow_name: string;
        status: string;
        started_at: string;
        duration_ms: number;
    }>;
}

export default function DashboardPage() {
    const { workspace, role, hasPermission } = useAuth();
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const canViewAdminDashboard = hasPermission('member', 'read');
    const canViewWorkflows = hasPermission('workflow', 'read');
    const canViewRuns = hasPermission('workflow_run', 'read');

    useEffect(() => {
        async function fetchDashboard() {
            setLoading(true);
            setError('');

            if (!workspace) {
                setData(null);
                setLoading(false);
                return;
            }

            if (!canViewAdminDashboard) {
                setData(null);
                setLoading(false);
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/admin/dashboard`, {
                    credentials: 'include',
                });

                if (response.ok) {
                    const result = await response.json();
                    setData(result);
                } else {
                    setError('加载管理员概览失败');
                }
            } catch {
                setError('网络错误');
            } finally {
                setLoading(false);
            }
        }

        void fetchDashboard();
    }, [workspace, canViewAdminDashboard]);

    if (loading) {
        return (
            <div className={styles.loading}>
                <div className={styles.spinner} />
            </div>
        );
    }

    if (canViewAdminDashboard && error) {
        return (
            <div className={styles.error}>
                <p>{error}</p>
            </div>
        );
    }

    const failureRate = data && data.today_runs > 0
        ? ((data.today_failed_runs / data.today_runs) * 100).toFixed(1)
        : '0';

    return (
        <div className={styles.container}>
            <h1 className={styles.title}>工作台</h1>
            <p className={styles.subtitle}>
                {canViewAdminDashboard
                    ? '欢迎回来，这是当前工作空间的管理员概览'
                    : '欢迎回来，这里展示你在当前工作空间的可用入口'}
            </p>

            {!canViewAdminDashboard && (
                <div className={styles.summaryGrid}>
                    <div className={styles.summaryCard}>
                        <div className={styles.summaryLabel}>当前工作空间</div>
                        <div className={styles.summaryValue}>{workspace?.name || '未选择'}</div>
                    </div>

                    <div className={styles.summaryCard}>
                        <div className={styles.summaryLabel}>当前角色</div>
                        <div className={styles.summaryValue}>{getRoleLabel(role)}</div>
                    </div>

                    <div className={styles.summaryCard}>
                        <div className={styles.summaryLabel}>权限提示</div>
                        <div className={styles.summaryText}>
                            {role === 'editor'
                                ? '可维护自己创建的工作流，并查看当前工作空间中的运行记录。'
                                : '可运行已发布工作流，并查看当前工作空间中的运行记录。'}
                        </div>
                    </div>
                </div>
            )}

            {canViewAdminDashboard && (
                <div className={styles.statsGrid}>
                    <div className={styles.statCard}>
                        <div className={styles.statIcon}>📊</div>
                        <div className={styles.statContent}>
                            <div className={styles.statValue}>{data?.today_runs || 0}</div>
                            <div className={styles.statLabel}>今日运行</div>
                        </div>
                    </div>

                    <div className={styles.statCard}>
                        <div className={styles.statIcon}>✅</div>
                        <div className={styles.statContent}>
                            <div className={styles.statValue}>{data?.today_success_runs || 0}</div>
                            <div className={styles.statLabel}>成功运行</div>
                        </div>
                    </div>

                    <div className={styles.statCard}>
                        <div className={styles.statIcon}>❌</div>
                        <div className={styles.statContent}>
                            <div className={styles.statValue}>{failureRate}%</div>
                            <div className={styles.statLabel}>失败率</div>
                        </div>
                    </div>

                    <div className={styles.statCard}>
                        <div className={styles.statIcon}>⏱️</div>
                        <div className={styles.statContent}>
                            <div className={styles.statValue}>
                                {data?.today_avg_duration_ms
                                    ? `${(data.today_avg_duration_ms / 1000).toFixed(1)}s`
                                    : '0s'}
                            </div>
                            <div className={styles.statLabel}>平均耗时</div>
                        </div>
                    </div>
                </div>
            )}

            <div className={styles.section}>
                <h2 className={styles.sectionTitle}>快捷操作</h2>
                <div className={styles.quickActions}>
                    {canViewWorkflows && (
                        <a href="/console/workflows" className={styles.actionCard}>
                            <span className={styles.actionIcon}>⚡</span>
                            <span className={styles.actionLabel}>
                                {role === 'viewer' ? '查看工作流' : '管理工作流'}
                            </span>
                        </a>
                    )}
                    {canViewRuns && (
                        <a href="/console/runs" className={styles.actionCard}>
                            <span className={styles.actionIcon}>📋</span>
                            <span className={styles.actionLabel}>查看运行记录</span>
                        </a>
                    )}
                    {hasPermission('member', 'manage') && (
                        <a href="/console/settings/members" className={styles.actionCard}>
                            <span className={styles.actionIcon}>👥</span>
                            <span className={styles.actionLabel}>成员管理</span>
                        </a>
                    )}
                </div>
            </div>

            {!canViewAdminDashboard && (
                <div className={styles.hintCard}>
                    <h2 className={styles.sectionTitle}>当前边界</h2>
                    <p className={styles.summaryText}>
                        成员管理、模型配置、密钥管理和审计日志只对管理员开放。若你需要这些能力，请联系当前工作空间拥有者或管理员调整角色。
                    </p>
                </div>
            )}

            {canViewAdminDashboard && (
                <div className={styles.section}>
                    <h2 className={styles.sectionTitle}>最近运行</h2>
                    {data?.recent_runs && data.recent_runs.length > 0 ? (
                        <div className={styles.recentRuns}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>工作流</th>
                                        <th>状态</th>
                                        <th>开始时间</th>
                                        <th>耗时</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.recent_runs.map((run) => (
                                        <tr key={run.id}>
                                            <td>{run.workflow_name}</td>
                                            <td>
                                                <span className={`${styles.status} ${styles[run.status]}`}>
                                                    {run.status === 'completed' ? '完成' :
                                                        run.status === 'failed' ? '失败' :
                                                            run.status === 'running' ? '运行中' : run.status}
                                                </span>
                                            </td>
                                            <td>{new Date(run.started_at).toLocaleString()}</td>
                                            <td>{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <div className={styles.empty}>
                            <p>暂无运行记录</p>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
