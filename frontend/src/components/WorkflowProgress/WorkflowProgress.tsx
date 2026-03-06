'use client';

import React from 'react';
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

// 工作流步骤定义
const DEFAULT_STEPS: WorkflowStep[] = [
    { id: 'parse_intent', name: 'parse_intent', label: '意图解析', status: 'pending' },
    { id: 'generate_outline', name: 'generate_outline', label: '提纲生成', status: 'pending' },
    { id: 'generate_content', name: 'generate_content', label: '内容生成', status: 'pending' },
    { id: 'self_refine', name: 'self_refine', label: '自检修订', status: 'pending' },
    { id: 'check_facts', name: 'check_facts', label: '事实核查', status: 'pending' },
    { id: 'finalize', name: 'finalize', label: '最终输出', status: 'pending' },
];

export function WorkflowProgress({
    steps = DEFAULT_STEPS,
    currentStep,
    onStepClick,
}: WorkflowProgressProps) {
    // 获取步骤状态图标
    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed':
                return '✓';
            case 'running':
                return '●';
            case 'interrupted':
                return '⏸';
            case 'failed':
                return '✕';
            default:
                return '';
        }
    };

    // 获取步骤状态类名
    const getStatusClass = (status: string) => {
        switch (status) {
            case 'completed':
                return styles.completed;
            case 'running':
                return styles.running;
            case 'interrupted':
                return styles.interrupted;
            case 'failed':
                return styles.failed;
            default:
                return styles.pending;
        }
    };

    // 格式化持续时间
    const formatDuration = (ms?: number) => {
        if (!ms) return '-';
        if (ms < 1000) return `${ms}ms`;
        return `${(ms / 1000).toFixed(1)}s`;
    };

    return (
        <div className={styles.container}>
            <h3 className={styles.title}>工作流进度</h3>

            <div className={styles.timeline}>
                {steps.map((step, index) => (
                    <div
                        key={step.id}
                        className={`${styles.step} ${getStatusClass(step.status)} ${currentStep === step.id ? styles.current : ''
                            }`}
                        onClick={() => onStepClick?.(step.id)}
                    >
                        {/* 连接线 */}
                        {index > 0 && (
                            <div
                                className={`${styles.connector} ${step.status !== 'pending' ? styles.connectorActive : ''
                                    }`}
                            />
                        )}

                        {/* 步骤指示器 */}
                        <div className={styles.indicator}>
                            {step.status === 'running' ? (
                                <div className={styles.spinner} />
                            ) : (
                                <span className={styles.indicatorIcon}>
                                    {getStatusIcon(step.status) || index + 1}
                                </span>
                            )}
                        </div>

                        {/* 步骤信息 */}
                        <div className={styles.info}>
                            <span className={styles.stepLabel}>{step.label}</span>
                            {step.status !== 'pending' && (
                                <span className={styles.stepMeta}>
                                    {step.status === 'running' && '进行中...'}
                                    {step.status === 'completed' && formatDuration(step.durationMs)}
                                    {step.status === 'interrupted' && '等待用户确认'}
                                    {step.status === 'failed' && '执行失败'}
                                </span>
                            )}
                        </div>

                        {/* 产物数量 */}
                        {step.artifactCount && step.artifactCount > 0 && (
                            <div className={styles.artifactBadge}>
                                📦 {step.artifactCount}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
