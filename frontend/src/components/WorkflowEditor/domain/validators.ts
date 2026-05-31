/**
 * 领域模型 - 前端校验
 * 为什么这样分层：本地先做一些速错校验（如是否成环、是否有孤立节点等），减少无用的网络请求。
 * 后端 /validate 接口依然是最终门禁。
 */

import type { Node } from '@xyflow/react';

export function checkHasNodes(nodes: Node[]): string | null {
    if (nodes.length === 0) {
        return '工作流不能为空';
    }
    return null;
}

export function checkHasInputNode(nodes: Node[]): string | null {
    if (!nodes.some((node) => node.type === 'input')) {
        return '缺少输入节点';
    }
    return null;
}
