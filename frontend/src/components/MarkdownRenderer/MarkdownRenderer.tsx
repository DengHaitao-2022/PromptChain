'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './MarkdownRenderer.module.css';

function normalizeLooseMarkdown(content: string): string {
    // 兼容模型常见的非标准 strong 写法，避免 `** 标题**` 直接漏渲染。
    return content.replace(/(^|[\s(（])\*\*\s+([^*\n]+?)\s*\*\*/g, '$1**$2**');
}

interface MarkdownRendererProps {
    content: string;
    compact?: boolean;
    isStreaming?: boolean;
}

export function MarkdownRenderer({
    content,
    compact = false,
    isStreaming = false,
}: MarkdownRendererProps) {
    return (
        <div
            className={`${styles.markdown} ${compact ? styles.compact : ''} ${
                isStreaming ? styles.streaming : ''
            }`}
        >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {normalizeLooseMarkdown(content)}
            </ReactMarkdown>
        </div>
    );
}
