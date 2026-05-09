'use client';

/**
 * 运行记录总览页。
 *
 * 当前页面通过 workflowApi.getRuns() 读取真实运行记录，并负责列表态展示与详情跳转入口。
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  PlayCircle,
  ShieldAlert,
  Sparkles,
  Waypoints,
} from 'lucide-react';
import styles from './runs.module.css';
import { workflowApi } from '@/lib/api';
import type { WorkflowRunSummary } from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';

interface InsightItem {
  icon: LucideIcon;
  title: string;
  description: string;
}

const INSIGHTS: InsightItem[] = [
  {
    icon: Activity,
    title: '状态回放',
    description: '运行开始后，这里会按时间顺序展示状态、节点与异常切换。',
  },
  {
    icon: ShieldAlert,
    title: '异常定位',
    description: '失败、暂停与门控等待会被提取成独立状态，便于快速值守。',
  },
  {
    icon: Sparkles,
    title: '追踪入口',
    description: '每条运行都会保留详情入口，便于回看 trace、产物与审批链路。',
  },
];

function formatStatusLabel(status: string) {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'failed':
      return '失败';
    case 'running':
      return '进行中';
    case 'paused':
      return '已暂停';
    case 'needs_clarification':
      return '待澄清';
    case 'awaiting_outline_approval':
      return '待审提纲';
    case 'awaiting_fact_check_approval':
      return '待审事实核查';
    default:
      return status;
  }
}

function getStatusToneClass(status: string) {
  switch (status) {
    case 'completed':
      return styles.statusCompleted;
    case 'failed':
      return styles.statusFailed;
    case 'running':
      return styles.statusRunning;
    default:
      return styles.statusWaiting;
  }
}

function formatDuration(durationMs: number | null) {
  if (!durationMs) {
    return '未完成';
  }

  return `${(durationMs / 1000).toFixed(1)}s`;
}

function formatStartedAt(dateString: string) {
  return formatAppDateTime(dateString);
}

function summarizeInput(text: string) {
  if (!text) {
    return '未记录输入摘要';
  }

  if (text.length <= 84) {
    return text;
  }

  return `${text.slice(0, 84)}…`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<WorkflowRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    const fetchRuns = async () => {
      try {
        const response = await workflowApi.getRuns();
        if (active) {
          setRuns(response.data.runs || []);
        }
      } catch {
        if (active) {
          setError('运行记录加载失败，请稍后重试。');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void fetchRuns();

    return () => {
      active = false;
    };
  }, []);

  const completedCount = runs.filter((run) => run.status === 'completed').length;
  const failedCount = runs.filter((run) => run.status === 'failed').length;
  const activeCount = runs.filter((run) => !['completed', 'failed'].includes(run.status)).length;
  const averageDurationMs =
    runs.length > 0
      ? runs.reduce((sum, run) => sum + (run.total_duration_ms || 0), 0) / runs.length
      : null;

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroBackdrop} aria-hidden="true">
          <span className={styles.heroOrbPrimary} />
          <span className={styles.heroOrbSecondary} />
          <span className={styles.heroBeam} />
        </div>

        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <span className={styles.eyebrow}>运行总览</span>
            <h1 className={styles.title}>把每一次生成放进可值守的监控面板</h1>
            <p className={styles.description}>
              运行记录页会收拢工作流执行、当前节点、异常状态和回看入口。当前先完成页面视觉与状态层，等待列表接口接入真实数据。
            </p>

            <div className={styles.heroActions}>
              <Link href="/" className={styles.primaryAction}>
                <PlayCircle size={18} strokeWidth={1.9} />
                <span>返回首页发起运行</span>
              </Link>
              <Link href="/console/workflows" className={styles.secondaryAction}>
                <span>查看工作流库</span>
                <ArrowUpRight size={16} strokeWidth={1.9} />
              </Link>
            </div>
          </div>

          <div className={styles.heroSignal}>
            <div className={styles.heroSignalHeader}>
              <span className={styles.heroSignalLabel}>监控信号</span>
              <span className={styles.heroSignalValue}>{runs.length}</span>
            </div>
            <p className={styles.heroSignalText}>本页当前优先收口空态、错误态、加载态和运行卡片语言。</p>
            <div className={styles.heroSignalGrid}>
              <div className={styles.heroSignalItem}>
                <span>活跃运行</span>
                <strong>{activeCount}</strong>
              </div>
              <div className={styles.heroSignalItem}>
                <span>失败运行</span>
                <strong>{failedCount}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.metricsGrid}>
        <article className={styles.metricCard}>
          <span className={styles.metricIcon} aria-hidden="true">
            <Waypoints size={18} strokeWidth={1.9} />
          </span>
          <div className={styles.metricCopy}>
            <span className={styles.metricLabel}>累计运行</span>
            <strong className={styles.metricValue}>{runs.length}</strong>
          </div>
        </article>

        <article className={styles.metricCard}>
          <span className={styles.metricIcon} aria-hidden="true">
            <Activity size={18} strokeWidth={1.9} />
          </span>
          <div className={styles.metricCopy}>
            <span className={styles.metricLabel}>活跃运行</span>
            <strong className={styles.metricValue}>{activeCount}</strong>
          </div>
        </article>

        <article className={styles.metricCard}>
          <span className={styles.metricIcon} aria-hidden="true">
            <CheckCircle2 size={18} strokeWidth={1.9} />
          </span>
          <div className={styles.metricCopy}>
            <span className={styles.metricLabel}>完成运行</span>
            <strong className={styles.metricValue}>{completedCount}</strong>
          </div>
        </article>

        <article className={styles.metricCard}>
          <span className={styles.metricIcon} aria-hidden="true">
            <Clock3 size={18} strokeWidth={1.9} />
          </span>
          <div className={styles.metricCopy}>
            <span className={styles.metricLabel}>平均耗时</span>
            <strong className={styles.metricValue}>{formatDuration(averageDurationMs)}</strong>
          </div>
        </article>
      </section>

      <section className={styles.contentGrid}>
        <div className={styles.primaryColumn}>
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}>运行流</h2>
              <p className={styles.panelDescription}>真实接口接入后，这里将按时间倒序显示每一次工作流运行。</p>
            </div>
          </div>

          {loading ? (
            <div className={styles.loadingState}>
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className={styles.skeletonCard} aria-hidden="true">
                  <div className={styles.skeletonLineWide} />
                  <div className={styles.skeletonLineMedium} />
                  <div className={styles.skeletonMetaRow}>
                    <div className={styles.skeletonChip} />
                    <div className={styles.skeletonChip} />
                    <div className={styles.skeletonChip} />
                  </div>
                </div>
              ))}
            </div>
          ) : error ? (
            <div className={styles.errorState}>
              <span className={styles.errorIcon} aria-hidden="true">
                <ShieldAlert size={20} strokeWidth={1.9} />
              </span>
              <div>
                <h3>运行记录暂时不可用</h3>
                <p>{error}</p>
              </div>
            </div>
          ) : runs.length > 0 ? (
            <div className={styles.runList}>
              {runs.map((run) => (
                <article key={run.id} className={styles.runCard}>
                  <div className={styles.runCardHeader}>
                    <div className={styles.runTitleGroup}>
                      <h3 className={styles.runTitle}>{run.workflow_name}</h3>
                      <p className={styles.runPrompt}>{summarizeInput(run.user_input)}</p>
                    </div>
                    <span className={`${styles.statusBadge} ${getStatusToneClass(run.status)}`}>
                      {formatStatusLabel(run.status)}
                    </span>
                  </div>

                  <div className={styles.runMetaGrid}>
                    <div className={styles.metaItem}>
                      <span className={styles.metaLabel}>开始时间</span>
                      <strong>{formatStartedAt(run.started_at)}</strong>
                    </div>
                    <div className={styles.metaItem}>
                      <span className={styles.metaLabel}>当前节点</span>
                      <strong>{run.current_node || '等待更新'}</strong>
                    </div>
                    <div className={styles.metaItem}>
                      <span className={styles.metaLabel}>累计耗时</span>
                      <strong>{formatDuration(run.total_duration_ms)}</strong>
                    </div>
                  </div>

                  <Link href={`/workflow/${run.id}`} className={styles.detailLink}>
                    查看详情
                    <ArrowUpRight size={16} strokeWidth={1.9} />
                  </Link>
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <span className={styles.emptyIcon} aria-hidden="true">
                <Waypoints size={22} strokeWidth={1.9} />
              </span>
              <h3 className={styles.emptyTitle}>运行记录尚未出现</h3>
              <p className={styles.emptyDescription}>
                启动工作流后，这里会依次展示运行状态、当前节点、累计耗时与详情入口，用于回看和排障。
              </p>

              <div className={styles.emptyActions}>
                <Link href="/" className={styles.primaryAction}>
                  <PlayCircle size={18} strokeWidth={1.9} />
                  <span>发起第一条运行</span>
                </Link>
                <Link href="/console/workflows" className={styles.secondaryAction}>
                  <span>先查看工作流列表</span>
                  <ArrowUpRight size={16} strokeWidth={1.9} />
                </Link>
              </div>
            </div>
          )}
        </div>

        <aside className={styles.sideColumn}>
          <section className={styles.sidePanel}>
            <div className={styles.sidePanelHeader}>
              <h2 className={styles.sidePanelTitle}>监控焦点</h2>
              <p className={styles.sidePanelDescription}>先把值守语言建立起来，再接入真实运行数据。</p>
            </div>

            <div className={styles.insightList}>
              {INSIGHTS.map((item) => {
                const Icon = item.icon;

                return (
                  <article key={item.title} className={styles.insightItem}>
                    <span className={styles.insightIcon} aria-hidden="true">
                      <Icon size={18} strokeWidth={1.9} />
                    </span>
                    <div className={styles.insightCopy}>
                      <strong>{item.title}</strong>
                      <span>{item.description}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
