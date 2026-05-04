/**
 * 工作流编辑器 - 界面外壳
 * 为什么这样分层：在这个组件中只负责组织界面骨架（头部状态栏、动作按钮组、画布区域、配置面板），
 * 业务数据（如 nodes/edges/选中节点）全部通过 selectors 从 Zustand 中获取，
 * 解除了原来大组件里茫茫多的 useState，同时也是为了后续灵活对接各种面板布局做准备。
 */

'use client';

import { useCallback } from 'react';
import { ReactFlow, Background, Controls, MiniMap, BackgroundVariant, Panel, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useWorkflowContext } from './provider/WorkflowProvider';
import { useWorkflowActions } from './store/actions';
import { selectNodes, selectEdges, selectSelectedNode, selectReadOnly } from './store/selectors';
import { nodeTypes } from './nodes';
import NodeLibrary from './panels/NodeLibrary';
import PropertiesPanel from './panels/PropertiesPanel';
import CanvasToolbar from './CanvasToolbar';
import { useYjsBindings } from './collaboration/yjs/bindings';
import { ConnectionStatusBadge } from './collaboration/components/ConnectionStatusBadge';
import { UserPresenceAvatarStack } from './collaboration/components/UserPresenceAvatarStack';
import { RemoteSelectionHighlight } from './collaboration/components/RemoteSelectionHighlight';
import { ConflictHintToast } from './collaboration/components/ConflictHintToast';
import { getDefaultLabel } from './domain/schema';
import { WORKFLOW_NODE_CARD_HEIGHT, WORKFLOW_NODE_CARD_WIDTH } from './domain/nodePresentation';
import { registry } from './registry';
import styles from './WorkflowEditor.module.css';
import type { WorkflowEditorProps } from './index';

export function WorkflowEditorShell({
workflowId,
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
const nodes = useWorkflowContext(selectNodes);
const edges = useWorkflowContext(selectEdges);
const selectedNode = useWorkflowContext(selectSelectedNode);
const readOnly = useWorkflowContext(selectReadOnly);

    const actions = useWorkflowActions();
    const { status: yjsStatus, provider: yjsProvider } = useYjsBindings(workflowId, initialNodes, initialEdges);

    const busy = Boolean(
        actionState?.isSaving || actionState?.isValidating || actionState?.isPublishing,
    );

    const onSelectionChange = useCallback(
        ({ nodes: selectedNodes }: { nodes: Node[]; edges: Edge[] }) => {
            if (selectedNodes.length === 1) {
                actions.setSelectedNode(selectedNodes[0]);
            } else {
                actions.setSelectedNode(null);
            }
        },
        [actions]
    );

    const onNodeConfigChange = useCallback(
        (nodeId: string, newData: Record<string, unknown>) => {
            actions.updateNodeData(nodeId, newData);
        },
        [actions],
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
                initialWidth: WORKFLOW_NODE_CARD_WIDTH,
                initialHeight: WORKFLOW_NODE_CARD_HEIGHT,
                data: {
                    label: getDefaultLabel(type),
                    ...(registry.get(type)?.defaultData ?? {}),
                },
            };

            actions.addNode(newNode);
        },
        [readOnly, actions],
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

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '12px' }}>
                        <UserPresenceAvatarStack provider={yjsProvider} />
                        <ConnectionStatusBadge status={yjsStatus} />
                    </div>
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
                        onNodesChange={readOnly ? undefined : actions.onNodesChange}
                        onEdgesChange={readOnly ? undefined : actions.onEdgesChange}
                        onConnect={readOnly ? undefined : actions.onConnect}
                        onSelectionChange={onSelectionChange}
                        onDrop={readOnly ? undefined : onDrop}
                        onDragOver={readOnly ? undefined : onDragOver}
                        nodeTypes={nodeTypes}
                        className={styles.flow}
                        fitView
                        snapToGrid
                        snapGrid={[15, 15]}
                    >
                        <Background
                            variant={BackgroundVariant.Dots}
                            gap={28}
                            size={1.25}
                            color="var(--editor-canvas-dot)"
                        />
                        <Controls />
                        <MiniMap
                            nodeColor={(node) => getMiniMapNodeColor(node.type)}
                            nodeStrokeColor={(node) => getMiniMapNodeStrokeColor(node.type)}
                            nodeComponent={WorkflowMiniMapNode}
                            nodeBorderRadius={18}
                            nodeStrokeWidth={3}
                            maskColor="var(--editor-minimap-mask)"
                            pannable
                            zoomable
                        />
                        <Panel position="top-right" className={styles.canvasHint}>
                            {readOnly ? '当前为只读模式' : '拖拽节点、配置参数并发布'}
                        </Panel>
                        <RemoteSelectionHighlight provider={yjsProvider} />
                        <CanvasToolbar />
                    </ReactFlow>

                    {selectedNode ? (
                        <div style={{ position: 'absolute', right: 24, top: 24, zIndex: 10, display: 'flex', flexDirection: 'column' }}>
                            <ConflictHintToast provider={yjsProvider} />
                            <PropertiesPanel
                                node={selectedNode}
                                onClose={() => actions.setSelectedNode(null)}
                                onChange={onNodeConfigChange}
                            />
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}

type WorkflowMiniMapNodeProps = {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    color?: string;
    strokeColor?: string;
    strokeWidth?: number;
    selected: boolean;
    onClick?: (event: React.MouseEvent, id: string) => void;
};

function WorkflowMiniMapNode({
    id,
    x,
    y,
    width,
    height,
    color = '#e2e8f0',
    strokeColor = '#64748b',
    strokeWidth = 2,
    selected,
    onClick,
}: WorkflowMiniMapNodeProps) {
    const safeWidth = Math.max(width, WORKFLOW_NODE_CARD_WIDTH);
    const safeHeight = Math.max(height, WORKFLOW_NODE_CARD_HEIGHT);
    const radius = Math.min(24, safeHeight * 0.24);
    const padding = Math.min(20, safeHeight * 0.18);
    const iconSize = Math.min(40, safeHeight * 0.34);
    const stripeWidth = Math.max(4, safeWidth * 0.018);
    const textX = x + padding + iconSize + 14;
    const textWidth = Math.max(42, safeWidth - padding * 2 - iconSize - 28);

    return (
        <g
            className={styles.miniMapNodeThumb}
            onClick={onClick ? (event) => onClick(event, id) : undefined}
        >
            <rect
                className={styles.miniMapNodeCard}
                x={x}
                y={y}
                width={safeWidth}
                height={safeHeight}
                rx={radius}
                fill={color}
                stroke={strokeColor}
                strokeWidth={selected ? strokeWidth + 1 : strokeWidth}
            />
            <rect
                x={x + padding}
                y={y + padding}
                width={stripeWidth}
                height={safeHeight - padding * 2}
                rx={stripeWidth}
                fill={strokeColor}
                opacity="0.9"
            />
            <rect
                x={x + padding + stripeWidth + 12}
                y={y + padding}
                width={iconSize}
                height={iconSize}
                rx={Math.min(14, iconSize * 0.32)}
                fill="rgba(255, 255, 255, 0.58)"
                stroke={strokeColor}
                strokeWidth={Math.max(1.5, strokeWidth * 0.45)}
                opacity="0.86"
            />
            <rect
                x={textX}
                y={y + padding + 4}
                width={textWidth * 0.58}
                height={safeHeight * 0.12}
                rx={safeHeight * 0.06}
                fill={strokeColor}
                opacity="0.76"
            />
            <rect
                x={textX}
                y={y + padding + iconSize * 0.62}
                width={textWidth}
                height={safeHeight * 0.1}
                rx={safeHeight * 0.05}
                fill={strokeColor}
                opacity="0.28"
            />
        </g>
    );
}

function getMiniMapNodeColor(type?: string): string {
    const colors: Record<string, string> = {
        input: '#dbeafe',
        process: '#dcfce7',
        gate: '#fef3c7',
        checker: '#ffedd5',
        output: '#f3e8ff',
    };
    return colors[type || ''] || '#e2e8f0';
}

function getMiniMapNodeStrokeColor(type?: string): string {
    const colors: Record<string, string> = {
        input: '#2563eb',
        process: '#16a34a',
        gate: '#d97706',
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
