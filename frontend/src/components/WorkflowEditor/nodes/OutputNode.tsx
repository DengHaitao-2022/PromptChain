'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { FileOutput } from 'lucide-react';
import styles from './NodeStyles.module.css';

// 输出节点数据类型
export interface OutputNodeData {
    label: string;
    config?: {
        outputFormat?: 'text' | 'markdown' | 'json';
        saveTo?: string;
    };
}

/**
 * 输出节点 - 最终结果输出
 * 颜色标识: 紫色
 */
function OutputNode({ data, selected }: NodeProps) {
    // 类型断言
    const nodeData = data as unknown as OutputNodeData;

    return (
        <div className={`${styles.node} ${styles.outputNode} ${selected ? styles.selected : ''}`}>
            {/* 输入连接点 */}
            <Handle
                type="target"
                position={Position.Top}
                className={styles.handle}
            />

            <div className={styles.nodeHeader}>
                <FileOutput size={16} />
                <span>{nodeData.label || '输出节点'}</span>
            </div>

            <div className={styles.nodeContent}>
                {nodeData.config?.outputFormat && (
                    <div className={styles.badge}>
                        {nodeData.config.outputFormat.toUpperCase()}
                    </div>
                )}
            </div>
        </div>
    );
}

export default memo(OutputNode);
