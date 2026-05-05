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
import type { WorkflowTrace, TimelineEvent } from '@/lib/api';
import { formatAppTime } from '@/lib/date-time';

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

    // 格式化时间
    const formatTime = (timestamp: string) => {
        return formatAppTime(timestamp);
    };
function formatTime(timestamp: unknown): string {
    if (typeof timestamp !== 'string' || !timestamp) {
        return '-';
    }

    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        return timestamp;
    }

    return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
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

function getArtifactText(content: unknown): string {
    if (typeof content === 'string') {
        return content;
    }

    if (!isRecord(content)) {
        return JSON.stringify(content ?? {}, null, 2);
    }

    if (typeof content.compiled_content === 'string') {
        return content.compiled_content;
    }

    if (typeof content.content === 'string') {
        return content.content;
    }

    if (isRecord(content.sections)) {
        return Object.entries(content.sections)
            .map(([sectionId, sectionContent]) => {
                const text = typeof sectionContent === 'string'
                    ? sectionContent
                    : JSON.stringify(sectionContent, null, 2);
                return `## ${sectionId}\n${text}`;
            })
            .join('\n\n');
    }

    return JSON.stringify(content, null, 2);
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
                                        {node.error_message && (
                                            <div className={styles.errorPanel}>
                                                <AlertTriangle size={16} aria-hidden="true" />
                                                <span>{asString(node.error_message)}</span>
                                            </div>
                                        )}

                                        <dl className={styles.detailGrid}>
                                            <div>
                                                <dt>开始时间</dt>
                                                <dd>{formatTime(node.started_at)}</dd>
                                            </div>
                                            <div>
                                                <dt>完成时间</dt>
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
                                                    {llmCalls.map((call, callIndex) => (
                                                        <div key={`${nodeId}-llm-${callIndex}`} className={styles.llmCard}>
                                                            <div className={styles.llmHeader}>
                                                                <strong>{asString(call.provider)} / {asString(call.model)}</strong>
                                                                <span>{formatDuration(call.latency_ms)}</span>
                                                            </div>
                                                            {call.prompt_preview && (
                                                                <p><strong>Prompt：</strong>{asString(call.prompt_preview)}</p>
                                                            )}
                                                            {call.response_preview && (
                                                                <p><strong>Response：</strong>{asString(call.response_preview)}</p>
                                                            )}
                                                        </div>
                                                    ))}
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
                    {trace.timeline.map((event, index) => (
                        <div key={`${event.event}-${event.timestamp}-${index}`} className={styles.timelineItem}>
                            <div className={styles.timelineTime}>{formatTime(event.timestamp)}</div>
                            <div className={styles.timelineDot} />
                            <div className={styles.timelineContent}>
                                <span className={styles.timelineIcon}>{getEventIcon(event.event)}</span>
                                <span className={styles.timelineText}>{getEventDescription(event)}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
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
                        <details key={artifactId} className={styles.artifactCard}>
                            <summary>
                                <span>{asString(artifact.type, 'artifact')}</span>
                                <code>{artifactId.slice(0, 8)}...</code>
                                {typeof artifact.version === 'number' && (
                                    <small>v{artifact.version}</small>
                                )}
                            </summary>
                            <pre>{getArtifactText(artifact.content)}</pre>
                        </details>
                    );
                })}
            </div>
        </div>
    );
}
