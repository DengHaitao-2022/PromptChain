'use client';

import React from 'react';
import {
    Target,
    Pin,
    Users,
    Tag,
    Palette,
    Ruler,
    CheckCircle,
    XCircle,
    AlertTriangle,
} from 'lucide-react';
import styles from './IntentCardViewer.module.css';
import type { IntentCard } from '@/lib/api';

interface IntentCardViewerProps {
    intentCard: IntentCard;
}

export function IntentCardViewer({
    intentCard,
}: IntentCardViewerProps) {
    // 获取优先级颜色
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

    // 字段配置
    const fields = [
        { key: 'goal', label: '目标', icon: <Target className={styles.fieldIconSvg} /> },
        { key: 'topic', label: '主题', icon: <Pin className={styles.fieldIconSvg} /> },
        { key: 'audience', label: '目标读者', icon: <Users className={styles.fieldIconSvg} /> },
        { key: 'scenario', label: '使用场景', icon: <Tag className={styles.fieldIconSvg} /> },
        { key: 'tone', label: '语气风格', icon: <Palette className={styles.fieldIconSvg} /> },
        { key: 'length', label: '目标字数', icon: <Ruler className={styles.fieldIconSvg} />, format: (v: number) => `${v.toLocaleString()} 字` },
    ];

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h3 className={styles.title}>意图卡</h3>
                <span className="badge badge-success">已解析</span>
            </div>

            {/* 主要字段 */}
            <div className={styles.fields}>
                {fields.map(({ key, label, icon, format }) => {
                    const value = intentCard[key as keyof IntentCard];
                    const displayValue = format
                        ? format(value as number)
                        : String(value || '-');

                    return (
                        <div key={key} className={styles.field}>
                            <span className={styles.fieldIcon}>{icon}</span>
                            <div className={styles.fieldContent}>
                                <span className={styles.fieldLabel}>{label}</span>
                                <span className={styles.fieldValue}>{displayValue}</span>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* 必须包含 */}
            {intentCard.must_include.length > 0 && (
                <div className={styles.tagSection}>
                    <span className={styles.tagLabel}>
                        <CheckCircle className={styles.tagIcon} /> 必须包含
                    </span>
                    <div className={styles.tags}>
                        {intentCard.must_include.map((item, index) => (
                            <span key={index} className={`${styles.tag} ${styles.tagInclude}`}>
                                {item}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* 必须排除 */}
            {intentCard.must_exclude.length > 0 && (
                <div className={styles.tagSection}>
                    <span className={styles.tagLabel}>
                        <XCircle className={styles.tagIcon} /> 必须排除
                    </span>
                    <div className={styles.tags}>
                        {intentCard.must_exclude.map((item, index) => (
                            <span key={index} className={`${styles.tag} ${styles.tagExclude}`}>
                                {item}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* 待澄清项 */}
            {intentCard.clarification_questions && intentCard.clarification_questions.length > 0 && (
                <div className={styles.uncertainties}>
                    <span className={styles.tagLabel}>
                        <AlertTriangle className={styles.tagIcon} /> 待澄清事项
                    </span>
                    <div className={styles.uncertaintyList}>
                        {intentCard.clarification_questions.map((q, index) => (
                            <div key={index} className={styles.uncertaintyItem}>
                                <span className={`badge badge-${getPriorityColor(q.priority)}`}>
                                    {q.priority === 'high' ? '必填' : q.priority === 'medium' ? '建议' : '可选'}
                                </span>
                                <span className={styles.uncertaintyField}>{q.field}</span>
                                <span className={styles.uncertaintyQuestion}>{q.question}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
