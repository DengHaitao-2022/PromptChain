'use client';

import { useState, useEffect, useRef } from 'react';
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
  UserPlus,
  Waypoints,
} from 'lucide-react';
import styles from './page.module.css';
import { HomeWorkflowPreview } from '@/components/HomeWorkflowPreview/HomeWorkflowPreview';
import { ThemeSwitcher } from '@/components/ThemeSwitcher/ThemeSwitcher';
import { workflowDefinitionApi, workflowApi, WorkflowDefinition, WorkflowVersion } from '@/lib/api';

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

interface ExamplePrompt {
  icon: LucideIcon;
  title: string;
  description: string;
  prompt: string;
}

const examplePrompts: ExamplePrompt[] = [
  {
    icon: ScrollText,
    title: '技术深度长文',
    description: '适合工程实践、架构分析和风险拆解类内容起稿。',
    prompt: '写一篇关于 AI Agent 技术架构的深度文章，面向技术开发者，2000 字左右',
  },
  {
    icon: GitBranch,
    title: '商业方案提案',
    description: '适合商业计划书、增长策略和竞争壁垒型表达。',
    prompt: '生成一份面向投资人的智能客服 SaaS 商业计划书，突出市场和护城河',
  },
  {
    icon: ShieldCheck,
    title: '高风险科普稿',
    description: '适合需要审慎论证、标注风险和事实约束的主题。',
    prompt: '输出一篇关于量子计算应用边界的科普稿，要求论证严谨并标注高风险事实',
  },
];

const workflowChain = [
  '意图解析',
  '需求澄清',
  '提纲生成',
  '内容生成',
  '自检优化',
  '事实核查',
  '最终交付',
];

const features: FeatureCard[] = [
  {
    icon: ScanSearch,
    title: '智能意图解析',
    description: '自动抽取目标、读者、限制条件和缺失信息，先把需求结构化再进入生成链路。',
    tag: '意图解析',
  },
  {
    icon: ScrollText,
    title: '交互式提纲生成',
    description: '先生成可审批提纲，再把结构确认变成正式的工作流节点，而不是一次性输出。',
    tag: '提纲门控',
  },
  {
    icon: ShieldCheck,
    title: '高风险事实门控',
    description: '把事实核查结果显式暴露给用户，支持确认、采纳建议或人工修正。',
    tag: '事实审批',
  },
  {
    icon: Sparkles,
    title: '自我精炼 (Self-Refine) 优化',
    description: '生成、反馈、精炼形成闭环，让内容质量提升成为可重复的流程步骤。',
    tag: '优化闭环',
  },
  {
    icon: GitBranch,
    title: '版本化重跑',
    description: '每一次产物都保持可追溯版本，并允许从指定节点重跑，而不是整体重来。',
    tag: '支持重跑',
  },
  {
    icon: Radar,
    title: 'Trace 可视化',
    description: '完整记录节点输入、输出、耗时与决策，让 AI 工作流具备工程化可观测性。',
    tag: '执行追踪',
  },
];

const trustSignals: TrustSignal[] = [
  {
    eyebrow: '[审批门控]',
    title: '关键节点留给人确认',
    description: '提纲审批和高风险事实确认都被建模为门控节点，不把不确定决策藏进黑盒。',
  },
  {
    eyebrow: '[产物历史]',
    title: '产物版本写一次，永久可追',
    description: '生成内容、核查报告和节点输出都按版本保留，支持回看与重跑。',
  },
  {
    eyebrow: '[追踪可见]',
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
  const pageRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [userInput, setUserInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [workflowRunId, setWorkflowRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSuggestionPanelOpen, setIsSuggestionPanelOpen] = useState(false);
  const [activePromptIndex, setActivePromptIndex] = useState(0);
  const [errorTitle, setErrorTitle] = useState<string>('错误');
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>('');
  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [publishedCompatibilityMessage, setPublishedCompatibilityMessage] = useState<string | null>(null);

  const railRef = useRef<HTMLElement | null>(null);
  const featuresRef = useRef<HTMLElement | null>(null);
  const trustRef = useRef<HTMLElement | null>(null);
  const [revealed, setRevealed] = useState({ rail: false, features: false, trust: false });

  // 主盒体的指针高光只对精确指针设备启用，避免在触屏上依赖 hover。
  useEffect(() => {
    const root = pageRef.current;
    if (!root) {
      return;
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const supportsFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

    if (prefersReducedMotion || !supportsFinePointer) {
      return;
    }

    const panels = Array.from(root.querySelectorAll<HTMLElement>('[data-pointer-glow]'));
    const cleanups = panels.map((panel) => {
      panel.style.setProperty('--pointer-x', '50%');
      panel.style.setProperty('--pointer-y', '50%');
      panel.style.setProperty('--pointer-active', '0');

      let frame = 0;

      const updatePointer = (event: PointerEvent) => {
        const bounds = panel.getBoundingClientRect();
        const x = ((event.clientX - bounds.left) / bounds.width) * 100;
        const y = ((event.clientY - bounds.top) / bounds.height) * 100;

        cancelAnimationFrame(frame);
        frame = window.requestAnimationFrame(() => {
          panel.style.setProperty('--pointer-x', `${Math.max(0, Math.min(100, x))}%`);
          panel.style.setProperty('--pointer-y', `${Math.max(0, Math.min(100, y))}%`);
          panel.style.setProperty('--pointer-active', '1');
        });
      };

      const resetPointer = () => {
        cancelAnimationFrame(frame);
        frame = window.requestAnimationFrame(() => {
          panel.style.setProperty('--pointer-active', '0');
        });
      };

      panel.addEventListener('pointerenter', updatePointer);
      panel.addEventListener('pointermove', updatePointer);
      panel.addEventListener('pointerleave', resetPointer);

      return () => {
        cancelAnimationFrame(frame);
        panel.removeEventListener('pointerenter', updatePointer);
        panel.removeEventListener('pointermove', updatePointer);
        panel.removeEventListener('pointerleave', resetPointer);
      };
    });

    return () => {
      cleanups.forEach((cleanup) => cleanup());
    };
  }, []);

  // Scroll Reveal Logic
  useEffect(() => {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion || !('IntersectionObserver' in window)) {
      setRevealed({ rail: true, features: true, trust: true });
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const section = entry.target.getAttribute('data-section') as keyof typeof revealed;
            if (section) {
              setRevealed((prev) => ({ ...prev, [section]: true }));
              observer.unobserve(entry.target);
            }
          }
        });
      },
      { threshold: 0.1 }
    );

    const sections = [
      { ref: railRef, id: 'rail' },
      { ref: featuresRef, id: 'features' },
      { ref: trustRef, id: 'trust' },
    ];

    sections.forEach(({ ref, id }) => {
      if (ref.current) {
        ref.current.setAttribute('data-section', id);
        observer.observe(ref.current);
      }
    });

    return () => observer.disconnect();
  }, []);

  // Data Fetching
  useEffect(() => {
    const fetchWorkflows = async () => {
      try {
        setError(null);
        const response = await workflowDefinitionApi.listPublic();
        const workflowData = response.workflows || [];

        const hasPublished = workflowData.some((w: WorkflowDefinition) => 'is_published' in w);
        const displayableWorkflows = hasPublished
          ? workflowData.filter((w: WorkflowDefinition) => w.is_published)
          : workflowData;

        if (!hasPublished) {
          setPublishedCompatibilityMessage('当前接口未显式暴露发布态，因此展示版本候选，需手动选择版本。');
        } else {
          setPublishedCompatibilityMessage(null);
        }

        setWorkflows(displayableWorkflows);
        if (displayableWorkflows.length > 0) {
          setSelectedWorkflow(displayableWorkflows[0].id);
        }
      } catch (err) {
        setErrorTitle('加载工作流失败');
        setError(err instanceof Error ? err.message : '未知错误');
      }
    };
    fetchWorkflows();
  }, []);

  useEffect(() => {
    if (!selectedWorkflow) {
      setVersions([]);
      setSelectedVersion('');
      return;
    }

    setVersions([]);
    setSelectedVersion('');

    const fetchVersions = async () => {
      try {
        setError(null);
        const response = await workflowDefinitionApi.getPublicVersions(selectedWorkflow);
        const versionData = response.versions || [];
        setVersions(versionData);
        if (versionData.length > 0) {
          setSelectedVersion(versionData[0].id);
        } else {
          setSelectedVersion('');
        }
      } catch (err) {
        setErrorTitle('加载版本失败');
        setError(err instanceof Error ? err.message : '未知错误');
      }
    };
    fetchVersions();
  }, [selectedWorkflow]);

  useEffect(() => {
    if (!isSuggestionPanelOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }

      if (composerRef.current?.contains(target)) {
        return;
      }

      setIsSuggestionPanelOpen(false);
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [isSuggestionPanelOpen]);

  const handleSubmit = async () => {
    if (!userInput.trim() || !selectedWorkflow || !selectedVersion || isLoading) return;

    setIsLoading(true);
    setError(null);
    setLaunchState('launching');

    try {
      const result = await workflowApi.start(userInput.trim(), selectedWorkflow, selectedVersion);

      setWorkflowRunId(result.workflow_run_id);
      setLaunchState('handoff');
      await sleep(280);
      router.push(`/workflow/${result.workflow_run_id}`);
    } catch (err) {
      setLaunchState('idle');
      setWorkflowRunId(null);
      setErrorTitle('启动工作流失败');
      setError(err instanceof Error ? err.message : '未知错误');
    } finally {
      setIsLoading(false);
    }
  };

  const fillExample = (example: ExamplePrompt) => {
    setUserInput(example.prompt);
    setError(null);
    setIsSuggestionPanelOpen(false);
    setActivePromptIndex(0);

    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      const length = example.prompt.length;
      textareaRef.current?.setSelectionRange(length, length);
    });
  };

  const isSuggestionPanelVisible = isSuggestionPanelOpen && !isLoading && !userInput.trim();

  const handleTextareaFocus = () => {
    if (isLoading) {
      return;
    }

    setIsSuggestionPanelOpen(true);
    setActivePromptIndex(0);
  };

  const handleTextareaKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!isSuggestionPanelVisible || event.nativeEvent.isComposing) {
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActivePromptIndex((current) => (current + 1) % examplePrompts.length);
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActivePromptIndex((current) => (current - 1 + examplePrompts.length) % examplePrompts.length);
      return;
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      fillExample(examplePrompts[activePromptIndex]);
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      setIsSuggestionPanelOpen(false);
    }
  };

  const isLaunchDisabled = !userInput.trim() || isLoading || workflows.length === 0 || versions.length === 0;

  let currentLaunchHint = launchState === 'launching'
    ? '正在依次编排意图解析、提纲生成与事实核查节点。'
    : launchState === 'handoff'
      ? `工作流 ${workflowRunId?.slice(0, 8) ?? '准备中'} 已建立，准备进入详情页。`
      : '点击后会先完成首页启动反馈，再跳转到工作流详情。';

  if (workflows.length === 0) {
    currentLaunchHint = '没有可用的工作流，请联系管理员配置。';
  } else if (versions.length === 0) {
    currentLaunchHint = '当前工作流没有可用版本，请联系管理员配置。';
  }

  return (
    <div ref={pageRef} className={styles.page} data-launch-state={launchState}>
      <div className={styles.backgroundCanvas} aria-hidden="true">
        <svg className={styles.backgroundSvg} viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
          <defs>
            <linearGradient id="home-fluid-a" x1="112" y1="744" x2="1080" y2="120" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="var(--page-fluid-a-deep)" />
              <stop offset="0.48" stopColor="var(--page-fluid-a-mid)" />
              <stop offset="1" stopColor="var(--page-fluid-a-light)" />
            </linearGradient>
            <linearGradient id="home-fluid-b" x1="604" y1="24" x2="1380" y2="660" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="var(--page-fluid-b-light)" />
              <stop offset="0.44" stopColor="var(--page-fluid-b-mid)" />
              <stop offset="1" stopColor="var(--page-fluid-b-deep)" />
            </linearGradient>
            <radialGradient id="home-fluid-c" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(1158 236) rotate(134.842) scale(544.44 392.65)">
              <stop offset="0" stopColor="var(--page-fluid-c-core)" />
              <stop offset="0.54" stopColor="var(--page-fluid-c-mid)" />
              <stop offset="1" stopColor="var(--page-fluid-c-fade)" />
            </radialGradient>
            <linearGradient id="home-rim-primary" x1="430" y1="310" x2="1000" y2="278" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="transparent" />
              <stop offset="0.5" stopColor="var(--page-fluid-rim)" />
              <stop offset="1" stopColor="transparent" />
            </linearGradient>
            <linearGradient id="home-rim-secondary" x1="868" y1="282" x2="1320" y2="428" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="transparent" />
              <stop offset="0.48" stopColor="var(--page-fluid-rim-alt)" />
              <stop offset="1" stopColor="transparent" />
            </linearGradient>
            <linearGradient id="home-shadow-plane" x1="164" y1="702" x2="1262" y2="510" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="var(--page-fluid-shadow)" stopOpacity="0.68" />
              <stop offset="0.56" stopColor="var(--page-fluid-shadow)" stopOpacity="0.18" />
              <stop offset="1" stopColor="transparent" />
            </linearGradient>
            <filter id="home-depth-shadow" x="-12%" y="-12%" width="124%" height="124%">
              <feDropShadow dx="0" dy="36" stdDeviation="32" floodColor="var(--page-fluid-shadow)" floodOpacity="0.36" />
            </filter>
            <filter id="home-soft-shadow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="20" stdDeviation="22" floodColor="var(--page-fluid-shadow)" floodOpacity="0.22" />
            </filter>
          </defs>

          <path
            d="M-184 758C22 660 206 598 346 542C524 470 640 432 782 420C958 404 1132 430 1476 548V940H-184V758Z"
            fill="url(#home-shadow-plane)"
            filter="url(#home-depth-shadow)"
            opacity="0.76"
          />
          <path
            d="M-184 736C-38 594 104 502 270 456C466 402 646 450 822 382C1008 310 1178 166 1476 52V602C1302 690 1138 736 972 748C782 760 608 710 430 702C224 692 44 724 -184 836V736Z"
            fill="url(#home-fluid-a)"
            filter="url(#home-soft-shadow)"
          />
          <path
            d="M430 -110C598 -60 722 18 832 126C930 222 1048 278 1180 318C1294 352 1388 374 1476 438V-110H430Z"
            fill="url(#home-fluid-b)"
            filter="url(#home-soft-shadow)"
            opacity="0.94"
          />
          <path
            d="M720 104C862 154 980 228 1080 316C1150 378 1248 446 1476 564V96C1378 116 1292 144 1194 204C1070 280 950 286 868 248C808 220 772 174 720 104Z"
            fill="url(#home-fluid-c)"
            opacity="0.92"
          />
          <path
            d="M346 394C488 332 626 330 768 316C888 304 972 258 1098 188"
            fill="none"
            stroke="url(#home-rim-primary)"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <path
            d="M856 252C986 274 1082 326 1186 360C1270 388 1350 404 1476 442"
            fill="none"
            stroke="url(#home-rim-secondary)"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
      </div>

      <div className={styles.backgroundMotion} aria-hidden="true">
        <span className={styles.backgroundOrbPrimary} />
        <span className={styles.backgroundOrbSecondary} />
        <span className={styles.backgroundBeam} />
      </div>

      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.logo}>
            <span className={styles.logoIcon}>
              <Waypoints size={18} aria-hidden="true" />
            </span>
            <span className={styles.logoText}>PromptChain</span>
          </Link>

          <div className={styles.headerStatus}>
            <span className={styles.headerBadge}>可追溯 AI 工作流</span>
            <nav className={styles.nav} aria-label="主导航">
              <Link href="/console" className={styles.navLink}>
                控制台
              </Link>
              <Link href="/console/workflows" className={styles.navLink}>
                工作流管理
              </Link>
              <Link href="/console/runs" className={styles.navLink}>
                运行历史
              </Link>
            </nav>
            <div className={styles.headerActions}>
              <ThemeSwitcher className={styles.headerTheme} showStatus={false} compact />
              <Link href="/register" className={styles.registerButton}>
                <UserPlus size={15} aria-hidden="true" />
                注册
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <div className={styles.eyebrowRow}>
              <span className={styles.eyebrow}>[系统就绪]</span>
              <span className={styles.eyebrowMeta}>Prompt Chain + LangGraph + HITL</span>
            </div>

            <h1 className={styles.heroTitle}>
              让灵感进入
              <span className={styles.heroTitleAccent}>可追踪的 AI 生产线</span>
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

            <section
              className={styles.composer}
              ref={composerRef}
              data-pointer-glow
              aria-labelledby="launch-composer-title"
            >
              <span className={styles.panelStandbyBorder} aria-hidden="true" />
              <span className={styles.panelPointerGlow} aria-hidden="true" />
              <div className={styles.composerInner}>
                <div className={styles.composerHeader}>
                  <div>
                    <p className={styles.composerLabel}>启动编辑器</p>
                    <h2 id="launch-composer-title" className={styles.composerTitle}>
                      发起一次新的内容工作流
                    </h2>
                  </div>
                  <span className={styles.composerPill}>
                    <Cable size={14} aria-hidden="true" />
                    实时编排中
                  </span>
                </div>

                <textarea
                  ref={textareaRef}
                  className={styles.mainTextarea}
                  placeholder="描述你要产出的内容、目标读者、口吻和约束条件。&#10;&#10;例如：写一篇关于 AI Agent 技术架构的深度文章，面向技术开发者，2000 字左右，需要包含工程实践与风险说明。"
                  value={userInput}
                  onChange={(event) => setUserInput(event.target.value)}
                  onFocus={handleTextareaFocus}
                  onKeyDown={handleTextareaKeyDown}
                  disabled={isLoading}
                  aria-label="工作流输入"
                />

                <div className={styles.composerFooter}>
                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <div className={styles.selectWrapper} style={{ flex: '1 1 200px' }}>
                      <label htmlFor="workflow-select" className={styles.selectLabel}>工作流</label>
                      <select
                        id="workflow-select"
                        className={styles.customSelect}
                        value={selectedWorkflow}
                        onChange={(e) => setSelectedWorkflow(e.target.value)}
                        disabled={isLoading || workflows.length === 0}
                      >
                        {workflows.length === 0 ? (
                          <option value="">没有可用工作流</option>
                        ) : (
                          workflows.map((workflow) => (
                            <option key={workflow.id} value={workflow.id}>
                              {workflow.name}
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                    <div className={styles.selectWrapper} style={{ flex: '1 1 200px' }}>
                      <label htmlFor="version-select" className={styles.selectLabel}>版本</label>
                      <select
                        id="version-select"
                        className={styles.customSelect}
                        value={selectedVersion}
                        onChange={(e) => setSelectedVersion(e.target.value)}
                        disabled={isLoading || versions.length === 0}
                      >
                        {versions.length === 0 ? (
                          <option value="">没有可用版本</option>
                        ) : (
                          versions.map((version) => (
                            <option key={version.id} value={version.id}>
                              版本 {version.version} ({version.change_log || '无更新说明'})
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                  </div>

                  {publishedCompatibilityMessage && (
                    <div className={styles.compatibilityNote}>
                      {publishedCompatibilityMessage}
                    </div>
                  )}

                  {isSuggestionPanelVisible ? (
                    <div className={styles.inputHints} role="region" aria-label="快捷提示模板">
                      <div className={styles.inputHintsHeader}>
                        <div>
                          <p className={styles.inputHintsLabel}>快速起稿</p>
                          <p className={styles.inputHintsTitle}>从一个成熟模板开始，再继续细化目标、约束和口吻。</p>
                        </div>
                        <span className={styles.inputHintsMeta}>↑↓ 选择 · Enter 填充</span>
                      </div>

                      <div className={styles.inputHintGrid}>
                        {examplePrompts.map((prompt, index) => {
                          const Icon = prompt.icon;
                          const isActive = index === activePromptIndex;

                          return (
                            <button
                              key={prompt.title}
                              type="button"
                              className={`${styles.hintTag} ${isActive ? styles.hintTagActive : ''}`}
                              onClick={() => fillExample(prompt)}
                              onMouseEnter={() => setActivePromptIndex(index)}
                              disabled={isLoading}
                            >
                              <span className={styles.hintTagIcon}>
                                <Icon size={16} aria-hidden="true" />
                              </span>
                              <span className={styles.hintTagCopy}>
                                <strong>{prompt.title}</strong>
                                <span>{prompt.description}</span>
                              </span>
                              <span className={styles.hintTagShortcut}>
                                {isActive ? '回车填充' : '示例模板'}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  <div className={styles.actionArea}>
                    <p className={styles.launchHint} aria-live="polite">
                      {currentLaunchHint}
                    </p>
                    <button
                      type="button"
                      className={`btn btn-primary ${styles.launchButton}`}
                      onClick={handleSubmit}
                      disabled={isLaunchDisabled}
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
                    <strong>{errorTitle}</strong>
                    <span>{error}</span>
                  </div>
                ) : null}
              </div>
            </section>
          </div>

          <div className={styles.heroPreview} data-pointer-glow>
            <span className={styles.panelStandbyBorder} aria-hidden="true" />
            <span className={styles.panelPointerGlow} aria-hidden="true" />
            <HomeWorkflowPreview mode={launchState} workflowId={workflowRunId} />
          </div>
        </section>

        <section
          ref={railRef}
          className={`${styles.capabilityRail} ${revealed.rail ? styles.revealed : styles.revealSection}`}
          aria-label="工作流链路"
        >
          {workflowChain.map((item) => (
            <div key={item} className={styles.capabilityChip}>
              {item}
            </div>
          ))}
        </section>

        <section
          ref={featuresRef}
          className={`${styles.featuresSection} ${revealed.features ? styles.revealed : styles.revealSection}`}
        >
          <div className={styles.sectionHeading}>
            <span className={styles.sectionEyebrow}>工作流界面</span>
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

        <section
          ref={trustRef}
          className={`${styles.trustSection} ${revealed.trust ? styles.revealed : styles.revealSection}`}
        >
          <div className={styles.sectionHeading}>
            <span className={styles.sectionEyebrow}>工程化信任</span>
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
