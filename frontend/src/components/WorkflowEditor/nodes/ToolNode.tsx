'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Wrench } from 'lucide-react';
import styles from './NodeStyles.module.css';

export interface ToolNodeData {
    label: string;
    config?: {
        toolName?: string;
        executionPhase?: string;
        approvalMode?: string;
        failureStrategy?: string;
    };
}

const phaseLabels: Record<string, string> = {
    pre_outline: '提纲前',
    post_content: '正文后',
    pre_finalize: '收尾前',
};

function ToolNode({ data, selected }: NodeProps) {
    const nodeData = data as unknown as ToolNodeData;
    const toolName = nodeData.config?.toolName;
    const phase = nodeData.config?.executionPhase;

    return (
        <div className={`${styles.node} ${styles.toolNode} ${selected ? styles.selected : ''}`}>
            <Handle
                type="target"
                position={Position.Top}
                className={styles.handle}
            />

            <div className={styles.nodeHeader}>
                <span className={styles.nodeIcon} aria-hidden="true">
                    <Wrench size={18} />
                </span>
                <span className={styles.nodeTitle}>{nodeData.label || '工具节点'}</span>
                <span className={styles.nodeType}>工具</span>
            </div>

            <div className={styles.nodeContent}>
                <p className={styles.nodeDescription}>调用 Tool Registry 中的受控工具</p>
                {toolName ? (
                    <div className={styles.badge}>
                        {toolName}
                    </div>
                ) : null}
                {phase ? (
                    <span className={styles.hint}>
                        执行阶段：{phaseLabels[phase] || phase}
                    </span>
                ) : null}
            </div>

            <Handle
                type="source"
                position={Position.Bottom}
                className={styles.handle}
            />
        </div>
    );
}

export default memo(ToolNode);
