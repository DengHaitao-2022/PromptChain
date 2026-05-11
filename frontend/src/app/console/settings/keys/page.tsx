'use client';

/**
 * 密钥管理页面
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Copy, KeyRound, LockKeyhole, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { apiUrl } from '@/lib/api-config';
import { authenticatedFetch } from '@/lib/auth';
import { formatAppDate } from '@/lib/date-time';
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
  description: string | null;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

interface ApiKeyCreateResponse {
  id: string;
  name: string;
  key: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  created_at: string;
  message?: string;
}

interface SecretForm {
  name: string;
  description: string;
  value: string;
}

interface ApiKeyForm {
  name: string;
  description: string;
  scopes: string[];
  expiresInDays: string;
}

const apiKeyScopes = ['execute', 'read', 'write', 'all'];

function createEmptySecretForm(): SecretForm {
  return {
    name: '',
    description: '',
    value: '',
  };
}

function createEmptyApiKeyForm(): ApiKeyForm {
  return {
    name: '',
    description: '',
    scopes: ['execute'],
    expiresInDays: '',
  };
}

function getScopeLabel(scope: string) {
  switch (scope) {
    case 'read':
      return '读取';
    case 'write':
      return '写入';
    case 'execute':
      return '执行';
    case 'all':
      return '全部权限';
    default:
      return scope;
  }
}

async function readApiError(response: Response, fallback: string) {
  try {
    const data = (await response.json()) as { detail?: string; message?: string };
    return data.detail || data.message || fallback;
  } catch {
    return fallback;
  }
}

export default function KeysPage() {
  const { hasPermission } = useAuth();
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [secretDialogOpen, setSecretDialogOpen] = useState(false);
  const [apiKeyDialogOpen, setApiKeyDialogOpen] = useState(false);
  const [secretForm, setSecretForm] = useState<SecretForm>(createEmptySecretForm);
  const [apiKeyForm, setApiKeyForm] = useState<ApiKeyForm>(createEmptyApiKeyForm);
  const [createdApiKey, setCreatedApiKey] = useState<ApiKeyCreateResponse | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');

  const canReadSecrets = hasPermission('secret', 'read');
  const canReadApiKeys = hasPermission('api_key', 'read');
  const canCreateSecrets = hasPermission('secret', 'create');
  const canCreateApiKeys = hasPermission('api_key', 'create');
  const canDeleteSecrets = hasPermission('secret', 'delete');
  const canDeleteApiKeys = hasPermission('api_key', 'delete');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const [secretsRes, keysRes] = await Promise.all([
        canReadSecrets ? authenticatedFetch(apiUrl('/admin/secrets')) : Promise.resolve(null),
        canReadApiKeys ? authenticatedFetch(apiUrl('/admin/api-keys')) : Promise.resolve(null),
      ]);

      if (secretsRes?.ok) {
        const secretData = (await secretsRes.json()) as { secrets?: Secret[] };
        setSecrets(secretData.secrets || []);
      } else if (secretsRes) {
        setSecrets([]);
        throw new Error(await readApiError(secretsRes, '加载平台密钥失败'));
      } else {
        setSecrets([]);
      }

      if (keysRes?.ok) {
        const keyData = (await keysRes.json()) as { api_keys?: ApiKey[] };
        setApiKeys(keyData.api_keys || []);
      } else if (keysRes) {
        setApiKeys([]);
        throw new Error(await readApiError(keysRes, '加载 API Key 失败'));
      } else {
        setApiKeys([]);
      }
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载密钥数据失败');
    } finally {
      setLoading(false);
    }
  }, [canReadApiKeys, canReadSecrets]);

  useEffect(() => {
    if (!canReadSecrets && !canReadApiKeys) {
      setLoading(false);
      return;
    }

    void fetchData();
  }, [canReadSecrets, canReadApiKeys, fetchData]);

  const summary = useMemo(() => {
    const totalSecrets = secrets.length;
    const totalApiKeys = apiKeys.length;
    const activeKeys = apiKeys.filter((key) => !key.revoked_at).length;
    const revokedKeys = totalApiKeys - activeKeys;

    return { totalSecrets, totalApiKeys, activeKeys, revokedKeys };
  }, [apiKeys, secrets]);

  function openSecretDialog() {
    setSecretForm(createEmptySecretForm());
    setSecretDialogOpen(true);
    setFeedback('');
    setError('');
  }

  function openApiKeyDialog() {
    setApiKeyForm(createEmptyApiKeyForm());
    setApiKeyDialogOpen(true);
    setCreatedApiKey(null);
    setCopyStatus('');
    setFeedback('');
    setError('');
  }

  async function handleCreateSecret() {
    if (!secretForm.name.trim()) {
      setError('请填写密钥名称');
      return;
    }

    if (!secretForm.value.trim()) {
      setError('请填写密钥值');
      return;
    }

    setSaving(true);
    setFeedback('');
    setError('');

    try {
      const response = await authenticatedFetch(apiUrl('/admin/secrets'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: secretForm.name.trim(),
          description: secretForm.description.trim() || null,
          value: secretForm.value,
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response, '创建平台密钥失败'));
      }

      setFeedback('平台密钥已创建');
      setSecretDialogOpen(false);
      setSecretForm(createEmptySecretForm());
      await fetchData();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : '创建平台密钥失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteSecret(secret: Secret) {
    const confirmed = window.confirm(`确认删除「${secret.name}」吗？此操作不会回显或恢复密钥值。`);
    if (!confirmed) {
      return;
    }

    setPendingId(`secret:${secret.id}`);
    setFeedback('');
    setError('');

    try {
      const response = await authenticatedFetch(apiUrl(`/admin/secrets/${secret.id}`), {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(await readApiError(response, '删除平台密钥失败'));
      }

      setFeedback('平台密钥已删除');
      await fetchData();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : '删除平台密钥失败');
    } finally {
      setPendingId(null);
    }
  }

  function toggleScope(scope: string, checked: boolean) {
    setApiKeyForm((current) => {
      const scopes = checked
        ? Array.from(new Set([...current.scopes, scope]))
        : current.scopes.filter((item) => item !== scope);
      return { ...current, scopes };
    });
  }

  async function handleCreateApiKey() {
    if (!apiKeyForm.name.trim()) {
      setError('请填写 API Key 名称');
      return;
    }

    if (apiKeyForm.scopes.length === 0) {
      setError('请至少选择一个权限范围');
      return;
    }

    const expiresInDays = apiKeyForm.expiresInDays.trim()
      ? Number(apiKeyForm.expiresInDays.trim())
      : null;

    if (expiresInDays !== null && (!Number.isInteger(expiresInDays) || expiresInDays <= 0)) {
      setError('有效期必须是大于 0 的整数天数');
      return;
    }

    setSaving(true);
    setFeedback('');
    setError('');
    setCopyStatus('');

    try {
      const response = await authenticatedFetch(apiUrl('/admin/api-keys'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: apiKeyForm.name.trim(),
          description: apiKeyForm.description.trim() || null,
          scopes: apiKeyForm.scopes,
          expires_in_days: expiresInDays,
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response, '创建 API Key 失败'));
      }

      const data = (await response.json()) as ApiKeyCreateResponse;
      setCreatedApiKey(data);
      setFeedback('API Key 已创建，请立即保存完整密钥');
      setApiKeyDialogOpen(false);
      setApiKeyForm(createEmptyApiKeyForm());
      await fetchData();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : '创建 API Key 失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleRevokeApiKey(apiKey: ApiKey) {
    const confirmed = window.confirm(`确认撤销「${apiKey.name}」吗？撤销后外部系统将无法继续使用此 API Key。`);
    if (!confirmed) {
      return;
    }

    setPendingId(`api-key:${apiKey.id}`);
    setFeedback('');
    setError('');

    try {
      const response = await authenticatedFetch(apiUrl(`/admin/api-keys/${apiKey.id}`), {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(await readApiError(response, '撤销 API Key 失败'));
      }

      setFeedback('API Key 已撤销');
      await fetchData();
    } catch (revokeError) {
      setError(revokeError instanceof Error ? revokeError.message : '撤销 API Key 失败');
    } finally {
      setPendingId(null);
    }
  }

  async function copyCreatedApiKey() {
    if (!createdApiKey) {
      return;
    }

    try {
      await navigator.clipboard.writeText(createdApiKey.key);
      setCopyStatus('已复制完整 API Key');
    } catch {
      setCopyStatus('');
      setError('复制失败，请手动选中并保存完整 API Key');
    }
  }

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
          {canCreateSecrets ? (
            <button className={styles.button} onClick={openSecretDialog} type="button">
              <Plus size={16} strokeWidth={2} />
              添加密钥
            </button>
          ) : null}
          {canCreateApiKeys ? (
            <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={openApiKeyDialog} type="button">
              <KeyRound size={16} strokeWidth={2} />
              创建 API Key
            </button>
          ) : null}
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

      {feedback ? (
        <div className={`${styles.notice} ${styles.noticeSuccess}`} role="status">
          {feedback}
        </div>
      ) : null}

      {error ? (
        <div className={`${styles.notice} ${styles.noticeError}`} role="alert">
          {error}
        </div>
      ) : null}

      {createdApiKey ? (
        <section className={`${styles.section} ${styles.secretReveal}`} aria-live="polite">
          <div className={styles.sectionHeader}>
            <div className={styles.sectionHeaderStack}>
              <h2 className={styles.sectionTitle}>请立即保存完整 API Key</h2>
              <p className={styles.sectionDescription}>
                完整密钥只会在创建后显示一次。关闭此提示后，页面只能看到前缀，无法再次查看完整值。
              </p>
            </div>
            <span className={`${styles.statusTag} ${styles.warning}`}>仅此一次</span>
          </div>
          <div className={styles.secretValueBox}>
            <code>{createdApiKey.key}</code>
          </div>
          <div className={styles.actionsRow}>
            <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void copyCreatedApiKey()} type="button">
              <Copy size={16} strokeWidth={2} />
              复制完整密钥
            </button>
            <button
              className={`${styles.button} ${styles.buttonGhost}`}
              onClick={() => {
                setCreatedApiKey(null);
                setCopyStatus('');
              }}
              type="button"
            >
              我已保存
            </button>
            {copyStatus ? <span className={`${styles.pill} ${styles.success}`}>{copyStatus}</span> : null}
          </div>
        </section>
      ) : null}

      <Dialog.Root modal={false} open={secretDialogOpen && canCreateSecrets} onOpenChange={(open) => {
        setSecretDialogOpen(open);
        if (!open) {
          setSecretForm(createEmptySecretForm());
        }
      }}>
        <Dialog.Portal>
          <Dialog.Content className={styles.dialogContent}>
            <div className={styles.dialogHeader}>
              <Dialog.Title className={styles.dialogTitle}>添加平台密钥</Dialog.Title>
              <Dialog.Description className={styles.dialogDescription}>
                密钥值会加密存储，创建后只展示尾号。请用清晰名称标注用途和环境。
              </Dialog.Description>
            </div>
            <div className={styles.dialogBody}>
              <div className={styles.stackedFields}>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>密钥名称</span>
                  <input
                    className={styles.input}
                    value={secretForm.name}
                    onChange={(event) => setSecretForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="例如：生产 OpenAI Key"
                  />
                </label>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>密钥值</span>
                  <input
                    className={styles.input}
                    type="password"
                    value={secretForm.value}
                    onChange={(event) => setSecretForm((current) => ({ ...current, value: event.target.value }))}
                    placeholder="粘贴完整密钥，提交后不再回显"
                  />
                </label>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>说明</span>
                  <textarea
                    className={styles.textarea}
                    value={secretForm.description}
                    onChange={(event) => setSecretForm((current) => ({ ...current, description: event.target.value }))}
                    placeholder="记录用途、环境、轮换负责人或过期策略"
                  />
                </label>
              </div>
            </div>
            <div className={styles.dialogFooter}>
              <Dialog.Close asChild>
                <button className={`${styles.button} ${styles.buttonSecondary}`} disabled={saving} type="button">
                  取消
                </button>
              </Dialog.Close>
              <button className={styles.button} disabled={saving} onClick={() => void handleCreateSecret()} type="button">
                {saving ? '创建中...' : '创建密钥'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root modal={false} open={apiKeyDialogOpen && canCreateApiKeys} onOpenChange={(open) => {
        setApiKeyDialogOpen(open);
        if (!open) {
          setApiKeyForm(createEmptyApiKeyForm());
        }
      }}>
        <Dialog.Portal>
          <Dialog.Content className={styles.dialogContent}>
            <div className={styles.dialogHeader}>
              <Dialog.Title className={styles.dialogTitle}>创建 API Key</Dialog.Title>
              <Dialog.Description className={styles.dialogDescription}>
                建议按调用方或业务场景拆分 API Key，后续可单独撤销，便于审计和风险隔离。
              </Dialog.Description>
            </div>
            <div className={styles.dialogBody}>
              <div className={styles.stackedFields}>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>名称</span>
                  <input
                    className={styles.input}
                    value={apiKeyForm.name}
                    onChange={(event) => setApiKeyForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="例如：官网内容生成入口"
                  />
                </label>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>说明</span>
                  <textarea
                    className={styles.textarea}
                    value={apiKeyForm.description}
                    onChange={(event) => setApiKeyForm((current) => ({ ...current, description: event.target.value }))}
                    placeholder="记录调用方、负责人、环境或权限边界"
                  />
                </label>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>有效期（天）</span>
                  <input
                    className={styles.input}
                    inputMode="numeric"
                    value={apiKeyForm.expiresInDays}
                    onChange={(event) => setApiKeyForm((current) => ({ ...current, expiresInDays: event.target.value }))}
                    placeholder="留空表示永不过期"
                  />
                </label>
                <div className={styles.field}>
                  <span className={styles.fieldLabel}>权限范围</span>
                  <div className={styles.checkboxGrid}>
                    {apiKeyScopes.map((scope) => (
                      <label key={scope} className={styles.checkboxRow}>
                        <input
                          checked={apiKeyForm.scopes.includes(scope)}
                          type="checkbox"
                          onChange={(event) => toggleScope(scope, event.target.checked)}
                        />
                        {getScopeLabel(scope)}
                      </label>
                    ))}
                  </div>
                  <p className={styles.helperText}>只给外部系统需要的最小权限；不确定时优先选择“执行”。</p>
                </div>
              </div>
            </div>
            <div className={styles.dialogFooter}>
              <Dialog.Close asChild>
                <button className={`${styles.button} ${styles.buttonSecondary}`} disabled={saving} type="button">
                  取消
                </button>
              </Dialog.Close>
              <button className={styles.button} disabled={saving} onClick={() => void handleCreateApiKey()} type="button">
                {saving ? '创建中...' : '创建 API Key'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

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
              <button className={styles.button} onClick={openSecretDialog} type="button">
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
                      创建于 {formatAppDate(secret.created_at)}
                    </span>
                  </div>
                  {canDeleteSecrets ? (
                    <div className={styles.actionsRow}>
                      <button
                        className={`${styles.button} ${styles.buttonDanger} ${styles.buttonSmall}`}
                        disabled={pendingId === `secret:${secret.id}`}
                        onClick={() => void handleDeleteSecret(secret)}
                        type="button"
                      >
                        <Trash2 size={14} strokeWidth={2} />
                        {pendingId === `secret:${secret.id}` ? '删除中...' : '删除'}
                      </button>
                    </div>
                  ) : null}
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
              <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={openApiKeyDialog} type="button">
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
                    {key.description || '暂未填写说明，可用于记录调用方、权限边界或轮换策略。'}
                  </div>
                  <div className={styles.moduleMetaRow}>
                    <span className={`${styles.pill} ${styles.neutral}`}>前缀：{key.key_prefix}</span>
                    <span className={`${styles.pill} ${styles.info}`}>
                      权限：{key.scopes.length > 0 ? key.scopes.map(getScopeLabel).join(' / ') : '未标注'}
                    </span>
                    <span className={`${styles.pill} ${key.expires_at ? styles.warning : styles.neutral}`}>
                      {key.expires_at ? `到期 ${formatAppDate(key.expires_at)}` : '永不过期'}
                    </span>
                    <span className={`${styles.pill} ${styles.neutral}`}>
                      {key.last_used_at ? `最近使用 ${formatAppDate(key.last_used_at)}` : '尚未使用'}
                    </span>
                    <span className={`${styles.pill} ${styles.neutral}`}>
                      创建于 {formatAppDate(key.created_at)}
                    </span>
                  </div>
                  {canDeleteApiKeys && !key.revoked_at ? (
                    <div className={styles.actionsRow}>
                      <button
                        className={`${styles.button} ${styles.buttonDanger} ${styles.buttonSmall}`}
                        disabled={pendingId === `api-key:${key.id}`}
                        onClick={() => void handleRevokeApiKey(key)}
                        type="button"
                      >
                        <Trash2 size={14} strokeWidth={2} />
                        {pendingId === `api-key:${key.id}` ? '撤销中...' : '撤销'}
                      </button>
                    </div>
                  ) : key.revoked_at ? (
                    <div className={styles.moduleMetaRow}>
                      <span className={`${styles.pill} ${styles.error}`}>撤销于 {formatAppDate(key.revoked_at)}</span>
                    </div>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>暂无 API Key</div>
            <div className={styles.emptyText}>创建 API Key 后，外部系统才能以受控方式调用工作流能力。</div>
            {canCreateApiKeys ? (
              <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={openApiKeyDialog} type="button">
                <Plus size={16} strokeWidth={2} />
                创建第一枚 API Key
              </button>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
