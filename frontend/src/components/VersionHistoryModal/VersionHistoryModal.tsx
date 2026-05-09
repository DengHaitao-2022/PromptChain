'use client';

import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import styles from './VersionHistoryModal.module.css';
import { artifactApi } from '@/lib/api';
import { formatCompactAppDateTime } from '@/lib/date-time';

interface VersionInfo {
    id: string;
    version: number;
    created_at: string;
    content_hash: string;
    parent_version: string | null;
}

interface VersionHistoryModalProps {
    artifactId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onVersionSelect?: (versionId: string) => void;
}

export function VersionHistoryModal({
    artifactId,
    open,
    onOpenChange,
    onVersionSelect,
}: VersionHistoryModalProps) {
    const [versions, setVersions] = React.useState<VersionInfo[]>([]);
    const [loading, setLoading] = React.useState(false);
    const [selectedVersions, setSelectedVersions] = React.useState<string[]>([]);

    // 加载版本历史
    React.useEffect(() => {
        if (open && artifactId) {
            loadVersionHistory();
        }
    }, [open, artifactId]);

    const loadVersionHistory = async () => {
        setLoading(true);
        try {
            const response = await artifactApi.getHistory(artifactId);
            setVersions(response.history as unknown as VersionInfo[]);
        } catch (error) {
            console.error('Failed to load version history:', error);
        } finally {
            setLoading(false);
        }
    };

    // 格式化时间
    const formatTime = (timestamp: string) => {
        return formatCompactAppDateTime(timestamp);
    };

    // 切换版本选择
    const toggleVersionSelect = (versionId: string) => {
        if (selectedVersions.includes(versionId)) {
            setSelectedVersions(selectedVersions.filter((v) => v !== versionId));
        } else if (selectedVersions.length < 2) {
            setSelectedVersions([...selectedVersions, versionId]);
        }
    };

    return (
        <Dialog.Root open={open} onOpenChange={onOpenChange}>
            <Dialog.Portal>
                <Dialog.Overlay className={styles.overlay} />
                <Dialog.Content className={styles.content}>
                    <Dialog.Title className={styles.title}>
                        版本历史
                    </Dialog.Title>
                    <Dialog.Description className={styles.description}>
                        查看产物的所有历史版本，选择两个版本可进行对比
                    </Dialog.Description>

                    {loading ? (
                        <div className={styles.loading}>
                            <div className="spinner" />
                            <span>加载中...</span>
                        </div>
                    ) : (
                        <div className={styles.versionList}>
                            {versions.map((version, index) => (
                                <div
                                    key={version.id}
                                    className={`${styles.versionItem} ${selectedVersions.includes(version.id) ? styles.selected : ''
                                        }`}
                                    onClick={() => toggleVersionSelect(version.id)}
                                >
                                    <div className={styles.versionIndex}>
                                        v{version.version}
                                    </div>
                                    <div className={styles.versionInfo}>
                                        <div className={styles.versionTime}>
                                            {formatTime(version.created_at)}
                                        </div>
                                        <div className={styles.versionHash}>
                                            Hash: {version.content_hash.slice(0, 8)}...
                                        </div>
                                    </div>
                                    {index === 0 && (
                                        <span className="badge badge-success">当前</span>
                                    )}
                                    {version.parent_version && (
                                        <div className={styles.parentLink}>
                                            ← v{versions.find((v) => v.id === version.parent_version)?.version || '?'}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className={styles.actions}>
                        {selectedVersions.length === 2 && (
                            <button
                                className="btn btn-secondary"
                                onClick={() => {
                                    // TODO: 打开对比视图
                                    console.log('Compare:', selectedVersions);
                                }}
                            >
                                对比版本
                            </button>
                        )}
                        <Dialog.Close asChild>
                            <button className="btn btn-ghost">关闭</button>
                        </Dialog.Close>
                    </div>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
