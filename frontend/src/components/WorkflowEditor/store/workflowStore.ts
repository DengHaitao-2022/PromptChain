/**
 * 状态管理 - 根 Store
 * 为什么这样分层：使用 Zustand 构建本地只读的内存数据库，所有 UI 状态（选中的节点、连线、面板信息）全部挂载于此。
 * 编辑器的组件（Shell, Canvas, Panel）只关注如何渲染或派发 Action，不用互相通过 props 传递庞大的数据结构。
 */

import { createStore } from 'zustand/vanilla';
import { type Node, type Edge, type Viewport } from '@xyflow/react';

export interface WorkflowState {
    nodes: Node[];
    edges: Edge[];
    selectedNode: Node | null;
    viewport: Viewport;
    isDirty: boolean;
    isLayouting: boolean;
    panelTab: string;
    layoutDirection: 'DOWN' | 'LEFT' | 'TOP' | 'RIGHT';
    readOnly: boolean;
}

export type WorkflowStore = ReturnType<typeof createWorkflowStore>;

export const createWorkflowStore = (initialProps?: Partial<WorkflowState>) => {
    return createStore<WorkflowState>()(() => ({
        nodes: [],
        edges: [],
        selectedNode: null,
        viewport: { x: 0, y: 0, zoom: 1 },
        isDirty: false,
        isLayouting: false,
        panelTab: 'config',
        layoutDirection: 'RIGHT',
        readOnly: false,
        ...initialProps,
    }));
};
