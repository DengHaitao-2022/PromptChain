'use client';

import { Wifi, WifiOff, RefreshCcw } from 'lucide-react';
import styles from './CollaborationStyles.module.css';

interface ConnectionStatusBadgeProps {
    status: 'connecting' | 'connected' | 'disconnected';
}

export function ConnectionStatusBadge({ status }: ConnectionStatusBadgeProps) {
    if (status === 'connected') {
        return (
            <div className={`${styles.connectionBadge} ${styles.connected}`} title="已连接到协作服务器">
                <Wifi size={14} />
                <span className={styles.statusText}>已同步</span>
            </div>
        );
    }

    if (status === 'connecting') {
        return (
            <div className={`${styles.connectionBadge} ${styles.connecting}`} title="正在连接协作服务器...">
                <RefreshCcw size={14} className={styles.spin} />
                <span className={styles.statusText}>连接中...</span>
            </div>
        );
    }

    return (
        <div className={`${styles.connectionBadge} ${styles.disconnected}`} title="协作连接断开，目前为单人本地模式">
            <WifiOff size={14} />
            <span className={styles.statusText}>本地模式</span>
        </div>
    );
}
