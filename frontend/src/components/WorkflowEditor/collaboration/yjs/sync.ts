/**
 * Yjs 和 Zustand 同步逻辑
 * 为什么这样分层：充当数据流的中间件，处理 React Flow Change 事件到 Yjs 的转换。
 */

import { yNodes, yEdges } from './ydoc';
import type { Node, Edge, NodeChange, EdgeChange } from '@xyflow/react';

export function getNodesArray(): Node[] {
    return Array.from(yNodes.values());
}

export function getEdgesArray(): Edge[] {
    return Array.from(yEdges.values());
}

export function setNodesToYjs(nodes: Node[]) {
    yNodes.clear();
    nodes.forEach(n => yNodes.set(n.id, n));
}

export function setEdgesToYjs(edges: Edge[]) {
    yEdges.clear();
    edges.forEach(e => yEdges.set(e.id, e));
}

// 拦截并应用节点变更（排除单纯的选中态变更，选中态走 awareness）
export function applyNodeChangesToYjs(changes: NodeChange[]) {
    changes.forEach((change) => {
        if (change.type === 'add') {
            yNodes.set(change.item.id, change.item);
        } else if (change.type === 'remove') {
            yNodes.delete(change.id);
        } else if (change.type === 'position' && change.position) {
            const node = yNodes.get(change.id);
            if (node) {
                yNodes.set(change.id, {
                    ...node,
                    position: change.position,
                    positionAbsolute: change.positionAbsolute,
                    dragging: change.dragging,
                });
            }
        } else if (change.type === 'dimensions' && change.dimensions) {
            const node = yNodes.get(change.id);
            if (node) {
                yNodes.set(change.id, {
                    ...node,
                    measured: { ...node.measured, ...change.dimensions },
                });
            }
        }
    });
}

export function applyEdgeChangesToYjs(changes: EdgeChange[]) {
    changes.forEach((change) => {
        if (change.type === 'add') {
            yEdges.set(change.item.id, change.item);
        } else if (change.type === 'remove') {
            yEdges.delete(change.id);
        }
    });
}
