'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowUpRight,
  Bot,
  PlayCircle,
  ShieldAlert,
  Wrench,
} from 'lucide-react';
import { agentApi } from '@/lib/api';
import type { AgentRun, AgentToolDefinition } from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';
import styles from './agents.module.css';

const DEFAULT_GOAL =
  '请围绕当前项目，调研从 Workflow Agent 到 Autonomous Agent 的技术路线，输出一份可用于后续论文展望和答辩回答的材料。';

function statusLabel(status: string) {
  switch (status) {
    case 'planning':
      return '规划中';
    case 'running':
      return '执行中';
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

function summarize(text: string) {
  return text.length > 120 ? `${text.slice(0, 120)}...` : text;
}

export default function AgentRunsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [tools, setTools] = useState<AgentToolDefinition[]>([]);
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function refresh() {
    const [runResult, toolResult] = await Promise.all([
      agentApi.getRuns(),
      agentApi.getTools(),
    ]);
    setRuns(runResult.runs || []);
    setTools(toolResult.tools || []);
  }

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [runResult, toolResult] = await Promise.all([
          agentApi.getRuns(),
          agentApi.getTools(),
        ]);
        if (active) {
          setRuns(runResult.runs || []);
          setTools(toolResult.tools || []);
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
    };
  }, []);

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!goal.trim()) {
      setError('请输入明确的目标。');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await agentApi.start(goal.trim(), { autoExecute: true, autonomyLevel: 'supervised' });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动自主 Agent 失败');
    } finally {
      setSubmitting(false);
    }
  }

  const metrics = useMemo(() => {
    const active = runs.filter((run) =>
      ['planning', 'running', 'awaiting_gate', 'paused'].includes(run.status),
    ).length;
    const completed = runs.filter((run) => run.status === 'completed').length;
    const failed = runs.filter((run) => ['failed', 'cancelled'].includes(run.status)).length;
    return { active, completed, failed };
  }, [runs]);

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>Autonomous Agent</span>
          <h1 className={styles.title}>目标驱动的长程任务运行台</h1>
          <p className={styles.description}>
            自主 Agent 会把开放目标拆成计划图，执行工具调用，记录评估与重规划，并把最终产物和过程证据留在可回放链路中。
          </p>
          <div className={styles.headerActions}>
            <Link href="/console/runs" className={styles.secondaryAction}>
              工作流运行记录
              <ArrowUpRight size={16} strokeWidth={1.9} />
            </Link>
          </div>
        </div>

        <section className={styles.formPanel} aria-label="启动自主 Agent">
          <div>
            <h2 className={styles.panelTitle}>启动目标</h2>
            <p className={styles.panelDescription}>输入目标后会立即生成计划、执行步骤并沉淀审计记录。</p>
          </div>

          <form className={styles.goalForm} onSubmit={handleStart}>
            <textarea
              className={styles.goalInput}
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder="输入需要自主规划和长程执行的目标"
            />
            <button type="submit" className={styles.primaryAction} disabled={submitting}>
              <PlayCircle size={17} strokeWidth={1.9} />
              {submitting ? '正在启动' : '启动 Agent'}
            </button>
          </form>
        </section>
      </section>

      <section className={styles.metricsGrid}>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>累计运行</span>
          <strong className={styles.metricValue}>{runs.length}</strong>
        </article>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>活跃运行</span>
          <strong className={styles.metricValue}>{metrics.active}</strong>
        </article>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>已完成</span>
          <strong className={styles.metricValue}>{metrics.completed}</strong>
        </article>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>异常收口</span>
          <strong className={styles.metricValue}>{metrics.failed}</strong>
        </article>
      </section>

      {error && (
        <div className={styles.errorState}>
          <ShieldAlert size={20} strokeWidth={1.9} />
          <p>{error}</p>
        </div>
      )}

      <section className={styles.contentGrid}>
        <main className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}>Agent 运行</h2>
              <p className={styles.panelDescription}>按创建时间倒序展示当前工作空间内可见的自主运行。</p>
            </div>
          </div>

          {loading ? (
            <div className={styles.emptyState}>正在加载自主 Agent 运行...</div>
          ) : runs.length > 0 ? (
            <div className={styles.runList}>
              {runs.map((run) => (
                <article key={run.id} className={styles.runCard}>
                  <div className={styles.runHeader}>
                    <div>
                      <h3 className={styles.runTitle}>{summarize(run.goal)}</h3>
                      <p className={styles.runGoal}>创建于 {formatAppDateTime(run.created_at)}</p>
                    </div>
                    <span className={`${styles.statusBadge} ${statusClass(run.status)}`}>
                      {statusLabel(run.status)}
                    </span>
                  </div>

                  <div className={styles.metaGrid}>
                    <div className={styles.metaItem}>
                      <span className={styles.metaLabel}>自治级别</span>
                      <strong className={styles.metaValue}>{run.autonomy_level}</strong>
                    </div>
                    <div className={styles.metaItem}>
                      <span className={styles.metaLabel}>计划版本</span>
                      <strong className={styles.metaValue}>{String(run.metadata?.plan_version || '-')}</strong>
                    </div>
                    <div className={styles.metaItem}>
                      <span className={styles.metaLabel}>最终产物</span>
                      <strong className={styles.metaValue}>{run.final_artifact_id ? '已生成' : '待生成'}</strong>
                    </div>
                  </div>

                  <Link href={`/console/agents/${run.id}`} className={styles.secondaryAction}>
                    查看详情
                    <ArrowUpRight size={16} strokeWidth={1.9} />
                  </Link>
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <Bot size={22} strokeWidth={1.9} />
              <p>还没有自主 Agent 运行。输入一个开放目标即可生成第一条动态计划。</p>
            </div>
          )}
        </main>

        <aside className={styles.sidePanel}>
          <div>
            <h2 className={styles.panelTitle}>工具注册中心</h2>
            <p className={styles.panelDescription}>工具调用会按风险等级进入审计或 Gate。</p>
          </div>
          <div className={styles.sectionStack}>
            {tools.map((tool) => (
              <article key={tool.name} className={styles.toolItem}>
                <div className={styles.timelineHeader}>
                  <h3 className={styles.timelineTitle}>{tool.name}</h3>
                  <span className={`${styles.statusBadge} ${tool.risk_level === 'low' ? styles.statusRunning : styles.statusWaiting}`}>
                    {tool.risk_level}
                  </span>
                </div>
                <p className={styles.timelineText}>{tool.description}</p>
                <div className={styles.chipRow}>
                  <span className={styles.chip}>
                    <Wrench size={14} strokeWidth={1.9} />
                    {tool.permission}
                  </span>
                  <span className={styles.chip}>{tool.idempotent ? '幂等' : '写入'}</span>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </section>
    </div>
  );
}
