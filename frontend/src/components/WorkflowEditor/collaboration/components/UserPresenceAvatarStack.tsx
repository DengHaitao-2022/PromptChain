'use client';

import { useEffect, useState } from 'react';
import { provider } from '../yjs/provider';
import type { AwarenessState } from '../yjs/awareness';
import styles from './CollaborationStyles.module.css';

export function UserPresenceAvatarStack() {
    const [states, setStates] = useState<Map<number, AwarenessState>>(new Map());
    const [localClientId, setLocalClientId] = useState<number | null>(null);

    useEffect(() => {
        if (!provider) return;

        setLocalClientId(provider.awareness.clientID);

        const updateStates = () => {
            if (!provider) return;
            setStates(new Map(provider.awareness.getStates() as Map<number, AwarenessState>));
        };

        // 初始获取
        updateStates();

        provider.awareness.on('change', updateStates);
        return () => {
            if (provider) {
                provider.awareness.off('change', updateStates);
            }
        };
    }, []);

    // 过滤掉自己
    const remoteUsers = Array.from(states.entries())
        .filter(([clientId, state]) => clientId !== localClientId && state.user)
        .map(([_, state]) => state.user);

    if (remoteUsers.length === 0) {
        return null; // 没有其他在线成员时不渲染栈
    }

    return (
        <div className={styles.avatarStack}>
            {remoteUsers.slice(0, 4).map((user, index) => (
                <div
                    key={user.id}
                    className={styles.avatar}
                    style={{ backgroundColor: user.color, zIndex: 10 - index }}
                    title={`${user.name} 正在浏览`}
                >
                    {user.name.charAt(0).toUpperCase()}
                </div>
            ))}
            {remoteUsers.length > 4 && (
                <div className={styles.avatarMore}>
                    +{remoteUsers.length - 4}
                </div>
            )}
        </div>
    );
}
