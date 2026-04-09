/**
 * Yjs Hook 绑定
 * 为什么这样分层：在 React 组件顶层调用，用于初始化 Provider，监听 Yjs 文档变化，
 * 并把远程修改反写到 Zustand 渲染缓存中。
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import type { WebsocketProvider } from 'y-websocket';
import { yNodes, yEdges, ydoc, resetSharedDocument } from './ydoc';
import { initProvider, destroyProvider } from './provider';
import { useWorkflowStoreInstance } from '../../provider/WorkflowProvider';
import { getNodesArray, getEdgesArray } from './sync';

export function useYjsBindings(workflowId?: string, initialNodes?: any[], initialEdges?: any[]) {
    const store = useWorkflowStoreInstance();
    const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
    const [providerInstance, setProviderInstance] = useState<WebsocketProvider | null>(null);
    const draftRoomRef = useRef(`draft-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);

    useEffect(() => {
        const docId = workflowId || draftRoomRef.current;
        resetSharedDocument();

        // 生成临时用户信息（如果有 AuthContext 可以传进来，目前生成随机数做演示）
        const randomId = String(Math.floor(Math.random() * 10000));
        const colors = ['#f87171', '#fb923c', '#fbbf24', '#a3e635', '#4ade80', '#34d399', '#2dd4bf', '#22d3ee', '#38bdf8', '#60a5fa', '#818cf8', '#a78bfa', '#c084fc', '#e879f9', '#f472b6', '#fb7185', '#f43f5e'];
        const p = initProvider(docId, {
            id: randomId,
            name: `User ${randomId}`,
            color: colors[Math.floor(Math.random() * colors.length)]
        });
        setProviderInstance(p);

        p.on('status', (event: { status: string }) => {
            setStatus(event.status as any);
        });

        // 仅在文档为空且有初始节点时同步到 Yjs
        const initDoc = () => {
             if (yNodes.size === 0 && initialNodes?.length) {
                 ydoc.transact(() => {
                     initialNodes.forEach(n => yNodes.set(n.id, n));
                     initialEdges?.forEach(e => yEdges.set(e.id, e));
                 }, 'init');
             }
        };

        if (p.synced) {
            initDoc();
        } else {
            p.on('sync', (isSynced: boolean) => {
                if (isSynced) {
                    initDoc();
                }
            });
        }

        // 核心同步：Yjs 更新 -> 写入 Zustand 渲染缓存
        const updateZustand = () => {
            // 本地选中态不存 Yjs，重置时需合并回来
            const localNodes = store.getState().nodes;
            const selectionMap = new Map(localNodes.map((n: any) => [n.id, n.selected]));

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

        // 初始拉取一次
        updateZustand();

        return () => {
            yNodes.unobserve(updateZustand);
            yEdges.unobserve(updateZustand);
            destroyProvider();
            setProviderInstance(null);
            setStatus('disconnected');
        };
    }, [workflowId, store, initialNodes, initialEdges]);

    return { status, provider: providerInstance };
}
