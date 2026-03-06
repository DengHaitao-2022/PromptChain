'use client';

/**
 * 运行记录列表页面
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import styles from './runs.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

interface WorkflowRun {
    id: string;
    workflow_name: string;
    status: string;
    current_node: string | null;
    user_input: string;
    started_at: string;
    completed_at: string | null;
    total_duration_ms: number | null;
}

export default function RunsPage() {
    const [runs, setRuns] = useState<WorkflowRun[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        async function fetchRuns() {
            try {
                // 获取所有工作流运行记录
                // 这里需要新的 API 端点，暂时模拟
                setRuns([]);
            } catch (err) {
                setError('加载失败');
            } finally {
                setLoading(false);
            }
        }

        fetchRuns();
    }, []);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h1 className={styles.title}>运行记录</h1>
                <p className={styles.subtitle}>查看所有工作流运行历史</p>
            </div>

            {loading ? (
                <div className={styles.loading}>
                    <div className={styles.spinner} />
                </div>
            ) : error ? (
                <div className={styles.error}>{error}</div>
            ) : runs.length > 0 ? (
                <div className={styles.tableContainer}>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>工作流</th>
                                <th>状态</th>
                                <th>当前节点</th>
                                <th>开始时间</th>
                                <th>耗时</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {runs.map((run) => (
                                <tr key={run.id}>
                                    <td>
                                        <div className={styles.workflowName}>{run.workflow_name}</div>
                                        <div className={styles.userInput}>{run.user_input?.slice(0, 50)}...</div>
                                    </td>
                                    <td>
                                        <span className={`${styles.status} ${styles[run.status]}`}>
                                            {run.status === 'completed' ? '完成' :
                                                run.status === 'failed' ? '失败' :
                                                    run.status === 'running' ? '运行中' : run.status}
                                        </span>
                                    </td>
                                    <td>{run.current_node || '-'}</td>
                                    <td>{new Date(run.started_at).toLocaleString()}</td>
                                    <td>
                                        {run.total_duration_ms
                                            ? `${(run.total_duration_ms / 1000).toFixed(1)}s`
                                            : '-'}
                                    </td>
                                    <td>
                                        <Link href={`/workflow/${run.id}`} className={styles.viewLink}>
                                            查看详情
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className={styles.empty}>
                    <div className={styles.emptyIcon}>📋</div>
                    <h3>暂无运行记录</h3>
                    <p>启动工作流后，运行记录将显示在这里</p>
                </div>
            )}
        </div>
    );
}
