/**
 * Yjs 文档和共享结构
 * 为什么这样分层：将所有协作数据定义剥离出来，这里是真正的“持久化源（Source of Truth）”。
 */

import * as Y from 'yjs';
import type { Node, Edge } from '@xyflow/react';

// 初始化单例 Yjs 文档
export const ydoc = new Y.Doc();

// 核心共享类型
export const yNodes = ydoc.getMap<Node>('nodes');
export const yEdges = ydoc.getMap<Edge>('edges');
export const yMeta = ydoc.getMap<Record<string, unknown>>('meta');
export const ySettings = ydoc.getMap<Record<string, unknown>>('settings');

// 接入 Y.UndoManager 管理撤销重做（只监听需要撤销的图形变化，不监听 viewport/selection）
export const undoManager = new Y.UndoManager([yNodes, yEdges]);

export function resetSharedDocument() {
    ydoc.transact(() => {
        yNodes.clear();
        yEdges.clear();
        yMeta.clear();
        ySettings.clear();
    }, 'reset');
    undoManager.clear();
}
