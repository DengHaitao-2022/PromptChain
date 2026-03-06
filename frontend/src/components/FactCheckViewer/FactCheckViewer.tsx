'use client';

import React from 'react';
import styles from './FactCheckViewer.module.css';
import type { FactCheckReport, FactClaim, VerificationResult } from '@/lib/api';

interface FactCheckViewerProps {
    report: FactCheckReport;
    onApprove: (
        decisions: Record<string, 'confirm' | 'use_suggestion' | 'manual'>,
        manualCorrections: Record<string, string>
    ) => void;
    isLoading?: boolean;
}

export function FactCheckViewer({
    report,
    onApprove,
    isLoading = false,
}: FactCheckViewerProps) {
    const [decisions, setDecisions] = React.useState<Record<string, 'confirm' | 'use_suggestion' | 'manual'>>({});
    const [manualCorrections, setManualCorrections] = React.useState<Record<string, string>>({});

    // 获取声明对应的验证结果
    const getResult = (claimId: string): VerificationResult | undefined => {
        return report.results.find((r) => r.claim_id === claimId);
    };

    // 设置决策
    const setDecision = (claimId: string, decision: 'confirm' | 'use_suggestion' | 'manual') => {
        setDecisions({ ...decisions, [claimId]: decision });
    };

    // 设置手动修正
    const setManualCorrection = (claimId: string, correction: string) => {
        setManualCorrections({ ...manualCorrections, [claimId]: correction });
    };

    // 风险等级颜色
    const getRiskColor = (level: string) => {
        switch (level) {
            case 'high':
                return 'danger';
            case 'medium':
                return 'warning';
            default:
                return 'success';
        }
    };

    // 风险等级文本
    const getRiskText = (level: string) => {
        switch (level) {
            case 'high':
                return '高风险';
            case 'medium':
                return '中风险';
            default:
                return '低风险';
        }
    };

    // 渲染单个声明
    const renderClaim = (claim: FactClaim) => {
        const result = getResult(claim.id);
        if (!result) return null;

        const isHighRisk = result.risk_level === 'high';
        const currentDecision = decisions[claim.id] || (isHighRisk ? '' : 'confirm');

        return (
            <div
                key={claim.id}
                className={`${styles.claimCard} ${isHighRisk ? styles.highRisk : ''}`}
            >
                {/* 声明内容 */}
                <div className={styles.claimContent}>
                    <div className={styles.claimHeader}>
                        <span className={`badge badge-${getRiskColor(result.risk_level)}`}>
                            {getRiskText(result.risk_level)}
                        </span>
                        <span className={styles.category}>{claim.category}</span>
                        <span className={styles.confidence}>
                            置信度: {Math.round(result.confidence * 100)}%
                        </span>
                    </div>
                    <p className={styles.claimText}>{claim.text}</p>
                </div>

                {/* 验证详情 */}
                <div className={styles.verificationDetails}>
                    <div className={styles.verificationItem}>
                        <label>验证问题</label>
                        <p>{result.verification_question}</p>
                    </div>
                    <div className={styles.verificationItem}>
                        <label>验证答案</label>
                        <p>{result.verification_answer}</p>
                    </div>
                    {result.suggested_correction && (
                        <div className={styles.verificationItem}>
                            <label>建议修正</label>
                            <p className={styles.suggestion}>{result.suggested_correction}</p>
                        </div>
                    )}
                </div>

                {/* 决策选项 (仅对高风险项) */}
                {isHighRisk && (
                    <div className={styles.decisionSection}>
                        <label className={styles.decisionLabel}>请选择处理方式：</label>
                        <div className={styles.decisionOptions}>
                            <label className={styles.radioOption}>
                                <input
                                    type="radio"
                                    name={`decision-${claim.id}`}
                                    checked={currentDecision === 'confirm'}
                                    onChange={() => setDecision(claim.id, 'confirm')}
                                    disabled={isLoading}
                                />
                                <span>确认无误</span>
                            </label>
                            {result.suggested_correction && (
                                <label className={styles.radioOption}>
                                    <input
                                        type="radio"
                                        name={`decision-${claim.id}`}
                                        checked={currentDecision === 'use_suggestion'}
                                        onChange={() => setDecision(claim.id, 'use_suggestion')}
                                        disabled={isLoading}
                                    />
                                    <span>采用建议修正</span>
                                </label>
                            )}
                            <label className={styles.radioOption}>
                                <input
                                    type="radio"
                                    name={`decision-${claim.id}`}
                                    checked={currentDecision === 'manual'}
                                    onChange={() => setDecision(claim.id, 'manual')}
                                    disabled={isLoading}
                                />
                                <span>手动修正</span>
                            </label>
                        </div>
                        {currentDecision === 'manual' && (
                            <textarea
                                className={`${styles.manualInput} input textarea`}
                                value={manualCorrections[claim.id] || ''}
                                onChange={(e) => setManualCorrection(claim.id, e.target.value)}
                                placeholder="请输入正确的内容..."
                                disabled={isLoading}
                            />
                        )}
                    </div>
                )}

                {/* 已验证标记 */}
                {result.is_verified && !isHighRisk && (
                    <div className={styles.verifiedBadge}>
                        ✓ 已验证
                    </div>
                )}
            </div>
        );
    };

    // 高风险声明
    const highRiskClaims = report.claims.filter(
        (c) => getResult(c.id)?.risk_level === 'high'
    );

    // 其他声明
    const otherClaims = report.claims.filter(
        (c) => getResult(c.id)?.risk_level !== 'high'
    );

    // 检查是否所有高风险项都有决策
    const allDecided = highRiskClaims.every((c) => {
        const decision = decisions[c.id];
        if (!decision) return false;
        if (decision === 'manual' && !manualCorrections[c.id]?.trim()) return false;
        return true;
    });

    return (
        <div className={styles.container}>
            {/* 统计概览 */}
            <div className={styles.stats}>
                <div className={styles.statItem}>
                    <span className={styles.statValue}>{report.total_claims}</span>
                    <span className={styles.statLabel}>总声明数</span>
                </div>
                <div className={styles.statItem}>
                    <span className={styles.statValue}>{report.verified_count}</span>
                    <span className={styles.statLabel}>已验证</span>
                </div>
                <div className={styles.statItem}>
                    <span className={`${styles.statValue} ${styles.danger}`}>
                        {report.high_risk_count}
                    </span>
                    <span className={styles.statLabel}>高风险</span>
                </div>
            </div>

            {/* 高风险声明 */}
            {highRiskClaims.length > 0 && (
                <div className={styles.section}>
                    <h3 className={styles.sectionTitle}>
                        ⚠️ 需要确认的高风险项 ({highRiskClaims.length})
                    </h3>
                    {highRiskClaims.map(renderClaim)}
                </div>
            )}

            {/* 其他声明 */}
            {otherClaims.length > 0 && (
                <div className={styles.section}>
                    <h3 className={styles.sectionTitle}>
                        ✓ 已验证的声明 ({otherClaims.length})
                    </h3>
                    {otherClaims.map(renderClaim)}
                </div>
            )}

            {/* 提交按钮 */}
            <div className={styles.actions}>
                <button
                    className="btn btn-primary"
                    onClick={() => onApprove(decisions, manualCorrections)}
                    disabled={!allDecided || isLoading}
                >
                    {isLoading ? '处理中...' : '确认并继续'}
                </button>
            </div>
        </div>
    );
}
