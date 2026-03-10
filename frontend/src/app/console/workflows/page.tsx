'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

import { useAuth } from '@/contexts/AuthContext';
import {
    useWorkflowApi,
    type WorkflowDefinition,
} from '@/components/WorkflowEditor/hooks/useWorkflowApi';
import styles from './workflows.module.css';

export default function WorkflowsPage() {
    const { hasPermission } = useAuth();
    const { listWorkflows } = useWorkflowApi();
    const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;

        async function fetchWorkflows() {
            setLoading(true);
            setError(null);

            try {
                const data = await listWorkflows();
                if (!cancelled) {
                    setWorkflows(data.workflows);
                }
            } catch (requestError) {
                if (!cancelled) {
                    setError(
                        requestError instanceof Error
                            ? requestError.message
                            : '加载工作流列表失败',
                    );
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        void fetchWorkflows();
        return () => {
            cancelled = true;
        };
    }, [listWorkflows]);

    const canCreate = hasPermission('workflow', 'create');
    const canEdit = hasPermission('workflow', 'update');

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div>
                    <h1 className={styles.title}>工作流</h1>
                    <p className={styles.subtitle}>
                        统一管理草稿、已发布版本和普通用户可运行状态。
                    </p>
                </div>
                {canCreate ? (
                    <Link href="/console/workflows/edit" className={styles.createButton}>
                        + 创建工作流
                    </Link>
                ) : null}
            </div>

            {error ? <div className={styles.errorBanner}>{error}</div> : null}

            {loading ? (
                <div className={styles.loading}>
                    <div className={styles.spinner} />
                    <span>正在加载工作流列表...</span>
                </div>
            ) : workflows.length > 0 ? (
                <div className={styles.workflowGrid}>
                    {workflows.map((workflow) => (
                        <article key={workflow.id} className={styles.workflowCard}>
                            <div className={styles.cardHeader}>
                                <div>
                                    <h3>{workflow.name}</h3>
                                    <p>{workflow.description || '暂无说明，建议补充工作流用途。'}</p>
                                </div>
                                <div className={styles.badges}>
                                    <span
                                        className={`${styles.badge} ${
                                            workflow.is_published ? styles.published : styles.draft
                                        }`}
                                    >
                                        {workflow.is_published ? '已发布' : '草稿'}
                                    </span>
                                    <span className={`${styles.badge} ${styles.version}`}>
                                        当前草稿 v{workflow.version}
                                    </span>
                                    {workflow.published_version ? (
                                        <>
                                            <span className={`${styles.badge} ${styles.runnable}`}>
                                                可运行 v{workflow.published_version}
                                            </span>
                                            {workflow.version !== workflow.published_version && (
                                                <span className={`${styles.badge} ${styles.draft}`}>
                                                    有未发布变更
                                                </span>
                                            )}
                                        </>
                                    ) : (
                                        <span className={`${styles.badge} ${styles.pending}`}>
                                            需发布后运行
                                        </span>
                                    )}
                                </div>
                            </div>

                            <dl className={styles.metaList}>
                                <div>
                                    <dt>最近更新时间</dt>
                                    <dd>{formatDateTime(workflow.updated_at)}</dd>
                                </div>
                                <div>
                                    <dt>最近发布时间</dt>
                                    <dd>{workflow.published_at ? formatDateTime(workflow.published_at) : '尚未发布'}</dd>
                                </div>
                            </dl>

                            <div className={styles.cardFooter}>
                                <span className={styles.runState}>
                                    {workflow.is_published
                                        ? '普通用户可见并可运行'
                                        : '仅设计者可见，普通用户不可运行'}
                                </span>
                                {canEdit ? (
                                    <Link
                                        href={`/console/workflows/edit?id=${workflow.id}`}
                                        className={styles.editLink}
                                    >
                                        编辑与发布
                                    </Link>
                                ) : null}
                            </div>
                        </article>
                    ))}
                </div>
            ) : (
                <div className={styles.empty}>
                    <div className={styles.emptyIcon}>流程</div>
                    <h3>还没有工作流</h3>
                    <p>
                        {canCreate
                            ? '从一个草稿开始，先保存、再校验、最后显式发布。'
                            : '当前工作空间还没有可见的已发布工作流。'}
                    </p>
                    {canCreate ? (
                        <Link href="/console/workflows/edit" className={styles.createButton}>
                            + 创建第一个工作流
                        </Link>
                    ) : null}
                </div>
            )}
        </div>
    );
}

function formatDateTime(value?: string): string {
    if (!value) {
        return '暂无记录';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    }).format(date);
}
