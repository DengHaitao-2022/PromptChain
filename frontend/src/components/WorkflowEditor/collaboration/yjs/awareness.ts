/**
 * Awareness (状态感知) 管理
 * 为什么这样分层：解耦用户的临时 UI 状态（鼠标位置、选区、在线情况）。这些状态不应落入 ydoc 持久化 DSL 中。
 */

import { provider } from './provider';

export interface UserPresence {
    id: string;
    name: string;
    color: string;
}

export interface AwarenessState {
    user: UserPresence;
    cursor: { x: number; y: number } | null;
    selection: string[];
}

export function updateCursor(cursor: { x: number; y: number } | null) {
    if (provider?.awareness) {
        provider.awareness.setLocalStateField('cursor', cursor);
    }
}

export function updateSelection(selection: string[]) {
    if (provider?.awareness) {
        provider.awareness.setLocalStateField('selection', selection);
    }
}

export function getAwarenessStates(): Map<number, AwarenessState> {
    if (!provider?.awareness) return new Map();
    return provider.awareness.getStates() as Map<number, AwarenessState>;
}

export function getRemoteSelections(localClientId: number): Map<string, UserPresence[]> {
    const states = getAwarenessStates();
    const selections = new Map<string, UserPresence[]>();

    states.forEach((state, clientId) => {
        if (clientId !== localClientId && state.user && state.selection) {
            state.selection.forEach(nodeId => {
                const users = selections.get(nodeId) || [];
                users.push(state.user);
                selections.set(nodeId, users);
            });
        }
    });

    return selections;
}
