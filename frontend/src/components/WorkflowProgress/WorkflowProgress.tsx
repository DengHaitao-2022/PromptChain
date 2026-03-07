'use client';

import React from 'react';
import {
    AlertTriangle,
    CheckCheck,
    CircleDot,
    LoaderCircle,
    PauseCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import styles from './WorkflowProgress.module.css';

export interface WorkflowStep {
    id: string;
    name: string;
    label: string;
    status: 'pending' | 'running' | 'completed' | 'interrupted' | 'failed';
    startedAt?: string;
    completedAt?: string;
    durationMs?: number;
    artifactCount?: number;
}

interface WorkflowProgressProps {
    steps: WorkflowStep[];
    currentStep?: string;
    onStepClick?: (stepId: string) => void;
}

const DEFAULT_STEPS: WorkflowStep[] = [
    { id: 'parse_intent', name: 'parse_intent', label: '意图解析', status: 'pending' },
    { id: 'generate_outline', name: 'generate_outline', label: '提纲生成', status: 'pending' },
    { id: 'generate_content', name: 'generate_content', label: '内容生成', status: 'pending' },
    { id: 'self_refine', name: 'self_refine', label: '自检修订', status: 'pending' },
    { id: 'check_facts', name: 'check_facts', label: '事实核查', status: 'pending' },
    { id: 'finalize', name: 'finalize', label: '最终输出', status: 'pending' },
];

function getStatusMeta(status: WorkflowStep['status']): {
    icon: LucideIcon;
    text: string;
} {
    switch (status) {
        case 'completed':
            return { icon: CheckCheck, text: '已完成' };
        case 'running':
            return { icon: LoaderCircle, text: '执行中' };
        case 'interrupted':
            return { icon: PauseCircle, text: '等待确认' };
        case 'failed':
            return { icon: AlertTriangle, text: '执行失败' };
        default:
            return { icon: CircleDot, text: '待开始' };
    }
}

function formatDuration(ms?: number): string {
    if (!ms) {
        return '';
    }

    if (ms < 1000) {
        return `${ms}ms`;
    }

    return `${(ms / 1000).toFixed(1)}s`;
}

export function WorkflowProgress({
    steps = DEFAULT_STEPS,
    currentStep,
    onStepClick,
}: WorkflowProgressProps) {
    const completedCount = steps.filter((step) => step.status === 'completed').length;
    const interactive = Boolean(onStepClick);

    const handleKeyDown = (
        event: React.KeyboardEvent<HTMLDivElement>,
        stepId: string
    ) => {
        if (!onStepClick) {
            return;
        }

        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onStepClick(stepId);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div>
                    <h3 className={styles.title}>工作流轨道</h3>
                    <p className={styles.subtitle}>当前运行与人工中断都会在这里留下轨迹。</p>
                </div>
                <span className={styles.summary}>{completedCount}/{steps.length} 已完成</span>
            </div>

            <div className={styles.timeline}>
                {steps.map((step, index) => {
                    const statusMeta = getStatusMeta(step.status);
                    const StatusIcon = statusMeta.icon;
                    const isCurrent = currentStep === step.id;

                    return (
                        <div
                            key={step.id}
                            className={`${styles.step} ${styles[step.status]} ${
                                isCurrent ? styles.current : ''
                            } ${interactive ? styles.interactive : ''}`}
                            onClick={() => onStepClick?.(step.id)}
                            onKeyDown={(event) => handleKeyDown(event, step.id)}
                            role={interactive ? 'button' : undefined}
                            tabIndex={interactive ? 0 : undefined}
                            aria-current={isCurrent ? 'step' : undefined}
                        >
                            {index > 0 && (
                                <div
                                    className={`${styles.connector} ${
                                        step.status === 'completed'
                                            ? styles.connectorCompleted
                                            : step.status === 'running'
                                                ? styles.connectorRunning
                                                : step.status === 'failed'
                                                    ? styles.connectorFailed
                                                    : step.status === 'interrupted'
                                                        ? styles.connectorInterrupted
                                                        : ''
                                    }`}
                                />
                            )}

                            <div className={styles.indicator}>
                                <StatusIcon
                                    className={`${styles.indicatorIcon} ${
                                        step.status === 'running' ? styles.spinIcon : ''
                                    }`}
                                    aria-hidden="true"
                                />
                            </div>

                            <div className={styles.info}>
                                <div className={styles.labelRow}>
                                    <span className={styles.stepLabel}>{step.label}</span>
                                    <span className={styles.stepState}>{statusMeta.text}</span>
                                </div>
                                <span className={styles.stepMeta}>
                                    {step.status === 'completed' && formatDuration(step.durationMs)
                                        ? `耗时 ${formatDuration(step.durationMs)}`
                                        : step.status === 'running'
                                            ? '系统正在推进该节点'
                                            : step.status === 'interrupted'
                                                ? '等待你的确认'
                                                : step.status === 'failed'
                                                    ? '该节点未能完成'
                                                    : '尚未开始执行'}
                                </span>
                            </div>

                            {typeof step.artifactCount === 'number' && step.artifactCount > 0 && (
                                <div className={styles.artifactBadge}>{step.artifactCount}</div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
