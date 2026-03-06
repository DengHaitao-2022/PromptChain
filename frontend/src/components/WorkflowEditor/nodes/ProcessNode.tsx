'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Cpu } from 'lucide-react';
import styles from './NodeStyles.module.css';

// 处理节点数据类型
export interface ProcessNodeData {
    label: string;
    config?: {
        promptTemplate?: string;
        modelName?: string;
        maxTokens?: number;
        temperature?: number;
    };
}

/**
 * 处理节点 - LLM处理
 * 颜色标识: 绿色
 */
function ProcessNode({ data, selected }: NodeProps) {
    // 类型断言
    const nodeData = data as unknown as ProcessNodeData;

    return (
        <div className={`${styles.node} ${styles.processNode} ${selected ? styles.selected : ''}`}>
            {/* 输入连接点 */}
            <Handle
                type="target"
                position={Position.Top}
                className={styles.handle}
            />

            <div className={styles.nodeHeader}>
                <Cpu size={16} />
                <span>{nodeData.label || '处理节点'}</span>
            </div>

            <div className={styles.nodeContent}>
                {nodeData.config?.modelName && (
                    <div className={styles.badge}>
                        {nodeData.config.modelName}
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

export default memo(ProcessNode);
