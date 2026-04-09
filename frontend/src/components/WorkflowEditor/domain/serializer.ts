/**
 * 领域模型 - 序列化
 * 为什么这样分层：完全隔离 React Flow 内部状态表示 (Node, Edge) 和后端领域实体 (WorkflowNode, WorkflowEdge)。
 * 保证保存或发布时，给后端发送的 JSON 完全兼容现有结构。
 */

import type { Node, Edge } from '@xyflow/react';
import type { WorkflowNode, WorkflowEdge } from './types';

function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function serializeNodes(nodes: Node[]): WorkflowNode[] {
    return nodes.map((node) => ({
        id: node.id,
        type: String(node.type ?? 'process'),
        position: { x: node.position.x, y: node.position.y },
        data: {
            label: String(node.data?.label ?? ''),
            config: isRecord(node.data?.config) ? node.data.config : undefined,
        },
    }));
}

export function serializeEdges(edges: Edge[]): WorkflowEdge[] {
    return edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        data: isRecord(edge.data)
            ? {
                  condition: typeof edge.data.condition === 'string' ? edge.data.condition : undefined,
                  label: typeof edge.data.label === 'string' ? edge.data.label : undefined,
              }
            : undefined,
    }));
}
