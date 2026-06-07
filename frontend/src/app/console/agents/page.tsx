'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Layers3,
  Maximize2,
  Pause,
  Play,
  Plus,
  Search,
  ShieldAlert,
  ShieldCheck,
  Square,
  Wrench,
  Zap,
} from 'lucide-react';
import { agentApi } from '@/lib/api';
import type {
  AgentPlanNode,
  AgentRun,
  AgentRunDetail,
  AgentStep,
  AgentToolCall,
  AgentToolDefinition,
} from '@/lib/api';
import styles from './agents.module.css';

const DEFAULT_GOAL =
  '请围绕当前项目，调研从 Workflow Agent 到 Autonomous Agent 的技术路线，输出一份可用于后续论文展望和答辩回答的材料。';

type TokenUsage = {
  input: number;
  output: number;
  total: number;
};

type TimelineEvent = {
  id: string;
  at: string | null;
  title: string;
  description: string;
  actor: string;
  status: string;
};

type TokenPoint = {
  label: string;
  input: number;
  output: number;
};

function statusLabel(status: string) {
  switch (status) {
    case 'planning':
      return '规划中';
    case 'running':
      return '运行中';
    case 'paused':
      return '已暂停';
    case 'awaiting_gate':
      return '等待 Gate';
    case 'completed':
      return '已完成';
    case 'failed':
      return '失败';
    case 'cancelled':
      return '已取消';
    case 'blocked':
      return '已阻塞';
    case 'skipped':
      return '已跳过';
    case 'pending':
      return '待执行';
    default:
      return status;
  }
}

function statusClass(status: string) {
  switch (status) {
    case 'completed':
      return styles.statusCompleted;
    case 'failed':
      return styles.statusFailed;
    case 'cancelled':
      return styles.statusCancelled;
    case 'running':
      return styles.statusRunning;
    case 'planning':
    case 'paused':
      return styles.statusPlanning;
    default:
      return styles.statusWaiting;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function numberFromUnknown(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function parseTime(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}

function formatClock(value: string | null | undefined) {
  const time = parseTime(value);
  if (!time) {
    return '-';
  }
  return new Date(time).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatDuration(start: string | null | undefined, end: string | null | undefined) {
  const started = parseTime(start);
  const finished = parseTime(end) || Date.now();
  if (!started || finished < started) {
    return '-';
  }
  const seconds = Math.max(0, Math.floor((finished - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return '';
}

function addUsage(left: TokenUsage, right: TokenUsage): TokenUsage {
  return {
    input: left.input + right.input,
    output: left.output + right.output,
    total: left.total + right.total,
  };
}

function extractUsage(value: unknown, depth = 0): TokenUsage {
  if (depth > 5) {
    return { input: 0, output: 0, total: 0 };
  }
  if (Array.isArray(value)) {
    return value.reduce<TokenUsage>(
      (sum, item) => addUsage(sum, extractUsage(item, depth + 1)),
      { input: 0, output: 0, total: 0 },
    );
  }
  if (!isRecord(value)) {
    return { input: 0, output: 0, total: 0 };
  }

  const input = numberFromUnknown(value.input_tokens) + numberFromUnknown(value.prompt_tokens);
  const output = numberFromUnknown(value.output_tokens) + numberFromUnknown(value.completion_tokens);
  const total = numberFromUnknown(value.total_tokens) || input + output;
  const direct = { input, output, total };

  return Object.entries(value).reduce<TokenUsage>((sum, [key, child]) => {
    if (
      key === 'input_tokens' ||
      key === 'prompt_tokens' ||
      key === 'output_tokens' ||
      key === 'completion_tokens' ||
      key === 'total_tokens'
    ) {
      return sum;
    }
    return addUsage(sum, extractUsage(child, depth + 1));
  }, direct);
}

function usageFromDetail(detail: AgentRunDetail | null) {
  if (!detail) {
    return { input: 0, output: 0, total: 0 };
  }
  const planUsage = detail.plans.reduce<TokenUsage>(
    (sum, plan) => addUsage(sum, extractUsage(plan.metadata)),
    { input: 0, output: 0, total: 0 },
  );
  const stepUsage = detail.steps.reduce<TokenUsage>(
    (sum, step) => addUsage(sum, addUsage(extractUsage(step.metadata), extractUsage(step.output))),
    { input: 0, output: 0, total: 0 },
  );
  const toolUsage = detail.tool_calls.reduce<TokenUsage>(
    (sum, call) => addUsage(sum, addUsage(extractUsage(call.metadata), extractUsage(call.output))),
    { input: 0, output: 0, total: 0 },
  );
  const usage = addUsage(addUsage(planUsage, stepUsage), toolUsage);
  return {
    input: usage.input,
    output: usage.output,
    total: usage.total || usage.input + usage.output,
  };
}

function buildTokenSeries(detail: AgentRunDetail | null): TokenPoint[] {
  if (!detail) {
    return [{ label: '-', input: 0, output: 0 }];
  }

  let input = 0;
  let output = 0;
  const items = [
    ...detail.steps.map((step) => ({
      at: step.ended_at || step.started_at || detail.run.created_at,
      usage: addUsage(extractUsage(step.metadata), extractUsage(step.output)),
    })),
    ...detail.tool_calls.map((call) => ({
      at: call.completed_at || call.created_at,
      usage: addUsage(extractUsage(call.metadata), extractUsage(call.output)),
    })),
  ].sort((left, right) => (parseTime(left.at) || 0) - (parseTime(right.at) || 0));

  if (items.length === 0) {
    return [{ label: formatClock(detail.run.created_at), input: 0, output: 0 }];
  }

  return items.map((item) => {
    input += item.usage.input;
    output += item.usage.output;
    return {
      label: formatClock(item.at),
      input,
      output,
    };
  });
}

function stepForNode(steps: AgentStep[], node: AgentPlanNode) {
  return [...steps].reverse().find((step) => step.node_id === node.id);
}

function activeNodeFromDetail(detail: AgentRunDetail | null) {
  const nodes = detail?.plans.at(-1)?.plan_graph.nodes || [];
  if (!detail || nodes.length === 0) {
    return undefined;
  }
  const currentStepId = detail.run.current_step_id;
  const currentStep = detail.steps.find((step) => step.id === currentStepId);
  const currentNodeId = currentStep?.node_id || firstString(detail.run.metadata?.current_node_id);
  return (
    nodes.find((node) => node.id === currentNodeId) ||
    nodes.find((node) => ['running', 'blocked'].includes(stepForNode(detail.steps, node)?.status || node.status)) ||
    nodes[0]
  );
}

function buildTimeline(detail: AgentRunDetail | null): TimelineEvent[] {
  if (!detail) {
    return [];
  }

  const events: TimelineEvent[] = [
    {
      id: `${detail.run.id}-created`,
      at: detail.run.created_at,
      title: '任务启动',
      description: `用户创建任务：${detail.run.goal}`,
      actor: '系统',
      status: 'completed',
    },
  ];

  detail.steps.forEach((step) => {
    events.push({
      id: step.id,
      at: step.started_at || step.ended_at,
      title: step.title || step.node_id,
      description: step.description || step.error_message || 'Agent 步骤执行记录',
      actor: step.step_type.includes('tool') ? '工具' : 'Agent',
      status: step.status,
    });
  });

  detail.tool_calls.forEach((call) => {
    events.push({
      id: call.id,
      at: call.created_at || call.completed_at,
      title: `调用 ${call.tool_name}`,
      description: call.error_message || `风险等级 ${call.risk_level}，耗时 ${call.latency_ms ?? 0}ms`,
      actor: '工具',
      status: call.status,
    });
  });

  if (detail.run.status === 'awaiting_gate' && detail.run.gate) {
    events.push({
      id: `${detail.run.id}-gate`,
      at: firstString(detail.run.gate.opened_at) || detail.run.updated_at,
      title: '等待人工 Gate',
      description: firstString(detail.run.gate.reason) || '当前操作需要人工确认',
      actor: '用户',
      status: 'awaiting_gate',
    });
  }

  return events.sort((left, right) => (parseTime(left.at) || 0) - (parseTime(right.at) || 0));
}

function countItems(value: unknown) {
  if (Array.isArray(value)) {
    return value.length;
  }
  if (isRecord(value) && Array.isArray(value.results)) {
    return value.results.length;
  }
  if (isRecord(value) && Array.isArray(value.items)) {
    return value.items.length;
  }
  return value ? 1 : 0;
}

function shortTitle(text: string, max = 18) {
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function isActiveStatus(status: string) {
  return ['planning', 'running', 'awaiting_gate', 'paused'].includes(status);
}

function isTerminalStatus(status: string) {
  return ['completed', 'failed', 'cancelled'].includes(status);
}

function TokenChart({ points }: { points: TokenPoint[] }) {
  const normalizedPoints = points.length > 0 ? points : [{ label: '-', input: 0, output: 0 }];
  const maxValue = Math.max(1, ...normalizedPoints.flatMap((point) => [point.input, point.output]));
  const width = 440;
  const height = 150;
  const padding = 18;

  function lineFor(key: 'input' | 'output') {
    const denominator = Math.max(1, normalizedPoints.length - 1);
    return normalizedPoints
      .map((point, index) => {
        const x = padding + (index / denominator) * (width - padding * 2);
        const y = height - padding - (point[key] / maxValue) * (height - padding * 2);
        return `${x},${y}`;
      })
      .join(' ');
  }

  return (
    <div className={styles.tokenChart}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Token 使用趋势">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
        <polyline className={styles.tokenLineInput} points={lineFor('input')} />
        <polyline className={styles.tokenLineOutput} points={lineFor('output')} />
      </svg>
      <div className={styles.chartTicks}>
        {normalizedPoints.slice(-6).map((point, index) => (
          <span key={`${point.label}-${index}`}>{point.label}</span>
        ))}
      </div>
    </div>
  );
}

function toolIconClass(tool: AgentToolDefinition) {
  if (tool.risk_level === 'high') {
    return styles.toolIconDanger;
  }
  if (tool.risk_level === 'medium') {
    return styles.toolIconWarning;
  }
  return styles.toolIconSuccess;
}

export default function AgentRunsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [tools, setTools] = useState<AgentToolDefinition[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<AgentRunDetail | null>(null);
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');

  async function refresh(preferredRunId?: string) {
    const [runResult, toolResult] = await Promise.all([
      agentApi.getRuns(),
      agentApi.getTools(),
    ]);
    const nextRuns = runResult.runs || [];
    setRuns(nextRuns);
    setTools(toolResult.tools || []);
    setSelectedRunId((current) => preferredRunId || current || nextRuns.find((run) => isActiveStatus(run.status))?.id || nextRuns[0]?.id || null);
  }

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      try {
        const [runResult, toolResult] = await Promise.all([
          agentApi.getRuns(),
          agentApi.getTools(),
        ]);
        if (active) {
          const nextRuns = runResult.runs || [];
          setRuns(nextRuns);
          setTools(toolResult.tools || []);
          setSelectedRunId((current) => current || nextRuns.find((run) => isActiveStatus(run.status))?.id || nextRuns[0]?.id || null);
        }
        if (active && (runResult.runs || []).some((run) => isActiveStatus(run.status))) {
          timer = setTimeout(load, 5000);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : '自主 Agent 数据加载失败');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      active = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedDetail(null);
      return;
    }

    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let hasLoadedOnce = false;

    async function loadDetail() {
      if (!hasLoadedOnce) {
        setDetailLoading(true);
      }
      try {
        const result = await agentApi.getDetail(selectedRunId as string);
        if (active) {
          setSelectedDetail(result);
          if (!isTerminalStatus(result.run.status)) {
            timer = setTimeout(loadDetail, 5000);
          }
        }
      } catch {
        if (active) {
          setSelectedDetail(null);
        }
      } finally {
        if (active) {
          setDetailLoading(false);
          hasLoadedOnce = true;
        }
      }
    }

    void loadDetail();

    return () => {
      active = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [selectedRunId]);

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goal.trim()) {
      setError('请输入明确的目标。');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const result = await agentApi.start(goal.trim(), { autoExecute: true, autonomyLevel: 'supervised' });
      setSelectedDetail(result);
      await refresh(result.run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动自主 Agent 失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePause() {
    if (!selectedRunId) {
      return;
    }
    setActing(true);
    setError('');
    try {
      const result = await agentApi.pause(selectedRunId, '用户从 Agent 控制台暂停');
      setSelectedDetail(result);
      await refresh(result.run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '暂停执行失败');
    } finally {
      setActing(false);
    }
  }

  async function handleResume() {
    if (!selectedRunId) {
      return;
    }
    setActing(true);
    setError('');
    try {
      const result = await agentApi.resume(selectedRunId);
      setSelectedDetail(result);
      await refresh(result.run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '继续执行失败');
    } finally {
      setActing(false);
    }
  }

  async function handleCancel() {
    if (!selectedRunId) {
      return;
    }
    setActing(true);
    setError('');
    try {
      const result = await agentApi.cancel(selectedRunId, '用户从 Agent 控制台终止');
      setSelectedDetail(result);
      await refresh(result.run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '终止运行失败');
    } finally {
      setActing(false);
    }
  }

  const selectedRun = runs.find((run) => run.id === selectedRunId) || selectedDetail?.run || runs[0];
  const activeDetail = selectedDetail && selectedDetail.run.id === selectedRun?.id ? selectedDetail : null;
  const activePlan = activeDetail?.plans.at(-1);
  const nodes = activePlan?.plan_graph.nodes || [];
  const activeNode = activeNodeFromDetail(activeDetail);
  const activeStep = activeNode && activeDetail ? stepForNode(activeDetail.steps, activeNode) : undefined;
  const activeToolCalls = useMemo(() => {
    if (!activeDetail || !activeNode) {
      return [] as AgentToolCall[];
    }
    return activeDetail.tool_calls.filter((call) => {
      if (activeStep?.id && call.step_id === activeStep.id) {
        return true;
      }
      return activeNode.tool_name && call.tool_name === activeNode.tool_name;
    });
  }, [activeDetail, activeNode, activeStep]);
  const memoryEvidence = activeDetail?.steps.find((step) => step.node_id === 'retrieve_memory')?.output;
  const timeline = useMemo(() => buildTimeline(activeDetail), [activeDetail]);
  const tokenSeries = useMemo(() => buildTokenSeries(activeDetail), [activeDetail]);
  const tokenUsage = useMemo(() => usageFromDetail(activeDetail), [activeDetail]);
  const metrics = useMemo(() => {
    const active = runs.filter((run) => isActiveStatus(run.status)).length;
    const gateRunIds = new Set(
      runs
        .filter((run) => run.status === 'awaiting_gate' || run.gate)
        .map((run) => run.id),
    );
    if (activeDetail?.run.gate) {
      gateRunIds.add(activeDetail.run.id);
    }
    return {
      active,
      gate: gateRunIds.size,
      duration: selectedRun ? formatDuration(selectedRun.created_at, selectedRun.completed_at) : '-',
      currentStage: activeNode?.title || statusLabel(selectedRun?.status || 'pending'),
    };
  }, [activeDetail, activeNode, runs, selectedRun]);

  return (
    <div className={`${styles.page} ${styles.agentConsolePage}`}>
      <section className={styles.agentConsoleShell}>
        <div className={styles.agentTopbar}>
          <div className={styles.agentTitleBlock}>
            <div className={styles.backLink}>
              <span>console</span>
              <span>/</span>
              <span>agents</span>
            </div>
            <div className={styles.agentTitleRow}>
              <span className={styles.agentTitleIcon}>
                <Bot size={18} strokeWidth={1.9} />
              </span>
              <div>
                <h1 className={styles.agentConsoleTitle}>自主 Agent 控制台</h1>
                <p className={styles.agentConsoleSubtitle}>面向长文本、多步骤、多约束任务的运行控制中心</p>
              </div>
            </div>
          </div>

          <form className={styles.consoleSearch} role="search" onSubmit={(event) => event.preventDefault()}>
            <Search size={17} strokeWidth={1.9} />
            <input placeholder="搜索 Agents、任务、节点、Artifact..." aria-label="搜索 Agents、任务、节点、Artifact" />
            <kbd>⌘K</kbd>
          </form>

          <div className={styles.agentToolbar}>
            <button className={styles.primaryAction} type="submit" form="agent-start-form" disabled={submitting}>
              <Plus size={17} strokeWidth={2} />
              {submitting ? '启动中' : '新建任务'}
            </button>
            {selectedRun?.status === 'running' && (
              <button className={styles.secondaryAction} onClick={handlePause} disabled={acting} type="button">
                <Pause size={16} strokeWidth={1.9} />
                暂停
              </button>
            )}
            {selectedRun && ['planning', 'paused'].includes(selectedRun.status) && (
              <button className={styles.secondaryAction} onClick={handleResume} disabled={acting} type="button">
                <Play size={16} strokeWidth={1.9} />
                继续
              </button>
            )}
            {selectedRun && !isTerminalStatus(selectedRun.status) && (
              <button className={styles.dangerAction} onClick={handleCancel} disabled={acting} type="button">
                <Square size={13} strokeWidth={2.4} />
                终止
              </button>
            )}
          </div>
        </div>

        <form id="agent-start-form" className={styles.consoleGoalComposer} onSubmit={handleStart} aria-label="启动自主 Agent">
          <textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="输入需要自主规划和长程执行的目标"
          />
        </form>

        {error && (
          <div className={styles.errorState}>
            <ShieldAlert size={20} strokeWidth={1.9} />
            <p>{error}</p>
          </div>
        )}

        <section className={styles.agentMetricStrip}>
          <article className={styles.agentMetricCard}>
            <div>
              <span className={styles.metricLabel}>运行状态</span>
              <strong className={styles.agentMetricValue}>
                {statusLabel(selectedRun?.status || 'pending')}
                {selectedRun && isActiveStatus(selectedRun.status) && <span className={styles.liveDot} />}
              </strong>
            </div>
            <span className={`${styles.agentMetricIcon} ${styles.metricIconSuccess}`}>
              <Activity size={19} strokeWidth={1.9} />
            </span>
          </article>
          <article className={styles.agentMetricCard}>
            <div>
              <span className={styles.metricLabel}>当前阶段</span>
              <strong className={styles.agentMetricValue}>{metrics.currentStage}</strong>
            </div>
            <span className={`${styles.agentMetricIcon} ${styles.metricIconBlue}`}>
              <Layers3 size={19} strokeWidth={1.9} />
            </span>
          </article>
          <article className={styles.agentMetricCard}>
            <div>
              <span className={styles.metricLabel}>运行时长</span>
              <strong className={styles.agentMetricValue}>{metrics.duration}</strong>
            </div>
            <span className={`${styles.agentMetricIcon} ${styles.metricIconBlue}`}>
              <Clock3 size={19} strokeWidth={1.9} />
            </span>
          </article>
          <article className={styles.agentMetricCard}>
            <div>
              <span className={styles.metricLabel}>Token</span>
              <strong className={styles.agentMetricValue}>{formatNumber(tokenUsage.total)}</strong>
            </div>
            <span className={`${styles.agentMetricIcon} ${styles.metricIconPurple}`}>
              <Database size={19} strokeWidth={1.9} />
            </span>
          </article>
          <article className={styles.agentMetricCard}>
            <div>
              <span className={styles.metricLabel}>待审批 Gate</span>
              <strong className={styles.agentMetricValue}>{metrics.gate}</strong>
            </div>
            <span className={`${styles.agentMetricIcon} ${styles.metricIconWarning}`}>
              <ShieldCheck size={19} strokeWidth={1.9} />
            </span>
          </article>
        </section>

        <section className={styles.agentCommandGrid}>
          <aside className={styles.agentLeftRail}>
            <section className={styles.agentPanel}>
              <div className={styles.compactPanelHeader}>
                <h2>Agent 列表</h2>
                <button className={styles.iconOnlyButton} type="submit" form="agent-start-form" aria-label="新增 Agent">
                  <Plus size={16} strokeWidth={1.9} />
                </button>
              </div>
              {loading ? (
                <div className={styles.emptyState}>正在加载自主 Agent...</div>
              ) : runs.length > 0 ? (
                <div className={styles.agentRunNav} data-testid="agent-run-list">
                  {runs.map((run) => (
                    <button
                      key={run.id}
                      className={`${styles.agentRunNavItem} ${run.id === selectedRun?.id ? styles.agentRunNavItemActive : ''}`}
                      onClick={() => setSelectedRunId(run.id)}
                      type="button"
                      aria-label={`${run.goal} ${statusLabel(run.status)}`}
                      data-testid="agent-run-card"
                    >
                      <FileText size={17} strokeWidth={1.8} />
                      <span>{shortTitle(run.goal, 18)}</span>
                      <em className={statusClass(run.status)}>{statusLabel(run.status)}</em>
                    </button>
                  ))}
                </div>
              ) : (
                <div className={styles.emptyState}>暂无自主 Agent 运行。</div>
              )}
            </section>

            <section className={styles.agentPanel}>
              <div className={styles.compactPanelHeader}>
                <h2>工具注册中心</h2>
                <span className={styles.panelInlineLink}>{tools.length} 个工具</span>
              </div>
              <div className={styles.toolRegistryList}>
                {tools.slice(0, 5).map((tool) => (
                  <article key={tool.name} className={styles.toolRegistryItem}>
                    <span className={`${styles.toolRegistryIcon} ${toolIconClass(tool)}`}>
                      <Wrench size={16} strokeWidth={1.9} />
                    </span>
                    <div>
                      <strong>{tool.name}</strong>
                      <span>{tool.idempotent ? '幂等工具' : '写入工具'} · {tool.permission}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </aside>

          <main className={styles.workflowPanel}>
            <div className={styles.panelChromeHeader}>
              <div>
                <h2>执行图 / Workflow Graph</h2>
                <p>节点依赖、工具调用和人工 Gate 在同一张图里对齐。</p>
              </div>
              <div className={styles.graphTools}>
                <button className={styles.iconOnlyButton} type="button" aria-label="适配视图">
                  <Maximize2 size={16} strokeWidth={1.9} />
                </button>
                <span>100%</span>
              </div>
            </div>

            <div className={styles.workflowCanvas}>
              {detailLoading ? (
                <div className={styles.emptyState}>正在加载执行图...</div>
              ) : (
                <div className={styles.workflowSpine}>
                  {nodes.length > 0 ? (
                    nodes.map((node, index) => {
                      const step = activeDetail ? stepForNode(activeDetail.steps, node) : undefined;
                      const currentStatus = step?.status || node.status;
                      const isActive = activeNode?.id === node.id;

                      return (
                        <div key={node.id} className={styles.graphRow}>
                          <Link
                            className={`${styles.graphNode} ${isActive ? styles.graphNodeSelected : ''} ${statusClass(currentStatus)}`}
                            href={selectedRun ? `/console/agents/${selectedRun.id}` : '/console/agents'}
                          >
                            <span className={styles.graphNodeIcon}>
                              {currentStatus === 'completed' ? (
                                <CheckCircle2 size={17} strokeWidth={2} />
                              ) : node.tool_name ? (
                                <Wrench size={17} strokeWidth={2} />
                              ) : (
                                <Zap size={17} strokeWidth={2} />
                              )}
                            </span>
                            <span>{node.title || node.id}</span>
                          </Link>
                          {index < nodes.length - 1 && <span className={styles.graphConnector} />}
                          {node.tool_name && (
                            <span className={styles.graphSideCallout}>
                              <Wrench size={16} strokeWidth={1.9} />
                              {node.tool_name}
                            </span>
                          )}
                          {node.risk_level !== 'low' && (
                            <span className={styles.graphGateCallout}>
                              <ShieldCheck size={16} strokeWidth={1.9} />
                              人工 Gate
                            </span>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <div className={styles.emptyState}>等待 Planner 生成执行图。</div>
                  )}
                </div>
              )}
              <div className={styles.miniMap} aria-hidden="true">
                {nodes.slice(0, 8).map((node) => (
                  <span key={`${node.id}-mini`} className={node.id === activeNode?.id ? styles.miniMapActive : ''} />
                ))}
              </div>
            </div>
          </main>

          <aside className={styles.nodeInspector}>
            <div className={styles.panelChromeHeader}>
              <div>
                <h2>节点详情</h2>
                <p>{activeNode?.title || '暂无选中节点'}</p>
              </div>
              <Link href={selectedRun ? `/console/agents/${selectedRun.id}` : '/console/agents'} className={styles.iconOnlyButton} aria-label="打开运行详情">
                <ArrowUpRight size={16} strokeWidth={1.9} />
              </Link>
            </div>

            <section className={styles.inspectorCard}>
              <div className={styles.nodeTitleLine}>
                <Activity size={20} strokeWidth={1.9} />
                <h3>{activeNode?.title || '未选择节点'}</h3>
                <span className={`${styles.statusBadge} ${statusClass(activeStep?.status || activeNode?.status || selectedRun?.status || 'pending')}`}>
                  {statusLabel(activeStep?.status || activeNode?.status || selectedRun?.status || 'pending')}
                </span>
              </div>
              <div className={styles.inspectorTabs}>
                <span>输入</span>
                <span>输出</span>
                <span>工具调用</span>
                <span>Trace</span>
                <span>Artifact</span>
              </div>
              <p className={styles.inspectorText}>{activeNode?.description || activeStep?.description || '等待节点详情。'}</p>
              <div className={styles.nodeMetaGrid}>
                <span>Node ID</span>
                <strong>{activeNode?.id || '-'}</strong>
                <span>模型</span>
                <strong>{firstString(activeDetail?.run.metadata.model_name) || '默认模型'}</strong>
                <span>耗时</span>
                <strong>{formatDuration(activeStep?.started_at, activeStep?.ended_at)}</strong>
                <span>工具</span>
                <strong>{activeNode?.tool_name || '-'}</strong>
              </div>
              <pre className={styles.jsonPreview}>{JSON.stringify(activeStep?.input || activeNode || {}, null, 2)}</pre>
            </section>

            <section className={styles.inspectorCard}>
              <h3>Artifacts</h3>
              <div className={styles.artifactList}>
                {(activeStep?.artifact_ids || []).length > 0 ? (
                  (activeStep?.artifact_ids || []).map((artifactId) => (
                    <span key={artifactId}>
                      <FileText size={16} strokeWidth={1.9} />
                      Artifact {artifactId.slice(0, 10)}
                    </span>
                  ))
                ) : (
                  <p className={styles.mutedText}>该节点暂无产物。</p>
                )}
              </div>
            </section>
          </aside>
        </section>

        <section className={styles.agentBottomGrid}>
          <section className={styles.timelinePanel}>
            <div className={styles.panelChromeHeader}>
              <div>
                <h2>实时事件 / Timeline</h2>
                <p>按发生时间展示任务、节点、工具和 Gate 事件。</p>
              </div>
            </div>
            <div className={styles.timelineTable}>
              {timeline.length > 0 ? (
                timeline.slice(-8).map((event) => (
                  <div key={event.id} className={styles.timelineTableRow}>
                    <time>{formatClock(event.at)}</time>
                    <span className={`${styles.eventDot} ${statusClass(event.status)}`} />
                    <strong>{event.title}</strong>
                    <p>{event.description}</p>
                    <em>{event.actor}</em>
                  </div>
                ))
              ) : (
                <div className={styles.emptyState}>暂无实时事件。</div>
              )}
            </div>
          </section>

          <section className={styles.tokenPanel}>
            <div className={styles.tokenTabs}>
              <span className={styles.tokenTabActive}>Token 使用</span>
              <span>成本估算</span>
            </div>
            <div className={styles.tokenSummary}>
              <strong>总计 {formatNumber(tokenUsage.total)}</strong>
              <span>
                <i className={styles.tokenLegendInput} />
                输入 {formatNumber(tokenUsage.input)}
              </span>
              <span>
                <i className={styles.tokenLegendOutput} />
                输出 {formatNumber(tokenUsage.output)}
              </span>
            </div>
            <TokenChart points={tokenSeries} />
          </section>
        </section>

        <section className={styles.agentAuxGrid}>
          <section className={styles.agentPanel}>
            <h2>证据复用</h2>
            {memoryEvidence ? (
              <div className={styles.evidenceGrid}>
                <article className={styles.evidenceItem}>
                  <span className={styles.metricLabel}>知识库</span>
                  <strong className={styles.metaValue}>{countItems(memoryEvidence.knowledge_evidence)}</strong>
                </article>
                <article className={styles.evidenceItem}>
                  <span className={styles.metricLabel}>Artifact</span>
                  <strong className={styles.metaValue}>{countItems(memoryEvidence.artifact_evidence)}</strong>
                </article>
                <article className={styles.evidenceItem}>
                  <span className={styles.metricLabel}>Trace</span>
                  <strong className={styles.metaValue}>{countItems(memoryEvidence.trace_evidence)}</strong>
                </article>
                <article className={styles.evidenceItem}>
                  <span className={styles.metricLabel}>ToolCall</span>
                  <strong className={styles.metaValue}>{countItems(memoryEvidence.tool_evidence)}</strong>
                </article>
              </div>
            ) : (
              <p className={styles.mutedText}>等待记忆与证据检索步骤完成。</p>
            )}
          </section>

          <section className={styles.agentPanel}>
            <h2>工具调用</h2>
            <div className={styles.sectionStack}>
              {(activeToolCalls.length > 0 ? activeToolCalls : activeDetail?.tool_calls.slice(0, 4) || []).map((call) => (
                <article key={call.id} className={styles.toolItem}>
                  <div className={styles.timelineHeader}>
                    <h3 className={styles.timelineTitle}>{call.tool_name}</h3>
                    <span className={`${styles.statusBadge} ${statusClass(call.status)}`}>{statusLabel(call.status)}</span>
                  </div>
                  <div className={styles.chipRow}>
                    <span className={styles.chip}>
                      <Wrench size={14} strokeWidth={1.9} />
                      {call.risk_level}
                    </span>
                    <span className={styles.chip}>{call.latency_ms ?? 0}ms</span>
                  </div>
                </article>
              ))}
              {(!activeDetail || activeDetail.tool_calls.length === 0) && <p className={styles.mutedText}>暂无工具调用。</p>}
            </div>
          </section>

          <section className={styles.agentPanel}>
            <h2>运行入口</h2>
            <div className={styles.sectionStack}>
              {selectedRun ? (
                <Link href={`/console/agents/${selectedRun.id}`} className={styles.secondaryAction}>
                  查看完整运行详情
                  <ArrowUpRight size={16} strokeWidth={1.9} />
                </Link>
              ) : (
                <p className={styles.mutedText}>创建任务后可进入详情页查看目标卡、动态计划和评估记录。</p>
              )}
            </div>
          </section>
        </section>
      </section>
    </div>
  );
}
