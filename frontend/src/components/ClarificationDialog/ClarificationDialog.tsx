'use client';

import React from 'react';
import {
    AlertTriangle,
    CheckCircle2,
    CircleHelp,
    Sparkles,
} from 'lucide-react';
import styles from './ClarificationDialog.module.css';
import type { ClarificationQuestion } from '@/lib/api';

interface ClarificationDialogProps {
    questions: ClarificationQuestion[];
    onSubmit: (answers: Record<string, string>) => void;
    isLoading?: boolean;
}

export function ClarificationDialog({
    questions,
    onSubmit,
    isLoading = false,
}: ClarificationDialogProps) {
    const [answers, setAnswers] = React.useState<Record<string, string>>({});
    const [focusedField, setFocusedField] = React.useState<string | null>(
        questions[0]?.field ?? null
    );

    React.useEffect(() => {
        if (!questions.some((question) => question.field === focusedField)) {
            setFocusedField(questions[0]?.field ?? null);
        }
    }, [focusedField, questions]);

    const updateAnswer = (field: string, value: string) => {
        setAnswers((current) => ({ ...current, [field]: value }));
    };

    const requiredQuestions = questions.filter((question) => question.priority === 'high');
    const answeredRequiredCount = requiredQuestions.filter((question) =>
        answers[question.field]?.trim()
    ).length;
    const requiredRemaining = requiredQuestions.length - answeredRequiredCount;
    const answeredCount = questions.filter((question) => answers[question.field]?.trim()).length;
    const progressPercent =
        questions.length > 0 ? Math.round((answeredCount / questions.length) * 100) : 0;
    const allAnswered = requiredRemaining === 0;

    const getPriorityText = (priority: ClarificationQuestion['priority']) => {
        switch (priority) {
            case 'high':
                return '必填';
            case 'medium':
                return '建议填写';
            default:
                return '可选';
        }
    };

    const handleSubmit = () => {
        if (allAnswered) {
            onSubmit(answers);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.summary}>
                <div className={styles.summaryCopy}>
                    <p className={styles.eyebrow}>需求澄清</p>
                    <h3 className={styles.title}>补全这轮工作流的关键上下文</h3>
                    <p className={styles.subtitle}>
                        这些问题会直接影响提纲质量和后续事实核查负担。先把关键信息补全，再让工作流继续推进。
                    </p>
                </div>

                <div className={styles.progressCard}>
                    <div className={styles.progressHeader}>
                        <div>
                            <span className={styles.progressValue}>
                                {answeredCount}/{questions.length}
                            </span>
                            <span className={styles.progressLabel}>已记录回答</span>
                        </div>
                        <div className={styles.progressMeta}>
                            {requiredRemaining > 0 ? (
                                <>
                                    <AlertTriangle
                                        className={styles.progressMetaIcon}
                                        aria-hidden="true"
                                    />
                                    还差 {requiredRemaining} 个必填问题
                                </>
                            ) : (
                                <>
                                    <CheckCircle2
                                        className={styles.progressMetaIcon}
                                        aria-hidden="true"
                                    />
                                    已满足继续条件
                                </>
                            )}
                        </div>
                    </div>
                    <div
                        className={styles.progressBar}
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={progressPercent}
                        aria-label="澄清问题完成进度"
                    >
                        <span
                            className={styles.progressFill}
                            style={{ width: `${progressPercent}%` }}
                        />
                    </div>
                </div>
            </div>

            <div className={styles.questions}>
                {questions.map((question, index) => {
                    const isFocused = focusedField === question.field;
                    const hasAnswer = Boolean(answers[question.field]?.trim());
                    const inputId = `clarification-${question.field}`;
                    const hintId = `${inputId}-hint`;

                    return (
                        <section
                            key={question.field}
                            className={`${styles.question} ${
                                question.priority === 'high'
                                    ? styles.questionHigh
                                    : question.priority === 'medium'
                                        ? styles.questionMedium
                                        : styles.questionLow
                            } ${isFocused ? styles.questionFocused : ''}`}
                        >
                            <div className={styles.questionHeader}>
                                <div className={styles.questionIndex}>{index + 1}</div>

                                <div className={styles.questionMeta}>
                                    <div className={styles.questionTopRow}>
                                        <label
                                            htmlFor={inputId}
                                            className={styles.questionText}
                                        >
                                            {question.question}
                                        </label>
                                        <span className={styles.priorityBadge}>
                                            {getPriorityText(question.priority)}
                                        </span>
                                    </div>

                                    <div className={styles.questionHintRow} id={hintId}>
                                        <span className={styles.questionHint}>
                                            <CircleHelp
                                                className={styles.inlineIcon}
                                                aria-hidden="true"
                                            />
                                            {question.priority === 'high'
                                                ? '继续生成前必须回答'
                                                : '补充越具体，后续输出越稳定'}
                                        </span>
                                        {question.default_assumption && (
                                            <span className={styles.defaultAssumption}>
                                                默认假设：{question.default_assumption}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <textarea
                                id={inputId}
                                className={`${styles.answerInput} input textarea`}
                                value={answers[question.field] || ''}
                                onChange={(event) =>
                                    updateAnswer(question.field, event.target.value)
                                }
                                onFocus={() => setFocusedField(question.field)}
                                placeholder="在这里补充你的上下文、偏好或限制条件..."
                                aria-describedby={hintId}
                                disabled={isLoading}
                            />

                            <div className={styles.answerFooter}>
                                <span className={styles.answerStatus}>
                                    {hasAnswer ? (
                                        <>
                                            <CheckCircle2
                                                className={styles.inlineIcon}
                                                aria-hidden="true"
                                            />
                                            已记录本题回答
                                        </>
                                    ) : (
                                        <>
                                            <Sparkles
                                                className={styles.inlineIcon}
                                                aria-hidden="true"
                                            />
                                            当前为空，可继续编辑
                                        </>
                                    )}
                                </span>
                            </div>
                        </section>
                    );
                })}
            </div>

            <div className={styles.actions}>
                <p className={styles.hint} aria-live="polite">
                    {requiredRemaining > 0
                        ? `还有 ${requiredRemaining} 个必填问题未完成。`
                        : '关键问题已完成，可以继续生成。'}
                </p>
                <button
                    className="btn btn-primary"
                    onClick={handleSubmit}
                    disabled={!allAnswered || isLoading}
                >
                    {isLoading ? '正在提交...' : '确认并继续'}
                </button>
            </div>
        </div>
    );
}
