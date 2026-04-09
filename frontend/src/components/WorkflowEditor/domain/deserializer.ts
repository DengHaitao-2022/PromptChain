/**
 * 领域模型 - 反序列化
 * 为什么这样分层：加载工作流草稿或已发布版本时，将后端的强类型实体转化为 React Flow 的 UI 模型。
 */

import type { Node, Edge } from '@xyflow/react';
import type { WorkflowNode, WorkflowEdge } from './types';

export function deserializeNodes(nodes: WorkflowNode[]): Node[] {
    return nodes.map((node) => ({
        id: node.id,
        type: node.type,
        position: { x: node.position.x, y: node.position.y },
        data: { ...node.data },
    }));
}

export function deserializeEdges(edges: WorkflowEdge[]): Edge[] {
    return edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        data: edge.data ? { ...edge.data } : undefined,
    }));
}
