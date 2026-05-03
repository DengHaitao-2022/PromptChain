'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { UserCheck } from 'lucide-react';
import styles from './NodeStyles.module.css';

// 门控节点数据类型
export interface GateNodeData {
    label: string;
    config?: {
        gateType: 'approval' | 'edit' | 'input';
        approvers?: string[];
        approvalMode?: 'any' | 'all';
        timeout?: number;
        timeoutAction?: 'auto_approve' | 'auto_reject' | 'escalate';
        autoApproveThreshold?: number;
        skipIfConfident?: boolean;
    };
}

/**
 * 门控节点 - 人机交互审批
 * 颜色标识: 黄色
 */
function GateNode({ data, selected }: NodeProps) {
    // 类型断言
    const nodeData = data as unknown as GateNodeData;

    const gateTypeLabels: Record<string, string> = {
        approval: '审批',
        edit: '编辑',
        input: '输入',
    };

    return (
        <div className={`${styles.node} ${styles.gateNode} ${selected ? styles.selected : ''}`}>
            {/* 输入连接点 */}
            <Handle
                type="target"
                position={Position.Top}
                className={styles.handle}
            />

            <div className={styles.nodeHeader}>
                <span className={styles.nodeIcon} aria-hidden="true">
                    <UserCheck size={18} />
                </span>
                <span className={styles.nodeTitle}>{nodeData.label || '门控节点'}</span>
                <span className={styles.nodeType}>门控</span>
            </div>

            <div className={styles.nodeContent}>
                <p className={styles.nodeDescription}>人机交互审批与编辑</p>
                {nodeData.config?.gateType && (
                    <div className={styles.badge}>
                        {gateTypeLabels[nodeData.config.gateType] || nodeData.config.gateType}
                    </div>
                )}
                {nodeData.config?.timeout && (
                    <div className={styles.hint}>
                        超时: {Math.floor(nodeData.config.timeout / 60)}分钟
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

export default memo(GateNode);
