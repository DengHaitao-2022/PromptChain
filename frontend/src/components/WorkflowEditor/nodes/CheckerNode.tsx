'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { ShieldCheck } from 'lucide-react';
import styles from './NodeStyles.module.css';

// 核查节点数据类型
export interface CheckerNodeData {
    label: string;
    config?: {
        confidenceThreshold?: number;
        riskLevels?: ('low' | 'medium' | 'high')[];
        autoApprove?: boolean;
    };
}

/**
 * 核查节点 - 事实核查与置信度检测
 * 颜色标识: 橙色
 */
function CheckerNode({ data, selected }: NodeProps) {
    // 类型断言
    const nodeData = data as unknown as CheckerNodeData;

    return (
        <div className={`${styles.node} ${styles.checkerNode} ${selected ? styles.selected : ''}`}>
            {/* 输入连接点 */}
            <Handle
                type="target"
                position={Position.Top}
                className={styles.handle}
            />

            <div className={styles.nodeHeader}>
                <ShieldCheck size={16} />
                <span>{nodeData.label || '核查节点'}</span>
            </div>

            <div className={styles.nodeContent}>
                {nodeData.config?.confidenceThreshold && (
                    <div className={styles.badge}>
                        阈值: {(nodeData.config.confidenceThreshold * 100).toFixed(0)}%
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

export default memo(CheckerNode);
