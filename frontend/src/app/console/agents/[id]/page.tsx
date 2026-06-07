'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  Activity,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Download,
  FileText,
  Layers3,
  Pause,
  Play,
  Plus,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  SkipForward,
  Square,
  Wrench,
  XCircle,
} from 'lucide-react';
import { agentApi } from '@/lib/api';
import type {
  AgentPlanNode,
  AgentRunDetail,
  AgentStep,
  AgentToolCall,
} from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';
import styles from '../agents.module.css';

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

function safeJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
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

function stepForNode(steps: AgentStep[], node: AgentPlanNode) {
  return [...steps].reverse().find((step) => step.node_id === node.id);
}

function isTerminalStatus(status: string) {
  return ['completed', 'failed', 'cancelled'].includes(status);
}

function costAmount(cost: Record<string, unknown>) {
  return numberFromUnknown(cost?.amount);
}

function shortId(value?: string | null) {
  return value ? value.slice(0, 12) : '-';
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
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

function resolveActiveNodeId(detail: AgentRunDetail) {
  const nodes = detail.plans.at(-1)?.plan_graph.nodes || [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const currentStepId = detail.run.current_step_id;
  if (currentStepId && nodeIds.has(currentStepId)) {
    return currentStepId;
  }

  const stepNodeId = detail.steps.find((step) => step.id === currentStepId)?.node_id;
  if (stepNodeId && nodeIds.has(stepNodeId)) {
    return stepNodeId;
  }

  const metadataNodeId = firstString(detail.run.metadata?.current_node_id);
  if (metadataNodeId && nodeIds.has(metadataNodeId)) {
    return metadataNodeId;
  }

  return (
    nodes.find((node) => ['running', 'blocked'].includes(stepForNode(detail.steps, node)?.status || node.status))?.id ||
    nodes[0]?.id ||
    null
  );
}

function buildTimeline(detail: AgentRunDetail): TimelineEvent[] {
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

  detail.replan_records.forEach((record) => {
    events.push({
      id: record.id,
      at: record.created_at,
      title: '触发重规划',
      description: record.trigger_reason,
      actor: 'Agent',
      status: 'planning',
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

function buildTokenSeries(detail: AgentRunDetail): TokenPoint[] {
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

function usageFromDetail(detail: AgentRunDetail) {
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

export default function AgentRunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [planDraft, setPlanDraft] = useState('');
  const [planDraftDirty, setPlanDraftDirty] = useState(false);
  const [clarificationDraft, setClarificationDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const planDraftDirtyRef = useRef(false);
  const planDraftPlanIdRef = useRef<string | null>(null);

  const markPlanDraftDirty = useCallback((value: boolean) => {
    planDraftDirtyRef.current = value;
    setPlanDraftDirty(value);
  }, []);

  const syncDetail = useCallback((result: AgentRunDetail, options?: { preservePlanDraft?: boolean }) => {
    setDetail(result);
    setSelectedNodeId((current) => {
      const nodeIds = new Set((result.plans.at(-1)?.plan_graph.nodes || []).map((node) => node.id));
      return current && nodeIds.has(current) ? current : resolveActiveNodeId(result);
    });

    const latestPlan = result.plans.at(-1);
    const latestPlanId = latestPlan?.id ?? null;
    const planChanged = planDraftPlanIdRef.current !== latestPlanId;
    if (!options?.preservePlanDraft || !planDraftDirtyRef.current || planChanged) {
      planDraftPlanIdRef.current = latestPlanId;
      setPlanDraft(JSON.stringify(latestPlan?.plan_graph ?? {}, null, 2));
      markPlanDraftDirty(false);
    }
  }, [markPlanDraftDirty]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function fetchDetail() {
      try {
        const result = await agentApi.getDetail(runId);
        if (active) {
          syncDetail(result, { preservePlanDraft: true });
          if (!isTerminalStatus(result.run.status)) {
            timer = setTimeout(fetchDetail, 3500);
          }
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : '自主 Agent 详情加载失败');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    setSelectedNodeId(null);
    void fetchDetail();

    return () => {
      active = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [runId, syncDetail]);

  async function handleResume() {
    setActing(true);
    setError('');
    try {
      const result = await agentApi.resume(runId);
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '继续执行失败');
    } finally {
      setActing(false);
    }
  }

  async function handlePause() {
    setActing(true);
    setError('');
    try {
      const result = await agentApi.pause(runId, '用户从运行详情页暂停');
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '暂停执行失败');
    } finally {
      setActing(false);
    }
  }

  async function handleCancel() {
    setActing(true);
    setError('');
    try {
      const result = await agentApi.cancel(runId, '用户从运行详情页取消');
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '取消运行失败');
    } finally {
      setActing(false);
    }
  }

  async function handleGate(approved: boolean) {
    setActing(true);
    setError('');
    try {
      const result = await agentApi.decideGate(runId, approved, approved ? '确认继续执行' : '拒绝高风险操作');
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gate 审批失败');
    } finally {
      setActing(false);
    }
  }

  async function handleClarifyGoal() {
    if (!clarificationDraft.trim()) {
      setError('请先填写补充目标说明');
      return;
    }
    setActing(true);
    setError('');
    try {
      const result = await agentApi.clarify(runId, clarificationDraft.trim());
      setClarificationDraft('');
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '目标澄清提交失败');
    } finally {
      setActing(false);
    }
  }

  async function handlePlanUpdate() {
    setActing(true);
    setError('');
    try {
      const parsedPlan = JSON.parse(planDraft);
      const result = await agentApi.updatePlan(runId, parsedPlan, '前端人工调整计划');
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '计划 JSON 无法保存');
    } finally {
      setActing(false);
    }
  }

  async function handleSkipNode(nodeId: string) {
    setActing(true);
    setError('');
    try {
      const result = await agentApi.skipNode(runId, nodeId, '用户从运行详情页跳过节点');
      syncDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '跳过节点失败');
    } finally {
      setActing(false);
    }
  }

  const activePlan = detail?.plans.at(-1);
  const nodes = activePlan?.plan_graph.nodes || [];
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || nodes[0];
  const selectedStep = selectedNode ? stepForNode(detail?.steps || [], selectedNode) : undefined;
  const selectedToolCalls = useMemo(() => {
    if (!detail || !selectedNode) {
      return [] as AgentToolCall[];
    }
    return detail.tool_calls.filter((call) => {
      if (selectedStep?.id && call.step_id === selectedStep.id) {
        return true;
      }
      return selectedNode.tool_name && call.tool_name === selectedNode.tool_name;
    });
  }, [detail, selectedNode, selectedStep]);
  const finalEval = detail?.eval_results.find((item) => item.target_type === 'final_output');
  const memoryEvidence = detail?.steps.find((step) => step.node_id === 'retrieve_memory')?.output;
  const timeline = useMemo(() => (detail ? buildTimeline(detail) : []), [detail]);
  const tokenSeries = useMemo(() => (detail ? buildTokenSeries(detail) : []), [detail]);
  const tokenUsage = useMemo(() => (detail ? usageFromDetail(detail) : { input: 0, output: 0, total: 0 }), [detail]);
  const metrics = useMemo(() => {
    if (!detail) {
      return {
        stepCount: 0,
        toolCount: 0,
        replanCount: 0,
        totalCost: 0,
        gateCount: 0,
        completedSteps: 0,
      };
    }
    return {
      stepCount: detail.steps.length,
      toolCount: detail.tool_calls.length,
      replanCount: detail.replan_records.length,
      totalCost: detail.tool_calls.reduce((sum, call) => sum + costAmount(call.cost), 0),
      gateCount: detail.run.gate ? 1 : 0,
      completedSteps: detail.steps.filter((step) => step.status === 'completed').length,
    };
  }, [detail]);

  if (loading) {
    return <div className={styles.emptyState}>正在加载自主 Agent 详情...</div>;
  }

  if (!detail) {
    return (
      <div className={styles.errorState}>
        <ShieldAlert size={20} strokeWidth={1.9} />
        <p>{error || '未找到 Autonomous Agent 运行。'}</p>
      </div>
    );
  }

  const selectedStatus = selectedStep?.status || selectedNode?.status || detail.run.status;
  const canSkipSelectedNode =
    Boolean(selectedNode) &&
    detail.run.status === 'planning' &&
    !selectedStep &&
    !['completed', 'running', 'blocked', 'skipped'].includes(selectedStatus);
  const selectedArtifacts = Array.from(new Set([
    ...(selectedStep?.artifact_ids || []),
    ...(detail.run.final_artifact_id ? [detail.run.final_artifact_id] : []),
  ]));
  const successCriteria = activePlan?.goal_card.success_criteria || [];
  const deliverables = activePlan?.goal_card.deliverables || [];
  const planNodes = nodes.map((node) => {
    const step = stepForNode(detail.steps, node);
    return {
      node,
      step,
      status: step?.status || node.status,
    };
  });
  const executionSteps = detail.steps.length > 0 ? detail.steps : planNodes.map(({ node, status }) => ({
    id: node.id,
    run_id: detail.run.id,
    plan_id: activePlan?.id || '',
    node_id: node.id,
    parent_step_id: null,
    step_type: node.step_type,
    title: node.title,
    description: node.description,
    status,
    input: {},
    output: {},
    artifact_ids: [],
    started_at: null,
    ended_at: null,
    error_message: null,
    metadata: {},
  }));

  return (
    <div className={`${styles.page} ${styles.agentConsolePage} ${styles.agentRunDetailPage}`}>
      <section className={styles.runDetailHero}>
        <div className={styles.runSummaryPanel}>
          <Link href="/console/agents" className={styles.backLink}>
            <ArrowLeft size={16} strokeWidth={1.9} />
            返回 Agent 运行台
          </Link>
          <span className={styles.eyebrow}>Agent Run</span>
          <h1 className={styles.runDetailTitle}>{detail.run.goal}</h1>
          <p className={styles.runDetailMeta}>
            创建于 {formatAppDateTime(detail.run.created_at)}，当前计划版本 {activePlan?.version || '-'}。
          </p>
          <div className={styles.headerActions}>
            <span
              className={`${styles.statusBadge} ${statusClass(detail.run.status)}`}
              data-testid="agent-run-status"
            >
              {statusLabel(detail.run.status)}
            </span>
            {detail.run.status === 'running' && (
              <button className={styles.secondaryAction} onClick={handlePause} disabled={acting} type="button">
                <Pause size={16} strokeWidth={1.9} />
                暂停
              </button>
            )}
            {['planning', 'paused'].includes(detail.run.status) && (
              <button className={styles.secondaryAction} onClick={handleResume} disabled={acting} type="button">
                <Play size={16} strokeWidth={1.9} />
                继续
              </button>
            )}
            {!isTerminalStatus(detail.run.status) && (
              <button className={styles.dangerAction} onClick={handleCancel} disabled={acting} type="button">
                <Square size={13} strokeWidth={2.4} />
                取消运行
              </button>
            )}
            <Link href="/console/agents" className={styles.secondaryAction}>
              <Plus size={16} strokeWidth={1.9} />
              新建任务
            </Link>
          </div>
        </div>

        <aside className={styles.goalCardPanel}>
          <div className={styles.panelChromeHeader}>
            <div>
              <h2>目标卡</h2>
              <p>目标标签、成功标准和交付边界。</p>
            </div>
            <button className={styles.iconOnlyButton} type="button" aria-label="编辑目标卡">
              <FileText size={16} strokeWidth={1.9} />
            </button>
          </div>
          <div className={styles.detailTagSection}>
            <span className={styles.metricLabel}>目标标签</span>
            <div className={styles.chipRow}>
              <span className={styles.chip}>{activePlan?.goal_card.task_type || '未识别类型'}</span>
              {deliverables.map((item) => (
                <span key={item} className={styles.chip}>{item}</span>
              ))}
            </div>
          </div>
          <div>
            <span className={styles.metricLabel}>成功标准</span>
            <p className={styles.mutedText}>{successCriteria.join(' / ') || '等待计划生成'}</p>
          </div>
        </aside>
      </section>

      {error && (
        <div className={styles.errorState}>
          <ShieldAlert size={20} strokeWidth={1.9} />
          <p>{error}</p>
        </div>
      )}

      <section className={`${styles.agentMetricStrip} ${styles.runSummaryMetricStrip}`}>
        <article className={styles.agentMetricCard}>
          <div>
            <span className={styles.metricLabel}>步骤数</span>
            <strong className={styles.agentMetricValue}>{metrics.stepCount}</strong>
          </div>
          <span className={`${styles.agentMetricIcon} ${styles.metricIconBlue}`}>
            <Layers3 size={19} strokeWidth={1.9} />
          </span>
        </article>
        <article className={styles.agentMetricCard}>
          <div>
            <span className={styles.metricLabel}>工具调用</span>
            <strong className={styles.agentMetricValue}>{metrics.toolCount}</strong>
          </div>
          <span className={`${styles.agentMetricIcon} ${styles.metricIconPurple}`}>
            <Wrench size={19} strokeWidth={1.9} />
          </span>
        </article>
        <article className={styles.agentMetricCard}>
          <div>
            <span className={styles.metricLabel}>评估记录</span>
            <strong className={styles.agentMetricValue}>{detail.eval_results.length}</strong>
          </div>
          <span className={`${styles.agentMetricIcon} ${styles.metricIconBlue}`}>
            <FileText size={19} strokeWidth={1.9} />
          </span>
        </article>
        <article className={styles.agentMetricCard}>
          <div>
            <span className={styles.metricLabel}>重规划</span>
            <strong className={styles.agentMetricValue}>{metrics.replanCount}</strong>
          </div>
          <span className={`${styles.agentMetricIcon} ${styles.metricIconWarning}`}>
            <RotateCcw size={19} strokeWidth={1.9} />
          </span>
        </article>
      </section>

      <section className={styles.runDetailMainGrid}>
        <main className={styles.runDetailPrimary}>
          {detail.run.status === 'planning' && (
            <section className={styles.workflowPanel}>
              <div className={styles.panelChromeHeader}>
                <div>
                  <h2>计划编辑</h2>
                  <p>当前运行仍在规划阶段，可直接调整 Plan Graph JSON。</p>
                </div>
              </div>
              <div className={styles.planEditor}>
                <textarea
                  className={styles.goalInput}
                  value={planDraft}
                  onChange={(event) => {
                    setPlanDraft(event.target.value);
                    markPlanDraftDirty(true);
                  }}
                  aria-label="编辑 Plan Graph JSON"
                />
                <button
                  className={styles.secondaryAction}
                  onClick={handlePlanUpdate}
                  disabled={acting || !planDraftDirty}
                  type="button"
                >
                  保存计划修改
                </button>
              </div>
            </section>
          )}

          <section className={styles.runDetailWorkGrid}>
            <section className={styles.workflowPanel}>
              <div className={styles.panelChromeHeader}>
                <div>
                  <h2>动态计划图</h2>
                  <p>节点依赖、工具、风险等级和实时执行状态在这里对齐。</p>
                </div>
              </div>
              <div className={styles.planTimeline}>
                {planNodes.length > 0 ? (
                  planNodes.map(({ node, status }, index) => (
                    <button
                      key={node.id}
                      className={`${styles.planTimelineItem} ${selectedNode?.id === node.id ? styles.planTimelineItemActive : ''}`}
                      onClick={() => setSelectedNodeId(node.id)}
                      type="button"
                    >
                      <span className={styles.planTimelineIndex}>{index + 1}</span>
                      <strong>{node.title || node.id}</strong>
                      <span className={`${styles.statusBadge} ${statusClass(status)}`}>{statusLabel(status)}</span>
                      <span className={styles.chip}>{node.step_type}</span>
                      {node.tool_name && <span className={styles.chip}>{node.tool_name}</span>}
                      <span className={styles.chip}>风险 {node.risk_level}</span>
                      <em>{node.depends_on.length > 0 ? `依赖 ${node.depends_on.join(', ')}` : '-'}</em>
                    </button>
                  ))
                ) : (
                  <div className={styles.emptyState}>等待 Planner 生成动态计划。</div>
                )}
              </div>
            </section>

            <section className={styles.workflowPanel}>
              <div className={styles.panelChromeHeader}>
                <div>
                  <h2>执行步骤</h2>
                  <p>每个步骤都保留输入、输出、错误和产物引用。</p>
                </div>
              </div>
              <div className={styles.executionStepList}>
                {executionSteps.map((step) => {
                  const node = nodes.find((item) => item.id === step.node_id);
                  const isSelected = selectedNode?.id === step.node_id;

                  return (
                    <article key={step.id} className={`${styles.executionStepCard} ${isSelected ? styles.executionStepCardActive : ''}`}>
                      <button className={styles.executionStepHeader} onClick={() => setSelectedNodeId(step.node_id)} type="button">
                        <span className={`${styles.eventDot} ${statusClass(step.status)}`} />
                        <strong>{step.title || node?.title || step.node_id}</strong>
                        <span className={`${styles.statusBadge} ${statusClass(step.status)}`}>{statusLabel(step.status)}</span>
                        <time>{formatClock(step.started_at || step.ended_at)}</time>
                      </button>
                      <div className={styles.chipRow}>
                        <span className={styles.chip}>{step.step_type}</span>
                        {node?.tool_name && <span className={styles.chip}>{node.tool_name}</span>}
                        {step.artifact_ids.map((artifactId) => (
                          <span key={artifactId} className={styles.chip}>Artifact {shortId(artifactId)}</span>
                        ))}
                      </div>
                      <pre className={styles.jsonPreview}>{safeJson(step.output || step.error_message || {})}</pre>
                    </article>
                  );
                })}
              </div>
            </section>
          </section>

          <section className={styles.agentBottomGrid}>
            <section className={styles.timelinePanel}>
              <div className={styles.panelChromeHeader}>
                <div>
                  <h2>实时事件 / Timeline</h2>
                  <p>按发生时间展示任务、节点、工具和 Gate 事件。</p>
                </div>
                <button className={styles.secondaryAction} type="button">
                  <Download size={16} strokeWidth={1.9} />
                  导出日志
                </button>
              </div>
              <div className={styles.timelineTable}>
                {timeline.map((event) => (
                  <div key={event.id} className={styles.timelineTableRow}>
                    <time>{formatClock(event.at)}</time>
                    <span className={`${styles.eventDot} ${statusClass(event.status)}`} />
                    <strong>{event.title}</strong>
                    <p>{event.description}</p>
                    <em>{event.actor}</em>
                  </div>
                ))}
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
        </main>

        <aside className={styles.runDetailSideRail}>
          {detail.run.status === 'awaiting_gate' && detail.run.gate?.gate_type === 'planner_clarification' && (
            <section className={styles.approvalPanel} data-testid="agent-clarification-panel">
              <div className={styles.nodeTitleLine}>
                <Bot size={20} strokeWidth={1.9} />
                <h3>补充目标信息</h3>
                <span className={`${styles.statusBadge} ${styles.statusWaiting}`}>等待补充</span>
              </div>
              <p>{String(detail.run.gate?.reason || 'Planner 需要更多信息。')}</p>
              <pre className={styles.jsonPreview}>{safeJson(detail.run.gate?.questions)}</pre>
              <textarea
                className={styles.goalInput}
                value={clarificationDraft}
                onChange={(event) => setClarificationDraft(event.target.value)}
                placeholder="补充目标、交付格式、受众、质量标准或限制条件"
                aria-label="补充目标信息"
              />
              <button className={styles.primaryAction} onClick={handleClarifyGoal} disabled={acting} type="button">
                <CheckCircle2 size={16} strokeWidth={1.9} />
                提交补充并继续规划
              </button>
            </section>
          )}

          {detail.run.status === 'awaiting_gate' && detail.run.gate?.gate_type !== 'planner_clarification' && (
            <section className={styles.approvalPanel} data-testid="agent-gate-panel">
              <div className={styles.nodeTitleLine}>
                <ShieldCheck size={20} strokeWidth={1.9} />
                <h3>Gate 审批</h3>
                <span className={`${styles.statusBadge} ${styles.statusWaiting}`}>等待确认</span>
              </div>
              <p>{String(detail.run.gate?.reason || '当前操作需要人工确认。')}</p>
              <pre className={styles.jsonPreview}>{safeJson(detail.run.gate)}</pre>
              <div className={styles.buttonRow}>
                <button className={styles.primaryAction} onClick={() => handleGate(true)} disabled={acting} type="button">
                  <CheckCircle2 size={16} strokeWidth={1.9} />
                  批准继续
                </button>
                <button className={styles.secondaryAction} onClick={() => handleGate(false)} disabled={acting} type="button">
                  <XCircle size={16} strokeWidth={1.9} />
                  拒绝操作
                </button>
              </div>
            </section>
          )}

          <section className={styles.agentPanel}>
            <h2>最终评估</h2>
            <div className={styles.finalScoreRow}>
              <strong>{finalEval ? `${Math.round(finalEval.score * 100)}%` : '-'}</strong>
              <span>{finalEval ? (finalEval.passed ? '已通过质量门槛' : '仍有未关闭问题') : '等待最终评估'}</span>
            </div>
            {finalEval ? (
              <pre className={styles.jsonPreview}>{safeJson(finalEval.issues || finalEval.suggestions || {})}</pre>
            ) : (
              <p className={styles.mutedText}>暂无最终评估记录。</p>
            )}
          </section>

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
            <h2>节点详情</h2>
            <div className={styles.inspectorCard}>
              <div className={styles.nodeTitleLine}>
                <Activity size={20} strokeWidth={1.9} />
                <h3>{selectedNode?.title || '未选择节点'}</h3>
                <span className={`${styles.statusBadge} ${statusClass(selectedStatus)}`}>{statusLabel(selectedStatus)}</span>
              </div>
              <div className={styles.inspectorTabs}>
                <span>输入</span>
                <span>输出</span>
                <span>工具调用</span>
                <span>Trace</span>
                <span>Artifact</span>
              </div>
              <p className={styles.inspectorText}>{selectedNode?.description || selectedStep?.description || '等待节点详情。'}</p>
              <div className={styles.nodeMetaGrid}>
                <span>Node ID</span>
                <strong>{selectedNode?.id || '-'}</strong>
                <span>模型</span>
                <strong>{firstString(detail.run.metadata.model_name) || '默认模型'}</strong>
                <span>耗时</span>
                <strong>{formatDuration(selectedStep?.started_at, selectedStep?.ended_at)}</strong>
                <span>状态</span>
                <strong>{statusLabel(selectedStatus)}</strong>
              </div>
              {selectedNode && (
                <div className={styles.chipRow}>
                  <span className={styles.chip}>{selectedNode.step_type}</span>
                  <span className={styles.chip}>风险 {selectedNode.risk_level}</span>
                  {selectedNode.depends_on.map((dep) => (
                    <span key={dep} className={styles.chip}>依赖 {dep}</span>
                  ))}
                </div>
              )}
              {canSkipSelectedNode && selectedNode && (
                <button
                  className={styles.secondaryAction}
                  onClick={() => handleSkipNode(selectedNode.id)}
                  disabled={acting}
                  type="button"
                >
                  <SkipForward size={15} strokeWidth={1.9} />
                  跳过节点
                </button>
              )}
              <pre className={styles.jsonPreview}>{safeJson(selectedStep?.input || selectedNode)}</pre>
            </div>
          </section>

          <section className={styles.agentPanel}>
            <h2>工具调用</h2>
            <div className={styles.sectionStack}>
              {(selectedToolCalls.length > 0 ? selectedToolCalls : detail.tool_calls.slice(0, 4)).map((call) => (
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
                    <span className={styles.chip}>成本 {costAmount(call.cost).toFixed(1)}</span>
                  </div>
                </article>
              ))}
              {detail.tool_calls.length === 0 && <p className={styles.mutedText}>暂无工具调用。</p>}
            </div>
          </section>

          <section className={styles.agentPanel}>
            <h2>Artifacts</h2>
            <div className={styles.artifactList}>
              {selectedArtifacts.length > 0 ? (
                selectedArtifacts.map((artifactId) => (
                  <span key={artifactId}>
                    <FileText size={16} strokeWidth={1.9} />
                    Artifact {shortId(artifactId)}
                  </span>
                ))
              ) : (
                <p className={styles.mutedText}>该节点暂无产物。</p>
              )}
            </div>
          </section>

          <section className={styles.agentPanel}>
            <h2>重规划历史</h2>
            {detail.replan_records.length > 0 ? (
              detail.replan_records.map((record) => (
                <article key={record.id} className={styles.memoryItem}>
                  <div className={styles.chipRow}>
                    <span className={styles.chip}>
                      <RotateCcw size={14} strokeWidth={1.9} />
                      {record.trigger_reason}
                    </span>
                  </div>
                  <pre className={styles.jsonPreview}>{safeJson(record.reflection)}</pre>
                </article>
              ))
            ) : (
              <p className={styles.mutedText}>当前运行未触发重规划。</p>
            )}
          </section>

          <section className={styles.agentPanel}>
            <h2>记忆引用</h2>
            {detail.memories.length > 0 ? (
              detail.memories.slice(0, 4).map((memory) => (
                <article key={memory.id} className={styles.memoryItem}>
                  <span className={styles.chip}>{memory.memory_type}</span>
                  <p className={styles.memoryText}>{memory.content}</p>
                </article>
              ))
            ) : (
              <p className={styles.mutedText}>暂无可显示的记忆记录。</p>
            )}
          </section>
        </aside>
      </section>
    </div>
  );
}
