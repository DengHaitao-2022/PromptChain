/**
 * 结构映射器
 * 为什么这样分层：剥离 React Flow 的特有数据结构，将其转换为 ELK 标准的图数据格式。
 * 这里同时支持子图/容器（group / subflow）的基础 parentId 树形结构映射。
 */

import type { Node, Edge } from '@xyflow/react';
import type { ElkNode, ElkExtendedEdge } from 'elkjs';

const DEFAULT_NODE_WIDTH = 280;
const DEFAULT_NODE_HEIGHT = 120;

export function mapToElkGraph(nodes: Node[], edges: Edge[]): ElkNode {
    // 构建一个节点映射，用于快速查找
    const nodeMap = new Map<string, ElkNode>();

    // 初始化 ELK 节点
    nodes.forEach((node) => {
        // 固定节点跳过布局位置计算（可以在后续 apply 时再恢复，或者在 elk 中锁定位置，
        // 但简单起见，先把它们都按通常节点传递给 ELK，再在 applyLayout 阶段把 pinned 的节点剔除/还原）。
        // 或者给 ELK 传递尺寸即可，ELK 不支持部分固定节点的 layered 布局，只能布局全部。
        nodeMap.set(node.id, {
            id: node.id,
            width: node.measured?.width ?? DEFAULT_NODE_WIDTH,
            height: node.measured?.height ?? DEFAULT_NODE_HEIGHT,
            // 预留子节点列表
            children: [],
        });
    });

    const rootNodes: ElkNode[] = [];

    // 处理层级结构
    nodes.forEach((node) => {
        const elkNode = nodeMap.get(node.id)!;
        if (node.parentId && nodeMap.has(node.parentId)) {
            const parent = nodeMap.get(node.parentId)!;
            parent.children!.push(elkNode);
        } else {
            rootNodes.push(elkNode);
        }
    });

    const elkEdges: ElkExtendedEdge[] = edges.map((edge) => ({
        id: edge.id,
        sources: [edge.source],
        targets: [edge.target],
    }));

    return {
        id: 'root',
        layoutOptions: {
            'elk.algorithm': 'layered',
        },
        children: rootNodes,
        edges: elkEdges,
    };
}
