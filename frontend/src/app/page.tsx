'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';
import { workflowApi, type WorkflowResponse } from '@/lib/api';

// 功能特性数据
const features = [
  {
    icon: '🎯',
    title: '智能意图解析',
    description: '自动分析用户需求，生成结构化意图卡，识别缺失信息并主动澄清',
  },
  {
    icon: '📋',
    title: '交互式提纲生成',
    description: '基于意图卡生成可编辑提纲，支持人机交互确认和实时调整',
  },
  {
    icon: '✅',
    title: 'CoVe 事实核查',
    description: '四步验证链自动提取并核查事实声明，标注高风险项',
  },
  {
    icon: '✍️',
    title: 'Self-Refine 优化',
    description: '生成→反馈→精炼循环，自动优化内容质量直到达标',
  },
  {
    icon: '🔄',
    title: '版本化追溯',
    description: '每个产物都有完整版本历史，支持任意节点重跑',
  },
  {
    icon: '📊',
    title: 'Trace 可视化',
    description: '完整的执行时间线，可视化展示每个节点的输入输出',
  },
];

// 示例提示
const examplePrompts = [
  '写一篇关于 AI Agent 技术架构的深度文章',
  '科普文：量子计算的原理与应用',
  '商业计划书：智能客服 SaaS 平台',
];

export default function Home() {
  const router = useRouter();
  const [userInput, setUserInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 启动工作流
  const handleSubmit = async () => {
    if (!userInput.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await workflowApi.start(userInput);
      setWorkflow(response);
      // 跳转到工作流详情页
      router.push(`/workflow/${response.workflow_run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '工作流启动失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 填充示例
  const fillExample = (example: string) => {
    setUserInput(example);
  };

  return (
    <div className={styles.page}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <a href="/" className={styles.logo}>
            <span className={styles.logoIcon}>⚡</span>
            PromptChain
          </a>
          <nav className={styles.nav}>
            <a href="/workflows" className={styles.navLink}>工作流</a>
            <a href="/traces" className={styles.navLink}>追踪</a>
            <a href="/docs" className={styles.navLink}>文档</a>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className={styles.hero}>
        <h1>AI 驱动的内容生成平台</h1>
        <p className={styles.heroSubtitle}>
          基于 Prompt Chain 的全流程自动化写作系统<br />
          意图解析 → 提纲生成 → 事实核查 → 内容优化
        </p>
      </section>

      {/* Input Section */}
      <section className={styles.inputSection}>
        <div className={styles.inputContainer}>
          <textarea
            className={styles.mainTextarea}
            placeholder="描述你想要创作的内容...&#10;&#10;例如：写一篇关于 AI Agent 技术架构的深度文章，面向技术开发者，2000字左右"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            disabled={isLoading}
          />
          <div className={styles.inputActions}>
            <div className={styles.inputHints}>
              {examplePrompts.map((prompt, index) => (
                <span
                  key={index}
                  className={styles.hintTag}
                  onClick={() => fillExample(prompt)}
                >
                  {prompt.slice(0, 20)}...
                </span>
              ))}
            </div>
            <button
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={!userInput.trim() || isLoading}
            >
              {isLoading ? (
                <>
                  <span className="spinner" style={{ width: 16, height: 16 }} />
                  生成中...
                </>
              ) : (
                '开始生成'
              )}
            </button>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="card mt-md" style={{ borderColor: 'var(--color-danger)' }}>
            <p style={{ color: 'var(--color-danger)', margin: 0 }}>
              ❌ {error}
            </p>
          </div>
        )}

        {/* Workflow Status */}
        {workflow && (
          <div className={styles.workflowContainer}>
            <div className={styles.workflowStatus}>
              <span
                className={`${styles.statusIndicator} ${workflow.status === 'completed'
                  ? styles.completed
                  : workflow.status.includes('awaiting')
                    ? styles.waiting
                    : styles.running
                  }`}
              />
              <span>
                工作流 ID: <code>{workflow.workflow_run_id}</code>
              </span>
              <span className={`badge badge-${workflow.status === 'completed' ? 'success' :
                workflow.status.includes('awaiting') ? 'warning' : 'info'
                }`}>
                {workflow.status === 'completed' && '已完成'}
                {workflow.status === 'running' && '运行中'}
                {workflow.status === 'needs_clarification' && '需要澄清'}
                {workflow.status === 'awaiting_outline_approval' && '等待提纲审批'}
                {workflow.status === 'awaiting_fact_check_approval' && '等待事实核查确认'}
              </span>
            </div>

            {/* Workflow steps will be rendered based on status */}
            <div className={styles.workflowSteps}>
              <div className={`${styles.workflowStep} ${styles.completed}`}>
                <span className={`${styles.stepNumber} ${styles.completed}`}>✓</span>
                <div className={styles.stepContent}>
                  <h4>意图解析</h4>
                  <p>已生成结构化意图卡</p>
                </div>
              </div>
              <div className={`${styles.workflowStep} ${styles.active}`}>
                <span className={`${styles.stepNumber} ${styles.active}`}>2</span>
                <div className={styles.stepContent}>
                  <h4>提纲生成</h4>
                  <p>正在生成文章提纲...</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Features */}
      {!workflow && (
        <section className={styles.features}>
          <div className={styles.featuresGrid}>
            {features.map((feature, index) => (
              <div key={index} className={styles.featureCard}>
                <div className={styles.featureIcon}>{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
