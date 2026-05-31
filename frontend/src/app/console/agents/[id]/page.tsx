'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  GitBranch,
  Pause,
  PlayCircle,
  RotateCcw,
  ShieldAlert,
  Wrench,
  XCircle,
} from 'lucide-react';
import { agentApi } from '@/lib/api';
import type { AgentPlanNode, AgentRunDetail, AgentStep } from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';
import styles from '../agents.module.css';

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
    case 'blocked':
      return '已阻塞';
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

export default function AgentRunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [planDraft, setPlanDraft] = useState('');
  const [clarificationDraft, setClarificationDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');

  function syncDetail(result: AgentRunDetail) {
    setDetail(result);
    setPlanDraft(JSON.stringify(result.plans.at(-1)?.plan_graph ?? {}, null, 2));
  }

  useEffect(() => {
    let active = true;

    async function fetchDetail() {
      try {
        const result = await agentApi.getDetail(runId);
        if (active) {
          syncDetail(result);
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

    void fetchDetail();

    return () => {
      active = false;
    };
  }, [runId]);

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

  const activePlan = detail?.plans.at(-1);
  const finalEval = detail?.eval_results.find((item) => item.target_type === 'final_output');
  const memoryEvidence = detail?.steps.find((step) => step.node_id === 'retrieve_memory')?.output;
  const metrics = useMemo(() => {
    if (!detail) {
      return { stepCount: 0, toolCount: 0, evalCount: 0, replanCount: 0 };
    }
    return {
      stepCount: detail.steps.length,
      toolCount: detail.tool_calls.length,
      evalCount: detail.eval_results.length,
      replanCount: detail.replan_records.length,
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

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <Link href="/console/agents" className={styles.ghostAction}>
            <ArrowLeft size={16} strokeWidth={1.9} />
            返回 Agent 运行台
          </Link>
          <span className={styles.eyebrow}>Agent Run</span>
          <h1 className={styles.title}>{detail.run.goal}</h1>
          <p className={styles.description}>
            创建于 {formatAppDateTime(detail.run.created_at)}，当前计划版本 {activePlan?.version || '-'}。
          </p>
          <div className={styles.headerActions}>
            <span className={`${styles.statusBadge} ${statusClass(detail.run.status)}`}>
              {statusLabel(detail.run.status)}
            </span>
            {['planning', 'paused'].includes(detail.run.status) && (
              <button className={styles.primaryAction} onClick={handleResume} disabled={acting} type="button">
                <PlayCircle size={16} strokeWidth={1.9} />
                继续执行
              </button>
            )}
            {detail.run.status === 'running' && (
              <button className={styles.secondaryAction} onClick={handlePause} disabled={acting} type="button">
                <Pause size={16} strokeWidth={1.9} />
                暂停
              </button>
            )}
            {!['completed', 'failed', 'cancelled'].includes(detail.run.status) && (
              <button className={styles.secondaryAction} onClick={handleCancel} disabled={acting} type="button">
                <XCircle size={16} strokeWidth={1.9} />
                取消运行
              </button>
            )}
          </div>
        </div>

        <aside className={styles.formPanel}>
          <h2 className={styles.panelTitle}>目标卡</h2>
          <div className={styles.chipRow}>
            <span className={styles.chip}>{activePlan?.goal_card.task_type || '未识别类型'}</span>
            {(activePlan?.goal_card.deliverables || []).map((item) => (
              <span key={item} className={styles.chip}>{item}</span>
            ))}
          </div>
          <p className={styles.mutedText}>
            {(activePlan?.goal_card.success_criteria || []).join(' / ') || '等待计划生成'}
          </p>
        </aside>
      </section>

      {error && (
        <div className={styles.errorState}>
          <ShieldAlert size={20} strokeWidth={1.9} />
          <p>{error}</p>
        </div>
      )}

      {detail.run.status === 'awaiting_gate' && detail.run.gate?.gate_type === 'planner_clarification' && (
        <section className={styles.detailCard}>
          <div className={styles.detailHeader}>
            <div>
              <h2 className={styles.detailTitle}>补充目标信息</h2>
              <p className={styles.panelDescription}>{String(detail.run.gate?.reason || 'Planner 需要更多信息。')}</p>
            </div>
            <span className={`${styles.statusBadge} ${styles.statusWaiting}`}>等待补充</span>
          </div>
          <pre className={styles.jsonPreview}>{safeJson(detail.run.gate?.questions)}</pre>
          <textarea
            className={styles.goalInput}
            value={clarificationDraft}
            onChange={(event) => setClarificationDraft(event.target.value)}
            placeholder="补充目标、交付格式、受众、质量标准或限制条件"
            aria-label="补充目标信息"
          />
          <div className={styles.buttonRow}>
            <button className={styles.primaryAction} onClick={handleClarifyGoal} disabled={acting} type="button">
              <CheckCircle2 size={16} strokeWidth={1.9} />
              提交补充并继续规划
            </button>
          </div>
        </section>
      )}

      {detail.run.status === 'awaiting_gate' && detail.run.gate?.gate_type !== 'planner_clarification' && (
        <section className={styles.detailCard}>
          <div className={styles.detailHeader}>
            <div>
              <h2 className={styles.detailTitle}>Gate 审批</h2>
              <p className={styles.panelDescription}>{String(detail.run.gate?.reason || '当前操作需要人工确认。')}</p>
            </div>
            <span className={`${styles.statusBadge} ${styles.statusWaiting}`}>等待确认</span>
          </div>
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

      <section className={styles.metricsGrid}>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>步骤数</span>
          <strong className={styles.metricValue}>{metrics.stepCount}</strong>
        </article>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>工具调用</span>
          <strong className={styles.metricValue}>{metrics.toolCount}</strong>
        </article>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>评估记录</span>
          <strong className={styles.metricValue}>{metrics.evalCount}</strong>
        </article>
        <article className={styles.metricCard}>
          <span className={styles.metricLabel}>重规划</span>
          <strong className={styles.metricValue}>{metrics.replanCount}</strong>
        </article>
      </section>

      <section className={styles.detailGrid}>
        <main className={styles.sectionStack}>
          <section className={styles.detailCard}>
            <div className={styles.detailHeader}>
              <div>
                <h2 className={styles.detailTitle}>动态计划图</h2>
                <p className={styles.panelDescription}>节点依赖、工具、风险等级和实际执行状态在这里对齐。</p>
              </div>
              <GitBranch size={20} strokeWidth={1.9} />
            </div>
            {detail.run.status === 'planning' && (
              <div className={styles.planEditor}>
                <textarea
                  className={styles.goalInput}
                  value={planDraft}
                  onChange={(event) => setPlanDraft(event.target.value)}
                  aria-label="编辑 Plan Graph JSON"
                />
                <div className={styles.buttonRow}>
                  <button className={styles.secondaryAction} onClick={handlePlanUpdate} disabled={acting} type="button">
                    保存计划修改
                  </button>
                </div>
              </div>
            )}
            <div className={styles.nodeList}>
              {(activePlan?.plan_graph.nodes || []).map((node, index) => {
                const step = stepForNode(detail.steps, node);
                const currentStatus = step?.status || node.status;

                return (
                  <article key={node.id} className={styles.nodeItem}>
                    <span className={styles.nodeIndex}>{index + 1}</span>
                    <div className={styles.nodeBody}>
                      <div className={styles.timelineHeader}>
                        <h3 className={styles.nodeTitle}>{node.title}</h3>
                        <span className={`${styles.statusBadge} ${statusClass(currentStatus)}`}>
                          {statusLabel(currentStatus)}
                        </span>
                      </div>
                      <p className={styles.nodeDescription}>{node.description}</p>
                      <div className={styles.chipRow}>
                        <span className={styles.chip}>{node.step_type}</span>
                        {node.tool_name && <span className={styles.chip}>{node.tool_name}</span>}
                        <span className={styles.chip}>风险 {node.risk_level}</span>
                        {node.depends_on.map((dep) => (
                          <span key={dep} className={styles.chip}>依赖 {dep}</span>
                        ))}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className={styles.detailCard}>
            <div className={styles.detailHeader}>
              <div>
                <h2 className={styles.detailTitle}>执行步骤</h2>
                <p className={styles.panelDescription}>每个步骤都保留输入、输出、错误和产物引用。</p>
              </div>
              <Bot size={20} strokeWidth={1.9} />
            </div>
            <div className={styles.timelineList}>
              {detail.steps.map((step) => (
                <article key={step.id} className={styles.timelineItem}>
                  <div className={styles.timelineHeader}>
                    <h3 className={styles.timelineTitle}>{step.title}</h3>
                    <span className={`${styles.statusBadge} ${statusClass(step.status)}`}>
                      {statusLabel(step.status)}
                    </span>
                  </div>
                  <p className={styles.timelineText}>{step.description}</p>
                  <div className={styles.chipRow}>
                    <span className={styles.chip}>{step.step_type}</span>
                    <span className={styles.chip}>{step.node_id}</span>
                    {step.artifact_ids.map((artifactId) => (
                      <span key={artifactId} className={styles.chip}>Artifact {artifactId.slice(0, 8)}</span>
                    ))}
                  </div>
                  <pre className={styles.jsonPreview}>{safeJson(step.output)}</pre>
                </article>
              ))}
            </div>
          </section>
        </main>

        <aside className={styles.sectionStack}>
          <section className={styles.sidePanel}>
            <h2 className={styles.panelTitle}>最终评估</h2>
            {finalEval ? (
              <>
                <strong className={styles.metricValue}>{Math.round(finalEval.score * 100)}%</strong>
                <p className={styles.mutedText}>{finalEval.passed ? '已通过目标完成判断' : '仍有未关闭问题'}</p>
                <pre className={styles.jsonPreview}>{safeJson(finalEval.issues)}</pre>
              </>
            ) : (
              <p className={styles.mutedText}>等待最终评估生成。</p>
            )}
          </section>

          <section className={styles.sidePanel}>
            <h2 className={styles.panelTitle}>证据复用</h2>
            {memoryEvidence ? (
              <>
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
                {memoryEvidence.knowledge_error && (
                  <p className={styles.mutedText}>知识库检索提示：{String(memoryEvidence.knowledge_error)}</p>
                )}
                <pre className={styles.jsonPreview}>
                  {safeJson({
                    knowledge_evidence: memoryEvidence.knowledge_evidence,
                    artifact_evidence: memoryEvidence.artifact_evidence,
                    trace_evidence: memoryEvidence.trace_evidence,
                    tool_evidence: memoryEvidence.tool_evidence,
                  })}
                </pre>
              </>
            ) : (
              <p className={styles.mutedText}>等待记忆与证据检索步骤完成。</p>
            )}
          </section>

          <section className={styles.sidePanel}>
            <h2 className={styles.panelTitle}>工具调用</h2>
            <div className={styles.sectionStack}>
              {detail.tool_calls.map((call) => (
                <article key={call.id} className={styles.toolItem}>
                  <div className={styles.timelineHeader}>
                    <h3 className={styles.timelineTitle}>{call.tool_name}</h3>
                    <span className={`${styles.statusBadge} ${statusClass(call.status)}`}>
                      {statusLabel(call.status)}
                    </span>
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
            </div>
          </section>

          <section className={styles.sidePanel}>
            <h2 className={styles.panelTitle}>重规划历史</h2>
            <div className={styles.sectionStack}>
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
            </div>
          </section>

          <section className={styles.sidePanel}>
            <h2 className={styles.panelTitle}>记忆引用</h2>
            <div className={styles.sectionStack}>
              {detail.memories.length > 0 ? (
                detail.memories.map((memory) => (
                  <article key={memory.id} className={styles.memoryItem}>
                    <span className={styles.chip}>{memory.memory_type}</span>
                    <p className={styles.memoryText}>{memory.content}</p>
                  </article>
                ))
              ) : (
                <p className={styles.mutedText}>暂无可显示的记忆记录。</p>
              )}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
