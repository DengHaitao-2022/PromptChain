'use client';

import { useMemo, useSyncExternalStore } from 'react';
import type { WebsocketProvider } from 'y-websocket';
import type { AwarenessState } from '../yjs/awareness';
import styles from './CollaborationStyles.module.css';

interface UserPresenceAvatarStackProps {
    provider: WebsocketProvider | null;
}

export function UserPresenceAvatarStack({ provider }: UserPresenceAvatarStackProps) {
    const serializedRemoteUsers = useSyncExternalStore(
        (onStoreChange) => {
            if (!provider) return () => undefined;
            provider.awareness.on('change', onStoreChange);
            return () => provider.awareness.off('change', onStoreChange);
        },
        () => {
            if (!provider) return '[]';
            const states = provider.awareness.getStates() as Map<number, AwarenessState>;
            const users = Array.from(states.entries())
                .filter(([clientId, state]) => clientId !== provider.awareness.clientID && state.user)
                .map(([, state]) => state.user);
            return JSON.stringify(users);
        },
        () => '[]',
    );

    // 过滤掉自己
    const remoteUsers = useMemo(
        () => JSON.parse(serializedRemoteUsers) as AwarenessState['user'][],
        [serializedRemoteUsers],
    );

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
