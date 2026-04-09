/**
 * 状态管理 - 状态选择器
 * 为什么这样分层：封装对 Zustand store 的精细化读取逻辑，隔离内部数据结构，使得组件订阅精确且不易引起不必要的重渲染。
 */

import type { WorkflowState } from './workflowStore';

export const selectNodes = (state: WorkflowState) => state.nodes;
export const selectEdges = (state: WorkflowState) => state.edges;
export const selectSelectedNode = (state: WorkflowState) => state.selectedNode;
export const selectIsDirty = (state: WorkflowState) => state.isDirty;
export const selectReadOnly = (state: WorkflowState) => state.readOnly;
export const selectViewport = (state: WorkflowState) => state.viewport;
export const selectPanelTab = (state: WorkflowState) => state.panelTab;
export const selectLayoutDirection = (state: WorkflowState) => state.layoutDirection;
export const selectIsLayouting = (state: WorkflowState) => state.isLayouting;
