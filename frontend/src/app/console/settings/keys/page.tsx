'use client';

/**
 * 密钥管理页面
 */

import { useEffect, useMemo, useState } from 'react';
import { KeyRound, LockKeyhole, Plus, RefreshCw } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { apiUrl } from '@/lib/api-config';
import styles from '../settings.module.css';

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
  const [error, setError] = useState('');

  const canReadSecrets = hasPermission('secret', 'read');
  const canReadApiKeys = hasPermission('api_key', 'read');
  const canCreateSecrets = hasPermission('secret', 'create');
  const canCreateApiKeys = hasPermission('api_key', 'create');

  async function fetchData() {
    setLoading(true);
    setError('');

    try {
      const [secretsRes, keysRes] = await Promise.all([
        fetch(apiUrl('/admin/secrets'), { credentials: 'include' }),
        fetch(apiUrl('/admin/api-keys'), { credentials: 'include' }),
      ]);

      if (secretsRes.ok) {
        const secretData = (await secretsRes.json()) as { secrets?: Secret[] };
        setSecrets(secretData.secrets || []);
      } else {
        setSecrets([]);
      }

      if (keysRes.ok) {
        const keyData = (await keysRes.json()) as { api_keys?: ApiKey[] };
        setApiKeys(keyData.api_keys || []);
      } else {
        setApiKeys([]);
      }

      if (!secretsRes.ok && !keysRes.ok) {
        throw new Error('加载密钥数据失败');
      }
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载密钥数据失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canReadSecrets && !canReadApiKeys) {
      setLoading(false);
      return;
    }

    void fetchData();
  }, [canReadSecrets, canReadApiKeys]);

  const summary = useMemo(() => {
    const totalSecrets = secrets.length;
    const totalApiKeys = apiKeys.length;
    const activeKeys = apiKeys.filter((key) => !key.revoked_at).length;
    const revokedKeys = totalApiKeys - activeKeys;

    return { totalSecrets, totalApiKeys, activeKeys, revokedKeys };
  }, [apiKeys, secrets]);

  if (!canReadSecrets && !canReadApiKeys) {
    return (
      <div className={styles.container}>
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <span className={styles.eyebrow}>Secrets Vault</span>
            <h1 className={styles.title}>密钥管理</h1>
            <p className={styles.subtitle}>您当前没有查看密钥或 API Key 的权限，请联系管理员开放访问。</p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.eyebrow}>Secrets Vault</span>
          <h1 className={styles.title}>密钥管理</h1>
          <p className={styles.subtitle}>
            管理平台密钥、对外 API Key 与生命周期状态，保持供应商接入与外部调用链路清晰可控。
          </p>
        </div>

        <div className={styles.heroActions}>
          <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void fetchData()} type="button">
            <RefreshCw size={16} strokeWidth={2} />
            刷新数据
          </button>
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>平台密钥</span>
            <span className={styles.summaryValue}>{summary.totalSecrets}</span>
            <span className={styles.summaryMeta}>用于模型供应商、Webhook 或第三方服务接入</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>API Key</span>
            <span className={styles.summaryValue}>{summary.totalApiKeys}</span>
            <span className={styles.summaryMeta}>给外部系统调用工作流或管理接口的凭证</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>有效中</span>
            <span className={styles.summaryValue}>{summary.activeKeys}</span>
            <span className={styles.summaryMeta}>仍可继续使用的 API Key 数量</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>已撤销</span>
            <span className={styles.summaryValue}>{summary.revokedKeys}</span>
            <span className={styles.summaryMeta}>已失效或主动停用的历史凭证</span>
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
            <h2 className={styles.sectionTitle}>平台密钥</h2>
            <p className={styles.sectionDescription}>
              存放供应商访问凭证。界面只展示名称和尾号，避免泄漏完整值。
            </p>
          </div>
          {canCreateSecrets ? (
            <div className={styles.sectionActions}>
              <button className={styles.button} type="button">
                <Plus size={16} strokeWidth={2} />
                添加密钥
              </button>
            </div>
          ) : null}
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
          </div>
        ) : secrets.length > 0 ? (
          <div className={styles.moduleGrid}>
            {secrets.map((secret) => (
              <article key={secret.id} className={styles.moduleCard}>
                <div className={styles.moduleIcon}>
                  <LockKeyhole size={22} strokeWidth={1.8} />
                </div>
                <div className={styles.moduleBody}>
                  <div className={styles.itemNameRow}>
                    <span className={styles.moduleName}>{secret.name}</span>
                    <span className={`${styles.statusTag} ${styles.warning}`}>仅展示尾号</span>
                  </div>
                  <div className={styles.moduleDescription}>
                    {secret.description || '暂未填写说明，可用于记录用途、环境或过期策略。'}
                  </div>
                  <div className={styles.moduleMetaRow}>
                    <span className={`${styles.pill} ${styles.neutral}`}>***{secret.last4}</span>
                    <span className={`${styles.pill} ${styles.info}`}>
                      创建于 {new Date(secret.created_at).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>暂无平台密钥</div>
            <div className={styles.emptyText}>添加供应商访问凭证后，模型、邮件或外部服务才能进入可配置状态。</div>
          </div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>API Key</h2>
            <p className={styles.sectionDescription}>
              供外部系统调用工作流或管理接口。建议按用途拆分，并在不再使用时及时撤销。
            </p>
          </div>
          {canCreateApiKeys ? (
            <div className={styles.sectionActions}>
              <button className={`${styles.button} ${styles.buttonSecondary}`} type="button">
                <Plus size={16} strokeWidth={2} />
                创建 API Key
              </button>
            </div>
          ) : null}
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
          </div>
        ) : apiKeys.length > 0 ? (
          <div className={styles.moduleGrid}>
            {apiKeys.map((key) => (
              <article key={key.id} className={styles.moduleCard}>
                <div className={styles.moduleIcon}>
                  <KeyRound size={22} strokeWidth={1.8} />
                </div>
                <div className={styles.moduleBody}>
                  <div className={styles.itemNameRow}>
                    <span className={styles.moduleName}>{key.name}</span>
                    <span className={`${styles.statusTag} ${key.revoked_at ? styles.error : styles.success}`}>
                      {key.revoked_at ? '已撤销' : '有效'}
                    </span>
                  </div>
                  <div className={styles.moduleDescription}>
                    前缀：{key.key_prefix}
                    {key.expires_at ? `，到期时间 ${new Date(key.expires_at).toLocaleDateString('zh-CN')}` : '，未设置自动过期'}
                  </div>
                  <div className={styles.moduleMetaRow}>
                    <span className={`${styles.pill} ${styles.info}`}>
                      权限：{key.scopes.length > 0 ? key.scopes.join(' / ') : '未标注'}
                    </span>
                    <span className={`${styles.pill} ${styles.neutral}`}>
                      创建于 {new Date(key.created_at).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>暂无 API Key</div>
            <div className={styles.emptyText}>创建 API Key 后，外部系统才能以受控方式调用工作流能力。</div>
          </div>
        )}
      </section>
    </div>
  );
}
