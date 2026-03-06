'use client';

import { useState, useCallback } from 'react';
import { type Node, type Edge } from '@xyflow/react';

/**
 * 工作流状态管理 Hook
 *
 * 管理编辑器的节点、边、选中状态等
 */
export function useWorkflowState(
  initialNodes: Node[] = [],
  initialEdges: Edge[] = []
) {
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  // 获取选中的节点
  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null;

  // 添加节点
  const addNode = useCallback((node: Node) => {
    setNodes((nds) => [...nds, node]);
    setIsDirty(true);
  }, []);

  // 删除节点
  const removeNode = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(null);
    }
    setIsDirty(true);
  }, [selectedNodeId]);

  // 更新节点
  const updateNode = useCallback((nodeId: string, updates: Partial<Node>) => {
    setNodes((nds) =>
      nds.map((n) => (n.id === nodeId ? { ...n, ...updates } : n))
    );
    setIsDirty(true);
  }, []);

  // 更新节点数据
  const updateNodeData = useCallback((nodeId: string, data: Record<string, unknown>) => {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      )
    );
    setIsDirty(true);
  }, []);

  // 添加边
  const addEdge = useCallback((edge: Edge) => {
    setEdges((eds) => [...eds, edge]);
    setIsDirty(true);
  }, []);

  // 删除边
  const removeEdge = useCallback((edgeId: string) => {
    setEdges((eds) => eds.filter((e) => e.id !== edgeId));
    setIsDirty(true);
  }, []);

  // 选中节点
  const selectNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
  }, []);

  // 重置状态
  const reset = useCallback((newNodes: Node[], newEdges: Edge[]) => {
    setNodes(newNodes);
    setEdges(newEdges);
    setSelectedNodeId(null);
    setIsDirty(false);
  }, []);

  // 标记为已保存
  const markSaved = useCallback(() => {
    setIsDirty(false);
  }, []);

  return {
    nodes,
    edges,
    selectedNode,
    selectedNodeId,
    isDirty,
    setNodes,
    setEdges,
    addNode,
    removeNode,
    updateNode,
    updateNodeData,
    addEdge,
    removeEdge,
    selectNode,
    reset,
    markSaved,
  };
}
