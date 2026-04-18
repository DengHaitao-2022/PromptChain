'use client';

import { useState, useCallback } from 'react';
import { requestResult } from '@/lib/api';

// ==================== 类型定义 ====================

export interface NodePosition {
  x: number;
  y: number;
}

export interface NodeData {
  label: string;
  config?: Record<string, unknown>;
}

export interface WorkflowNode {
  id: string;
  type: string;
  position: NodePosition;
  data: NodeData;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  data?: {
    condition?: string;
    label?: string;
  };
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description?: string;
  version: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  created_at?: string;
  updated_at?: string;
  created_by?: string;
  is_published?: boolean;
  published_version_id?: string;
  published_version?: number;
  published_at?: string;
  published_by?: string;
}

export interface ValidationResult {
  mode?: string;
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface CompileResult {
  success: boolean;
  graph_code?: string;
  errors: string[];
}

// ==================== API 调用 Hook ====================

export function useWorkflowApi() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 通用请求方法
  const request = useCallback(async <T>(
    url: string,
    options?: RequestInit
  ): Promise<T> => {
    setLoading(true);
    setError(null);

    try {
      return await requestResult<T>(`/api${url}`, options);
    } catch (err) {
      const message = err instanceof Error ? err.message : '请求失败';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // 获取工作流列表
  const listWorkflows = useCallback(async () => {
    return request<{ workflows: WorkflowDefinition[]; total: number }>(
      '/workflows'
    );
  }, [request]);

  // 获取单个工作流
  const getWorkflow = useCallback(async (id: string) => {
    return request<WorkflowDefinition>(`/workflows/${id}`);
  }, [request]);

  // 获取工作流定义（用于编辑器）
  const getWorkflowDefinition = useCallback(async (id: string) => {
    return request<WorkflowDefinition>(`/workflows/${id}/definition`);
  }, [request]);

  // 创建工作流
  const createWorkflow = useCallback(async (data: {
    name: string;
    description?: string;
    nodes?: WorkflowNode[];
    edges?: WorkflowEdge[];
  }) => {
    return request<WorkflowDefinition>('/workflows', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }, [request]);

  // 更新工作流
  const updateWorkflow = useCallback(async (
    id: string,
    data: {
      name?: string;
      description?: string;
      nodes?: WorkflowNode[];
      edges?: WorkflowEdge[];
    }
  ) => {
    return request<WorkflowDefinition>(`/workflows/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }, [request]);

  // 保存工作流定义（用于编辑器）
  const saveWorkflowDefinition = useCallback(async (
    id: string,
    data: {
      name?: string;
      description?: string;
      nodes?: WorkflowNode[];
      edges?: WorkflowEdge[];
      change_log?: string;
    }
  ) => {
    return request<WorkflowDefinition>(`/workflows/${id}/definition`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }, [request]);

  // 删除工作流
  const deleteWorkflow = useCallback(async (id: string) => {
    return request<{ message: string }>(`/workflows/${id}`, {
      method: 'DELETE',
    });
  }, [request]);

  // 验证工作流
  const validateWorkflow = useCallback(async (id: string, mode: 'save' | 'publish' = 'save') => {
    return request<ValidationResult & { mode: string }>(`/workflows/${id}/validate?mode=${mode}`, {
      method: 'POST',
    });
  }, [request]);

  // 发布工作流
  const publishWorkflow = useCallback(async (id: string, change_log?: string) => {
    return request<{ workflow: WorkflowDefinition, validation: ValidationResult, published_version_id: string }>(`/workflows/${id}/publish`, {
      method: 'POST',
      body: JSON.stringify({ change_log }),
    });
  }, [request]);

  // 编译工作流
  const compileWorkflow = useCallback(async (id: string) => {
    return request<CompileResult>(`/workflows/${id}/compile`, {
      method: 'POST',
    });
  }, [request]);

  return {
    loading,
    error,
    listWorkflows,
    getWorkflow,
    getWorkflowDefinition,
    createWorkflow,
    updateWorkflow,
    saveWorkflowDefinition,
    deleteWorkflow,
    validateWorkflow,
    publishWorkflow,
    compileWorkflow,
  };
}
