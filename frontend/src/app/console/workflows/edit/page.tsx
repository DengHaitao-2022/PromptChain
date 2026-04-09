'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import type { Edge, Node } from '@xyflow/react';

import WorkflowEditor from '@/components/WorkflowEditor';
import { useAuth } from '@/contexts/AuthContext';
import {
    useWorkflowApi,
    type ValidationResult,
    type WorkflowDefinition,
} from '@/components/WorkflowEditor/hooks/useWorkflowApi';
import { serializeNodes, serializeEdges } from '@/components/WorkflowEditor/domain/serializer';
import { deserializeNodes, deserializeEdges } from '@/components/WorkflowEditor/domain/deserializer';
import styles from './page.module.css';

export default function WorkflowEditPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const draftId = searchParams.get('id');
    const {
        getWorkflowDefinition,
        createWorkflow,
        saveWorkflowDefinition,
        validateWorkflow,
        publishWorkflow,
    } = useWorkflowApi();
    const { isAuthenticated, isLoading, hasPermission } = useAuth();

    const loadedIdRef = useRef<string | null>(null);

    const canCreate = hasPermission('workflow', 'create');
    const canUpdate = hasPermission('workflow', 'update');
    const canAccessPage = draftId ? canUpdate : canCreate;

    const [workflowId, setWorkflowId] = useState<string | undefined>(draftId ?? undefined);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [initialNodes, setInitialNodes] = useState<Node[] | undefined>(undefined);
    const [initialEdges, setInitialEdges] = useState<Edge[] | undefined>(undefined);
    const [pageLoading, setPageLoading] = useState(Boolean(draftId));
    const [isSaving, setIsSaving] = useState(false);
    const [isValidating, setIsValidating] = useState(false);
    const [isPublishing, setIsPublishing] = useState(false);
    const [statusMessage, setStatusMessage] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [validation, setValidation] = useState<ValidationResult | null>(null);
    const [isPublished, setIsPublished] = useState(false);
    const [currentVersion, setCurrentVersion] = useState<number>(1);
    const [publishedVersion, setPublishedVersion] = useState<number | null>(null);
    const [publishedAt, setPublishedAt] = useState<string | null>(null);

    const applyWorkflowMeta = useCallback((workflow: WorkflowDefinition) => {
        setWorkflowId(workflow.id);
        setName(workflow.name ?? '');
        setDescription(workflow.description ?? '');
        setIsPublished(Boolean(workflow.is_published));
        setCurrentVersion(workflow.version ?? 1);
        setPublishedVersion(workflow.published_version ?? null);
        setPublishedAt(workflow.published_at ?? null);
    }, []);

    const applyWorkflowAll = useCallback((workflow: WorkflowDefinition) => {
        applyWorkflowMeta(workflow);
        setInitialNodes(deserializeNodes(workflow.nodes));
        setInitialEdges(deserializeEdges(workflow.edges));
    }, [applyWorkflowMeta]);

    useEffect(() => {
        if (isLoading || !isAuthenticated || !canAccessPage) {
            return;
        }

        let cancelled = false;

        async function loadWorkflow(currentId: string) {
            if (loadedIdRef.current === currentId) {
                return;
            }

            setPageLoading(true);
            setLoadError(null);

            try {
                const workflow = await getWorkflowDefinition(currentId);
                if (!cancelled) {
                    loadedIdRef.current = currentId;
                    applyWorkflowAll(workflow);
                }
            } catch (error) {
                if (!cancelled) {
                    setLoadError(
                        error instanceof Error ? error.message : '加载工作流草稿失败',
                    );
                }
            } finally {
                if (!cancelled) {
                    setPageLoading(false);
                }
            }
        }

        if (draftId) {
            if (loadedIdRef.current !== draftId) {
                void loadWorkflow(draftId);
            }
            return () => {
                cancelled = true;
            };
        }

        loadedIdRef.current = null;
        setWorkflowId(undefined);
        setName('');
        setDescription('');
        setInitialNodes(undefined);
        setInitialEdges(undefined);
        setIsPublished(false);
        setPublishedVersion(null);
        setPublishedAt(null);
        setValidation(null);
        setLoadError(null);
        setActionError(null);
        setPageLoading(false);

        return () => {
            cancelled = true;
        };
    }, [applyWorkflowAll, isLoading, draftId, getWorkflowDefinition, canAccessPage, isAuthenticated]);

    const ensureWorkflowName = useCallback(() => {
        if (name.trim()) {
            return true;
        }

        setActionError('请先填写工作流名称，再执行保存或发布。');
        return false;
    }, [name]);

    const persistDraft = useCallback(
        async (nodes: Node[], edges: Edge[]) => {
            if (!ensureWorkflowName()) {
                return null;
            }

            const payload = {
                name: name.trim(),
                description: description.trim(),
                nodes: serializeNodes(nodes),
                edges: serializeEdges(edges),
                change_log: '编辑器保存草稿',
            };

            const workflow = workflowId
                ? await saveWorkflowDefinition(workflowId, payload)
                : await createWorkflow(payload);

            applyWorkflowMeta(workflow);
            if (!workflowId) {
                loadedIdRef.current = workflow.id;
                router.replace(`/console/workflows/edit?id=${workflow.id}`);
            }
            return workflow;
        },
        [
            applyWorkflowMeta,
            createWorkflow,
            description,
            ensureWorkflowName,
            name,
            router,
            saveWorkflowDefinition,
            workflowId,
        ],
    );

    const handleSave = useCallback(
        async (nodes: Node[], edges: Edge[]) => {
            setIsSaving(true);
            setActionError(null);
            setStatusMessage(null);

            try {
                const workflow = await persistDraft(nodes, edges);
                if (!workflow) {
                    return;
                }
                setStatusMessage('草稿已保存，可继续校验或发布。');
            } catch (error) {
                setActionError(error instanceof Error ? error.message : '保存草稿失败');
            } finally {
                setIsSaving(false);
            }
        },
        [persistDraft],
    );

    const handleValidate = useCallback(
        async (nodes: Node[], edges: Edge[]) => {
            setIsValidating(true);
            setActionError(null);
            setStatusMessage(null);

            try {
                const workflow = await persistDraft(nodes, edges);
                if (!workflow) {
                    return;
                }

                const result = await validateWorkflow(workflow.id, 'publish');
                setValidation(result);
                setStatusMessage(
                    result.is_valid
                        ? '校验通过，可以直接发布。'
                        : '校验未通过，请先处理阻塞问题。',
                );
            } catch (error) {
                setActionError(error instanceof Error ? error.message : '校验工作流失败');
            } finally {
                setIsValidating(false);
            }
        },
        [persistDraft, validateWorkflow],
    );

    const handlePublish = useCallback(
        async (nodes: Node[], edges: Edge[]) => {
            setIsPublishing(true);
            setActionError(null);
            setStatusMessage(null);

            try {
                const workflow = await persistDraft(nodes, edges);
                if (!workflow) {
                    return;
                }

                const result = await validateWorkflow(workflow.id, 'publish');
                setValidation(result);
                if (!result.is_valid) {
                    setStatusMessage('发布已拦截，请先修复校验问题。');
                    return;
                }

                const published = await publishWorkflow(workflow.id, '编辑器显式发布');
                applyWorkflowMeta(published.workflow);
                setValidation(published.validation);
                setStatusMessage(
                    `工作流已发布，可运行版本为 v${published.workflow.published_version ?? workflow.version}。`,
                );
            } catch (err: unknown) {
                const error = err as {
                    code?: number;
                    data?: { validation?: ValidationResult };
                };
                if (error.code === 40000 && error.data?.validation) {
                    setValidation(error.data.validation);
                    setStatusMessage('发布已拦截，请先修复校验问题。');
                } else {
                    setActionError(err instanceof Error ? err.message : '发布工作流失败');
                }
            } finally {
                setIsPublishing(false);
            }
        },
        [applyWorkflowMeta, persistDraft, publishWorkflow, validateWorkflow],
    );

    const headerTitle = useMemo(
        () => (workflowId ? '编辑工作流' : '新建工作流'),
        [workflowId],
    );

    if (isLoading) {
        return (
            <main className={styles.page}>
                <div className={styles.loadingCard}>正在加载认证信息...</div>
            </main>
        );
    }

    if (!isAuthenticated) {
        return (
            <main className={styles.page}>
                <div className={styles.pageHeader}>
                    <div>
                        <Link href="/console/workflows" className={styles.backLink}>
                            返回工作流列表
                        </Link>
                        <h1 className={styles.title}>{headerTitle}</h1>
                    </div>
                    <div className={styles.summaryCard}>
                        <span className={styles.summaryLabel}>认证状态</span>
                        <strong>未登录</strong>
                    </div>
                </div>
                <div className={styles.errorBanner}>
                    请先登录后再访问工作流编辑器。
                </div>
            </main>
        );
    }

    if (!canAccessPage) {
        return (
            <main className={styles.page}>
                <div className={styles.pageHeader}>
                    <div>
                        <Link href="/console/workflows" className={styles.backLink}>
                            返回工作流列表
                        </Link>
                        <h1 className={styles.title}>{headerTitle}</h1>
                    </div>
                    <div className={styles.summaryCard}>
                        <span className={styles.summaryLabel}>访问权限</span>
                        <strong>无权限</strong>
                    </div>
                </div>
                <div className={styles.errorBanner}>
                    {draftId
                        ? '您没有权限编辑此工作流。需要 workflow.update 权限。'
                        : '您没有权限创建新工作流。需要 workflow.create 权限。'}
                </div>
            </main>
        );
    }

    if (pageLoading) {
        return (
            <main className={styles.page}>
                <div className={styles.loadingCard}>正在加载工作流草稿...</div>
            </main>
        );
    }

    return (
        <main className={styles.page}>
            <div className={styles.pageHeader}>
                <div>
                    <Link href="/console/workflows" className={styles.backLink}>
                        返回工作流列表
                    </Link>
                    <h1 className={styles.title}>{headerTitle}</h1>
                    <p className={styles.subtitle}>
                        保存草稿、执行发布前校验，并将通过校验的版本显式发布给普通用户使用。
                    </p>
                </div>
                <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>当前状态</span>
                    <strong>
                        {isPublished
                            ? (currentVersion !== publishedVersion ? '有未发布变更' : '已发布')
                            : '草稿'}
                    </strong>
                    <span className={styles.summaryHint}>
                        {publishedVersion ? `已发布版本 v${publishedVersion}` : '尚未发布'}
                    </span>
                </div>
            </div>

            {loadError ? <div className={styles.errorBanner}>{loadError}</div> : null}

            <WorkflowEditor
                workflowId={workflowId}
                initialNodes={initialNodes}
                initialEdges={initialEdges}
                name={name}
                description={description}
                onNameChange={setName}
                onDescriptionChange={setDescription}
                isPublished={isPublished}
                publishedVersion={publishedVersion}
                publishedAt={publishedAt}
                onSave={handleSave}
                onValidate={handleValidate}
                onPublish={handlePublish}
                actionState={{
                    isSaving,
                    isValidating,
                    isPublishing,
                    statusMessage,
                    errorMessage: actionError,
                    validation,
                }}
            />
        </main>
    );
}
