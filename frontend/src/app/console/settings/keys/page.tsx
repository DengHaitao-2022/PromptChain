'use client';

/**
 * 密钥管理页面
 */

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

interface Secret {
    id: string;
    name: string;
    description: string | null;
    last4: string;
    created_at: string;
}

interface ApiKey {
    id: string;
    name: string;
    key_prefix: string;
    scopes: string[];
    expires_at: string | null;
    revoked_at: string | null;
    created_at: string;
}

export default function KeysPage() {
    const { hasPermission } = useAuth();
    const [secrets, setSecrets] = useState<Secret[]>([]);
    const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
    const [loading, setLoading] = useState(true);
    const canReadSecrets = hasPermission('secret', 'read');
    const canReadApiKeys = hasPermission('api_key', 'read');
    const canAccessPage = canReadSecrets || canReadApiKeys;

    useEffect(() => {
        if (!canAccessPage) {
            setLoading(false);
            return;
        }

        void fetchData();
    }, [canAccessPage]);

    async function fetchData() {
        try {
            const [secretsRes, keysRes] = await Promise.all([
                canReadSecrets ? fetch(`${API_BASE}/admin/secrets`, { credentials: 'include' }) : Promise.resolve(null),
                canReadApiKeys ? fetch(`${API_BASE}/admin/api-keys`, { credentials: 'include' }) : Promise.resolve(null),
            ]);

            if (canReadSecrets && secretsRes?.ok) {
                const data = await secretsRes.json();
                setSecrets(data.secrets || []);
            }

            if (canReadApiKeys && keysRes?.ok) {
                const data = await keysRes.json();
                setApiKeys(data.api_keys || []);
            }
        } catch (err) {
            console.error('加载失败', err);
        } finally {
            setLoading(false);
        }
    }

    if (!canAccessPage) {
        return (
            <div className={styles.container}>
                <h1 className={styles.title}>密钥管理</h1>
                <p className={styles.subtitle}>暂无访问权限</p>
                <div className={styles.empty}>
                    <p>您当前的账号角色无法查看或修改此页面配置。</p>
                    <p style={{ fontSize: 14, marginTop: 8 }}>
                        如需访问，请联系工作空间管理员为您分配权限。
                    </p>
                    <a href="/console" className={styles.button} style={{ marginTop: 16, display: 'inline-flex' }}>
                        返回控制台首页
                    </a>
                </div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <h1 className={styles.title}>密钥管理</h1>
            <p className={styles.subtitle}>管理密钥和 API Key</p>

            {/* 密钥部分 */}
            <div className={styles.section}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.sectionTitle}>密钥</h2>
                    {hasPermission('secret', 'create') && (
                        <button className={styles.button}>+ 添加密钥</button>
                    )}
                </div>

                {loading ? (
                    <div className={styles.loading}><div className={styles.spinner} /></div>
                ) : secrets.length > 0 ? (
                    <div className={styles.list}>
                        {secrets.map((secret) => (
                            <div key={secret.id} className={styles.listItem}>
                                <div style={{
                                    width: 40,
                                    height: 40,
                                    borderRadius: 8,
                                    background: '#fef3c7',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 20
                                }}>
                                    🔐
                                </div>
                                <div className={styles.itemInfo}>
                                    <div className={styles.itemName}>{secret.name}</div>
                                    <div className={styles.itemMeta}>***{secret.last4}</div>
                                </div>
                                <div className={styles.itemMeta}>
                                    {new Date(secret.created_at).toLocaleDateString()}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className={styles.empty}>
                        <p>暂无密钥</p>
                    </div>
                )}
            </div>

            {/* API Key 部分 */}
            <div className={styles.section}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.sectionTitle}>API Keys</h2>
                    {hasPermission('api_key', 'create') && (
                        <button className={styles.button}>+ 创建 API Key</button>
                    )}
                </div>

                {loading ? (
                    <div className={styles.loading}><div className={styles.spinner} /></div>
                ) : apiKeys.length > 0 ? (
                    <div className={styles.list}>
                        {apiKeys.map((key) => (
                            <div key={key.id} className={styles.listItem}>
                                <div style={{
                                    width: 40,
                                    height: 40,
                                    borderRadius: 8,
                                    background: '#dbeafe',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 20
                                }}>
                                    🔑
                                </div>
                                <div className={styles.itemInfo}>
                                    <div className={styles.itemName}>{key.name}</div>
                                    <div className={styles.itemMeta}>{key.key_prefix}</div>
                                </div>
                                <div>
                                    <span style={{
                                        display: 'inline-block',
                                        padding: '4px 12px',
                                        borderRadius: 20,
                                        fontSize: 12,
                                        background: key.revoked_at ? '#fee2e2' : '#d1fae5',
                                        color: key.revoked_at ? '#dc2626' : '#059669',
                                    }}>
                                        {key.revoked_at ? '已撤销' : '有效'}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className={styles.empty}>
                        <p>暂无 API Key</p>
                        <p style={{ fontSize: 14, marginTop: 8 }}>创建 API Key 供外部系统调用工作流</p>
                    </div>
                )}
            </div>
        </div>
    );
}
