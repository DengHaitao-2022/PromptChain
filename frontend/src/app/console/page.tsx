'use client';

/**
 * 控制台 Dashboard 页面
 */

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
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
    const { workspace, hasPermission } = useAuth();
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        async function fetchDashboard() {
            if (!workspace) return;

            try {
                const response = await fetch(`${API_BASE}/admin/dashboard`, {
                    credentials: 'include',
                });

                if (response.ok) {
                    const result = await response.json();
                    setData(result);
                } else {
                    setError('加载数据失败');
                }
            } catch (err) {
                setError('网络错误');
            } finally {
                setLoading(false);
            }
        }

        fetchDashboard();
    }, [workspace]);

    if (loading) {
        return (
            <div className={styles.loading}>
                <div className={styles.spinner} />
            </div>
        );
    }

    if (error) {
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
            <p className={styles.subtitle}>欢迎回来，这是您的工作空间概览</p>

            {/* 统计卡片 */}
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

            {/* 快捷操作 */}
            <div className={styles.section}>
                <h2 className={styles.sectionTitle}>快捷操作</h2>
                <div className={styles.quickActions}>
                    <a href="/console/workflows" className={styles.actionCard}>
                        <span className={styles.actionIcon}>⚡</span>
                        <span className={styles.actionLabel}>管理工作流</span>
                    </a>
                    <a href="/console/runs" className={styles.actionCard}>
                        <span className={styles.actionIcon}>📋</span>
                        <span className={styles.actionLabel}>查看运行记录</span>
                    </a>
                    {hasPermission('member', 'manage') && (
                        <a href="/console/settings/members" className={styles.actionCard}>
                            <span className={styles.actionIcon}>👥</span>
                            <span className={styles.actionLabel}>成员管理</span>
                        </a>
                    )}
                </div>
            </div>

            {/* 最近运行 */}
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
        </div>
    );
}
