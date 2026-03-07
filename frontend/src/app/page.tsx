'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  Bot,
  Cable,
  GitBranch,
  Play,
  Radar,
  ScanSearch,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from 'lucide-react';
import styles from './page.module.css';
import { HomeWorkflowPreview } from '@/components/HomeWorkflowPreview/HomeWorkflowPreview';
import { workflowApi } from '@/lib/api';

type LaunchState = 'idle' | 'launching' | 'handoff';

interface FeatureCard {
  icon: LucideIcon;
  title: string;
  description: string;
  tag: string;
}

interface TrustSignal {
  eyebrow: string;
  title: string;
  description: string;
}

const examplePrompts = [
  '写一篇关于 AI Agent 技术架构的深度文章，面向技术开发者，2000 字左右',
  '生成一份面向投资人的智能客服 SaaS 商业计划书，突出市场和护城河',
  '输出一篇关于量子计算应用边界的科普稿，要求论证严谨并标注高风险事实',
];

const workflowChain = [
  'Parse Intent',
  'Clarify',
  'Outline',
  'Generate',
  'Refine',
  'Fact Check',
  'Finalize',
];

const features: FeatureCard[] = [
  {
    icon: ScanSearch,
    title: '智能意图解析',
    description: '自动抽取目标、读者、限制条件和缺失信息，先把需求结构化再进入生成链路。',
    tag: 'Intent Parser',
  },
  {
    icon: ScrollText,
    title: '交互式提纲生成',
    description: '先生成可审批提纲，再把结构确认变成正式的工作流节点，而不是一次性输出。',
    tag: 'Outline Gate',
  },
  {
    icon: ShieldCheck,
    title: '高风险事实门控',
    description: '把事实核查结果显式暴露给用户，支持确认、采纳建议或人工修正。',
    tag: 'Fact Approval',
  },
  {
    icon: Sparkles,
    title: 'Self-Refine 优化',
    description: '生成、反馈、精炼形成闭环，让内容质量提升成为可重复的流程步骤。',
    tag: 'Refinement Loop',
  },
  {
    icon: GitBranch,
    title: '版本化重跑',
    description: '每一次产物都保持可追溯版本，并允许从指定节点重跑，而不是整体重来。',
    tag: 'Rerun Ready',
  },
  {
    icon: Radar,
    title: 'Trace 可视化',
    description: '完整记录节点输入、输出、耗时与决策，让 AI 工作流具备工程化可观测性。',
    tag: 'Execution Trace',
  },
];

const trustSignals: TrustSignal[] = [
  {
    eyebrow: '[APPROVAL_GATES]',
    title: '关键节点留给人确认',
    description: '提纲审批和高风险事实确认都被建模为门控节点，不把不确定决策藏进黑盒。',
  },
  {
    eyebrow: '[ARTIFACT_HISTORY]',
    title: '产物版本写一次，永久可追',
    description: '生成内容、核查报告和节点输出都按版本保留，支持回看与重跑。',
  },
  {
    eyebrow: '[TRACE_VISIBILITY]',
    title: '从 API 到节点执行都能定位',
    description: '首页启动后即进入可追踪的运行态，便于后续查看时间线与状态转移。',
  },
];

const sleep = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

export default function Home() {
  const router = useRouter();
  const [userInput, setUserInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!userInput.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);
    setLaunchState('launching');

    try {
      const [response] = await Promise.all([workflowApi.start(userInput.trim()), sleep(900)]);
      setWorkflowId(response.workflow_run_id);
      setLaunchState('handoff');
      await sleep(280);
      router.push(`/workflow/${response.workflow_run_id}`);
    } catch (err) {
      setLaunchState('idle');
      setWorkflowId(null);
      setError(err instanceof Error ? err.message : '工作流启动失败');
    } finally {
      setIsLoading(false);
    }
  };

  const fillExample = (example: string) => {
    setUserInput(example);
    setError(null);
  };

  const launchHint =
    launchState === 'launching'
      ? '正在依次编排意图解析、提纲生成与事实核查节点。'
      : launchState === 'handoff'
        ? `工作流 ${workflowId?.slice(0, 8) ?? 'pending'} 已建立，准备进入详情页。`
        : '点击后会先完成首页启动反馈，再跳转到工作流详情。';

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.logo}>
            <span className={styles.logoIcon}>
              <Waypoints size={18} aria-hidden="true" />
            </span>
            <span className={styles.logoText}>PromptChain</span>
          </Link>

          <div className={styles.headerStatus}>
            <span className={styles.headerBadge}>Traceable AI Workflow</span>
            <nav className={styles.nav} aria-label="主导航">
              <Link href="/console" className={styles.navLink}>
                Console
              </Link>
              <Link href="/console/workflows" className={styles.navLink}>
                Workflows
              </Link>
              <Link href="/console/runs" className={styles.navLink}>
                Runs
              </Link>
            </nav>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <div className={styles.eyebrowRow}>
              <span className={styles.eyebrow}>[SYSTEM_READY]</span>
              <span className={styles.eyebrowMeta}>Prompt Chain + LangGraph + HITL</span>
            </div>

            <h1 className={styles.heroTitle}>
              把模糊需求
              <span className={styles.heroTitleAccent}>编排成可发布内容</span>
            </h1>

            <p className={styles.heroSubtitle}>
              PromptChain 不是聊天框。它把意图解析、提纲审批、事实核查和最终输出拆成可追踪、
              可确认、可重跑的工作流。
            </p>

            <div className={styles.heroHighlights}>
              <span>版本化产物</span>
              <span>审批门控</span>
              <span>事实核查</span>
              <span>执行追踪</span>
            </div>

            <section className={styles.composer} aria-labelledby="launch-composer-title">
              <div className={styles.composerHeader}>
                <div>
                  <p className={styles.composerLabel}>Launch Composer</p>
                  <h2 id="launch-composer-title" className={styles.composerTitle}>
                    发起一次新的内容工作流
                  </h2>
                </div>
                <span className={styles.composerPill}>
                  <Cable size={14} aria-hidden="true" />
                  live orchestration
                </span>
              </div>

              <textarea
                className={styles.mainTextarea}
                placeholder="描述你要产出的内容、目标读者、口吻和约束条件。&#10;&#10;例如：写一篇关于 AI Agent 技术架构的深度文章，面向技术开发者，2000 字左右，需要包含工程实践与风险说明。"
                value={userInput}
                onChange={(event) => setUserInput(event.target.value)}
                disabled={isLoading}
                aria-label="工作流输入"
              />

              <div className={styles.composerFooter}>
                <div className={styles.inputHints}>
                  {examplePrompts.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className={styles.hintTag}
                      onClick={() => fillExample(prompt)}
                      disabled={isLoading}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>

                <div className={styles.actionArea}>
                  <p className={styles.launchHint} aria-live="polite">
                    {launchHint}
                  </p>
                  <button
                    type="button"
                    className={`btn btn-primary ${styles.launchButton}`}
                    onClick={handleSubmit}
                    disabled={!userInput.trim() || isLoading}
                  >
                    {isLoading ? (
                      <>
                        <span className={styles.buttonProgress} aria-hidden="true" />
                        <Bot size={16} aria-hidden="true" />
                        正在编排
                      </>
                    ) : (
                      <>
                        <Play size={16} aria-hidden="true" />
                        启动工作流
                        <ArrowRight size={16} aria-hidden="true" />
                      </>
                    )}
                  </button>
                </div>
              </div>

              {error ? (
                <div className={styles.errorCard} role="alert">
                  <strong>启动失败</strong>
                  <span>{error}</span>
                </div>
              ) : null}
            </section>
          </div>

          <div className={styles.heroPreview}>
            <HomeWorkflowPreview mode={launchState} workflowId={workflowId} />
          </div>
        </section>

        <section className={styles.capabilityRail} aria-label="工作流链路">
          {workflowChain.map((item) => (
            <div key={item} className={styles.capabilityChip}>
              {item}
            </div>
          ))}
        </section>

        <section className={styles.featuresSection}>
          <div className={styles.sectionHeading}>
            <span className={styles.sectionEyebrow}>Workflow Surface</span>
            <h2>围绕审批、追踪与重跑构建，而不是一次性输出</h2>
            <p>
              每个能力都对应工作流中的一个明确阶段，让内容生成从“提问”升级到“编排”。
            </p>
          </div>

          <div className={styles.featuresGrid}>
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <article key={feature.title} className={styles.featureCard}>
                  <div className={styles.featureIcon}>
                    <Icon size={20} aria-hidden="true" />
                  </div>
                  <span className={styles.featureTag}>{feature.tag}</span>
                  <h3>{feature.title}</h3>
                  <p>{feature.description}</p>
                </article>
              );
            })}
          </div>
        </section>

        <section className={styles.trustSection}>
          <div className={styles.sectionHeading}>
            <span className={styles.sectionEyebrow}>Engineering Trust</span>
            <h2>从首页启动的那一刻起，就进入可观测的工程链路</h2>
            <p>
              首页不是营销页，而是启动台。用户一点击，就能感知到节点、状态和后续审查路径。
            </p>
          </div>

          <div className={styles.trustGrid}>
            {trustSignals.map((signal) => (
              <article key={signal.title} className={styles.trustCard}>
                <span className={styles.trustEyebrow}>{signal.eyebrow}</span>
                <h3>{signal.title}</h3>
                <p>{signal.description}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
