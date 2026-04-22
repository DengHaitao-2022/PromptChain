'use client';

import { type Node, type Edge } from '@xyflow/react';
import type { ValidationResult } from './hooks/useWorkflowApi';
import { WorkflowProvider } from './provider/WorkflowProvider';
import { WorkflowEditorShell } from './WorkflowEditorShell';
import { useMemo } from 'react';

interface WorkflowEditorActionState {
    isSaving?: boolean;
    isValidating?: boolean;
    isPublishing?: boolean;
    statusMessage?: string | null;
    errorMessage?: string | null;
    validation?: ValidationResult | null;
}

export interface WorkflowEditorProps {
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

/**
 * 工作流编辑器 - 壳组件装配
 * 为什么这样分层：把原先大一统的组件拆分，这里只负责注入 Provider 并将传入的初始状态写入 store。
 * 真正的画布和 UI 逻辑在 WorkflowEditorShell 中。
 */
export default function WorkflowEditor(props: WorkflowEditorProps) {
    const autoResetKey = `${props.workflowId ?? 'new'}-${!!props.initialNodes}`;

    const initialState = useMemo(() => ({
        nodes: props.initialNodes ?? [],
        edges: props.initialEdges ?? [],
        readOnly: props.readOnly ?? false,
    }), [props.initialNodes, props.initialEdges, props.readOnly]);

    return (
        <WorkflowProvider key={autoResetKey} initialState={initialState}>
            <WorkflowEditorShell {...props} />
        </WorkflowProvider>
    );
}
