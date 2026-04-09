/**
 * 领域模型 - 结构约束
 * 为什么这样分层：定义一些核心的节点配置验证或 Schema。如果有复杂的 Yjs / JSON Schema 或者 Zod 约束，都收敛在这里。
 */

import { type NodeType } from './types';

export const SUPPORTED_NODE_TYPES: NodeType[] = [
    'input',
    'process',
    'gate',
    'checker',
    'output',
];

export function isSupportedNodeType(type: string): type is NodeType {
    return SUPPORTED_NODE_TYPES.includes(type as NodeType);
}

export function getDefaultLabel(type: string): string {
    const labels: Record<string, string> = {
        input: '输入节点',
        process: '处理节点',
        gate: '门控节点',
        checker: '核查节点',
        output: '输出节点',
    };
    return labels[type] || '未知节点';
}
