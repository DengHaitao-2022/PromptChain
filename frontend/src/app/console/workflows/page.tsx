'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowUpRight,
  GitBranch,
  PlayCircle,
  Rocket,
  Sparkles,
  Waypoints,
  Workflow,
} from 'lucide-react';

import { useAuth } from '@/contexts/AuthContext';
import {
  useWorkflowApi,
  type WorkflowDefinition,
} from '@/components/WorkflowEditor/hooks/useWorkflowApi';
import styles from './workflows.module.css';

interface SummaryItem {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: 'neutral' | 'success' | 'warning';
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

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function WorkflowsPage() {
  const { hasPermission } = useAuth();
  const { listWorkflows } = useWorkflowApi();
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchWorkflows() {
      setLoading(true);
      setError(null);

      try {
        const data = await listWorkflows();
        if (!cancelled) {
          setWorkflows(data.workflows);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : '加载工作流列表失败',
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchWorkflows();

    return () => {
      cancelled = true;
    };
  }, [listWorkflows]);

  const canCreate = hasPermission('workflow', 'create');
  const canEdit = hasPermission('workflow', 'update');
  const publishedCount = workflows.filter((workflow) => workflow.is_published).length;
  const draftCount = workflows.filter((workflow) => !workflow.is_published).length;
  const pendingCount = workflows.filter(
    (workflow) => workflow.published_version && workflow.version !== workflow.published_version,
  ).length;

  const summaryItems: SummaryItem[] = [
    {
      icon: Waypoints,
      label: '全部工作流',
      value: String(workflows.length),
      tone: 'neutral',
    },
    {
      icon: Rocket,
      label: '已发布',
      value: String(publishedCount),
      tone: 'success',
    },
    {
      icon: GitBranch,
      label: '待发布变更',
      value: String(pendingCount || draftCount),
      tone: 'warning',
    },
  ];

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
            <span className={styles.eyebrow}>工作流库</span>
            <h1 className={styles.title}>把草稿、发布与运行状态收进同一套版本视图</h1>
            <p className={styles.subtitle}>
              这里统一管理工作流定义、当前草稿版本、已发布版本和普通用户是否可运行的状态，避免编辑面和运行面脱节。
            </p>

            <div className={styles.heroActions}>
              {canCreate ? (
                <Link href="/console/workflows/edit" className={styles.primaryAction}>
                  <Sparkles size={18} strokeWidth={1.9} />
                  <span>创建工作流</span>
                </Link>
              ) : null}
              <Link href="/" className={styles.secondaryAction}>
                <PlayCircle size={18} strokeWidth={1.9} />
                <span>返回首页发起运行</span>
              </Link>
            </div>
          </div>

          <div className={styles.heroSignal}>
            <span className={styles.heroSignalLabel}>版本信号</span>
            <strong className={styles.heroSignalValue}>{publishedCount}</strong>
            <p className={styles.heroSignalText}>当前可供普通用户直接运行的已发布工作流数量。</p>
            <div className={styles.heroSignalGrid}>
              <div className={styles.heroSignalItem}>
                <span>草稿数</span>
                <strong>{draftCount}</strong>
              </div>
              <div className={styles.heroSignalItem}>
                <span>待发布变更</span>
                <strong>{pendingCount}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.summaryGrid}>
        {summaryItems.map((item) => {
          const Icon = item.icon;

          return (
            <article key={item.label} className={`${styles.summaryCard} ${styles[`tone${capitalize(item.tone)}`]}`}>
              <span className={styles.summaryIcon} aria-hidden="true">
                <Icon size={18} strokeWidth={1.9} />
              </span>
              <div className={styles.summaryCopy}>
                <span className={styles.summaryLabel}>{item.label}</span>
                <strong className={styles.summaryValue}>{item.value}</strong>
              </div>
            </article>
          );
        })}
      </section>

      {error ? (
        <div className={styles.errorBanner}>
          <strong>工作流列表暂时不可用</strong>
          <span>{error}</span>
        </div>
      ) : null}

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
      ) : workflows.length > 0 ? (
        <div className={styles.workflowGrid}>
          {workflows.map((workflow) => (
            <article key={workflow.id} className={styles.workflowCard}>
              <div className={styles.cardHeader}>
                <div className={styles.cardTitleGroup}>
                  <h3 className={styles.cardTitle}>{workflow.name}</h3>
                  <p className={styles.cardDescription}>
                    {workflow.description || '暂无说明，建议补充工作流用途与适用场景。'}
                  </p>
                </div>

                <div className={styles.badges}>
                  <span
                    className={`${styles.badge} ${
                      workflow.is_published ? styles.published : styles.draft
                    }`}
                  >
                    {workflow.is_published ? '已发布' : '草稿'}
                  </span>
                  <span className={`${styles.badge} ${styles.version}`}>
                    当前草稿 v{workflow.version}
                  </span>
                  {workflow.published_version ? (
                    <>
                      <span className={`${styles.badge} ${styles.runnable}`}>
                        可运行 v{workflow.published_version}
                      </span>
                      {workflow.version !== workflow.published_version && (
                        <span className={`${styles.badge} ${styles.pending}`}>
                          有未发布变更
                        </span>
                      )}
                    </>
                  ) : (
                    <span className={`${styles.badge} ${styles.pending}`}>
                      需发布后运行
                    </span>
                  )}
                </div>
              </div>

              <dl className={styles.metaList}>
                <div className={styles.metaItem}>
                  <dt>最近更新时间</dt>
                  <dd>{formatDateTime(workflow.updated_at)}</dd>
                </div>
                <div className={styles.metaItem}>
                  <dt>最近发布时间</dt>
                  <dd>{workflow.published_at ? formatDateTime(workflow.published_at) : '尚未发布'}</dd>
                </div>
              </dl>

              <div className={styles.cardFooter}>
                <span className={styles.runState}>
                  {workflow.is_published
                    ? '普通用户可见并可运行'
                    : '仅设计者可见，普通用户不可运行'}
                </span>
                {canEdit ? (
                  <Link
                    href={`/console/workflows/edit?id=${workflow.id}`}
                    className={styles.editLink}
                  >
                    <span>编辑与发布</span>
                    <ArrowUpRight size={16} strokeWidth={1.9} aria-hidden="true" />
                  </Link>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          <span className={styles.emptyIcon} aria-hidden="true">
            <Workflow size={20} strokeWidth={1.9} />
          </span>
          <h3>还没有工作流</h3>
          <p>
            {canCreate
              ? '从一个草稿开始，先保存、再校验、最后显式发布。'
              : '当前工作空间还没有可见的已发布工作流。'}
          </p>
          {canCreate ? (
            <Link href="/console/workflows/edit" className={styles.primaryAction}>
              <Sparkles size={18} strokeWidth={1.9} />
              <span>创建第一个工作流</span>
            </Link>
          ) : null}
        </div>
      )}
    </div>
  );
}
