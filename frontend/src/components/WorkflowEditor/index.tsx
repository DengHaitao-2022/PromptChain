'use client';

import { useCallback, useState } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    addEdge,
    useNodesState,
    useEdgesState,
    type OnConnect,
    type Node,
    type Edge,
    BackgroundVariant,
    Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { nodeTypes } from './nodes';
import NodeLibrary from './panels/NodeLibrary';
import NodeConfigPanel from './panels/NodeConfigPanel';
import styles from './WorkflowEditor.module.css';

// 初始节点示例
const initialNodes: Node[] = [
    {
        id: 'input-1',
        type: 'input',
        position: { x: 250, y: 50 },
        data: { label: '意图解析' },
    },
    {
        id: 'process-1',
        type: 'process',
        position: { x: 250, y: 150 },
        data: { label: '大纲生成', config: { modelName: 'gpt-4o' } },
    },
    {
        id: 'gate-1',
        type: 'gate',
        position: { x: 250, y: 250 },
        data: { label: '大纲审批', config: { gateType: 'approval', timeout: 3600 } },
    },
    {
        id: 'process-2',
        type: 'process',
        position: { x: 250, y: 350 },
        data: { label: '内容生成', config: { modelName: 'gpt-4o' } },
    },
    {
        id: 'checker-1',
        type: 'checker',
        position: { x: 250, y: 450 },
        data: { label: '事实核查', config: { confidenceThreshold: 0.8 } },
    },
    {
        id: 'output-1',
        type: 'output',
        position: { x: 250, y: 550 },
        data: { label: '最终输出', config: { outputFormat: 'markdown' } },
    },
];

// 初始边示例
const initialEdges: Edge[] = [
    { id: 'e1-2', source: 'input-1', target: 'process-1' },
    { id: 'e2-3', source: 'process-1', target: 'gate-1' },
    { id: 'e3-4', source: 'gate-1', target: 'process-2' },
    { id: 'e4-5', source: 'process-2', target: 'checker-1' },
    { id: 'e5-6', source: 'checker-1', target: 'output-1' },
];

interface WorkflowEditorProps {
    workflowId?: string;
    readOnly?: boolean;
    onSave?: (nodes: Node[], edges: Edge[]) => void;
}

/**
 * 可视化工作流编辑器
 * 基于 React Flow 实现拖拽式 DAG 编排
 */
export default function WorkflowEditor({
    workflowId,
    readOnly = false,
    onSave,
}: WorkflowEditorProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

    // 处理连线
    const onConnect: OnConnect = useCallback(
        (connection) => setEdges((eds) => addEdge(connection, eds)),
        [setEdges]
    );

    // 处理节点选中
    const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
        setSelectedNode(node);
    }, []);

    // 处理画布点击（取消选中）
    const onPaneClick = useCallback(() => {
        setSelectedNode(null);
    }, []);

    // 更新选中节点的配置
    const onNodeConfigChange = useCallback(
        (nodeId: string, newData: Record<string, unknown>) => {
            setNodes((nds) =>
                nds.map((node) =>
                    node.id === nodeId
                        ? { ...node, data: { ...node.data, ...newData } }
                        : node
                )
            );
            // 同步更新 selectedNode
            setSelectedNode((prev) =>
                prev?.id === nodeId ? { ...prev, data: { ...prev.data, ...newData } } : prev
            );
        },
        [setNodes]
    );

    // 从模板库拖入新节点
    const onDrop = useCallback(
        (event: React.DragEvent) => {
            event.preventDefault();

            const type = event.dataTransfer.getData('application/reactflow');
            if (!type) return;

            const position = {
                x: event.clientX - 250,
                y: event.clientY - 100,
            };

            const newNode: Node = {
                id: `${type}-${Date.now()}`,
                type,
                position,
                data: { label: getDefaultLabel(type) },
            };

            setNodes((nds) => nds.concat(newNode));
        },
        [setNodes]
    );

    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    return (
        <div className={styles.editorContainer}>
            {/* 左侧节点模板库 */}
            <NodeLibrary />

            {/* 中间画布区域 */}
            <div className={styles.canvas}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={readOnly ? undefined : onNodesChange}
                    onEdgesChange={readOnly ? undefined : onEdgesChange}
                    onConnect={readOnly ? undefined : onConnect}
                    onNodeClick={onNodeClick}
                    onPaneClick={onPaneClick}
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    nodeTypes={nodeTypes}
                    fitView
                    snapToGrid
                    snapGrid={[15, 15]}
                >
                    <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
                    <Controls />
                    <MiniMap
                        nodeColor={(node) => getNodeColor(node.type)}
                        maskColor="rgba(0, 0, 0, 0.1)"
                    />
                    <Panel position="top-right" className={styles.panel}>
                        <button
                            className={styles.saveButton}
                            onClick={() => onSave?.(nodes, edges)}
                        >
                            保存工作流
                        </button>
                    </Panel>
                </ReactFlow>
            </div>

            {/* 右侧配置面板 */}
            {selectedNode && (
                <NodeConfigPanel
                    node={selectedNode}
                    onClose={() => setSelectedNode(null)}
                    onChange={onNodeConfigChange}
                />
            )}
        </div>
    );
}

// 获取节点默认标签
function getDefaultLabel(type: string): string {
    const labels: Record<string, string> = {
        input: '输入节点',
        process: '处理节点',
        gate: '门控节点',
        checker: '核查节点',
        output: '输出节点',
    };
    return labels[type] || '未知节点';
}

// 获取节点颜色（用于MiniMap）
function getNodeColor(type?: string): string {
    const colors: Record<string, string> = {
        input: '#3b82f6',
        process: '#22c55e',
        gate: '#eab308',
        checker: '#f97316',
        output: '#a855f7',
    };
    return colors[type || ''] || '#94a3b8';
}
