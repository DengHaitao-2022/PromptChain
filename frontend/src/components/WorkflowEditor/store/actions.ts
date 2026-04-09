/**
 * 状态管理 - 动作分发
 * 为什么这样分层：将所有修改节点的复杂业务逻辑（如更新 Node、连接 Edge、派发重绘）独立到 actions 层中，方便后续集成 Yjs 协同。
 */

import { useMemo } from 'react';
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@xyflow/react';
import type { Node, Edge, OnNodesChange, OnEdgesChange, OnConnect, Viewport } from '@xyflow/react';
import { useWorkflowStoreInstance } from '../provider/WorkflowProvider';

export function useWorkflowActions() {
    const store = useWorkflowStoreInstance();

    return useMemo(() => ({
        setNodes(nodesOrUpdater: Node[] | ((current: Node[]) => Node[])) {
            store.setState((state) => {
                const nextNodes = typeof nodesOrUpdater === 'function' ? nodesOrUpdater(state.nodes) : nodesOrUpdater;
                return { nodes: nextNodes, isDirty: true };
            });
        },
        setEdges(edgesOrUpdater: Edge[] | ((current: Edge[]) => Edge[])) {
            store.setState((state) => {
                const nextEdges = typeof edgesOrUpdater === 'function' ? edgesOrUpdater(state.edges) : edgesOrUpdater;
                return { edges: nextEdges, isDirty: true };
            });
        },
        onNodesChange: ((changes) => {
            store.setState((state) => ({
                nodes: applyNodeChanges(changes, state.nodes),
                isDirty: true,
            }));
        }) as OnNodesChange,
        onEdgesChange: ((changes) => {
            store.setState((state) => ({
                edges: applyEdgeChanges(changes, state.edges),
                isDirty: true,
            }));
        }) as OnEdgesChange,
        onConnect: ((connection) => {
            store.setState((state) => ({
                edges: addEdge(connection, state.edges),
                isDirty: true,
            }));
        }) as OnConnect,
        setSelectedNode(node: Node | null) {
            store.setState({ selectedNode: node });
        },
        updateNodeData(nodeId: string, newData: Record<string, unknown>) {
            store.setState((state) => {
                const nextNodes = state.nodes.map((node) =>
                    node.id === nodeId
                        ? { ...node, data: { ...node.data, ...newData } }
                        : node
                );
                const nextSelected = state.selectedNode?.id === nodeId
                    ? { ...state.selectedNode, data: { ...state.selectedNode.data, ...newData } }
                    : state.selectedNode;
                return { nodes: nextNodes, selectedNode: nextSelected, isDirty: true };
            });
        },
        addNode(node: Node) {
            store.setState((state) => ({
                nodes: state.nodes.concat(node),
                isDirty: true,
            }));
        },
        setViewport(viewport: Viewport) {
            store.setState({ viewport });
        },
        setIsDirty(isDirty: boolean) {
            store.setState({ isDirty });
        },
        setPanelTab(panelTab: string) {
            store.setState({ panelTab });
        },
        setLayoutDirection(layoutDirection: 'TB' | 'LR') {
            store.setState({ layoutDirection });
        },
        reset() {
            store.setState({
                nodes: [],
                edges: [],
                selectedNode: null,
                viewport: { x: 0, y: 0, zoom: 1 },
                isDirty: false,
                panelTab: 'config',
                layoutDirection: 'TB',
            });
        }
    }), [store]);
}
