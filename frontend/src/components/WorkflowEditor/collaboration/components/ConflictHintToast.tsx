'use client';

import { useWorkflowContext } from '../../provider/WorkflowProvider';
import { selectSelectedNode } from '../../store/selectors';
import { useSyncExternalStore } from 'react';
import type { WebsocketProvider } from 'y-websocket';
import { getRemoteSelections } from '../yjs/awareness';
import { AlertCircle } from 'lucide-react';
import styles from './CollaborationStyles.module.css';

/**
 * 冲突提示软锁
 * 当用户选中一个正在被他人选中的节点时，给出提示。不阻断其继续编辑（软锁），但提示覆盖风险。
 */
interface ConflictHintToastProps {
    provider: WebsocketProvider | null;
}

export function ConflictHintToast({ provider }: ConflictHintToastProps) {
    const selectedNode = useWorkflowContext(selectSelectedNode);
    const conflictUsersText = useSyncExternalStore(
        (onStoreChange) => {
            if (!provider) return () => undefined;
            provider.awareness.on('change', onStoreChange);
            return () => provider.awareness.off('change', onStoreChange);
        },
        () => {
            if (!provider || !selectedNode) return '';
            const selections = getRemoteSelections(provider.awareness.clientID);
            return (selections.get(selectedNode.id) || []).map((user) => user.name).join(',');
        },
        () => '',
    );
    const conflictUsers = conflictUsersText ? conflictUsersText.split(',') : [];

    if (conflictUsers.length === 0) return null;

    return (
        <div className={styles.conflictHint}>
            <AlertCircle size={16} />
            <span>⚠️ 冲突警告: <strong>{conflictUsers.join(', ')}</strong> 也正在选中此节点。同时保存可能会互相覆盖。</span>
        </div>
    );
}
