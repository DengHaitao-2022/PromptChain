'use client';

import React from 'react';
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

    // 更新答案
    const updateAnswer = (field: string, value: string) => {
        setAnswers({ ...answers, [field]: value });
    };

    // 检查是否所有必填项都已回答
    const allAnswered = (questions || [])
        .filter((q) => q.priority === 'high')
        .every((q) => answers[q.field]?.trim());

    // 提交答案
    const handleSubmit = () => {
        if (allAnswered) {
            onSubmit(answers);
        }
    };

    // 优先级颜色
    const getPriorityColor = (priority: string) => {
        switch (priority) {
            case 'high':
                return 'danger';
            case 'medium':
                return 'warning';
            default:
                return 'info';
        }
    };

    // 优先级文本
    const getPriorityText = (priority: string) => {
        switch (priority) {
            case 'high':
                return '必填';
            case 'medium':
                return '建议填写';
            default:
                return '可选';
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div className={styles.icon}>💬</div>
                <div>
                    <h3 className={styles.title}>需要您的确认</h3>
                    <p className={styles.subtitle}>
                        为了更好地理解您的需求，请回答以下问题
                    </p>
                </div>
            </div>

            <div className={styles.questions}>
                {(questions || []).map((q, index) => (
                    <div key={q.field} className={styles.question}>
                        <div className={styles.questionHeader}>
                            <span className={styles.questionNumber}>{index + 1}</span>
                            <span className={styles.questionText}>{q.question}</span>
                            <span className={`badge badge-${getPriorityColor(q.priority)}`}>
                                {getPriorityText(q.priority)}
                            </span>
                        </div>
                        <textarea
                            className={`${styles.answerInput} input textarea`}
                            value={answers[q.field] || ''}
                            onChange={(e) => updateAnswer(q.field, e.target.value)}
                            placeholder="请输入您的回答..."
                            disabled={isLoading}
                        />
                    </div>
                ))}
            </div>

            <div className={styles.actions}>
                <p className={styles.hint}>
                    带有 <span className="badge badge-danger">必填</span> 标签的问题需要回答后才能继续
                </p>
                <button
                    className="btn btn-primary"
                    onClick={handleSubmit}
                    disabled={!allAnswered || isLoading}
                >
                    {isLoading ? '处理中...' : '确认并继续'}
                </button>
            </div>
        </div>
    );
}
