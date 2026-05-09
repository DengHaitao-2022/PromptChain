'use client';

import React from 'react';
import {
    AlertTriangle,
    CheckCircle2,
    FileWarning,
    ShieldCheck,
    SquarePen,
    WandSparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import styles from './FactCheckViewer.module.css';
import type { FactCheckReport, FactClaim, VerificationResult } from '@/lib/api';

type Decision = 'confirm' | 'use_suggestion' | 'manual';

interface FactCheckViewerProps {
    report: FactCheckReport;
    onApprove: (
        decisions: Record<string, Decision>,
        manualCorrections: Record<string, string>
    ) => void;
    isLoading?: boolean;
}

interface DecisionOption {
    value: Decision;
    label: string;
    description: string;
    icon: LucideIcon;
    requiresSuggestion?: boolean;
}

const DECISION_OPTIONS: DecisionOption[] = [
    {
        value: 'confirm',
        label: '确认无误',
        description: '保留当前表述，继续进入下一步。',
        icon: ShieldCheck,
    },
    {
        value: 'use_suggestion',
        label: '采用建议修正',
        description: '直接使用系统给出的推荐修正。',
        icon: WandSparkles,
        requiresSuggestion: true,
    },
    {
        value: 'manual',
        label: '手动修正',
        description: '针对该声明输入你的最终版本。',
        icon: SquarePen,
    },
];

export function FactCheckViewer({
    report,
    onApprove,
    isLoading = false,
}: FactCheckViewerProps) {
    const [decisions, setDecisions] = React.useState<Record<string, Decision>>({});
    const [manualCorrections, setManualCorrections] = React.useState<Record<string, string>>({});

    const getResult = (claimId: string): VerificationResult | undefined =>
        report.results.find((result) => result.claim_id === claimId);

    const highRiskClaims = report.claims.filter(
        (claim) => getResult(claim.id)?.risk_level === 'high'
    );
    const otherClaims = report.claims.filter(
        (claim) => getResult(claim.id)?.risk_level !== 'high'
    );
    const reviewClaims = highRiskClaims.length > 0 ? highRiskClaims : report.claims;

    const [selectedClaimId, setSelectedClaimId] = React.useState<string>(
        reviewClaims[0]?.id ?? ''
    );

    React.useEffect(() => {
        if (!reviewClaims.some((claim) => claim.id === selectedClaimId)) {
            setSelectedClaimId(reviewClaims[0]?.id ?? '');
        }
    }, [reviewClaims, selectedClaimId]);

    const selectedClaim = reviewClaims.find((claim) => claim.id === selectedClaimId);
    const selectedResult = selectedClaim ? getResult(selectedClaim.id) : undefined;

    const setDecision = (claimId: string, decision: Decision) => {
        setDecisions((current) => ({ ...current, [claimId]: decision }));
    };

    const setManualCorrection = (claimId: string, correction: string) => {
        setManualCorrections((current) => ({ ...current, [claimId]: correction }));
    };

    const getRiskText = (level: VerificationResult['risk_level']) => {
        switch (level) {
            case 'high':
                return '高风险';
            case 'medium':
                return '中风险';
            default:
                return '低风险';
        }
    };

    const getCurrentDecision = (claimId: string, result?: VerificationResult) => {
        if (!result) {
            return '';
        }

        return decisions[claimId] || (result.risk_level === 'high' ? '' : 'confirm');
    };

    const isClaimResolved = (claim: FactClaim) => {
        const result = getResult(claim.id);
        if (!result) {
            return false;
        }

        if (result.risk_level !== 'high') {
            return true;
        }

        const decision = decisions[claim.id];
        if (!decision) {
            return false;
        }

        if (decision === 'manual') {
            return Boolean(manualCorrections[claim.id]?.trim());
        }

        return true;
    };

    const resolvedHighRiskCount = highRiskClaims.filter(isClaimResolved).length;
    const reviewProgress =
        highRiskClaims.length > 0
            ? Math.round((resolvedHighRiskCount / highRiskClaims.length) * 100)
            : 100;

    const allDecided = highRiskClaims.every((claim) => isClaimResolved(claim));
    const currentDecision = selectedClaim
        ? getCurrentDecision(selectedClaim.id, selectedResult)
        : '';

    return (
        <div className={styles.container}>
            <div className={styles.summary}>
                <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>总声明数</span>
                    <strong className={styles.summaryValue}>{report.total_claims}</strong>
                </div>
                <div className={styles.summaryCard}>
                    <span className={styles.summaryLabel}>已验证</span>
                    <strong className={styles.summaryValue}>{report.verified_count}</strong>
                </div>
                <div className={`${styles.summaryCard} ${styles.summaryCardWarning}`}>
                    <span className={styles.summaryLabel}>高风险待处理</span>
                    <strong className={styles.summaryValue}>{report.high_risk_count}</strong>
                </div>
            </div>

            <div className={styles.reviewWorkbench}>
                <div className={styles.reviewRail}>
                    <div className={styles.railHeader}>
                        <div>
                            <p className={styles.railEyebrow}>风险队列</p>
                            <h3 className={styles.railTitle}>优先处理高风险声明</h3>
                        </div>
                        <span className={styles.railMeta}>
                            {highRiskClaims.length > 0
                                ? `${resolvedHighRiskCount}/${highRiskClaims.length} 已完成`
                                : '当前没有高风险声明'}
                        </span>
                    </div>

                    <div className={styles.claimList}>
                        {reviewClaims.map((claim, index) => {
                            const result = getResult(claim.id);
                            if (!result) {
                                return null;
                            }

                            const isActive = selectedClaimId === claim.id;
                            const isResolved = isClaimResolved(claim);

                            return (
                                <button
                                    key={claim.id}
                                    type="button"
                                    className={`${styles.claimItem} ${
                                        isActive ? styles.claimItemActive : ''
                                    } ${isResolved ? styles.claimItemResolved : ''}`}
                                    onClick={() => setSelectedClaimId(claim.id)}
                                >
                                    <div className={styles.claimItemTop}>
                                        <span className={styles.claimIndex}>
                                            {String(index + 1).padStart(2, '0')}
                                        </span>
                                        <span
                                            className={`${styles.riskBadge} ${
                                                result.risk_level === 'high'
                                                    ? styles.riskHigh
                                                    : result.risk_level === 'medium'
                                                        ? styles.riskMedium
                                                        : styles.riskLow
                                            }`}
                                        >
                                            {getRiskText(result.risk_level)}
                                        </span>
                                    </div>
                                    <p className={styles.claimSnippet}>{claim.text}</p>
                                    <div className={styles.claimItemBottom}>
                                        <span className={styles.claimCategory}>
                                            {claim.category}
                                        </span>
                                        <span className={styles.claimState}>
                                            {isResolved ? (
                                                <>
                                                    <CheckCircle2
                                                        className={styles.inlineIcon}
                                                        aria-hidden="true"
                                                    />
                                                    已处理
                                                </>
                                            ) : (
                                                <>
                                                    <AlertTriangle
                                                        className={styles.inlineIcon}
                                                        aria-hidden="true"
                                                    />
                                                    待决策
                                                </>
                                            )}
                                        </span>
                                    </div>
                                </button>
                            );
                        })}
                    </div>

                    {otherClaims.length > 0 && highRiskClaims.length > 0 && (
                        <details className={styles.autoPassPanel}>
                            <summary>
                                已自动通过 {otherClaims.length} 条中低风险声明
                            </summary>
                            <div className={styles.autoPassList}>
                                {otherClaims.map((claim) => (
                                    <div key={claim.id} className={styles.autoPassItem}>
                                        <ShieldCheck
                                            className={styles.inlineIcon}
                                            aria-hidden="true"
                                        />
                                        <span>{claim.text}</span>
                                    </div>
                                ))}
                            </div>
                        </details>
                    )}
                </div>

                <div className={styles.detailPanel}>
                    {selectedClaim && selectedResult ? (
                        <>
                            <div className={styles.detailHeader}>
                                <div>
                                    <p className={styles.detailEyebrow}>声明审阅</p>
                                    <h3 className={styles.detailTitle}>当前审阅项</h3>
                                </div>
                                <div
                                    className={`${styles.riskBadge} ${
                                        selectedResult.risk_level === 'high'
                                            ? styles.riskHigh
                                            : selectedResult.risk_level === 'medium'
                                                ? styles.riskMedium
                                                : styles.riskLow
                                    }`}
                                >
                                    {getRiskText(selectedResult.risk_level)}
                                </div>
                            </div>

                            <div className={styles.detailSection}>
                                <span className={styles.sectionLabel}>原始声明</span>
                                <p className={styles.claimText}>{selectedClaim.text}</p>
                                <div className={styles.claimMeta}>
                                    <span>{selectedClaim.category}</span>
                                    <span>
                                        置信度 {Math.round(selectedResult.confidence * 100)}%
                                    </span>
                                </div>
                            </div>

                            <div className={styles.detailGrid}>
                                <div className={styles.detailCard}>
                                    <span className={styles.sectionLabel}>验证问题</span>
                                    <p>{selectedResult.verification_question}</p>
                                </div>
                                <div className={styles.detailCard}>
                                    <span className={styles.sectionLabel}>验证结论</span>
                                    <p>{selectedResult.verification_answer}</p>
                                </div>
                            </div>

                            {selectedResult.suggested_correction && (
                                <div className={styles.suggestionCard}>
                                    <WandSparkles
                                        className={styles.suggestionIcon}
                                        aria-hidden="true"
                                    />
                                    <div>
                                        <span className={styles.sectionLabel}>建议修正</span>
                                        <p>{selectedResult.suggested_correction}</p>
                                    </div>
                                </div>
                            )}

                            <fieldset className={styles.decisionSection}>
                                <legend className={styles.decisionLegend}>处理方式</legend>

                                <div className={styles.optionGrid}>
                                    {DECISION_OPTIONS.filter(
                                        (option) =>
                                            !option.requiresSuggestion ||
                                            Boolean(selectedResult.suggested_correction)
                                    ).map((option) => {
                                        const Icon = option.icon;
                                        const active = currentDecision === option.value;

                                        return (
                                            <label
                                                key={option.value}
                                                className={`${styles.optionCard} ${
                                                    active ? styles.optionCardActive : ''
                                                }`}
                                            >
                                                <input
                                                    type="radio"
                                                    name={`decision-${selectedClaim.id}`}
                                                    checked={active}
                                                    onChange={() =>
                                                        setDecision(
                                                            selectedClaim.id,
                                                            option.value
                                                        )
                                                    }
                                                    disabled={isLoading}
                                                />
                                                <span className={styles.optionIconWrap}>
                                                    <Icon
                                                        className={styles.optionIcon}
                                                        aria-hidden="true"
                                                    />
                                                </span>
                                                <span className={styles.optionCopy}>
                                                    <strong>{option.label}</strong>
                                                    <span>{option.description}</span>
                                                </span>
                                            </label>
                                        );
                                    })}
                                </div>

                                {currentDecision === 'manual' && (
                                    <div className={styles.manualSection}>
                                        <label
                                            htmlFor={`manual-${selectedClaim.id}`}
                                            className={styles.sectionLabel}
                                        >
                                            手动修正文案
                                        </label>
                                        <textarea
                                            id={`manual-${selectedClaim.id}`}
                                            className={`${styles.manualInput} input textarea`}
                                            value={manualCorrections[selectedClaim.id] || ''}
                                            onChange={(event) =>
                                                setManualCorrection(
                                                    selectedClaim.id,
                                                    event.target.value
                                                )
                                            }
                                            placeholder="请输入你确认后的最终表述..."
                                            disabled={isLoading}
                                        />
                                    </div>
                                )}
                            </fieldset>
                        </>
                    ) : (
                        <div className={styles.emptyDetail}>
                            <FileWarning
                                className={styles.emptyDetailIcon}
                                aria-hidden="true"
                            />
                            <div>
                                <h3>暂无可审阅项</h3>
                                <p>当前没有 claim 详情可以显示，请检查报告结构。</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className={styles.actions}>
                <div className={styles.actionSummary}>
                    <p className={styles.hint} aria-live="polite">
                        {highRiskClaims.length > 0
                            ? `高风险项已处理 ${resolvedHighRiskCount}/${highRiskClaims.length} 条。`
                            : '当前没有高风险项，可以直接继续。'}
                    </p>
                    <div
                        className={styles.progressTrack}
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={reviewProgress}
                        aria-label="高风险声明处理进度"
                    >
                        <span
                            className={styles.progressFill}
                            style={{ width: `${reviewProgress}%` }}
                        />
                    </div>
                </div>

                <button
                    className="btn btn-primary"
                    onClick={() => onApprove(decisions, manualCorrections)}
                    disabled={!allDecided || isLoading}
                >
                    {isLoading ? '正在提交审阅结果...' : '确认并继续'}
                </button>
            </div>
        </div>
    );
}
