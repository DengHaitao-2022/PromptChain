'use client';

import { useWorkflowContext } from '../../provider/WorkflowProvider';
import { selectSelectedNode } from '../../store/selectors';
import { useEffect, useState } from 'react';
import { provider } from '../yjs/provider';
import { getRemoteSelections } from '../yjs/awareness';
import { AlertCircle } from 'lucide-react';
import styles from './CollaborationStyles.module.css';

/**
 * 冲突提示软锁
 * 当用户选中一个正在被他人选中的节点时，给出提示。不阻断其继续编辑（软锁），但提示覆盖风险。
 */
export function ConflictHintToast() {
    const selectedNode = useWorkflowContext(selectSelectedNode);
    const [conflictUsers, setConflictUsers] = useState<string[]>([]);

    useEffect(() => {
        if (!provider || !selectedNode) {
            setConflictUsers([]);
            return;
        }

        const checkConflicts = () => {
            if (!provider) return;
            const localClientId = provider.awareness.clientID;
            const selections = getRemoteSelections(localClientId);
            const usersOnThisNode = selections.get(selectedNode.id) || [];
            setConflictUsers(usersOnThisNode.map(u => u.name));
        };

        checkConflicts();
        provider.awareness.on('change', checkConflicts);

        return () => {
            if (provider) {
                provider.awareness.off('change', checkConflicts);
            }
        };
    }, [selectedNode]);

    if (conflictUsers.length === 0) return null;

    return (
        <div className={styles.conflictHint}>
            <AlertCircle size={16} />
            <span>⚠️ 冲突警告: <strong>{conflictUsers.join(', ')}</strong> 也正在选中此节点。同时保存可能会互相覆盖。</span>
        </div>
    );
}
