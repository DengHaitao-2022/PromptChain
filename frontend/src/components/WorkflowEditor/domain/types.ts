/**
 * 领域模型 - 类型定义
 * 为什么这样分层：将所有与后端契约对齐的领域层类型收敛在一处，避免散落在 UI 组件内部。后续扩展新的节点类型时，也只需要修改这里的领域配置。
 */

export type NodeType = 'input' | 'process' | 'gate' | 'checker' | 'output';

export interface WorkflowNodePosition {
    x: number;
    y: number;
}

export interface WorkflowNodeData {
    label: string;
    config?: Record<string, unknown>;
}

export interface WorkflowNode {
    id: string;
    type: string;
    position: WorkflowNodePosition;
    data: WorkflowNodeData;
}

export interface WorkflowEdgeData {
    condition?: string;
    label?: string;
}

export interface WorkflowEdge {
    id: string;
    source: string;
    target: string;
    type?: string;
    data?: WorkflowEdgeData;
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
