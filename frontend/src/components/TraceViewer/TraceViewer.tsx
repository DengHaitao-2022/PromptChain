'use client';

import React from 'react';
import {
    Play,
    CheckCircle,
    Bot,
    Package,
    User,
    Pause,
    RefreshCcw,
    Hourglass,
    Info,
    ChevronDown,
    ChevronRight,
    AlertTriangle,
} from 'lucide-react';
import styles from './TraceViewer.module.css';
import type { WorkflowGateState, WorkflowTrace, TimelineEvent } from '@/lib/api';
import { formatAppTime } from '@/lib/date-time';
import { MarkdownRenderer } from '@/components/MarkdownRenderer/MarkdownRenderer';

interface TraceViewerProps {
    trace: WorkflowTrace;
    focusedNodeId?: string | null;
    onNodeClick?: (nodeRunId: string) => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asString(value: unknown, fallback = '-'): string {
    return typeof value === 'string' && value.trim() ? value : fallback;
}

function asArray<T = unknown>(value: unknown): T[] {
    return Array.isArray(value) ? (value as T[]) : [];
}

function asNumber(value: unknown): number | null {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function isWorkflowGateState(value: unknown): value is WorkflowGateState {
    if (!isRecord(value)) {
        return false;
    }

    const gateType = value.gate_type;
    return (
        (
            gateType === 'clarification' ||
            gateType === 'outline_approval' ||
            gateType === 'fact_check' ||
            gateType === 'tool_risk_approval'
        ) &&
        (Array.isArray(value.questions) || typeof value.tool_name === 'string')
    );
}

function formatTime(timestamp: unknown): string {
    if (typeof timestamp !== 'string' || !timestamp) {
        return '-';
    }

    return formatAppTime(timestamp, '-');
}

function formatDuration(value: unknown): string {
    const ms = asNumber(value);
    if (ms === null) {
        return '-';
    }
    if (ms < 1000) {
        return `${ms}ms`;
    }
    return `${(ms / 1000).toFixed(2)}s`;
}

type ArtifactPreview = {
    content: string;
    format: 'markdown' | 'json';
};

// 统一抽取产物预览内容，Markdown 交给专用渲染器，结构化对象保留 JSON 视图。
function getArtifactPreview(content: unknown): ArtifactPreview {
    if (typeof content === 'string') {
        return {
            content,
            format: looksLikeJson(content) ? 'json' : 'markdown',
        };
    }

    if (!isRecord(content)) {
        return {
            content: JSON.stringify(content ?? {}, null, 2),
            format: 'json',
        };
    }

    if (typeof content.compiled_content === 'string') {
        return {
            content: content.compiled_content,
            format: 'markdown',
        };
    }

    const textField = getFirstStringField(content, ['content', 'markdown', 'text']);
    if (textField) {
        return {
            content: textField,
            format: looksLikeJson(textField) ? 'json' : 'markdown',
        };
    }

    if (isRecord(content.sections)) {
        return {
            content: Object.entries(content.sections)
                .map(([sectionId, sectionContent]) => {
                    const text = typeof sectionContent === 'string'
                        ? sectionContent
                        : JSON.stringify(sectionContent, null, 2);
                    return `## ${sectionId}\n${text}`;
                })
                .join('\n\n'),
            format: 'markdown',
        };
    }

    return {
        content: JSON.stringify(content, null, 2),
        format: 'json',
    };
}

function getFirstStringField(
    record: Record<string, unknown>,
    fields: string[]
): string | null {
    for (const field of fields) {
        const value = record[field];
        if (typeof value === 'string' && value.trim()) {
            return value;
        }
    }

    return null;
}

function looksLikeJson(value: string): boolean {
    const trimmed = value.trim();
    if (!trimmed) {
        return false;
    }

    return (
        (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
        (trimmed.startsWith('[') && trimmed.endsWith(']'))
    );
}

function getNodeStatusTone(status: string): string {
    switch (status) {
        case 'completed':
            return 'success';
        case 'running':
            return 'info';
        case 'failed':
            return 'danger';
        case 'interrupted':
            return 'warning';
        default:
            return 'info';
    }
}

function getEventIcon(event: string) {
    switch (event) {
        case 'node_started':
            return <Play size={16} />;
        case 'node_completed':
            return <CheckCircle size={16} />;
        case 'llm_call':
            return <Bot size={16} />;
        case 'artifact_created':
            return <Package size={16} />;
        case 'human_decision':
            return <User size={16} />;
        case 'workflow_paused':
            return <Pause size={16} />;
        case 'workflow_resumed':
            return <RefreshCcw size={16} />;
        case 'workflow_gate_waiting':
            return <Hourglass size={16} />;
        default:
            return <Info size={16} />;
    }
}

function getEventDescription(event: TimelineEvent) {
    switch (event.event) {
        case 'node_started':
            return `节点 ${event.node} 开始执行`;
        case 'node_completed':
            return `节点 ${event.node} 执行完成`;
        case 'llm_call':
            return `LLM 调用: ${event.model ?? '-'} (${event.tokens ?? 0} tokens)`;
        case 'artifact_created':
            return `创建产物: ${event.artifact_id?.slice(0, 8) ?? '-'}...`;
        case 'human_decision':
            return `用户决策: ${event.node ?? '-'}`;
        case 'workflow_paused':
            return '工作流已暂停';
        case 'workflow_resumed':
            return '工作流已恢复';
        case 'workflow_gate_waiting':
            return '工作流等待人工介入';
        default:
            return event.event;
    }
}

export function TraceViewer({ trace, focusedNodeId, onNodeClick }: TraceViewerProps) {
    const [expandedNodeId, setExpandedNodeId] = React.useState<string | null>(
        focusedNodeId ?? null
    );
    const gate = isWorkflowGateState(trace.workflow.gate) ? trace.workflow.gate : null;

    React.useEffect(() => {
        if (focusedNodeId) {
            setExpandedNodeId(focusedNodeId);
        }
    }, [focusedNodeId]);

    const getArtifacts = React.useCallback(
        (ids: unknown) =>
            asArray<string>(ids)
                .map((artifactId) => trace.artifacts[artifactId])
                .filter(Boolean),
        [trace.artifacts]
    );

    const handleNodeToggle = (nodeId: string) => {
        setExpandedNodeId((current) => (current === nodeId ? null : nodeId));
        onNodeClick?.(nodeId);
    };

    return (
        <div className={styles.container}>
            <div className={styles.overview}>
                <div className={styles.overviewHeader}>
                    <h3>工作流追踪</h3>
                    <span className={`badge badge-${getNodeStatusTone(asString(trace.workflow.status))}`}>
                        {asString(trace.workflow.status)}
                    </span>
                </div>
                <div className={styles.overviewStats}>
                    <div className={styles.stat}>
                        <span className={styles.statValue}>{trace.nodes.length}</span>
                        <span className={styles.statLabel}>节点</span>
                    </div>
                    <div className={styles.stat}>
                        <span className={styles.statValue}>{Object.keys(trace.artifacts).length}</span>
                        <span className={styles.statLabel}>产物</span>
                    </div>
                    <div className={styles.stat}>
                        <span className={styles.statValue}>{asNumber(trace.workflow.total_tokens) ?? 0}</span>
                        <span className={styles.statLabel}>Tokens</span>
                    </div>
                    <div className={styles.stat}>
                        <span className={styles.statValue}>
                            {formatDuration(trace.workflow.total_duration_ms)}
                        </span>
                        <span className={styles.statLabel}>耗时</span>
                    </div>
                </div>
            </div>

            {gate ? (
                <div className={styles.gatePanel}>
                    <h4 className={styles.sectionTitle}>人工 Gate</h4>
                    <dl className={styles.detailGrid}>
                        <div>
                            <dt>Gate 类型</dt>
                            <dd>{asString(gate.gate_type)}</dd>
                        </div>
                        <div>
                            <dt>打开时间</dt>
                            <dd>{formatTime(gate.opened_at)}</dd>
                        </div>
                        <div>
                            <dt>处理时间</dt>
                            <dd>{formatTime(gate.handled_at)}</dd>
                        </div>
                        <div>
                            <dt>等待耗时</dt>
                            <dd>{formatDuration(gate.waiting_duration_ms)}</dd>
                        </div>
                    </dl>
                </div>
            ) : null}

            <div className={styles.nodesSection}>
                <h4 className={styles.sectionTitle}>执行节点</h4>
                <div className={styles.nodesList}>
                    {trace.nodes.map((node, index) => {
                        const nodeId = asString(node.id, `node-${index}`);
                        const nodeName = asString(node.node_name);
                        const status = asString(node.status, 'pending');
                        const llmCalls = asArray<Record<string, unknown>>(node.llm_calls);
                        const inputArtifacts = getArtifacts(node.input_artifact_ids);
                        const outputArtifacts = getArtifacts(node.output_artifact_ids);
                        const expanded = expandedNodeId === nodeId;

                        return (
                            <article
                                key={nodeId}
                                className={`${styles.nodeCard} ${expanded ? styles.selected : ''}`}
                            >
                                <button
                                    type="button"
                                    className={styles.nodeButton}
                                    onClick={() => handleNodeToggle(nodeId)}
                                    aria-expanded={expanded}
                                >
                                    <span className={styles.nodeIndex}>{index + 1}</span>
                                    <span className={styles.nodeInfo}>
                                        <span className={styles.nodeHeader}>
                                            <span className={styles.nodeName}>{nodeName}</span>
                                            <span className={`badge badge-${getNodeStatusTone(status)}`}>
                                                {status}
                                            </span>
                                        </span>
                                        <span className={styles.nodeMeta}>
                                            <span><Hourglass size={12} className={styles.nodeMetaIcon} /> {formatDuration(node.duration_ms)}</span>
                                            <span><Bot size={12} className={styles.nodeMetaIcon} /> {llmCalls.length} 次调用</span>
                                            <span><Package size={12} className={styles.nodeMetaIcon} /> {outputArtifacts.length} 个产物</span>
                                        </span>
                                    </span>
                                    {expanded ? (
                                        <ChevronDown className={styles.expandIcon} aria-hidden="true" />
                                    ) : (
                                        <ChevronRight className={styles.expandIcon} aria-hidden="true" />
                                    )}
                                </button>

                                {expanded && (
                                    <div className={styles.nodeDetails}>
                                        {typeof node.error_message === 'string' && node.error_message ? (
                                            <div className={styles.errorPanel}>
                                                <AlertTriangle size={16} aria-hidden="true" />
                                                <span>{asString(node.error_message)}</span>
                                            </div>
                                        ) : null}

                                        <dl className={styles.detailGrid}>
                                            <div>
                                                <dt>节点执行开始</dt>
                                                <dd>{formatTime(node.started_at)}</dd>
                                            </div>
                                            <div>
                                                <dt>节点执行结束</dt>
                                                <dd>{formatTime(node.completed_at)}</dd>
                                            </div>
                                            <div>
                                                <dt>输入产物</dt>
                                                <dd>{inputArtifacts.length}</dd>
                                            </div>
                                            <div>
                                                <dt>输出产物</dt>
                                                <dd>{outputArtifacts.length}</dd>
                                            </div>
                                        </dl>

                                        {llmCalls.length > 0 && (
                                            <div className={styles.detailSection}>
                                                <h5>LLM 调用</h5>
                                                <div className={styles.llmList}>
                                                    {llmCalls.map((call, callIndex) => {
                                                        const promptPreview = asString(call.prompt_preview, '');
                                                        const responsePreview = asString(call.response_preview, '');
                                                        return (
                                                            <div key={`${nodeId}-llm-${callIndex}`} className={styles.llmCard}>
                                                                <div className={styles.llmHeader}>
                                                                    <strong>{asString(call.provider)} / {asString(call.model)}</strong>
                                                                    <span>{formatDuration(call.latency_ms)}</span>
                                                                </div>
                                                                {promptPreview ? (
                                                                    <p><strong>Prompt：</strong>{promptPreview}</p>
                                                                ) : null}
                                                                {responsePreview ? (
                                                                    <p><strong>Response：</strong>{responsePreview}</p>
                                                                ) : null}
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}

                                        <ArtifactList title="输入产物" artifacts={inputArtifacts} />
                                        <ArtifactList title="输出产物" artifacts={outputArtifacts} />
                                    </div>
                                )}
                            </article>
                        );
                    })}
                </div>
            </div>

            <div className={styles.timelineSection}>
                <h4 className={styles.sectionTitle}>执行时间线</h4>
                <div className={styles.timeline}>
                    {trace.timeline.map((event, index) => {
                        const timelineArtifact = typeof event.artifact_id === 'string'
                            ? trace.artifacts[event.artifact_id]
                            : undefined;

                        return (
                            <div key={`${event.event}-${event.timestamp}-${index}`} className={styles.timelineItem}>
                                <div className={styles.timelineTime}>{formatTime(event.timestamp)}</div>
                                <div className={styles.timelineDot} />
                                <div className={styles.timelineContent}>
                                    <div className={styles.timelineEventHeader}>
                                        <span className={styles.timelineIcon}>{getEventIcon(event.event)}</span>
                                        <span className={styles.timelineText}>{getEventDescription(event)}</span>
                                    </div>
                                    {/* 时间线产物直接复用 trace 快照，避免为展开预览额外请求接口。 */}
                                    {timelineArtifact ? (
                                        <TimelineArtifactPreview artifact={timelineArtifact} />
                                    ) : null}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

function TimelineArtifactPreview({ artifact }: { artifact: Record<string, unknown> }) {
    return (
        <ArtifactCard artifact={artifact} className={styles.timelineArtifactCard} />
    );
}

function ArtifactList({
    title,
    artifacts,
}: {
    title: string;
    artifacts: Record<string, unknown>[];
}) {
    if (artifacts.length === 0) {
        return null;
    }

    return (
        <div className={styles.detailSection}>
            <h5>{title}</h5>
            <div className={styles.artifactList}>
                {artifacts.map((artifact, index) => {
                    const artifactId = asString(artifact.id, `artifact-${index}`);
                    return (
                        <ArtifactCard key={artifactId} artifact={artifact} className={styles.artifactCard} />
                    );
                })}
            </div>
        </div>
    );
}

function ArtifactCard({
    artifact,
    className,
}: {
    artifact: Record<string, unknown>;
    className: string;
}) {
    const artifactId = asString(artifact.id, 'artifact');
    const preview = getArtifactPreview(artifact.content);

    return (
        <details className={className}>
            <summary>
                <span>{asString(artifact.type, 'artifact')}</span>
                <code>{artifactId.slice(0, 8)}...</code>
                {typeof artifact.version === 'number' && (
                    <small>v{artifact.version}</small>
                )}
            </summary>
            <div className={styles.artifactBody}>
                {preview.format === 'markdown' ? (
                    <MarkdownRenderer content={preview.content} compact />
                ) : (
                    <pre>{preview.content}</pre>
                )}
            </div>
        </details>
    );
}
