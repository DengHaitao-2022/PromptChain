'use client';

/**
 * 控制台首页。
 *
 * 展示工作空间总览、快捷入口和最近运行列表。
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowUpRight,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Sparkles,
  Users,
  Waypoints,
  Workflow,
  XCircle,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import styles from './dashboard.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

interface DashboardData {
  today_runs: number;
  today_success_runs: number;
  today_failed_runs: number;
  today_avg_duration_ms: number;
  total_runs: number;
  total_members: number;
  recent_runs: Array<{
    id: string;
    workflow_name: string;
    status: string;
    started_at: string;
    duration_ms: number;
  }>;
}

interface StatItem {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: 'neutral' | 'positive' | 'warning' | 'danger';
}

function formatStatusLabel(status: string) {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'failed':
      return '失败';
    case 'running':
      return '进行中';
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

function formatDateTime(value?: string): string {
  if (!value) {
    return '暂无记录';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export default function DashboardPage() {
  const { workspace, hasPermission } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    async function fetchDashboard() {
      if (!workspace) {
        if (active) {
          setLoading(false);
        }
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/admin/dashboard`, {
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error('加载数据失败');
        }

        const result = await response.json();
        if (active) {
          setData(result);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : '网络错误');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void fetchDashboard();

    return () => {
      active = false;
    };
  }, [workspace]);

  const failureRate =
    data && data.today_runs > 0 ? `${((data.today_failed_runs / data.today_runs) * 100).toFixed(1)}%` : '0%';

  const statItems: StatItem[] = [
    {
      icon: Waypoints,
      label: '今日运行',
      value: String(data?.today_runs || 0),
      tone: 'neutral',
    },
    {
      icon: CheckCircle2,
      label: '成功运行',
      value: String(data?.today_success_runs || 0),
      tone: 'positive',
    },
    {
      icon: XCircle,
      label: '失败率',
      value: failureRate,
      tone: 'danger',
    },
    {
      icon: Clock3,
      label: '平均耗时',
      value: data?.today_avg_duration_ms ? `${(data.today_avg_duration_ms / 1000).toFixed(1)}s` : '0s',
      tone: 'warning',
    },
  ];

  if (loading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
        <p>正在加载工作台概览...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.errorState}>
        <h2>控制台数据暂时不可用</h2>
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroGlow} aria-hidden="true">
          <span className={styles.heroOrbPrimary} />
          <span className={styles.heroOrbSecondary} />
        </div>

        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>工作台</span>
          <h1 className={styles.title}>欢迎回到 {workspace?.name || '当前工作空间'}</h1>
          <p className={styles.subtitle}>
            从这里查看今日运行、快速进入工作流库与运行回放，并持续观察当前工作空间的执行节奏。
          </p>
        </div>

        <div className={styles.heroPanel}>
          <span className={styles.heroPanelLabel}>空间信号</span>
          <strong className={styles.heroPanelValue}>{data?.total_runs || 0}</strong>
          <p className={styles.heroPanelText}>累计运行次数</p>
          <div className={styles.heroPanelMeta}>
            <div>
              <span>成员数</span>
              <strong>{data?.total_members || 0}</strong>
            </div>
            <div>
              <span>今日成功</span>
              <strong>{data?.today_success_runs || 0}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.statsGrid}>
        {statItems.map((item) => {
          const Icon = item.icon;

          return (
            <article key={item.label} className={`${styles.statCard} ${styles[`tone${capitalize(item.tone)}`]}`}>
              <span className={styles.statIcon} aria-hidden="true">
                <Icon size={18} strokeWidth={1.9} />
              </span>
              <div className={styles.statContent}>
                <div className={styles.statValue}>{item.value}</div>
                <div className={styles.statLabel}>{item.label}</div>
              </div>
            </article>
          );
        })}
      </section>

      <section className={styles.contentGrid}>
        <div className={styles.mainColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>快捷操作</h2>
                <p className={styles.sectionDescription}>围绕工作流设计、运行回放和成员协作的常用入口。</p>
              </div>
            </div>

            <div className={styles.quickActions}>
              <Link href="/console/workflows" className={styles.actionCard}>
                <span className={styles.actionIcon} aria-hidden="true">
                  <Workflow size={18} strokeWidth={1.9} />
                </span>
                <div className={styles.actionCopy}>
                  <strong>管理工作流</strong>
                  <span>查看草稿、发布版本和当前可运行状态。</span>
                </div>
                <ArrowUpRight size={16} strokeWidth={1.9} className={styles.actionArrow} aria-hidden="true" />
              </Link>

              <Link href="/console/runs" className={styles.actionCard}>
                <span className={styles.actionIcon} aria-hidden="true">
                  <ClipboardList size={18} strokeWidth={1.9} />
                </span>
                <div className={styles.actionCopy}>
                  <strong>查看运行记录</strong>
                  <span>进入运行流、状态切换和 trace 回放入口。</span>
                </div>
                <ArrowUpRight size={16} strokeWidth={1.9} className={styles.actionArrow} aria-hidden="true" />
              </Link>

              {hasPermission('member', 'manage') && (
                <Link href="/console/settings/members" className={styles.actionCard}>
                  <span className={styles.actionIcon} aria-hidden="true">
                    <Users size={18} strokeWidth={1.9} />
                  </span>
                  <div className={styles.actionCopy}>
                    <strong>成员管理</strong>
                    <span>调整工作空间成员、角色和协作边界。</span>
                  </div>
                  <ArrowUpRight size={16} strokeWidth={1.9} className={styles.actionArrow} aria-hidden="true" />
                </Link>
              )}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div>
                <h2 className={styles.sectionTitle}>最近运行</h2>
                <p className={styles.sectionDescription}>优先关注最近一次执行结果和当前状态。</p>
              </div>
            </div>

            {data?.recent_runs && data.recent_runs.length > 0 ? (
              <div className={styles.runList}>
                {data.recent_runs.map((run) => (
                  <article key={run.id} className={styles.runCard}>
                    <div className={styles.runCardHeader}>
                      <div>
                        <h3 className={styles.runName}>{run.workflow_name}</h3>
                        <p className={styles.runMeta}>开始于 {formatDateTime(run.started_at)}</p>
                      </div>
                      <span className={`${styles.statusBadge} ${getStatusToneClass(run.status)}`}>
                        {formatStatusLabel(run.status)}
                      </span>
                    </div>

                    <div className={styles.runFooter}>
                      <span className={styles.runDuration}>
                        耗时 {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '未记录'}
                      </span>
                      <Link href={`/workflow/${run.id}`} className={styles.detailLink}>
                        查看详情
                        <ArrowUpRight size={16} strokeWidth={1.9} aria-hidden="true" />
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className={styles.emptyState}>
                <span className={styles.emptyIcon} aria-hidden="true">
                  <Sparkles size={18} strokeWidth={1.9} />
                </span>
                <h3>还没有最近运行</h3>
                <p>当工作流开始执行后，这里会展示最近的运行记录与详情入口。</p>
              </div>
            )}
          </section>
        </div>

        <aside className={styles.sideColumn}>
          <section className={styles.sidePanel}>
            <h2 className={styles.sidePanelTitle}>运行提示</h2>
            <div className={styles.tipList}>
              <div className={styles.tipItem}>
                <strong>先看成功率</strong>
                <span>若失败率持续抬升，优先进入运行记录页定位异常节点。</span>
              </div>
              <div className={styles.tipItem}>
                <strong>再看平均耗时</strong>
                <span>耗时异常通常意味着模型调用或人工门控变慢。</span>
              </div>
              <div className={styles.tipItem}>
                <strong>最后回看 trace</strong>
                <span>详情页会给出节点流转、产物和审批链路的完整上下文。</span>
              </div>
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
