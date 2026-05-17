/**
 * Yjs Hook 绑定
 * 为什么这样分层：在 React 组件顶层调用，用于初始化 Provider，监听 Yjs 文档变化，
 * 并把远程修改反写到 Zustand 渲染缓存中。
 */

'use client';

import { useEffect, useId, useRef, useState } from 'react';
import type { Edge, Node } from '@xyflow/react';
import type { WebsocketProvider } from 'y-websocket';
import { yNodes, yEdges, yMeta, ydoc, resetSharedDocument } from './ydoc';
import { initProvider, destroyProvider } from './provider';
import { useWorkflowStoreInstance } from '../../provider/WorkflowProvider';
import { getNodesArray, getEdgesArray } from './sync';

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';
type InitialSource = {
    nodes: Node[];
    edges: Edge[];
    snapshotKey?: string;
};

function normalizeConnectionStatus(status: string): ConnectionStatus {
    return status === 'connecting' || status === 'connected' ? status : 'disconnected';
}

function seedGraphFromSnapshot(docId: string, snapshotKey: string | undefined, nodes: Node[], edges: Edge[]) {
    yNodes.clear();
    yEdges.clear();
    nodes.forEach((node) => yNodes.set(node.id, node));
    edges.forEach((edge) => yEdges.set(edge.id, edge));
    yMeta.set('seedDocId', docId);
    yMeta.set('seedSnapshotKey', snapshotKey ?? null);
    yMeta.set('seededAt', new Date().toISOString());
}

export function useYjsBindings(
    workflowId?: string,
    initialNodes?: Node[],
    initialEdges?: Edge[],
    initialSnapshotKey?: string,
) {
    const store = useWorkflowStoreInstance();
    const [status, setStatus] = useState<ConnectionStatus>('disconnected');
    const [providerInstance, setProviderInstance] = useState<WebsocketProvider | null>(null);
    const draftRoomId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
    const draftRoomRef = useRef(`draft-${draftRoomId}`);
    const initialSourceRef = useRef<InitialSource>({
        nodes: initialNodes ?? [],
        edges: initialEdges ?? [],
        snapshotKey: initialSnapshotKey,
    });

    initialSourceRef.current = {
        nodes: initialNodes ?? [],
        edges: initialEdges ?? [],
        snapshotKey: initialSnapshotKey,
    };

    useEffect(() => {
        const docId = workflowId || draftRoomRef.current;
        const { nodes: snapshotNodes, edges: snapshotEdges, snapshotKey } = initialSourceRef.current;
        resetSharedDocument();

        // 生成临时用户信息（如果有 AuthContext 可以传进来，目前生成随机数做演示）
        const randomId = String(Math.floor(Math.random() * 10000));
        const colors = ['#f87171', '#fb923c', '#fbbf24', '#a3e635', '#4ade80', '#34d399', '#2dd4bf', '#22d3ee', '#38bdf8', '#60a5fa', '#818cf8', '#a78bfa', '#c084fc', '#e879f9', '#f472b6', '#fb7185', '#f43f5e'];
        const p = initProvider(docId, {
            id: randomId,
            name: `User ${randomId}`,
            color: colors[Math.floor(Math.random() * colors.length)]
        });
        queueMicrotask(() => setProviderInstance(p));

        p.on('status', (event: { status: string }) => {
            setStatus(normalizeConnectionStatus(event.status));
        });

        // 核心同步：Yjs 更新 -> 写入 Zustand 渲染缓存
        let sourceReady = false;
        const updateZustand = () => {
            if (!sourceReady) {
                return;
            }

            // 本地选中态不存 Yjs，重置时需合并回来
            const localNodes = store.getState().nodes;
            const selectionMap = new Map(localNodes.map((n) => [n.id, Boolean(n.selected)]));

            const newNodes = getNodesArray().map(n => ({
                ...n,
                selected: selectionMap.get(n.id) || false
            }));

            // 为了让其它用户操作触发 dirty 时，不一定强制所有人都保存，
            // 这里就不把 isDirty 设为 true 了，除非当前客户端主动触发的 action。
            // 依赖本地 action.ts 去控制 isDirty。
            store.setState({ nodes: newNodes, edges: getEdgesArray() });
        };

        yNodes.observe(updateZustand);
        yEdges.observe(updateZustand);

        let sourceApplied = false;
        const applyInitialSource = () => {
            if (sourceApplied) {
                return;
            }
            sourceApplied = true;

            const hasSnapshotGraph = snapshotNodes.length > 0 || snapshotEdges.length > 0;

            if (snapshotKey) {
                const seededDocId = yMeta.get('seedDocId');
                const seededSnapshotKey = yMeta.get('seedSnapshotKey');
                const shouldReseed = seededDocId !== docId || seededSnapshotKey !== snapshotKey;

                sourceReady = true;
                if (shouldReseed) {
                    // 数据库草稿是页面打开时的持久化基线；Yjs 房间只保留同一快照内的协作态。
                    ydoc.transact(() => {
                        seedGraphFromSnapshot(docId, snapshotKey, snapshotNodes, snapshotEdges);
                    }, 'init');
                }
                updateZustand();
                return;
            }

            sourceReady = true;
            if (yNodes.size === 0 && yEdges.size === 0 && hasSnapshotGraph) {
                ydoc.transact(() => {
                    seedGraphFromSnapshot(docId, undefined, snapshotNodes, snapshotEdges);
                }, 'init');
            }
            updateZustand();
        };

        if (p.synced) {
            applyInitialSource();
        } else {
            p.on('sync', (isSynced: boolean) => {
                if (isSynced) {
                    applyInitialSource();
                }
            });
        }

        return () => {
            yNodes.unobserve(updateZustand);
            yEdges.unobserve(updateZustand);
            destroyProvider();
            setProviderInstance(null);
            setStatus('disconnected');
        };
    }, [workflowId, store]);

    useEffect(() => {
        if (!providerInstance || !workflowId || !initialSnapshotKey) {
            return;
        }

        const seededDocId = yMeta.get('seedDocId');
        if (seededDocId !== workflowId) {
            return;
        }

        ydoc.transact(() => {
            yMeta.set('seedSnapshotKey', initialSnapshotKey);
            yMeta.set('seededAt', new Date().toISOString());
        }, 'save');
    }, [workflowId, initialSnapshotKey, providerInstance]);

    return { status, provider: providerInstance };
}
