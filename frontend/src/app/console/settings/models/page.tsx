'use client';

/**
 * 模型配置页面
 */

import { useEffect, useMemo, useState } from 'react';
import { Bot, Plus, RefreshCw, Sparkles } from 'lucide-react';
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
  const [error, setError] = useState('');

  const canReadProviders = hasPermission('model_provider', 'read');
  const canCreateProviders = hasPermission('model_provider', 'create');

  async function fetchProviders() {
    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE}/admin/model-providers`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('加载模型供应商失败');
      }

      const data = (await response.json()) as { providers?: ModelProvider[] };
      setProviders(data.providers || []);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载模型供应商失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canReadProviders) {
      setLoading(false);
      return;
    }

    void fetchProviders();
  }, [canReadProviders]);

  const summary = useMemo(() => {
    const total = providers.length;
    const enabled = providers.filter((provider) => provider.enabled).length;
    const disabled = total - enabled;
    const families = new Set(providers.map((provider) => provider.provider)).size;

    return { total, enabled, disabled, families };
  }, [providers]);

  if (!canReadProviders) {
    return (
      <div className={styles.container}>
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <span className={styles.eyebrow}>Model Registry</span>
            <h1 className={styles.title}>模型配置</h1>
            <p className={styles.subtitle}>您当前没有查看模型配置的权限，请联系管理员开放访问。</p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.eyebrow}>Model Registry</span>
          <h1 className={styles.title}>模型配置</h1>
          <p className={styles.subtitle}>
            统一管理模型供应商、启用状态与接入节奏，为工作流运行提供稳定的推理入口。
          </p>
        </div>

        <div className={styles.heroActions}>
          <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void fetchProviders()} type="button">
            <RefreshCw size={16} strokeWidth={2} />
            刷新配置
          </button>
          {canCreateProviders ? (
            <button className={styles.button} type="button">
              <Plus size={16} strokeWidth={2} />
              添加模型供应商
            </button>
          ) : null}
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>供应商总数</span>
            <span className={styles.summaryValue}>{summary.total}</span>
            <span className={styles.summaryMeta}>已登记可供接入的模型端点数量</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>已启用</span>
            <span className={styles.summaryValue}>{summary.enabled}</span>
            <span className={styles.summaryMeta}>允许被工作流使用的供应商配置</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>已禁用</span>
            <span className={styles.summaryValue}>{summary.disabled}</span>
            <span className={styles.summaryMeta}>保留但暂不参与运行的供应商</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>供应商家族</span>
            <span className={styles.summaryValue}>{summary.families}</span>
            <span className={styles.summaryMeta}>用于观察当前接入的多样性与冗余度</span>
          </div>
        </div>
      </section>

      {error ? (
        <div className={`${styles.notice} ${styles.noticeError}`} role="alert">
          {error}
        </div>
      ) : null}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>供应商清单</h2>
            <p className={styles.sectionDescription}>
              当前页展示已登记的模型供应商、所属平台、接入说明和可用状态。
            </p>
          </div>
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
          </div>
        ) : providers.length > 0 ? (
          <div className={styles.moduleGrid}>
            {providers.map((provider) => (
              <article key={provider.id} className={styles.moduleCard}>
                <div className={styles.moduleIcon}>
                  <Bot size={22} strokeWidth={1.8} />
                </div>
                <div className={styles.moduleBody}>
                  <div className={styles.itemNameRow}>
                    <span className={styles.moduleName}>{provider.name}</span>
                    <span className={`${styles.statusTag} ${provider.enabled ? styles.success : styles.neutral}`}>
                      {provider.enabled ? '已启用' : '已禁用'}
                    </span>
                  </div>

                  <div className={styles.moduleDescription}>
                    {provider.description || '暂未填写说明，可用于记录接入模型、配额或用途边界。'}
                  </div>

                  <div className={styles.moduleMetaRow}>
                    <span className={`${styles.pill} ${styles.info}`}>
                      <Sparkles size={12} strokeWidth={2} />
                      {providerLabels[provider.provider] || provider.provider}
                    </span>
                    <span className={`${styles.pill} ${styles.neutral}`}>
                      创建于 {new Date(provider.created_at).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>暂未配置模型供应商</div>
            <div className={styles.emptyText}>
              先登记 OpenAI、Anthropic 或其他推理入口，再在工作流中绑定具体模型版本。
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
