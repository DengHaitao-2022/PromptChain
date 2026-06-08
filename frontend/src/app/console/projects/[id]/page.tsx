'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowRight,
  DatabaseZap,
  FilePlus2,
  History,
  Layers3,
  Play,
  RefreshCw,
  Save,
  Sparkles,
} from 'lucide-react';

import {
  scenarioApi,
  type ContentProject,
  type ProjectAsset,
  type ScenarioFormField,
  type ScenarioGenerationMode,
  type ScenarioTemplate,
  type WorkflowRunSummary,
} from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';
import styles from '../scenario-workbench.module.css';

type Tab = 'overview' | 'assets' | 'generate' | 'memory' | 'runs';
const TAB_VALUES: Tab[] = ['overview', 'assets', 'generate', 'memory', 'runs'];

interface MemoryUpdateCandidate {
  asset_type?: string;
  title?: string;
  content?: unknown;
  candidate_index?: number;
  source_artifact_id?: string | null;
  metadata?: Record<string, unknown>;
}

const assetTypeLabels: Record<string, string> = {
  story_bible: 'Story Bible',
  character_card: '人物卡',
  world_setting: '世界观',
  plot_arc: '主线大纲',
  timeline_event: '时间线事件',
  chapter_outline: '章节大纲',
  scene_draft: '场景草稿',
  style_guide: '风格指南',
  foreshadowing_record: '伏笔记录',
  consistency_report: '一致性报告',
  brand_voice: '品牌语气',
  audience_profile: '受众画像',
  product_knowledge: '产品知识',
  campaign_brief: '活动简报',
  content_variants: '内容版本',
  topic_brief: '选题简报',
  hook_options: '开场钩子',
  script_outline: '脚本大纲',
  shot_list: '分镜清单',
  voiceover_script: '口播稿',
  caption_pack: '标题字幕包',
  platform_variant: '平台变体',
  requirement_card: '需求卡片',
  user_story: '用户故事',
  feature_list: '功能清单',
  business_flow: '业务流程',
  exception_flow: '异常流程',
  acceptance_criteria: '验收标准',
  risk_report: '风险报告',
};

function stringifyContent(value: unknown) {
  if (typeof value === 'string') {
    return value;
  }
  return JSON.stringify(value ?? {}, null, 2);
}

function parseContent(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function assetTypeLabel(value: string) {
  return assetTypeLabels[value] || value;
}

function parseTabParam(value: string | null): Tab | null {
  return TAB_VALUES.includes(value as Tab) ? (value as Tab) : null;
}

function getMemoryCandidates(run: WorkflowRunSummary): MemoryUpdateCandidate[] {
  const candidates = run.metadata?.project_memory_update_candidates;
  return Array.isArray(candidates)
    ? candidates.filter((candidate): candidate is MemoryUpdateCandidate =>
        Boolean(candidate && typeof candidate === 'object'),
      )
    : [];
}

function metadataText(value: unknown, fallback: string) {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function buildPrompt(
  mode: ScenarioGenerationMode | undefined,
  values: Record<string, string>,
  project: ContentProject | null,
) {
  const parts = [
    `项目：${project?.title || ''}`,
    mode ? `生成模式：${mode.name}` : '',
    ...Object.entries(values)
      .filter(([, value]) => value.trim())
      .map(([key, value]) => `${key}: ${value}`),
  ];
  return parts.filter(Boolean).join('\n');
}

export default function ProjectWorkbenchPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = params.id;
  const [project, setProject] = useState<ContentProject | null>(null);
  const [scenario, setScenario] = useState<ScenarioTemplate | null>(null);
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [runs, setRuns] = useState<WorkflowRunSummary[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [assetType, setAssetType] = useState('');
  const [assetTitle, setAssetTitle] = useState('');
  const [assetContent, setAssetContent] = useState('{}');
  const [savingAsset, setSavingAsset] = useState(false);
  const [syncingAssetId, setSyncingAssetId] = useState('');
  const [generationMode, setGenerationMode] = useState('');
  const [targetAssetId, setTargetAssetId] = useState('');
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [startingRun, setStartingRun] = useState(false);
  const [applyingRunId, setApplyingRunId] = useState('');

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const loadedProject = await scenarioApi.getProject(projectId);
      const [loadedScenario, assetResponse, runResponse] = await Promise.all([
        scenarioApi.getScenario(loadedProject.scenario_code),
        scenarioApi.listAssets(projectId),
        scenarioApi.listProjectRuns(projectId),
      ]);
      setProject(loadedProject);
      setScenario(loadedScenario);
      setAssets(assetResponse.assets);
      setRuns(runResponse.runs);
      setAssetType(loadedScenario.artifact_schema.asset_types?.[0] || '');
      setGenerationMode(loadedScenario.default_generation_modes[0]?.code || '');
      setTargetAssetId((current) =>
        current && assetResponse.assets.some((asset) => asset.id === current) ? current : '',
      );
      setFormValues((current) => {
        const next = { ...current };
        for (const field of loadedScenario.ui_schema.fields || []) {
          next[field.name] = next[field.name] || '';
        }
        return next;
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '项目工作台加载失败');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadProject();
  }, [loadProject]);

  useEffect(() => {
    // 支持 Issue #20 指定的资产/运行记录子入口深链到同一个工作台。
    const tab = parseTabParam(new URLSearchParams(window.location.search).get('tab'));
    if (tab) {
      setActiveTab(tab);
    }
  }, []);

  function handleTabSelect(tab: Tab) {
    setActiveTab(tab);
    const nextUrl = new URL(window.location.href);
    if (tab === 'overview') {
      nextUrl.searchParams.delete('tab');
    } else {
      nextUrl.searchParams.set('tab', tab);
    }
    window.history.replaceState(null, '', `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
  }

  const assetTypes = scenario?.artifact_schema.asset_types || [];
  const generationModes = scenario?.default_generation_modes || [];
  const selectedMode = generationModes.find((mode) => mode.code === generationMode);
  const fields: ScenarioFormField[] = scenario?.ui_schema.fields || [];
  const assetsByType = useMemo(() => {
    const map = new Map<string, ProjectAsset[]>();
    for (const asset of assets) {
      const group = map.get(asset.asset_type) || [];
      group.push(asset);
      map.set(asset.asset_type, group);
    }
    return map;
  }, [assets]);

  async function handleCreateAsset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assetType || !assetTitle.trim() || savingAsset) {
      return;
    }
    setSavingAsset(true);
    setError('');
    setNotice('');
    try {
      const created = await scenarioApi.createAsset(projectId, {
        asset_type: assetType,
        title: assetTitle.trim(),
        content: parseContent(assetContent),
      });
      setAssets((items) => [created, ...items]);
      setAssetTitle('');
      setAssetContent('{}');
      setNotice('项目资产已创建');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '创建项目资产失败');
    } finally {
      setSavingAsset(false);
    }
  }

  async function handleSyncAsset(assetId: string) {
    setSyncingAssetId(assetId);
    setError('');
    setNotice('');
    try {
      const updated = await scenarioApi.syncAssetToKnowledge(assetId);
      setAssets((items) => items.map((item) => (item.id === assetId ? updated : item)));
      setNotice('项目资产已同步到检索记忆');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '同步项目记忆失败');
    } finally {
      setSyncingAssetId('');
    }
  }

  async function handleStartRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (startingRun) {
      return;
    }
    const missingRequiredField = fields.find(
      (field) => field.required && !(formValues[field.name] || '').trim(),
    );
    if (missingRequiredField) {
      setError(`请填写${missingRequiredField.label}`);
      return;
    }
    const userInput = buildPrompt(selectedMode, formValues, project);
    if (!userInput.trim()) {
      setError('请先填写生成输入');
      return;
    }
    setStartingRun(true);
    setError('');
    setNotice('');
    try {
      const response = await scenarioApi.startProjectRun(projectId, {
        user_input: userInput,
        generation_mode: generationMode,
        target_asset_id: targetAssetId || null,
        edit_mode: 'project_workbench',
        retrieval_config: {
          enabled: true,
          use_workspace_kb: true,
          use_personal_kb: false,
          use_run_upload: false,
          top_k: 8,
          min_score: 0,
          mode: 'hybrid',
          enable_query_rewrite: true,
          enable_multi_query: true,
          enable_rerank: true,
          enable_context_compression: true,
          enable_conflict_detection: true,
        },
      });
      router.push(`/workflow/${response.workflow_run_id}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '启动项目运行失败');
    } finally {
      setStartingRun(false);
    }
  }

  async function handleApplyMemoryUpdates(run: WorkflowRunSummary, syncToKnowledge: boolean) {
    const candidates = getMemoryCandidates(run);
    if (candidates.length === 0 || applyingRunId) {
      return;
    }
    setApplyingRunId(run.id);
    setError('');
    setNotice('');
    try {
      const response = await scenarioApi.applyMemoryUpdates(projectId, {
        workflow_run_id: run.id,
        candidate_indexes: candidates
          .map((candidate, index) =>
            typeof candidate.candidate_index === 'number' ? candidate.candidate_index : index,
          ),
        sync_to_knowledge: syncToKnowledge,
      });
      setAssets((items) => [...response.assets, ...items]);
      setNotice(`已写回 ${response.assets.length} 条项目记忆`);
      await loadProject();
      handleTabSelect('assets');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '写回项目记忆失败');
    } finally {
      setApplyingRunId('');
    }
  }

  const runsWithMemoryCandidates = runs.filter((run) => getMemoryCandidates(run).length > 0);

  if (loading) {
    return <div className={styles.loading}>正在加载项目工作台...</div>;
  }

  if (!project || !scenario) {
    return <div className={styles.errorBanner}>{error || '项目不存在或无权访问'}</div>;
  }

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>{scenario.name}</span>
          <h1 className={styles.title}>{project.title}</h1>
          <p className={styles.subtitle}>
            {project.description || '这个项目会把场景资产、项目记忆和运行记录组织在同一个工作台中。'}
          </p>
          <div className={styles.actions}>
            <button
              className={styles.button}
              type="button"
              onClick={() => handleTabSelect('generate')}
            >
              <Play size={16} aria-hidden="true" />
              发起生成
            </button>
            <button className={styles.secondaryButton} type="button" onClick={() => void loadProject()}>
              <RefreshCw size={16} aria-hidden="true" />
              刷新
            </button>
          </div>
        </div>
        <div className={styles.heroMetric}>
          <span>项目资产</span>
          <strong>{assets.length}</strong>
          <p className={styles.cardText}>当前运行记录 {runs.length} 条，最近更新 {formatAppDateTime(project.updated_at)}。</p>
        </div>
      </section>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}
      {notice ? <div className={styles.noticeBanner}>{notice}</div> : null}

      <div className={styles.tabList} role="tablist" aria-label="项目工作台视图">
        {([
          ['overview', '概览'],
          ['assets', '资产'],
          ['generate', '生成'],
          ['memory', '记忆更新'],
          ['runs', '运行记录'],
        ] as Array<[Tab, string]>).map(([tab, label]) => (
          <button
            key={tab}
            className={`${styles.tabButton} ${activeTab === tab ? styles.tabButtonActive : ''}`}
            type="button"
            onClick={() => handleTabSelect(tab)}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' ? (
        <section className={styles.twoColumn}>
          <div className={styles.panel}>
            <h2 className={styles.panelTitle}>场景能力</h2>
            <div className={styles.summaryList}>
              <p className={styles.metaText}>{scenario.description}</p>
              <div className={styles.assetMeta}>
                {generationModes.map((mode) => (
                  <span key={mode.code} className={styles.badge}>
                    {mode.name}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className={styles.panel}>
            <h2 className={styles.panelTitle}>资产分布</h2>
            <div className={styles.summaryList}>
              {assetTypes.map((type) => (
                <div key={type} className={styles.assetMeta}>
                  <span className={styles.badge}>{assetTypeLabel(type)}</span>
                  <span className={styles.metaText}>{assetsByType.get(type)?.length || 0} 项</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === 'assets' ? (
        <section className={styles.twoColumn}>
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h2 className={styles.panelTitle}>项目资产</h2>
              <span className={styles.badge}>{assets.length} 项</span>
            </div>
            <div className={styles.assetList}>
              {assets.map((asset) => (
                <article key={asset.id} className={styles.assetRow}>
                  <div>
                    <h3 className={styles.assetTitle}>{asset.title}</h3>
                    <div className={styles.assetMeta}>
                      <span className={styles.badge}>{assetTypeLabel(asset.asset_type)}</span>
                      <span className={styles.badge}>v{asset.version}</span>
                      <span className={styles.badge}>{asset.embedding_status}</span>
                    </div>
                    <pre className={styles.contentPreview}>{stringifyContent(asset.content)}</pre>
                  </div>
                  <div className={styles.inlineActions}>
                    <button
                      className={styles.ghostButton}
                      type="button"
                      onClick={() => void handleSyncAsset(asset.id)}
                      disabled={syncingAssetId === asset.id}
                    >
                      <DatabaseZap size={16} aria-hidden="true" />
                      {syncingAssetId === asset.id ? '同步中' : '同步检索'}
                    </button>
                    <Link href={`/console/projects/${projectId}`} className={styles.ghostButton}>
                      <History size={16} aria-hidden="true" />
                      当前版本
                    </Link>
                  </div>
                </article>
              ))}
              {assets.length === 0 ? <p className={styles.metaText}>尚未创建项目资产。</p> : null}
            </div>
          </div>
          <form className={styles.assetEditor} onSubmit={handleCreateAsset}>
            <div className={styles.panelHeader}>
              <h2 className={styles.panelTitle}>新增资产</h2>
              <FilePlus2 size={20} aria-hidden="true" />
            </div>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>资产类型</span>
              <select className={styles.select} value={assetType} onChange={(event) => setAssetType(event.target.value)}>
                {assetTypes.map((type) => (
                  <option key={type} value={type}>
                    {assetTypeLabel(type)}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>标题</span>
              <input className={styles.input} value={assetTitle} onChange={(event) => setAssetTitle(event.target.value)} />
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>内容</span>
              <textarea
                className={styles.textarea}
                value={assetContent}
                onChange={(event) => setAssetContent(event.target.value)}
              />
            </label>
            <button className={styles.button} type="submit" disabled={savingAsset || !assetTitle.trim()}>
              <Save size={16} aria-hidden="true" />
              {savingAsset ? '保存中...' : '保存资产'}
            </button>
          </form>
        </section>
      ) : null}

      {activeTab === 'generate' ? (
        <form className={styles.formPanel} onSubmit={handleStartRun}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}>项目生成</h2>
              <p className={styles.metaText}>表单由场景模板驱动，运行会写入项目 metadata。</p>
            </div>
            <button className={styles.button} type="submit" disabled={startingRun}>
              <Play size={16} aria-hidden="true" />
              {startingRun ? '启动中...' : '启动工作流'}
            </button>
          </div>
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>生成模式</span>
              <select
                className={styles.select}
                value={generationMode}
                onChange={(event) => setGenerationMode(event.target.value)}
              >
                {generationModes.map((mode) => (
                  <option key={mode.code} value={mode.code}>
                    {mode.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>目标资产</span>
              <select
                className={styles.select}
                value={targetAssetId}
                onChange={(event) => setTargetAssetId(event.target.value)}
              >
                <option value="">不指定目标资产</option>
                {assets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {assetTypeLabel(asset.asset_type)} · {asset.title} · v{asset.version}
                  </option>
                ))}
              </select>
            </label>
            {fields.map((field) => (
              <label
                key={field.name}
                className={field.type === 'textarea' ? styles.fullField : styles.field}
              >
                <span className={styles.fieldLabel}>
                  {field.label}
                  {field.required ? ' *' : ''}
                </span>
                {field.type === 'textarea' ? (
                  <textarea
                    className={styles.textarea}
                    value={formValues[field.name] || ''}
                    onChange={(event) =>
                      setFormValues((current) => ({ ...current, [field.name]: event.target.value }))
                    }
                    placeholder={field.placeholder}
                  />
                ) : field.type === 'select' ? (
                  <select
                    className={styles.select}
                    value={formValues[field.name] || ''}
                    onChange={(event) =>
                      setFormValues((current) => ({ ...current, [field.name]: event.target.value }))
                    }
                  >
                    <option value="">请选择{field.label}</option>
                    {(field.options || []).map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className={styles.input}
                    type={field.type === 'number' ? 'number' : 'text'}
                    value={formValues[field.name] || ''}
                    onChange={(event) =>
                      setFormValues((current) => ({ ...current, [field.name]: event.target.value }))
                    }
                    placeholder={field.placeholder}
                  />
                )}
              </label>
            ))}
          </div>
        </form>
      ) : null}

      {activeTab === 'runs' ? (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>项目运行记录</h2>
            <span className={styles.badge}>{runs.length} 条</span>
          </div>
          <div className={styles.runList}>
            {runs.map((run) => (
              <article key={run.id} className={styles.runItem}>
                <div>
                  <h3 className={styles.assetTitle}>{run.workflow_name}</h3>
                  <p className={styles.runText}>{run.user_input}</p>
                  <div className={styles.runMeta}>
                    <span className={styles.badge}>{run.status}</span>
                    <span className={styles.badge}>{formatAppDateTime(run.started_at)}</span>
                  </div>
                </div>
                <Link href={`/workflow/${run.id}`} className={styles.linkButton}>
                  查看详情
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
              </article>
            ))}
            {runs.length === 0 ? <p className={styles.metaText}>这个项目还没有运行记录。</p> : null}
          </div>
        </section>
      ) : null}

      {activeTab === 'memory' ? (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}>待确认记忆更新</h2>
              <p className={styles.metaText}>工作流完成后抽取的新增事实，需要人工确认后才会写回项目资产。</p>
            </div>
            <span className={styles.badge}>{runsWithMemoryCandidates.length} 个运行</span>
          </div>
          <div className={styles.runList}>
            {runsWithMemoryCandidates.map((run) => {
              const candidates = getMemoryCandidates(run);
              return (
                <article key={run.id} className={styles.memoryPanel}>
                  <div className={styles.panelHeader}>
                    <div>
                      <h3 className={styles.assetTitle}>{run.workflow_name}</h3>
                      <p className={styles.metaText}>
                        {formatAppDateTime(run.started_at)} · {metadataText(run.metadata?.generation_mode, '默认生成')}
                      </p>
                    </div>
                    <Link href={`/workflow/${run.id}`} className={styles.ghostButton}>
                      查看详情
                    </Link>
                  </div>
                  <div className={styles.memoryCandidateGrid}>
                    {candidates.map((candidate, index) => (
                      <div key={`${run.id}-${index}`} className={styles.memoryCandidate}>
                        <span className={styles.badge}>
                          {assetTypeLabel(candidate.asset_type || 'memory_note')}
                        </span>
                        <h4 className={styles.assetTitle}>{candidate.title || `记忆更新 ${index + 1}`}</h4>
                        <pre className={styles.contentPreview}>{stringifyContent(candidate.content)}</pre>
                      </div>
                    ))}
                  </div>
                  <div className={styles.inlineActions}>
                    <button
                      className={styles.button}
                      type="button"
                      onClick={() => void handleApplyMemoryUpdates(run, false)}
                      disabled={applyingRunId === run.id}
                    >
                      <Sparkles size={16} aria-hidden="true" />
                      {applyingRunId === run.id ? '写回中' : '写回资产'}
                    </button>
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      onClick={() => void handleApplyMemoryUpdates(run, true)}
                      disabled={applyingRunId === run.id}
                    >
                      <DatabaseZap size={16} aria-hidden="true" />
                      写回并同步检索
                    </button>
                  </div>
                </article>
              );
            })}
            {runsWithMemoryCandidates.length === 0 ? (
              <p className={styles.metaText}>暂无待确认的项目记忆更新。完成一次项目运行后，候选会显示在这里。</p>
            ) : null}
          </div>
        </section>
      ) : null}

      <Link href="/console/projects" className={styles.ghostButton}>
        <Layers3 size={16} aria-hidden="true" />
        返回项目列表
      </Link>
    </div>
  );
}
