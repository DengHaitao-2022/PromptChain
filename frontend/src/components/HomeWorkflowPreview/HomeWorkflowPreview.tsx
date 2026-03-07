'use client';

import type { CSSProperties } from 'react';
import {
  BadgeCheck,
  Blocks,
  Bot,
  FileSearch,
  GitBranch,
  Radar,
  ScanSearch,
  Sparkles,
} from 'lucide-react';
import styles from './HomeWorkflowPreview.module.css';

type LaunchMode = 'idle' | 'launching' | 'handoff';

interface HomeWorkflowPreviewProps {
  mode: LaunchMode;
  workflowId: string | null;
}

const pipeline = [
  {
    id: 'parse_intent',
    label: 'Parse Intent',
    summary: '抽取目标、读者与约束',
    icon: ScanSearch,
  },
  {
    id: 'generate_outline',
    label: 'Generate Outline',
    summary: '形成可审批结构',
    icon: Blocks,
  },
  {
    id: 'generate_content',
    label: 'Generate Content',
    summary: '分段生成核心内容',
    icon: Bot,
  },
  {
    id: 'check_facts',
    label: 'Check Facts',
    summary: '识别高风险声明',
    icon: FileSearch,
  },
  {
    id: 'finalize',
    label: 'Finalize',
    summary: '写入最终产物版本',
    icon: BadgeCheck,
  },
];

const telemetry = [
  {
    label: 'Artifacts',
    value: 'write-once',
    detail: '产物按版本保留',
    icon: GitBranch,
  },
  {
    label: 'Approvals',
    value: 'human gate',
    detail: '提纲与事实双门控',
    icon: Sparkles,
  },
  {
    label: 'Trace',
    value: 'node-level',
    detail: '每个节点可追踪',
    icon: Radar,
  },
];

const statusMap = {
  idle: '[SYSTEM_READY]',
  launching: '[ORCHESTRATING]',
  handoff: '[HANDOFF_READY]',
} as const;

const stateLabelMap = {
  idle: 'ready',
  launching: 'running',
  handoff: 'synced',
} as const;

export function HomeWorkflowPreview({ mode, workflowId }: HomeWorkflowPreviewProps) {
  return (
    <section
      className={`${styles.container} ${styles[mode]}`}
      aria-label="工作流启动预览"
    >
      <div className={styles.mobileRibbon}>
        <span>{statusMap[mode]}</span>
        <span>{mode === 'idle' ? '5-step pipeline' : 'launch feedback active'}</span>
      </div>

      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Orchestration Matrix</p>
          <h2 className={styles.title}>启动前即可看见工作流编排路径</h2>
        </div>
        <span className={styles.statusPill}>{statusMap[mode]}</span>
      </div>

      <div className={styles.body}>
        <div className={styles.pipeline}>
          <div className={styles.pipelineLine} aria-hidden="true">
            <div className={styles.pipelineTrace} />
          </div>

          {pipeline.map((step, index) => {
            const Icon = step.icon;
            return (
              <article
                key={step.id}
                className={styles.node}
                style={{ '--node-delay': `${index * 140}ms` } as CSSProperties}
              >
                <div className={styles.nodeIcon}>
                  <Icon size={16} aria-hidden="true" />
                </div>
                <div className={styles.nodeCopy}>
                  <strong>{step.label}</strong>
                  <span>{step.summary}</span>
                </div>
                <span className={styles.nodeState}>{stateLabelMap[mode]}</span>
              </article>
            );
          })}
        </div>

        <div className={styles.telemetry}>
          {telemetry.map((item, index) => {
            const Icon = item.icon;
            return (
              <article
                key={item.label}
                className={styles.telemetryCard}
                style={{ '--node-delay': `${index * 160 + 160}ms` } as CSSProperties}
              >
                <div className={styles.telemetryIcon}>
                  <Icon size={16} aria-hidden="true" />
                </div>
                <span className={styles.telemetryLabel}>{item.label}</span>
                <strong>{item.value}</strong>
                <p>{item.detail}</p>
              </article>
            );
          })}
        </div>
      </div>

      <footer className={styles.footer}>
        <span className={styles.traceId}>TRACE_ID {workflowId ? workflowId.slice(0, 8) : 'pending'}</span>
        <span className={styles.footerNote}>首页先建立启动感知，再移交至详情页审批链路</span>
      </footer>
    </section>
  );
}
