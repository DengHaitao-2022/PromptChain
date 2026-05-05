'use client';

import React from 'react';
import { FileText, BarChart2, Pencil } from 'lucide-react';
import styles from './ContentViewer.module.css';

interface ContentSection {
    id: string;
    title: string;
    content: string;
    wordCount: number;
}

interface ContentViewerProps {
    title: string;
    abstract?: string;
    sections: ContentSection[];
    onSectionEdit?: (sectionId: string, newContent: string) => void;
    onExport?: (format: 'markdown' | 'html' | 'json') => void;
    isEditable?: boolean;
    isStreaming?: boolean;
}

export function ContentViewer({
    title,
    abstract,
    sections,
    onSectionEdit,
    onExport,
    isEditable = false,
    isStreaming = false,
}: ContentViewerProps) {
    const [editingSection, setEditingSection] = React.useState<string | null>(null);
    const [editContent, setEditContent] = React.useState('');

    // 计算总字数
    const totalWords = sections.reduce((sum, s) => sum + s.wordCount, 0);

    // 开始编辑
    const startEdit = (section: ContentSection) => {
        setEditingSection(section.id);
        setEditContent(section.content);
    };

    // 保存编辑
    const saveEdit = (sectionId: string) => {
        onSectionEdit?.(sectionId, editContent);
        setEditingSection(null);
        setEditContent('');
    };

    // 取消编辑
    const cancelEdit = () => {
        setEditingSection(null);
        setEditContent('');
    };

    return (
        <div className={styles.container}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.titleSection}>
                    <h1 className={styles.title}>{title}</h1>
                    <div className={styles.stats}>
                        <span className={styles.stat}>
                            <FileText className={styles.statIcon} /> {sections.length} 个章节
                        </span>
                        <span className={styles.stat}>
                            <BarChart2 className={styles.statIcon} /> {totalWords.toLocaleString()} 字
                        </span>
                    </div>
                </div>
                {onExport && (
                    <div className={styles.exportButtons}>
                        <button
                            className="btn btn-secondary"
                            onClick={() => onExport('markdown')}
                        >
                            导出 Markdown
                        </button>
                        <button
                            className="btn btn-secondary"
                            onClick={() => onExport('html')}
                        >
                            导出 HTML
                        </button>
                    </div>
                )}
            </div>

            {/* Abstract */}
            {abstract && (
                <div className={styles.abstract}>
                    <h4 className={styles.abstractLabel}>摘要</h4>
                    <p>{abstract}</p>
                </div>
            )}

            {/* Table of Contents */}
            <div className={styles.toc}>
                <h4 className={styles.tocLabel}>目录</h4>
                <ul className={styles.tocList}>
                    {sections.map((section, index) => (
                        <li key={section.id}>
                            <a href={`#section-${section.id}`} className={styles.tocLink}>
                                {index + 1}. {section.title}
                            </a>
                            <span className={styles.tocWordCount}>{section.wordCount} 字</span>
                        </li>
                    ))}
                </ul>
            </div>

            {/* Sections */}
            <div className={styles.content}>
                {sections.map((section, index) => (
                    <div
                        key={section.id}
                        id={`section-${section.id}`}
                        className={styles.section}
                    >
                        <div className={styles.sectionHeader}>
                            <h2 className={styles.sectionTitle}>
                                {index + 1}. {section.title}
                            </h2>
                            {isEditable && editingSection !== section.id && (
                                <button
                                    className="btn btn-ghost"
                                    onClick={() => startEdit(section)}
                                >
                                    <Pencil className={styles.editIcon} /> 编辑
                                </button>
                            )}
                        </div>

                        {editingSection === section.id ? (
                            <div className={styles.editArea}>
                                <textarea
                                    className={`${styles.editTextarea} input textarea`}
                                    value={editContent}
                                    onChange={(e) => setEditContent(e.target.value)}
                                />
                                <div className={styles.editActions}>
                                    <button className="btn btn-ghost" onClick={cancelEdit}>
                                        取消
                                    </button>
                                    <button
                                        className="btn btn-primary"
                                        onClick={() => saveEdit(section.id)}
                                    >
                                        保存
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div
                                className={`${styles.sectionContent} ${
                                    isStreaming && index === sections.length - 1
                                        ? styles.streaming
                                        : ''
                                }`}
                            >
                                {section.content
                                    .split(/\n{2,}/)
                                    .filter((paragraph) => paragraph.trim())
                                    .map((paragraph, pIndex) => (
                                        <p key={pIndex}>{paragraph}</p>
                                    ))}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
