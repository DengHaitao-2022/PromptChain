'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { FileInput } from 'lucide-react';
import styles from './NodeStyles.module.css';

// 输入节点数据类型
export interface InputNodeData {
    label: string;
    config?: {
        promptTemplate?: string;
        maxTokens?: number;
    };
}

/**
 * 输入节点 - 用户意图解析
 * 颜色标识: 蓝色
 */
function InputNode({ data, selected }: NodeProps) {
    // 类型断言
    const nodeData = data as unknown as InputNodeData;

    return (
        <div className={`${styles.node} ${styles.inputNode} ${selected ? styles.selected : ''}`}>
            <div className={styles.nodeHeader}>
                <span className={styles.nodeIcon} aria-hidden="true">
                    <FileInput size={18} />
                </span>
                <span className={styles.nodeTitle}>{nodeData.label || '输入节点'}</span>
                <span className={styles.nodeType}>输入</span>
            </div>

            <div className={styles.nodeContent}>
                <p className={styles.nodeDescription}>工作流起点，解析用户意图</p>
                {nodeData.config?.promptTemplate && (
                    <div className={styles.preview}>
                        {nodeData.config.promptTemplate.substring(0, 50)}...
                    </div>
                )}
            </div>

            {/* 输出连接点 */}
            <Handle
                type="source"
                position={Position.Bottom}
                className={styles.handle}
            />
        </div>
    );
}

export default memo(InputNode);
