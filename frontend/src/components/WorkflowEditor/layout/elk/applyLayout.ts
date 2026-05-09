/**
 * 布局结果应用器
 * 为什么这样分层：负责把 ELK 算出来的坐标写回 React Flow 的 Node 对象，
 * 同时过滤掉被用户 pin（锁定）的节点，只改 `position`，绝对不污染节点的业务 `data` 或其他属性。
 */

import type { Node } from '@xyflow/react';
import type { ElkNode } from 'elkjs';

export function applyElkLayout(
    currentNodes: Node[],
    elkRoot: ElkNode,
    options: {
        filterIds?: string[]; // 仅重排指定的选区
    } = {}
): Node[] {
    // 将 ELK 计算后平铺展开找到所有坐标
    const elkPositions = new Map<string, { x: number; y: number }>();

    function traverseElk(node: ElkNode) {
        if (node.id !== 'root' && node.x !== undefined && node.y !== undefined) {
            elkPositions.set(node.id, { x: node.x, y: node.y });
        }
        node.children?.forEach(traverseElk);
    }
    traverseElk(elkRoot);

    return currentNodes.map((node) => {
        // 如果节点被 pin 住，或者不在过滤列表（选区）中，则保持原样
        if (node.data?.isPinned) {
            return node;
        }

        if (options.filterIds && options.filterIds.length > 0 && !options.filterIds.includes(node.id)) {
            return node;
        }

        const newPos = elkPositions.get(node.id);
        if (newPos) {
            return {
                ...node,
                position: { ...newPos },
            };
        }

        return node;
    });
}
