/**
 * 状态管理 - 注入 Provider
 * 为什么这样分层：通过 React Context 隔离不同页面的工作流状态（虽然大部分时候只有单个编辑器，但为后续预留多开空间）。
 */

'use client';

import { createContext, useContext, useRef } from 'react';
import { useStore } from 'zustand';
import { type WorkflowStore, createWorkflowStore, type WorkflowState } from '../store/workflowStore';

export const WorkflowContext = createContext<WorkflowStore | null>(null);

interface WorkflowProviderProps extends React.PropsWithChildren {
    initialState?: Partial<WorkflowState>;
}

export function WorkflowProvider({ children, initialState }: WorkflowProviderProps) {
    const storeRef = useRef<WorkflowStore>(null);
    if (!storeRef.current) {
        storeRef.current = createWorkflowStore(initialState);
    }

    return (
        <WorkflowContext.Provider value={storeRef.current}>
            {children}
        </WorkflowContext.Provider>
    );
}

export function useWorkflowContext<T>(selector: (state: WorkflowState) => T): T {
    const store = useContext(WorkflowContext);
    if (!store) {
        throw new Error('useWorkflowContext must be used within a WorkflowProvider');
    }
    return useStore(store, selector);
}

export function useWorkflowStoreInstance() {
    const store = useContext(WorkflowContext);
    if (!store) {
        throw new Error('useWorkflowStoreInstance must be used within a WorkflowProvider');
    }
    return store;
}
