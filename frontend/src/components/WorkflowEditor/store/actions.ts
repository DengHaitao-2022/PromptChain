/**
 * 状态管理 - 动作分发
 * 为什么这样分层：将所有修改节点的复杂业务逻辑（如更新 Node、连接 Edge、派发重绘）独立到 actions 层中，方便后续集成 Yjs 协同。
 */

import { useMemo } from 'react';
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@xyflow/react';
import type { Node, Edge, NodeChange, OnNodesChange, OnEdgesChange, OnConnect, Viewport } from '@xyflow/react';
import { useWorkflowStoreInstance } from '../provider/WorkflowProvider';
import { layoutGraph } from '../layout/elk/elk';
import type { ElkLayoutOptions } from '../layout/elk/config';

import { ydoc, yNodes, undoManager } from '../collaboration/yjs/ydoc';
import { applyNodeChangesToYjs, applyEdgeChangesToYjs, setNodesToYjs, setEdgesToYjs } from '../collaboration/yjs/sync';
import { updateSelection } from '../collaboration/yjs/awareness';

function shouldPersistNodeChange(change: NodeChange): boolean {
    return change.type !== 'dimensions';
}

function isSelectionNodeChange(change: NodeChange): boolean {
    return change.type === 'select';
}

export function useWorkflowActions() {
const store = useWorkflowStoreInstance();

return useMemo(() => ({
setNodes(nodesOrUpdater: Node[] | ((current: Node[]) => Node[])) {
    const currentNodes = store.getState().nodes;
    const nextNodes = typeof nodesOrUpdater === 'function' ? nodesOrUpdater(currentNodes) : nodesOrUpdater;

ydoc.transact(() => {
setNodesToYjs(nextNodes);
}, 'local');
    store.setState({ isDirty: true });
},
setEdges(edgesOrUpdater: Edge[] | ((current: Edge[]) => Edge[])) {
const currentEdges = store.getState().edges;
const nextEdges = typeof edgesOrUpdater === 'function' ? edgesOrUpdater(currentEdges) : edgesOrUpdater;

    ydoc.transact(() => {
        setEdgesToYjs(nextEdges);
}, 'local');
store.setState({ isDirty: true });
},
onNodesChange: ((changes) => {
    // dimensions 是 React Flow 的本地测量事件，写回受控 store 会形成测量 -> setState -> 再测量的循环。
    const persistentChanges = changes.filter(shouldPersistNodeChange);

    if (persistentChanges.length > 0) {
        ydoc.transact(() => {
            applyNodeChangesToYjs(persistentChanges);
        }, 'local');

        store.setState((state) => ({
            nodes: applyNodeChanges(persistentChanges, state.nodes),
            isDirty: true,
        }));
    }

    if (changes.some(isSelectionNodeChange)) {
        const currentSelected = store.getState().nodes.filter(n => n.selected).map(n => n.id);
        updateSelection(currentSelected);
    }
}) as OnNodesChange,
onEdgesChange: ((changes) => {
ydoc.transact(() => {
applyEdgeChangesToYjs(changes);
}, 'local');

    store.setState((state) => ({
    edges: applyEdgeChanges(changes, state.edges),
isDirty: true,
}));
}) as OnEdgesChange,
onConnect: ((connection) => {
    ydoc.transact(() => {
    const state = store.getState();
        const newEdges = addEdge(connection, state.edges);
        setEdgesToYjs(newEdges);
}, 'local');
    store.setState({ isDirty: true });
}) as OnConnect,
setSelectedNode(node: Node | null) {
    store.setState({ selectedNode: node });
    updateSelection(node ? [node.id] : []);
},
updateNodeData(nodeId: string, newData: Record<string, unknown>) {
    ydoc.transact(() => {
    const node = yNodes.get(nodeId);
if (node) {
    yNodes.set(nodeId, {
        ...node,
        data: { ...node.data, ...newData }
    });
}
}, 'local');

// local UI sync for quick feedback
    store.setState((state) => {
        const nextNodes = state.nodes.map((n) =>
        n.id === nodeId
            ? { ...n, data: { ...n.data, ...newData } }
            : n
    );
    const nextSelected = state.selectedNode?.id === nodeId
    ? { ...state.selectedNode, data: { ...state.selectedNode.data, ...newData } }
    : state.selectedNode;
    return { nodes: nextNodes, selectedNode: nextSelected, isDirty: true };
            });
},
addNode(node: Node) {
ydoc.transact(() => {
yNodes.set(node.id, node);
}, 'local');
store.setState({ isDirty: true });
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
setLayoutDirection(layoutDirection: 'DOWN' | 'LEFT' | 'TOP' | 'RIGHT') {
store.setState({ layoutDirection });
},
reset() {
    // Because 'reset' resets everything, including Yjs doc if we want, but actually it's just for editor unmount.
        // Let's only clear the local state, bindings handle Yjs unobserve
            store.setState({
                nodes: [],
                edges: [],
                selectedNode: null,
                viewport: { x: 0, y: 0, zoom: 1 },
                isDirty: false,
                isLayouting: false,
                panelTab: 'config',
                layoutDirection: 'RIGHT',
            });
        },
        async autoLayout(options: Partial<ElkLayoutOptions> = {}, filterIds?: string[]) {
            store.setState({ isLayouting: true });
            const { nodes, edges, layoutDirection } = store.getState();

            const finalOptions = {
                direction: layoutDirection,
                ...options
            };

            const newNodes = await layoutGraph(nodes, edges, finalOptions as Partial<ElkLayoutOptions>, filterIds);

            // Push layout changes to Yjs
            ydoc.transact(() => {
                setNodesToYjs(newNodes);
            }, 'local');

            store.setState({
                isDirty: true,
                isLayouting: false
            });
        },
        togglePinNode(nodeId: string) {
            ydoc.transact(() => {
                const node = yNodes.get(nodeId);
                if (node) {
                    yNodes.set(nodeId, {
                        ...node,
                        data: { ...node.data, isPinned: !node.data.isPinned }
                    });
                }
            }, 'local');
            store.setState({ isDirty: true });
        },
        undo() {
            undoManager.undo();
        },
        redo() {
            undoManager.redo();
        }
    }), [store]);
}
