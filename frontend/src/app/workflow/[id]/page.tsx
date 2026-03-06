'use client';

import React from 'react';
import { useParams, useRouter } from 'next/navigation';
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

export default function WorkflowDetailPage() {
    const params = useParams();
    const router = useRouter();
    const workflowId = params.id as string;

    const [workflow, setWorkflow] = React.useState<WorkflowResponse | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState<string | null>(null);
    const [actionLoading, setActionLoading] = React.useState(false);

    // 轮询间隔
    const pollIntervalRef = React.useRef<NodeJS.Timeout | null>(null);

    // 停止轮询
    const stopPolling = React.useCallback(() => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    }, []);

    // 开始轮询
    const startPolling = React.useCallback(() => {
        if (!pollIntervalRef.current) {
            pollIntervalRef.current = setInterval(() => {
                workflowApi.getStatus(workflowId).then(response => {
                    setWorkflow(response);
                    if (response.status !== 'running') {
                        stopPolling();
                    }
                }).catch(() => {
                    stopPolling();
                });
            }, 3000);
        }
    }, [workflowId, stopPolling]);

    // 加载工作流状态
    const loadWorkflow = React.useCallback(async () => {
        try {
            const response = await workflowApi.getStatus(workflowId);
            setWorkflow(response);
            setError(null);

            // 如果工作流正在运行，继续轮询
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

    // 初始加载和清理
    React.useEffect(() => {
        loadWorkflow();
        return () => stopPolling();
    }, [loadWorkflow, stopPolling]);

    // 处理澄清回答
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

    // 处理提纲审批
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

    // 处理提纲修改
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

    // 处理提纲重新生成
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

    // 处理事实核查审批
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

    // 计算工作流步骤状态
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

        // 根据工作流状态确定各步骤状态
        const state = workflow.state;
        const currentStatus = workflow.status;

        return stepNames.map((name, index) => {
            let status: WorkflowStep['status'] = 'pending';

            // 简单的状态判断逻辑
            if (name === 'parse_intent' && state.intent_card) {
                status = 'completed';
            }
            if (name === 'generate_outline') {
                if (state.outline) {
                    status = currentStatus === 'awaiting_outline_approval' ? 'interrupted' : 'completed';
                }
            }
            if (name === 'generate_content' && state.generated_content) {
                status = 'completed';
            }
            if (name === 'self_refine' && state.final_content) {
                status = 'completed';
            }
            if (name === 'check_facts') {
                if (state.fact_check_report) {
                    status = currentStatus === 'awaiting_fact_check_approval' ? 'interrupted' : 'completed';
                }
            }
            if (name === 'finalize' && currentStatus === 'completed') {
                status = 'completed';
            }

            // 当前正在运行的步骤
            if (currentStatus === 'running') {
                const completedIndex = stepNames.findIndex((s) => {
                    if (s === 'parse_intent') return !state.intent_card;
                    if (s === 'generate_outline') return !state.outline;
                    return false;
                });
                if (completedIndex === index || (completedIndex === -1 && status === 'pending')) {
                    status = 'running';
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

    // 渲染当前阶段的交互组件
    const renderCurrentStage = () => {
        if (!workflow) return null;

        const { status, state } = workflow;

        // 需要澄清
        if (status === 'needs_clarification' && state.clarification_questions) {
            return (
                <ClarificationDialog
                    questions={state.clarification_questions}
                    onSubmit={handleClarification}
                    isLoading={actionLoading}
                />
            );
        }

        // 等待提纲审批
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

        // 等待事实核查确认
        if (status === 'awaiting_fact_check_approval' && state.fact_check_report) {
            return (
                <FactCheckViewer
                    report={state.fact_check_report as FactCheckReport}
                    onApprove={handleFactCheckApprove}
                    isLoading={actionLoading}
                />
            );
        }

        // 已完成
        if (status === 'completed') {
            const finalContent = state.final_content as Record<string, string> | undefined;
            return (
                <div className={styles.completedCard}>
                    <div className={styles.completedIcon}>✅</div>
                    <h3>内容生成完成</h3>
                    <p>您可以在下方查看生成的内容</p>
                    {finalContent && (
                        <div className={styles.contentPreview}>
                            <pre>{JSON.stringify(finalContent, null, 2)}</pre>
                        </div>
                    )}
                </div>
            );
        }

        // 运行中
        return (
            <div className={styles.runningCard}>
                <div className="spinner" style={{ width: 32, height: 32 }} />
                <p>正在处理中，请稍候...</p>
            </div>
        );
    };

    if (loading) {
        return (
            <div className={styles.loadingContainer}>
                <div className="spinner" />
                <p>加载工作流...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.errorContainer}>
                <div className={styles.errorIcon}>❌</div>
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
            {/* Header */}
            <header className={styles.header}>
                <button className={styles.backButton} onClick={() => router.push('/')}>
                    ← 返回
                </button>
                <h1 className={styles.title}>工作流详情</h1>
                <code className={styles.workflowId}>{workflowId.slice(0, 8)}...</code>
            </header>

            {/* Main Content */}
            <div className={styles.mainContent}>
                {/* Progress Sidebar */}
                <aside className={styles.sidebar}>
                    <WorkflowProgress steps={calculateSteps()} />
                </aside>

                {/* Current Stage */}
                <main className={styles.stageContent}>
                    {renderCurrentStage()}
                </main>
            </div>
        </div>
    );
}
