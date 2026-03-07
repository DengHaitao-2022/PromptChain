'use client';

import React from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    Activity,
    AlertTriangle,
    ArrowLeft,
    Braces,
    CheckCheck,
    CheckCircle2,
    Clock3,
    FileText,
    ListChecks,
    LoaderCircle,
    MessageSquareQuote,
    ShieldAlert,
    Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import styles from './page.module.css';
import {
    workflowApi,
    type WorkflowResponse,
    type Outline,
    type FactCheckReport,
} from '@/lib/api';
import {
    OutlineEditor,
    FactCheckViewer,
    ClarificationDialog,
    WorkflowProgress,
    type WorkflowStep,
} from '@/components';

type StageTone = 'brand' | 'success' | 'warning' | 'danger' | 'muted';

interface StageMetric {
    label: string;
    value: string;
    tone?: Exclude<StageTone, 'muted'>;
}

interface StatusMeta {
    eyebrow: string;
    label: string;
    title: string;
    description: string;
    tone: StageTone;
    icon: LucideIcon;
}

interface FinalContentEntry {
    key: string;
    preview: string;
    wordCount?: number;
    raw: unknown;
}

function getStatusMeta(status?: WorkflowResponse['status']): StatusMeta {
    switch (status) {
        case 'needs_clarification':
            return {
                eyebrow: 'Need Input',
                label: '等待澄清',
                title: '补全需求上下文',
                description: '模型在继续生成前需要你补充关键上下文，以减少误判和无效扩写。',
                tone: 'warning',
                icon: MessageSquareQuote,
            };
        case 'awaiting_outline_approval':
            return {
                eyebrow: 'Review Outline',
                label: '等待提纲审批',
                title: '审阅生成提纲',
                description: '检查结构、章节重点和篇幅分配，确认后工作流会继续进入正文生成。',
                tone: 'brand',
                icon: ListChecks,
            };
        case 'awaiting_fact_check_approval':
            return {
                eyebrow: 'Resolve Risks',
                label: '等待事实核查审批',
                title: '处理高风险声明',
                description: '优先确认高风险 claim 的去留和修正策略，再提交最终审阅决定。',
                tone: 'warning',
                icon: ShieldAlert,
            };
        case 'completed':
            return {
                eyebrow: 'Delivery Ready',
                label: '生成完成',
                title: '交付结果已准备好',
                description: '内容已完成生成与审阅，你可以先阅读结果，再决定是否回看原始数据。',
                tone: 'success',
                icon: CheckCircle2,
            };
        case 'failed':
            return {
                eyebrow: 'Execution Failed',
                label: '执行失败',
                title: '工作流未能完成',
                description: '当前执行已中断。请先检查错误信息，再决定是否重新发起或返回首页。',
                tone: 'danger',
                icon: AlertTriangle,
            };
        case 'running':
        default:
            return {
                eyebrow: 'In Progress',
                label: '执行中',
                title: '工作流正在推进',
                description: '系统会自动推进节点；一旦出现需要人工介入的步骤，页面会切换到对应审阅态。',
                tone: 'brand',
                icon: Activity,
            };
    }
}

function formatCount(value: number | undefined): string {
    return typeof value === 'number' ? value.toString() : '-';
}

function normalizeFinalContentEntries(
    finalContent: Record<string, unknown> | undefined
): FinalContentEntry[] {
    if (!finalContent) {
        return [];
    }

    return Object.entries(finalContent).map(([key, value]) => {
        if (typeof value === 'string') {
            return {
                key,
                preview: value,
                raw: value,
            };
        }

        if (value && typeof value === 'object') {
            const preview =
                typeof (value as { preview?: unknown }).preview === 'string'
                    ? ((value as { preview: string }).preview)
                    : JSON.stringify(value, null, 2);
            const wordCount =
                typeof (value as { word_count?: unknown }).word_count === 'number'
                    ? ((value as { word_count: number }).word_count)
                    : undefined;

            return {
                key,
                preview,
                wordCount,
                raw: value,
            };
        }

        return {
            key,
            preview: String(value ?? ''),
            raw: value,
        };
    });
}

function formatEntryLabel(key: string): string {
    return key
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

function formatStepStatus(step: WorkflowStep): string {
    switch (step.status) {
        case 'completed':
            return step.durationMs ? `${Math.round(step.durationMs / 1000)}s` : '已完成';
        case 'running':
            return '执行中';
        case 'interrupted':
            return '等待确认';
        case 'failed':
            return '执行失败';
        default:
            return '待开始';
    }
}

export default function WorkflowDetailPage() {
    const params = useParams();
    const router = useRouter();
    const workflowId = params.id as string;

    const [workflow, setWorkflow] = React.useState<WorkflowResponse | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState<string | null>(null);
    const [actionLoading, setActionLoading] = React.useState(false);
    const [completedView, setCompletedView] = React.useState<'preview' | 'raw'>('preview');

    const pollIntervalRef = React.useRef<NodeJS.Timeout | null>(null);

    const stopPolling = React.useCallback(() => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    }, []);

    const startPolling = React.useCallback(() => {
        if (!pollIntervalRef.current) {
            pollIntervalRef.current = setInterval(() => {
                workflowApi
                    .getStatus(workflowId)
                    .then((response) => {
                        setWorkflow(response);
                        if (response.status !== 'running') {
                            stopPolling();
                        }
                    })
                    .catch(() => {
                        stopPolling();
                    });
            }, 3000);
        }
    }, [workflowId, stopPolling]);

    const loadWorkflow = React.useCallback(async () => {
        try {
            const response = await workflowApi.getStatus(workflowId);
            setWorkflow(response);
            setError(null);

            if (response.status === 'running') {
                startPolling();
            } else {
                stopPolling();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '加载失败');
            stopPolling();
        } finally {
            setLoading(false);
        }
    }, [workflowId, startPolling, stopPolling]);

    React.useEffect(() => {
        loadWorkflow();
        return () => stopPolling();
    }, [loadWorkflow, stopPolling]);

    React.useEffect(() => {
        if (workflow?.status !== 'completed') {
            setCompletedView('preview');
        }
    }, [workflow?.status]);

    const handleClarification = async (answers: Record<string, string>) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.clarify(workflowId, answers);
            setWorkflow(response);
            startPolling();
        } catch (err) {
            setError(err instanceof Error ? err.message : '提交失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleOutlineApprove = async () => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveOutline(workflowId, 'approve');
            setWorkflow(response);
            startPolling();
        } catch (err) {
            setError(err instanceof Error ? err.message : '审批失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleOutlineModify = async (modifiedOutline: Outline) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveOutline(
                workflowId,
                'modify',
                undefined,
                modifiedOutline
            );
            setWorkflow(response);
            startPolling();
        } catch (err) {
            setError(err instanceof Error ? err.message : '保存失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleOutlineRegenerate = async (feedback: string) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveOutline(
                workflowId,
                'regenerate',
                feedback
            );
            setWorkflow(response);
            startPolling();
        } catch (err) {
            setError(err instanceof Error ? err.message : '重新生成失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleFactCheckApprove = async (
        decisions: Record<string, 'confirm' | 'use_suggestion' | 'manual'>,
        corrections: Record<string, string>
    ) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveFactCheck(
                workflowId,
                decisions,
                corrections
            );
            setWorkflow(response);
            startPolling();
        } catch (err) {
            setError(err instanceof Error ? err.message : '事实核查审批失败');
        } finally {
            setActionLoading(false);
        }
    };

    const calculateSteps = (): WorkflowStep[] => {
        const stepNames = [
            'parse_intent',
            'generate_outline',
            'generate_content',
            'self_refine',
            'check_facts',
            'finalize',
        ];
        const stepLabels: Record<string, string> = {
            parse_intent: '意图解析',
            generate_outline: '提纲生成',
            generate_content: '内容生成',
            self_refine: '自检修订',
            check_facts: '事实核查',
            finalize: '最终输出',
        };

        if (!workflow) {
            return stepNames.map((name) => ({
                id: name,
                name,
                label: stepLabels[name],
                status: 'pending' as const,
            }));
        }

        const state = workflow.state;
        const currentStatus = workflow.status;

        return stepNames.map((name, index) => {
            let status: WorkflowStep['status'] = 'pending';

            if (name === 'parse_intent' && state.intent_card) {
                status = 'completed';
            }
            if (name === 'generate_outline' && state.outline) {
                status =
                    currentStatus === 'awaiting_outline_approval'
                        ? 'interrupted'
                        : 'completed';
            }
            if (name === 'generate_content' && state.generated_content) {
                status = 'completed';
            }
            if (name === 'self_refine' && state.final_content) {
                status = 'completed';
            }
            if (name === 'check_facts' && state.fact_check_report) {
                status =
                    currentStatus === 'awaiting_fact_check_approval'
                        ? 'interrupted'
                        : 'completed';
            }
            if (name === 'finalize' && currentStatus === 'completed') {
                status = 'completed';
            }

            if (currentStatus === 'running') {
                const completedIndex = stepNames.findIndex((stepName) => {
                    if (stepName === 'parse_intent') {
                        return !state.intent_card;
                    }
                    if (stepName === 'generate_outline') {
                        return !state.outline;
                    }
                    return false;
                });

                if (completedIndex === index || (completedIndex === -1 && status === 'pending')) {
                    status = 'running';
                }
            }

            if (currentStatus === 'failed' && status === 'pending') {
                const firstPendingIndex = stepNames.findIndex((stepName) => {
                    if (stepName === 'parse_intent') {
                        return !state.intent_card;
                    }
                    if (stepName === 'generate_outline') {
                        return !state.outline;
                    }
                    if (stepName === 'generate_content') {
                        return !state.generated_content;
                    }
                    if (stepName === 'self_refine') {
                        return !state.final_content;
                    }
                    if (stepName === 'check_facts') {
                        return !state.fact_check_report;
                    }
                    return stepName === 'finalize';
                });

                if (index === firstPendingIndex || firstPendingIndex === -1) {
                    status = 'failed';
                }
            }

            return {
                id: name,
                name,
                label: stepLabels[name],
                status,
            };
        });
    };

    const steps = calculateSteps();
    const currentStep = steps.find(
        (step) => step.status === 'running' || step.status === 'interrupted'
    )?.id;
    const currentStepLabel = steps.find((step) => step.id === currentStep)?.label;
    const statusMeta = getStatusMeta(workflow?.status);

    const buildStageMetrics = (): StageMetric[] => {
        if (!workflow) {
            return [];
        }

        const { status, state } = workflow;

        if (status === 'needs_clarification') {
            const questions = state.clarification_questions ?? [];
            const required = questions.filter((question) => question.priority === 'high');
            return [
                { label: '澄清问题', value: formatCount(questions.length) },
                { label: '必填问题', value: formatCount(required.length), tone: 'warning' },
            ];
        }

        if (status === 'awaiting_outline_approval' && state.outline) {
            const outline = state.outline as Outline;
            return [
                { label: '章节数量', value: formatCount(outline.sections.length) },
                { label: '目标字数', value: formatCount(outline.total_target_words), tone: 'brand' },
            ];
        }

        if (status === 'awaiting_fact_check_approval' && state.fact_check_report) {
            const report = state.fact_check_report as FactCheckReport;
            return [
                { label: '总声明数', value: formatCount(report.total_claims) },
                { label: '已验证', value: formatCount(report.verified_count), tone: 'success' },
                { label: '高风险', value: formatCount(report.high_risk_count), tone: 'warning' },
            ];
        }

        if (status === 'completed') {
            const finalEntries = normalizeFinalContentEntries(
                state.final_content as Record<string, unknown> | undefined
            );
            const totalWords = finalEntries.reduce(
                (sum, entry) => sum + (entry.wordCount ?? 0),
                0
            );

            return [
                { label: '交付块数', value: formatCount(finalEntries.length), tone: 'success' },
                { label: '累计字数', value: formatCount(totalWords || undefined), tone: 'brand' },
            ];
        }

        return [
            { label: '当前步骤', value: currentStepLabel ?? '自动推进中', tone: 'brand' },
            { label: '已完成节点', value: formatCount(steps.filter((step) => step.status === 'completed').length) },
        ];
    };

    const stageMetrics = buildStageMetrics();

    const renderCompletedStage = () => {
        const rawFinalContent = workflow?.state.final_content as Record<string, unknown> | undefined;
        const finalEntries = normalizeFinalContentEntries(rawFinalContent);

        return (
            <div className={styles.completedStage}>
                <div className={styles.completedHero}>
                    <div className={styles.completedBadge}>
                        <CheckCheck className={styles.completedBadgeIcon} aria-hidden="true" />
                    </div>
                    <div className={styles.completedCopy}>
                        <p className={styles.completedEyebrow}>Delivery Ready</p>
                        <h3>内容产物已完成生成与审阅</h3>
                        <p>
                            先阅读可交付预览，再决定是否回看原始 JSON。这个阶段强调结果，而不是调试信息。
                        </p>
                    </div>
                    <div className={styles.completedActions}>
                        <button
                            type="button"
                            className={`${styles.viewToggle} ${
                                completedView === 'preview' ? styles.viewToggleActive : ''
                            }`}
                            onClick={() => setCompletedView('preview')}
                        >
                            <FileText className={styles.toggleIcon} aria-hidden="true" />
                            结果预览
                        </button>
                        <button
                            type="button"
                            className={`${styles.viewToggle} ${
                                completedView === 'raw' ? styles.viewToggleActive : ''
                            }`}
                            onClick={() => setCompletedView('raw')}
                        >
                            <Braces className={styles.toggleIcon} aria-hidden="true" />
                            原始数据
                        </button>
                        <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => router.push('/')}
                        >
                            返回首页
                        </button>
                    </div>
                </div>

                {completedView === 'preview' ? (
                    <div className={styles.previewGrid}>
                        {finalEntries.length > 0 ? (
                            finalEntries.map((entry) => (
                                <article key={entry.key} className={styles.previewCard}>
                                    <div className={styles.previewCardHeader}>
                                        <div>
                                            <p className={styles.previewLabel}>
                                                {formatEntryLabel(entry.key)}
                                            </p>
                                            {typeof entry.wordCount === 'number' && (
                                                <span className={styles.previewMeta}>
                                                    {entry.wordCount} 字
                                                </span>
                                            )}
                                        </div>
                                        <Sparkles
                                            className={styles.previewCardIcon}
                                            aria-hidden="true"
                                        />
                                    </div>
                                    <p className={styles.previewText}>{entry.preview}</p>
                                </article>
                            ))
                        ) : (
                            <div className={styles.emptyState}>
                                <FileText className={styles.emptyStateIcon} aria-hidden="true" />
                                <div>
                                    <h3>当前没有可展示的结果片段</h3>
                                    <p>工作流已完成，但 `final_content` 为空或结构不符合预览条件。</p>
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className={styles.rawSurface}>
                        <pre>{JSON.stringify(rawFinalContent ?? {}, null, 2)}</pre>
                    </div>
                )}
            </div>
        );
    };

    const renderRunningStage = () => (
        <div className={styles.runningStage}>
            <div className={styles.runningIntro}>
                <div className={styles.runningPulse} aria-hidden="true">
                    <LoaderCircle className={styles.spinIcon} />
                </div>
                <div>
                    <p className={styles.runningEyebrow}>Live Orchestration</p>
                    <h3>系统正在推进当前工作流</h3>
                    <p>
                        当前焦点：
                        <strong>{currentStepLabel ?? '正在解析上下文'}</strong>
                        。如果模型需要澄清或审批，本页会自动切换到对应审阅态。
                    </p>
                </div>
            </div>

            <div className={styles.liveRail}>
                {steps.map((step) => (
                    <div
                        key={step.id}
                        className={`${styles.liveItem} ${
                            step.id === currentStep ? styles.liveItemActive : ''
                        }`}
                    >
                        <span className={styles.liveLabel}>{step.label}</span>
                        <span className={styles.liveMeta}>{formatStepStatus(step)}</span>
                    </div>
                ))}
            </div>
        </div>
    );

    const renderFailedStage = () => (
        <div className={styles.failedStage}>
            <div className={styles.failedIconWrap}>
                <AlertTriangle className={styles.failedIcon} aria-hidden="true" />
            </div>
            <div>
                <h3>工作流执行失败</h3>
                <p>
                    当前工作流没有顺利走到最终交付。你可以先重新加载状态，确认是否是临时问题，再返回首页重新发起。
                </p>
            </div>
            <div className={styles.failedActions}>
                <button type="button" className="btn btn-secondary" onClick={() => void loadWorkflow()}>
                    重新加载
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => router.push('/')}>
                    返回首页
                </button>
            </div>
        </div>
    );

    const renderCurrentStage = () => {
        if (!workflow) {
            return null;
        }

        const { status, state } = workflow;

        if (status === 'needs_clarification' && state.clarification_questions) {
            return (
                <ClarificationDialog
                    questions={state.clarification_questions}
                    onSubmit={handleClarification}
                    isLoading={actionLoading}
                />
            );
        }

        if (status === 'awaiting_outline_approval' && state.outline) {
            return (
                <OutlineEditor
                    outline={state.outline as Outline}
                    onApprove={handleOutlineApprove}
                    onModify={handleOutlineModify}
                    onRegenerate={handleOutlineRegenerate}
                    isLoading={actionLoading}
                />
            );
        }

        if (status === 'awaiting_fact_check_approval' && state.fact_check_report) {
            return (
                <FactCheckViewer
                    report={state.fact_check_report as FactCheckReport}
                    onApprove={handleFactCheckApprove}
                    isLoading={actionLoading}
                />
            );
        }

        if (status === 'completed') {
            return renderCompletedStage();
        }

        if (status === 'failed') {
            return renderFailedStage();
        }

        return renderRunningStage();
    };

    if (loading) {
        return (
            <div className={styles.loadingContainer}>
                <LoaderCircle className={`${styles.spinIcon} ${styles.loadingIcon}`} />
                <p>加载工作流...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.errorContainer} role="alert">
                <div className={styles.errorIconWrap}>
                    <AlertTriangle className={styles.errorIcon} aria-hidden="true" />
                </div>
                <h3>加载失败</h3>
                <p>{error}</p>
                <button className="btn btn-secondary" onClick={() => router.push('/')}>
                    返回首页
                </button>
            </div>
        );
    }

    return (
        <div className={styles.page}>
            <header className={styles.header}>
                <button className={styles.backButton} onClick={() => router.push('/')}>
                    <ArrowLeft className={styles.backIcon} aria-hidden="true" />
                    返回首页
                </button>

                <div className={styles.headerCopy}>
                    <p className={styles.headerEyebrow}>Workflow Detail</p>
                    <h1 className={styles.title}>工作流详情</h1>
                </div>

                <div className={styles.headerMeta}>
                    <span className={`${styles.headerStatus} ${styles[`tone${statusMeta.tone[0].toUpperCase()}${statusMeta.tone.slice(1)}`]}`}>
                        <statusMeta.icon className={styles.headerStatusIcon} aria-hidden="true" />
                        {statusMeta.label}
                    </span>
                    <code className={styles.workflowId}>{workflowId.slice(0, 8)}...</code>
                </div>
            </header>

            <div className={styles.mainContent}>
                <aside className={styles.sidebar}>
                    <WorkflowProgress steps={steps} currentStep={currentStep} />
                </aside>

                <main className={styles.stageColumn}>
                    <section className={styles.statusStrip} aria-live="polite">
                        <div className={styles.statusStripMain}>
                            <div className={`${styles.statusIconWrap} ${styles[`tone${statusMeta.tone[0].toUpperCase()}${statusMeta.tone.slice(1)}`]}`}>
                                <statusMeta.icon className={styles.statusIcon} aria-hidden="true" />
                            </div>
                            <div>
                                <p className={styles.statusEyebrow}>{statusMeta.eyebrow}</p>
                                <p className={styles.statusMessage}>
                                    {statusMeta.label}
                                    {currentStepLabel ? ` · ${currentStepLabel}` : ''}
                                </p>
                            </div>
                        </div>
                        <div className={styles.statusHints}>
                            <Clock3 className={styles.hintIcon} aria-hidden="true" />
                            <span>
                                {workflow?.status === 'completed'
                                    ? '交付已准备好，可切换预览和原始数据。'
                                    : '系统会持续更新状态，无需手动刷新。'}
                            </span>
                        </div>
                    </section>

                    <section className={styles.stageShell}>
                        <div className={styles.stageHeader}>
                            <div className={styles.stageHeaderMain}>
                                <p className={styles.stageEyebrow}>{statusMeta.label}</p>
                                <h2 className={styles.stageTitle}>{statusMeta.title}</h2>
                                <p className={styles.stageDescription}>{statusMeta.description}</p>
                            </div>

                            {stageMetrics.length > 0 && (
                                <div className={styles.stageMetrics}>
                                    {stageMetrics.map((metric) => (
                                        <div
                                            key={metric.label}
                                            className={`${styles.metricCard} ${
                                                metric.tone
                                                    ? styles[`tone${metric.tone[0].toUpperCase()}${metric.tone.slice(1)}`]
                                                    : ''
                                            }`}
                                        >
                                            <span className={styles.metricLabel}>{metric.label}</span>
                                            <strong className={styles.metricValue}>{metric.value}</strong>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className={styles.stageBody}>{renderCurrentStage()}</div>
                    </section>
                </main>
            </div>
        </div>
    );
}
