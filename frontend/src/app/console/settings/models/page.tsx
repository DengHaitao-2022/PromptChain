'use client';

/**
 * 模型配置页面
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  MinusCircle,
  Pencil,
  PlayCircle,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  XCircle,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { apiUrl } from '@/lib/api-config';
import { formatAppDate } from '@/lib/date-time';
import styles from '../settings.module.css';

type ProviderType = 'openai' | 'anthropic' | 'google' | 'github' | 'ollama';

interface ModelProviderConfig {
  api_key?: string;
  base_url?: string;
  model?: string;
  model_name?: string;
  [key: string]: string | number | boolean | null | undefined;
}

interface ModelProvider {
  id: string;
  provider: string;
  name: string;
  description: string | null;
  enabled: boolean;
  is_default: boolean;
  runtime_supported: boolean;
  config: ModelProviderConfig;
  created_at: string;
  updated_at: string;
}

interface RuntimeModelInfo {
  provider: string;
  model: string;
  source: string;
  provider_id: string | null;
  provider_name: string | null;
}

type TestStepStatus = 'success' | 'warning' | 'failed' | 'skipped';

interface ModelProviderTestStep {
  name: string;
  label: string;
  status: TestStepStatus;
  message: string;
  duration_ms: number | null;
  detail?: {
    count?: number;
    response_preview?: string | null;
    sample?: string[];
    status_code?: number;
    [key: string]: string | number | string[] | null | undefined;
  };
}

interface ModelProviderTestResult {
  ok: boolean;
  provider_id: string;
  provider: string;
  model: string | null;
  models: string[];
  steps: ModelProviderTestStep[];
  duration_ms: number;
}

interface ModelProviderForm {
  provider: ProviderType;
  name: string;
  model: string;
  baseUrl: string;
  apiKey: string;
  description: string;
  enabled: boolean;
  setAsDefault: boolean;
}

const providerOptions: ProviderType[] = ['openai', 'anthropic', 'google', 'github', 'ollama'];

const providerLabels: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google Gemini',
  github: 'GitHub Models',
  ollama: 'Ollama',
  azure: 'Azure OpenAI',
  local: '本地模型',
  custom: '自定义',
};

const providerDefaultModels: Record<ProviderType, string> = {
  openai: 'gpt-4o',
  anthropic: 'claude-3-5-sonnet-20241022',
  google: 'gemini-2.5-flash',
  github: 'openai/gpt-4.1',
  ollama: 'qwen2.5:14b',
};

function createEmptyForm(): ModelProviderForm {
  return {
    provider: 'openai',
    name: 'OpenAI 默认配置',
    model: providerDefaultModels.openai,
    baseUrl: '',
    apiKey: '',
    description: '',
    enabled: true,
    setAsDefault: true,
  };
}

function getProviderLabel(provider: string) {
  return providerLabels[provider] || provider;
}

function getProviderModel(provider: ModelProvider) {
  return provider.config?.model || provider.config?.model_name || '使用供应商默认模型';
}

function formatDate(value: string) {
  return formatAppDate(value);
}

function getTestStepClass(status: TestStepStatus) {
  if (status === 'success') {
    return styles.success;
  }
  if (status === 'warning') {
    return styles.warning;
  }
  if (status === 'failed') {
    return styles.error;
  }
  return styles.neutral;
}

function getTestStepLabel(status: TestStepStatus) {
  if (status === 'success') {
    return '通过';
  }
  if (status === 'warning') {
    return '警告';
  }
  if (status === 'failed') {
    return '失败';
  }
  return '跳过';
}

function TestStepIcon({ status }: { status: TestStepStatus }) {
  if (status === 'success') {
    return <CheckCircle2 size={14} strokeWidth={2} />;
  }
  if (status === 'warning') {
    return <AlertCircle size={14} strokeWidth={2} />;
  }
  if (status === 'failed') {
    return <XCircle size={14} strokeWidth={2} />;
  }
  return <MinusCircle size={14} strokeWidth={2} />;
}

async function readApiError(response: Response, fallback: string) {
  try {
    const data = (await response.json()) as { detail?: string; message?: string };
    return data.detail || data.message || fallback;
  } catch {
    return fallback;
  }
}

export default function ModelsPage() {
  const { hasPermission } = useAuth();
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [runtime, setRuntime] = useState<RuntimeModelInfo | null>(null);
  const [supportedProviders, setSupportedProviders] = useState<string[]>(providerOptions);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingProviderId, setPendingProviderId] = useState<string | null>(null);
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [form, setForm] = useState<ModelProviderForm>(createEmptyForm);
  const [testResults, setTestResults] = useState<Record<string, ModelProviderTestResult>>({});
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');

  const canReadProviders = hasPermission('model_provider', 'read');
  const canCreateProviders = hasPermission('model_provider', 'create');
  const canUpdateProviders = hasPermission('model_provider', 'update');
  const canDeleteProviders = hasPermission('model_provider', 'delete');
  const canManageProviders = canCreateProviders || canUpdateProviders;

  const fetchProviders = useCallback(async () => {
    if (!canReadProviders) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch(apiUrl('/admin/model-providers'), {
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, '加载模型供应商失败'));
      }

      const data = (await response.json()) as {
        providers?: ModelProvider[];
        supported_providers?: string[];
      };
      setProviders(data.providers || []);
      setSupportedProviders(data.supported_providers || providerOptions);

      const runtimeResponse = await fetch(apiUrl('/admin/model-providers/runtime'), {
        credentials: 'include',
      });
      if (runtimeResponse.ok) {
        const runtimeData = (await runtimeResponse.json()) as {
          runtime?: RuntimeModelInfo;
          supported_providers?: string[];
        };
        setRuntime(runtimeData.runtime || null);
        setSupportedProviders(runtimeData.supported_providers || data.supported_providers || providerOptions);
      } else {
        setRuntime(null);
      }
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载模型供应商失败');
    } finally {
      setLoading(false);
    }
  }, [canReadProviders]);

  useEffect(() => {
    void fetchProviders();
  }, [fetchProviders]);

  const summary = useMemo(() => {
    const total = providers.length;
    const enabled = providers.filter((provider) => provider.enabled).length;
    const disabled = total - enabled;
    const families = new Set(providers.map((provider) => provider.provider)).size;

    return { total, enabled, disabled, families };
  }, [providers]);

  function openCreateForm() {
    setEditingProviderId(null);
    setForm(createEmptyForm());
    setFormVisible(true);
    setFeedback('');
    setError('');
  }

  function openEditForm(provider: ModelProvider) {
    const providerType = providerOptions.includes(provider.provider as ProviderType)
      ? (provider.provider as ProviderType)
      : 'openai';
    setEditingProviderId(provider.id);
    setForm({
      provider: providerType,
      name: provider.name,
      model: String(provider.config?.model || provider.config?.model_name || ''),
      baseUrl: String(provider.config?.base_url || ''),
      apiKey: '',
      description: provider.description || '',
      enabled: provider.enabled,
      setAsDefault: provider.is_default,
    });
    setFormVisible(true);
    setFeedback('');
    setError('');
  }

  function updateProvider(provider: ProviderType) {
    setForm((current) => ({
      ...current,
      provider,
      name: current.name ? current.name : `${getProviderLabel(provider)} 默认配置`,
      model: current.model ? current.model : providerDefaultModels[provider],
    }));
  }

  function buildConfigPayload() {
    const config: Record<string, string> = {};
    if (form.model.trim()) {
      config.model = form.model.trim();
    }
    if (form.baseUrl.trim()) {
      config.base_url = form.baseUrl.trim();
    }
    if (form.apiKey.trim()) {
      config.api_key = form.apiKey.trim();
    }
    return config;
  }

  async function handleSubmit() {
    if (!form.name.trim()) {
      setError('请填写配置名称');
      return;
    }

    setSaving(true);
    setFeedback('');
    setError('');

    const isEditing = Boolean(editingProviderId);
    const payload = {
      ...(isEditing ? {} : { provider: form.provider }),
      name: form.name.trim(),
      description: form.description.trim() || null,
      enabled: form.enabled,
      set_as_default: form.setAsDefault,
      config: buildConfigPayload(),
    };

    try {
      const response = await fetch(
        apiUrl(
          isEditing
            ? `/admin/model-providers/${editingProviderId}`
            : '/admin/model-providers',
        ),
        {
          method: isEditing ? 'PATCH' : 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) {
        throw new Error(await readApiError(response, isEditing ? '更新模型配置失败' : '创建模型配置失败'));
      }

      setFeedback(isEditing ? '模型配置已更新' : '模型配置已创建');
      setFormVisible(false);
      setEditingProviderId(null);
      setForm(createEmptyForm());
      await fetchProviders();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '保存模型配置失败');
    } finally {
      setSaving(false);
    }
  }

  async function patchProvider(provider: ModelProvider, payload: Record<string, unknown>, message: string) {
    setPendingProviderId(provider.id);
    setFeedback('');
    setError('');

    try {
      const response = await fetch(apiUrl(`/admin/model-providers/${provider.id}`), {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, '更新模型配置失败'));
      }
      setFeedback(message);
      await fetchProviders();
    } catch (patchError) {
      setError(patchError instanceof Error ? patchError.message : '更新模型配置失败');
    } finally {
      setPendingProviderId(null);
    }
  }

  async function handleDelete(provider: ModelProvider) {
    const confirmed = window.confirm(`确认删除「${provider.name}」吗？此操作不会删除历史运行记录。`);
    if (!confirmed) {
      return;
    }

    setPendingProviderId(provider.id);
    setFeedback('');
    setError('');

    try {
      const response = await fetch(apiUrl(`/admin/model-providers/${provider.id}`), {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, '删除模型配置失败'));
      }
      setFeedback('模型配置已删除');
      await fetchProviders();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : '删除模型配置失败');
    } finally {
      setPendingProviderId(null);
    }
  }

  async function handleTestProvider(provider: ModelProvider) {
    setTestingProviderId(provider.id);
    setFeedback('');
    setError('');

    const selectedModel = String(provider.config?.model || provider.config?.model_name || '').trim();

    try {
      const response = await fetch(apiUrl(`/admin/model-providers/${provider.id}/test`), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel || undefined,
        }),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, '模型供应商测试失败'));
      }

      const data = (await response.json()) as ModelProviderTestResult;
      setTestResults((current) => ({ ...current, [provider.id]: data }));
      setFeedback(data.ok ? '模型供应商测试通过' : '模型供应商测试完成，请查看未通过步骤');
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : '模型供应商测试失败');
    } finally {
      setTestingProviderId(null);
    }
  }

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
            统一管理工作空间默认推理入口，模型配置会直接影响后续内容工作流的实际调用。
          </p>
        </div>

        <div className={styles.heroActions}>
          <button className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => void fetchProviders()} type="button">
            <RefreshCw size={16} strokeWidth={2} />
            刷新配置
          </button>
          {canCreateProviders ? (
            <button className={styles.button} onClick={openCreateForm} type="button">
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
            <span className={styles.summaryMeta}>可参与运行时选择的供应商配置</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>当前模型</span>
            <span className={styles.summaryValue}>{runtime?.model || '未配置'}</span>
            <span className={styles.summaryMeta}>
              {runtime?.source === 'workspace'
                ? `${runtime.provider_name || '工作空间配置'}`
                : '环境变量回退'}
            </span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>供应商家族</span>
            <span className={styles.summaryValue}>{summary.families}</span>
            <span className={styles.summaryMeta}>用于观察当前接入的多样性与冗余度</span>
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

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>运行时配置</h2>
            <p className={styles.sectionDescription}>
              工作流启动时会优先读取当前工作空间的默认模型配置；若未配置，则回退到后端环境变量。
            </p>
          </div>
        </div>

        <div className={styles.runtimePanel}>
          <div className={styles.runtimeItem}>
            <span className={styles.summaryLabel}>当前来源</span>
            <span className={styles.runtimeValue}>
              {runtime?.source === 'workspace' ? '工作空间动态配置' : '环境变量回退'}
            </span>
          </div>
          <div className={styles.runtimeItem}>
            <span className={styles.summaryLabel}>供应商</span>
            <span className={styles.runtimeValue}>{runtime ? getProviderLabel(runtime.provider) : '未配置'}</span>
          </div>
          <div className={styles.runtimeItem}>
            <span className={styles.summaryLabel}>模型</span>
            <span className={styles.runtimeValue}>{runtime?.model || '未配置'}</span>
          </div>
        </div>
      </section>

      <Dialog.Root modal={false} open={formVisible && canManageProviders} onOpenChange={(open) => {
        if (!open) {
          setFormVisible(false);
          setEditingProviderId(null);
          setForm(createEmptyForm());
        }
      }}>
        <Dialog.Portal>
          <Dialog.Content className={styles.dialogContent}>
            <div className={styles.dialogHeader}>
              <Dialog.Title className={styles.dialogTitle}>
                {editingProviderId ? '编辑模型配置' : '添加模型供应商'}
              </Dialog.Title>
              <Dialog.Description className={styles.dialogDescription}>
                密钥只会在提交时写入后端，页面不会回显已保存的密钥内容。
              </Dialog.Description>
            </div>

            <div className={styles.dialogBody}>
              <div className={styles.formGrid} style={{ gridTemplateColumns: '1fr' }}>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>供应商</span>
                  <select
                    className={styles.select}
                    disabled={Boolean(editingProviderId)}
                    value={form.provider}
                    onChange={(event) => updateProvider(event.target.value as ProviderType)}
                  >
                    {providerOptions.map((provider) => (
                      <option key={provider} value={provider}>
                        {getProviderLabel(provider)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>配置名称</span>
                  <input
                    className={styles.input}
                    value={form.name}
                    onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="例如：生产内容生成默认模型"
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>模型名称</span>
                  <input
                    className={styles.input}
                    value={form.model}
                    onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                    placeholder={providerDefaultModels[form.provider]}
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Base URL</span>
                  <input
                    className={styles.input}
                    value={form.baseUrl}
                    onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
                    placeholder={form.provider === 'ollama' ? 'http://localhost:11434' : '默认留空'}
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>API Key / Token</span>
                  <input
                    className={styles.input}
                    type="password"
                    value={form.apiKey}
                    onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))}
                    placeholder={editingProviderId ? '留空则沿用已保存密钥' : 'Ollama 可留空'}
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>说明</span>
                  <textarea
                    className={styles.textarea}
                    value={form.description}
                    onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                    placeholder="记录用途、配额、环境或使用边界"
                  />
                </label>
              </div>

              <div className={styles.checkboxGrid} style={{ marginTop: '24px' }}>
                <label className={styles.checkboxRow}>
                  <input
                    checked={form.enabled}
                    type="checkbox"
                    onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                  />
                  启用此配置
                </label>
                <label className={styles.checkboxRow}>
                  <input
                    checked={form.setAsDefault}
                    type="checkbox"
                    onChange={(event) => setForm((current) => ({ ...current, setAsDefault: event.target.checked }))}
                  />
                  设为工作空间运行默认
                </label>
              </div>
            </div>

            <div className={styles.dialogFooter}>
              <Dialog.Close asChild>
                <button
                  className={`${styles.button} ${styles.buttonSecondary}`}
                  disabled={saving}
                  type="button"
                >
                  取消
                </button>
              </Dialog.Close>
              <button className={styles.button} disabled={saving} onClick={() => void handleSubmit()} type="button">
                {saving ? '保存中...' : editingProviderId ? '保存修改' : '创建配置'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

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
            {providers.map((provider) => {
              const pending = pendingProviderId === provider.id;
              const testing = testingProviderId === provider.id;
              const testResult = testResults[provider.id];
              return (
                <article key={provider.id} className={styles.moduleCard}>
                  <div className={styles.moduleIcon}>
                    <Bot size={22} strokeWidth={1.8} />
                  </div>
                  <div className={styles.moduleBody}>
                    <div className={styles.itemNameRow}>
                      <span className={styles.moduleName}>{provider.name}</span>
                      {provider.is_default ? (
                        <span className={`${styles.statusTag} ${styles.info}`}>
                          <CheckCircle2 size={12} strokeWidth={2} />
                          运行默认
                        </span>
                      ) : null}
                      <span className={`${styles.statusTag} ${provider.enabled ? styles.success : styles.neutral}`}>
                        {provider.enabled ? '已启用' : '已禁用'}
                      </span>
                      {!provider.runtime_supported ? (
                        <span className={`${styles.statusTag} ${styles.warning}`}>暂不支持运行</span>
                      ) : null}
                    </div>

                    <div className={styles.moduleDescription}>
                      {provider.description || '暂未填写说明，可用于记录接入模型、配额或用途边界。'}
                    </div>

                    <div className={styles.moduleMetaRow}>
                      <span className={`${styles.pill} ${styles.info}`}>
                        <Sparkles size={12} strokeWidth={2} />
                        {getProviderLabel(provider.provider)}
                      </span>
                      <span className={`${styles.pill} ${styles.neutral}`}>{getProviderModel(provider)}</span>
                      {provider.config?.base_url ? (
                        <span className={`${styles.pill} ${styles.neutral}`}>自定义 Base URL</span>
                      ) : null}
                      {provider.config?.api_key ? (
                        <span className={`${styles.pill} ${styles.neutral}`}>密钥已保存</span>
                      ) : null}
                      <span className={`${styles.pill} ${styles.neutral}`}>
                        更新于 {formatDate(provider.updated_at || provider.created_at)}
                      </span>
                    </div>

                    {testResult ? (
                      <div className={styles.testPanel} aria-live="polite">
                        <div className={styles.testHeader}>
                          <span className={styles.testTitle}>最近一次测试</span>
                          <span className={`${styles.statusTag} ${testResult.ok ? styles.success : styles.warning}`}>
                            {testResult.ok ? '全部通过' : '需要关注'}
                          </span>
                          <span className={`${styles.pill} ${styles.neutral}`}>{testResult.duration_ms} ms</span>
                        </div>
                        <div className={styles.testSteps}>
                          {testResult.steps.map((step) => (
                            <div key={step.name} className={styles.testStep}>
                              <span className={`${styles.statusTag} ${getTestStepClass(step.status)}`}>
                                <TestStepIcon status={step.status} />
                                {getTestStepLabel(step.status)}
                              </span>
                              <div className={styles.testStepBody}>
                                <span className={styles.testStepTitle}>
                                  {step.label}
                                  {typeof step.duration_ms === 'number' ? ` · ${step.duration_ms} ms` : ''}
                                </span>
                                <span className={styles.testStepMessage}>{step.message}</span>
                                {step.detail?.response_preview ? (
                                  <span className={styles.testStepMeta}>
                                    响应片段：{step.detail.response_preview}
                                  </span>
                                ) : null}
                                {step.detail?.sample?.length ? (
                                  <span className={styles.testStepMeta}>
                                    模型样例：{step.detail.sample.slice(0, 5).join('、')}
                                  </span>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {canUpdateProviders || canDeleteProviders ? (
                      <div className={styles.actionsRow}>
                        {canUpdateProviders ? (
                          <>
                            <button
                              className={`${styles.button} ${styles.buttonSecondary} ${styles.buttonSmall}`}
                              disabled={pending || testing || !provider.runtime_supported}
                              onClick={() => void handleTestProvider(provider)}
                              type="button"
                            >
                              <PlayCircle size={14} strokeWidth={2} />
                              {testing ? '测试中...' : '测试'}
                            </button>
                            <button
                              className={`${styles.button} ${styles.buttonSecondary} ${styles.buttonSmall}`}
                              disabled={pending || testing}
                              onClick={() => openEditForm(provider)}
                              type="button"
                            >
                              <Pencil size={14} strokeWidth={2} />
                              编辑
                            </button>
                            <button
                              className={`${styles.button} ${styles.buttonGhost} ${styles.buttonSmall}`}
                              disabled={pending || testing || provider.is_default || !provider.runtime_supported}
                              onClick={() =>
                                void patchProvider(
                                  provider,
                                  { enabled: true, set_as_default: true },
                                  '运行默认模型已更新',
                                )
                              }
                              type="button"
                            >
                              设为默认
                            </button>
                            <button
                              className={`${styles.button} ${styles.buttonGhost} ${styles.buttonSmall}`}
                              disabled={pending || testing}
                              onClick={() =>
                                void patchProvider(
                                  provider,
                                  { enabled: !provider.enabled },
                                  provider.enabled ? '模型配置已禁用' : '模型配置已启用',
                                )
                              }
                              type="button"
                            >
                              {provider.enabled ? '禁用' : '启用'}
                            </button>
                          </>
                        ) : null}
                        {canDeleteProviders ? (
                          <button
                            className={`${styles.button} ${styles.buttonDanger} ${styles.buttonSmall}`}
                            disabled={pending || testing}
                            onClick={() => void handleDelete(provider)}
                            type="button"
                          >
                            <Trash2 size={14} strokeWidth={2} />
                            删除
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>暂未配置模型供应商</div>
            <div className={styles.emptyText}>
              先登记 OpenAI、Anthropic、Google、GitHub Models 或 Ollama，再设为工作空间默认模型。
            </div>
            {canCreateProviders ? (
              <button className={styles.button} onClick={openCreateForm} type="button">
                <Plus size={16} strokeWidth={2} />
                添加第一条配置
              </button>
            ) : null}
          </div>
        )}
      </section>

      <p className={styles.helperText}>当前后端支持：{supportedProviders.map(getProviderLabel).join('、')}</p>
    </div>
  );
}
