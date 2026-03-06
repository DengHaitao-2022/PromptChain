'use client';

import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import styles from './OutlineEditor.module.css';
import type { Outline, OutlineSection } from '@/lib/api';

interface OutlineEditorProps {
    outline: Outline;
    onApprove: () => void;
    onModify: (modifiedOutline: Outline) => void;
    onRegenerate: (feedback: string) => void;
    isLoading?: boolean;
}

export function OutlineEditor({
    outline,
    onApprove,
    onModify,
    onRegenerate,
    isLoading = false,
}: OutlineEditorProps) {
    const [editedOutline, setEditedOutline] = React.useState<Outline>(outline);
    const [showFeedbackDialog, setShowFeedbackDialog] = React.useState(false);
    const [feedback, setFeedback] = React.useState('');
    const [isEditing, setIsEditing] = React.useState(false);

    // 更新章节标题
    const updateSectionTitle = (sectionId: string, newTitle: string) => {
        const updateSection = (sections: OutlineSection[]): OutlineSection[] => {
            return sections.map((section) => {
                if (section.id === sectionId) {
                    return { ...section, title: newTitle };
                }
                if (section.subsections.length > 0) {
                    return { ...section, subsections: updateSection(section.subsections) };
                }
                return section;
            });
        };

        setEditedOutline({
            ...editedOutline,
            sections: updateSection(editedOutline.sections),
        });
        setIsEditing(true);
    };

    // 更新章节摘要
    const updateSectionSummary = (sectionId: string, newSummary: string) => {
        const updateSection = (sections: OutlineSection[]): OutlineSection[] => {
            return sections.map((section) => {
                if (section.id === sectionId) {
                    return { ...section, summary: newSummary };
                }
                if (section.subsections.length > 0) {
                    return { ...section, subsections: updateSection(section.subsections) };
                }
                return section;
            });
        };

        setEditedOutline({
            ...editedOutline,
            sections: updateSection(editedOutline.sections),
        });
        setIsEditing(true);
    };

    // 渲染章节
    const renderSection = (section: OutlineSection, depth: number = 0) => (
        <div
            key={section.id}
            className={styles.section}
            style={{ marginLeft: depth * 24 }}
        >
            <div className={styles.sectionHeader}>
                <input
                    type="text"
                    className={styles.sectionTitle}
                    value={section.title}
                    onChange={(e) => updateSectionTitle(section.id, e.target.value)}
                    disabled={isLoading}
                />
                <span className={styles.wordCount}>{section.target_words} 字</span>
            </div>
            <textarea
                className={styles.sectionSummary}
                value={section.summary}
                onChange={(e) => updateSectionSummary(section.id, e.target.value)}
                placeholder="章节摘要..."
                disabled={isLoading}
            />
            {section.subsections.map((sub) => renderSection(sub, depth + 1))}
        </div>
    );

    return (
        <div className={styles.container}>
            {/* 标题 */}
            <div className={styles.header}>
                <div className={styles.titleSection}>
                    <input
                        type="text"
                        className={styles.mainTitle}
                        value={editedOutline.title}
                        onChange={(e) => {
                            setEditedOutline({ ...editedOutline, title: e.target.value });
                            setIsEditing(true);
                        }}
                        placeholder="文章标题"
                        disabled={isLoading}
                    />
                    <span className={`badge badge-info`}>v{editedOutline.version}</span>
                </div>
                <p className={styles.wordTotal}>
                    总字数目标: {editedOutline.total_target_words} 字
                </p>
            </div>

            {/* 摘要 */}
            <div className={styles.abstractSection}>
                <label className={styles.label}>文章摘要</label>
                <textarea
                    className={styles.abstract}
                    value={editedOutline.abstract}
                    onChange={(e) => {
                        setEditedOutline({ ...editedOutline, abstract: e.target.value });
                        setIsEditing(true);
                    }}
                    placeholder="文章概述..."
                    disabled={isLoading}
                />
            </div>

            {/* 章节列表 */}
            <div className={styles.sectionsContainer}>
                <label className={styles.label}>章节结构</label>
                {editedOutline.sections.map((section) => renderSection(section))}
            </div>

            {/* 操作按钮 */}
            <div className={styles.actions}>
                <button
                    className="btn btn-ghost"
                    onClick={() => setShowFeedbackDialog(true)}
                    disabled={isLoading}
                >
                    🔄 重新生成
                </button>

                {isEditing ? (
                    <button
                        className="btn btn-primary"
                        onClick={() => onModify(editedOutline)}
                        disabled={isLoading}
                    >
                        {isLoading ? '保存中...' : '保存修改'}
                    </button>
                ) : (
                    <button
                        className="btn btn-primary"
                        onClick={onApprove}
                        disabled={isLoading}
                    >
                        {isLoading ? '处理中...' : '✓ 确认提纲'}
                    </button>
                )}
            </div>

            {/* 重新生成对话框 */}
            <Dialog.Root open={showFeedbackDialog} onOpenChange={setShowFeedbackDialog}>
                <Dialog.Portal>
                    <Dialog.Overlay className={styles.dialogOverlay} />
                    <Dialog.Content className={styles.dialogContent}>
                        <Dialog.Title className={styles.dialogTitle}>
                            重新生成提纲
                        </Dialog.Title>
                        <Dialog.Description className={styles.dialogDescription}>
                            请描述您希望如何调整提纲结构
                        </Dialog.Description>

                        <textarea
                            className={`${styles.feedbackInput} input textarea`}
                            value={feedback}
                            onChange={(e) => setFeedback(e.target.value)}
                            placeholder="例如：请增加一个关于实战案例的章节，并减少理论部分的篇幅..."
                        />

                        <div className={styles.dialogActions}>
                            <Dialog.Close asChild>
                                <button className="btn btn-secondary">取消</button>
                            </Dialog.Close>
                            <button
                                className="btn btn-primary"
                                onClick={() => {
                                    onRegenerate(feedback);
                                    setShowFeedbackDialog(false);
                                    setFeedback('');
                                }}
                                disabled={!feedback.trim()}
                            >
                                重新生成
                            </button>
                        </div>
                    </Dialog.Content>
                </Dialog.Portal>
            </Dialog.Root>
        </div>
    );
}
