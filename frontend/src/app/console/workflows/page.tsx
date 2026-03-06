'use client';

/**
 * 工作流列表页面
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import styles from './workflows.module.css';

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

export default function WorkflowsPage() {
    const { hasPermission } = useAuth();
    const [workflows, setWorkflows] = useState<WorkflowRun[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchWorkflows() {
            try {
                // 这里暂时使用现有的工作流运行 API
                // 后续可添加专门的工作流定义 API
                const response = await fetch(`${API_BASE}/trace`, {
                    credentials: 'include',
                });

                if (response.ok) {
                    // 模拟数据，实际应该从后端获取
                    setWorkflows([]);
                }
            } catch (err) {
                console.error('加载失败', err);
            } finally {
                setLoading(false);
            }
        }

        fetchWorkflows();
    }, []);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div>
                    <h1 className={styles.title}>工作流</h1>
                    <p className={styles.subtitle}>管理您的自动化工作流</p>
                </div>
                {hasPermission('workflow', 'create') && (
                    <button className={styles.createButton}>
                        + 创建工作流
                    </button>
                )}
            </div>

            {loading ? (
                <div className={styles.loading}>
                    <div className={styles.spinner} />
                </div>
            ) : workflows.length > 0 ? (
                <div className={styles.workflowGrid}>
                    {workflows.map((workflow) => (
                        <div key={workflow.id} className={styles.workflowCard}>
                            <h3>{workflow.workflow_name}</h3>
                            <p>{workflow.user_input?.slice(0, 100)}...</p>
                            <div className={styles.cardFooter}>
                                <span className={`${styles.status} ${styles[workflow.status]}`}>
                                    {workflow.status}
                                </span>
                                <Link href={`/console/runs/${workflow.id}`}>
                                    查看详情 →
                                </Link>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className={styles.empty}>
                    <div className={styles.emptyIcon}>⚡</div>
                    <h3>还没有工作流</h3>
                    <p>创建您的第一个工作流开始自动化</p>
                    {hasPermission('workflow', 'create') && (
                        <button className={styles.createButton}>
                            + 创建工作流
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
