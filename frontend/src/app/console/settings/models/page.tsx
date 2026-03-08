'use client';

/**
 * 模型配置页面
 */

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

interface ModelProvider {
    id: string;
    provider: string;
    name: string;
    description: string | null;
    enabled: boolean;
    created_at: string;
}

const providerLabels: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    google: 'Google',
    azure: 'Azure OpenAI',
    local: '本地模型',
    custom: '自定义',
};

export default function ModelsPage() {
    const { hasPermission } = useAuth();
    const [providers, setProviders] = useState<ModelProvider[]>([]);
    const [loading, setLoading] = useState(true);
    const canReadProviders = hasPermission('model_provider', 'read');

    useEffect(() => {
        if (!canReadProviders) {
            setLoading(false);
            return;
        }

        void fetchProviders();
    }, [canReadProviders]);

    async function fetchProviders() {
        try {
            const response = await fetch(`${API_BASE}/admin/model-providers`, {
                credentials: 'include',
            });
            if (response.ok) {
                const data = await response.json();
                setProviders(data.providers || []);
            }
        } catch (err) {
            console.error('加载失败', err);
        } finally {
            setLoading(false);
        }
    }

    if (!canReadProviders) {
        return (
            <div className={styles.container}>
                <h1 className={styles.title}>模型配置</h1>
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
            <h1 className={styles.title}>模型配置</h1>
            <p className={styles.subtitle}>配置 AI 模型供应商和参数</p>

            {hasPermission('model_provider', 'create') && (
                <div className={styles.section}>
                    <button className={styles.button}>
                        + 添加模型供应商
                    </button>
                </div>
            )}

            <div className={styles.section}>
                {loading ? (
                    <div className={styles.loading}><div className={styles.spinner} /></div>
                ) : providers.length > 0 ? (
                    <div className={styles.list}>
                        {providers.map((provider) => (
                            <div key={provider.id} className={styles.listItem}>
                                <div style={{
                                    width: 40,
                                    height: 40,
                                    borderRadius: 8,
                                    background: '#f3f4f6',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 20
                                }}>
                                    🤖
                                </div>
                                <div className={styles.itemInfo}>
                                    <div className={styles.itemName}>{provider.name}</div>
                                    <div className={styles.itemMeta}>
                                        {providerLabels[provider.provider] || provider.provider}
                                    </div>
                                </div>
                                <div>
                                    <span style={{
                                        display: 'inline-block',
                                        padding: '4px 12px',
                                        borderRadius: 20,
                                        fontSize: 12,
                                        background: provider.enabled ? '#d1fae5' : '#f3f4f6',
                                        color: provider.enabled ? '#059669' : '#6b7280',
                                    }}>
                                        {provider.enabled ? '已启用' : '已禁用'}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className={styles.empty}>
                        <p>暂未配置模型供应商</p>
                        <p style={{ fontSize: 14, marginTop: 8 }}>添加 OpenAI、Anthropic 等模型供应商开始使用</p>
                    </div>
                )}
            </div>
        </div>
    );
}
