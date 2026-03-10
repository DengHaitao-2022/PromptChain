'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
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

import type { ValidationResult } from './hooks/useWorkflowApi';
import { nodeTypes } from './nodes';
import NodeLibrary from './panels/NodeLibrary';
import NodeConfigPanel from './panels/NodeConfigPanel';
import styles from './WorkflowEditor.module.css';

const defaultNodes: Node[] = [
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

const defaultEdges: Edge[] = [
    { id: 'e1-2', source: 'input-1', target: 'process-1' },
    { id: 'e2-3', source: 'process-1', target: 'gate-1' },
    { id: 'e3-4', source: 'gate-1', target: 'process-2' },
    { id: 'e4-5', source: 'process-2', target: 'checker-1' },
    { id: 'e5-6', source: 'checker-1', target: 'output-1' },
];

interface WorkflowEditorActionState {
    isSaving?: boolean;
    isValidating?: boolean;
    isPublishing?: boolean;
    statusMessage?: string | null;
    errorMessage?: string | null;
    validation?: ValidationResult | null;
}

interface WorkflowEditorProps {
    workflowId?: string;
    readOnly?: boolean;
    initialNodes?: Node[];
    initialEdges?: Edge[];
    name: string;
    description: string;
    onNameChange: (value: string) => void;
    onDescriptionChange: (value: string) => void;
    isPublished?: boolean;
    publishedVersion?: number | null;
    publishedAt?: string | null;
    onSave?: (nodes: Node[], edges: Edge[]) => void | Promise<void>;
    onValidate?: (nodes: Node[], edges: Edge[]) => void | Promise<void>;
    onPublish?: (nodes: Node[], edges: Edge[]) => void | Promise<void>;
    actionState?: WorkflowEditorActionState;
}

export default function WorkflowEditor({
    workflowId,
    readOnly = false,
    initialNodes,
    initialEdges,
    name,
    description,
    onNameChange,
    onDescriptionChange,
    isPublished = false,
    publishedVersion,
    publishedAt,
    onSave,
    onValidate,
    onPublish,
    actionState,
}: WorkflowEditorProps) {
    const startingNodes = useMemo(() => initialNodes ?? defaultNodes, [initialNodes]);
    const startingEdges = useMemo(() => initialEdges ?? defaultEdges, [initialEdges]);

    const [nodes, setNodes, onNodesChange] = useNodesState(startingNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(startingEdges);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

    useEffect(() => {
        setNodes(initialNodes ?? defaultNodes);
        setEdges(initialEdges ?? defaultEdges);
        setSelectedNode(null);
    }, [initialEdges, initialNodes, setEdges, setNodes]);

    const busy = Boolean(
        actionState?.isSaving || actionState?.isValidating || actionState?.isPublishing,
    );

    const onConnect: OnConnect = useCallback(
        (connection) => setEdges((currentEdges) => addEdge(connection, currentEdges)),
        [setEdges],
    );

    const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
        setSelectedNode(node);
    }, []);

    const onPaneClick = useCallback(() => {
        setSelectedNode(null);
    }, []);

    const onNodeConfigChange = useCallback(
        (nodeId: string, newData: Record<string, unknown>) => {
            setNodes((currentNodes) =>
                currentNodes.map((node) =>
                    node.id === nodeId
                        ? { ...node, data: { ...node.data, ...newData } }
                        : node,
                ),
            );
            setSelectedNode((currentNode) =>
                currentNode?.id === nodeId
                    ? { ...currentNode, data: { ...currentNode.data, ...newData } }
                    : currentNode,
            );
        },
        [setNodes],
    );

    const onDrop = useCallback(
        (event: React.DragEvent) => {
            if (readOnly) {
                return;
            }

            event.preventDefault();
            const type = event.dataTransfer.getData('application/reactflow');
            if (!type) {
                return;
            }

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

            setNodes((currentNodes) => currentNodes.concat(newNode));
        },
        [readOnly, setNodes],
    );

    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    const statusBadge = isPublished ? '已发布' : '草稿';
    const publishedLabel = publishedVersion ? `已发布 v${publishedVersion}` : '未发布';

    return (
        <div className={styles.editorShell}>
            <div className={styles.header}>
                <div className={styles.headerInfo}>
                    <div className={styles.badges}>
                        <span
                            className={`${styles.statusBadge} ${
                                isPublished ? styles.publishedBadge : styles.draftBadge
                            }`}
                        >
                            {statusBadge}
                        </span>
                        <span className={styles.versionBadge}>{publishedLabel}</span>
                        {workflowId ? (
                            <span className={styles.metaBadge}>ID: {workflowId.slice(0, 8)}</span>
                        ) : (
                            <span className={styles.metaBadge}>新建工作流</span>
                        )}
                    </div>
                    <label className={styles.fieldGroup}>
                        <span className={styles.fieldLabel}>工作流名称</span>
                        <input
                            className={styles.nameInput}
                            value={name}
                            onChange={(event) => onNameChange(event.target.value)}
                            placeholder="请输入工作流名称"
                            disabled={readOnly || busy}
                        />
                    </label>
                    <label className={styles.fieldGroup}>
                        <span className={styles.fieldLabel}>工作流说明</span>
                        <textarea
                            className={styles.descriptionInput}
                            value={description}
                            onChange={(event) => onDescriptionChange(event.target.value)}
                            placeholder="描述这个工作流的用途、节点职责与发布说明"
                            disabled={readOnly || busy}
                            rows={3}
                        />
                    </label>
                    {publishedAt ? (
                        <p className={styles.timestamp}>最近发布时间：{formatDateTime(publishedAt)}</p>
                    ) : null}
                </div>

                <div className={styles.actionGroup}>
                    <button
                        type="button"
                        className={styles.secondaryButton}
                        onClick={() => void onValidate?.(nodes, edges)}
                        disabled={readOnly || busy}
                    >
                        {actionState?.isValidating ? '校验中...' : '发布前校验'}
                    </button>
                    <button
                        type="button"
                        className={styles.saveButton}
                        onClick={() => void onSave?.(nodes, edges)}
                        disabled={readOnly || busy}
                    >
                        {actionState?.isSaving ? '保存中...' : '保存草稿'}
                    </button>
                    <button
                        type="button"
                        className={styles.publishButton}
                        onClick={() => void onPublish?.(nodes, edges)}
                        disabled={readOnly || busy}
                    >
                        {actionState?.isPublishing ? '发布中...' : '发布工作流'}
                    </button>
                </div>
            </div>

            {(actionState?.statusMessage || actionState?.errorMessage || actionState?.validation) && (
                <section className={styles.feedbackPanel}>
                    {actionState?.statusMessage ? (
                        <p className={styles.statusMessage}>{actionState.statusMessage}</p>
                    ) : null}
                    {actionState?.errorMessage ? (
                        <p className={styles.errorMessage}>{actionState.errorMessage}</p>
                    ) : null}
                    {actionState?.validation ? (
                        <div className={styles.validationGrid}>
                            <div className={styles.validationColumn}>
                                <h3>阻塞问题</h3>
                                {actionState.validation.errors.length > 0 ? (
                                    <ul className={styles.validationList}>
                                        {actionState.validation.errors.map((error) => (
                                            <li key={error}>{error}</li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p className={styles.emptyValidation}>没有阻塞项</p>
                                )}
                            </div>
                            <div className={styles.validationColumn}>
                                <h3>提示</h3>
                                {actionState.validation.warnings.length > 0 ? (
                                    <ul className={styles.validationList}>
                                        {actionState.validation.warnings.map((warning) => (
                                            <li key={warning}>{warning}</li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p className={styles.emptyValidation}>没有额外提示</p>
                                )}
                            </div>
                        </div>
                    ) : null}
                </section>
            )}

            <div className={styles.editorContainer}>
                <NodeLibrary />

                <div className={styles.canvas}>
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={readOnly ? undefined : onNodesChange}
                        onEdgesChange={readOnly ? undefined : onEdgesChange}
                        onConnect={readOnly ? undefined : onConnect}
                        onNodeClick={onNodeClick}
                        onPaneClick={onPaneClick}
                        onDrop={readOnly ? undefined : onDrop}
                        onDragOver={readOnly ? undefined : onDragOver}
                        nodeTypes={nodeTypes}
                        fitView
                        snapToGrid
                        snapGrid={[15, 15]}
                    >
                        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
                        <Controls />
                        <MiniMap
                            nodeColor={(node) => getNodeColor(node.type)}
                            maskColor="rgba(14, 24, 38, 0.08)"
                        />
                        <Panel position="top-right" className={styles.canvasHint}>
                            {readOnly ? '当前为只读模式' : '拖拽节点、配置参数并发布'}
                        </Panel>
                    </ReactFlow>
                </div>

                {selectedNode ? (
                    <NodeConfigPanel
                        node={selectedNode}
                        onClose={() => setSelectedNode(null)}
                        onChange={onNodeConfigChange}
                    />
                ) : null}
            </div>
        </div>
    );
}

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

function getNodeColor(type?: string): string {
    const colors: Record<string, string> = {
        input: '#2563eb',
        process: '#059669',
        gate: '#ca8a04',
        checker: '#ea580c',
        output: '#7c3aed',
    };
    return colors[type || ''] || '#94a3b8';
}

function formatDateTime(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    }).format(date);
}
