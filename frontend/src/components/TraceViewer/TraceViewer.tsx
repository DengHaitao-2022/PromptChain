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
} from 'lucide-react';
import styles from './TraceViewer.module.css';
import type { WorkflowTrace, TimelineEvent } from '@/lib/api';
import { formatAppTime } from '@/lib/date-time';

interface TraceViewerProps {
    trace: WorkflowTrace;
    onNodeClick?: (nodeRunId: string) => void;
}

export function TraceViewer({ trace, onNodeClick }: TraceViewerProps) {
    const [selectedNode, setSelectedNode] = React.useState<string | null>(null);

    // 格式化时间
    const formatTime = (timestamp: string) => {
        return formatAppTime(timestamp);
    };

    // 格式化持续时间
    const formatDuration = (ms: number) => {
        if (ms < 1000) return `${ms}ms`;
        return `${(ms / 1000).toFixed(2)}s`;
    };

    // 事件图标
    const getEventIcon = (event: string) => {
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
    };

    // 事件描述
    const getEventDescription = (event: TimelineEvent) => {
        switch (event.event) {
            case 'node_started':
                return `节点 ${event.node} 开始执行`;
            case 'node_completed':
                return `节点 ${event.node} 执行完成`;
            case 'llm_call':
                return `LLM 调用: ${event.model} (${event.tokens} tokens)`;
            case 'artifact_created':
                return `创建产物: ${event.artifact_id?.slice(0, 8)}...`;
            case 'human_decision':
                return `用户决策: ${event.node}`;
            case 'workflow_paused':
                return `工作流已暂停`;
            case 'workflow_resumed':
                return `工作流已恢复`;
            case 'workflow_gate_waiting':
                return `工作流等待人工介入`;
            default:
                return event.event;
        }
    };

    // 节点状态颜色
    const getNodeStatusColor = (status: string) => {
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
    };

    return (
        <div className={styles.container}>
            {/* 工作流概览 */}
            <div className={styles.overview}>
                <div className={styles.overviewHeader}>
                    <h3>工作流追踪</h3>
                    <span className={`badge badge-${getNodeStatusColor(trace.workflow.status as string)}`}>
                        {trace.workflow.status as string}
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
                        <span className={styles.statValue}>{trace.workflow.total_tokens as number}</span>
                        <span className={styles.statLabel}>Tokens</span>
                    </div>
                    <div className={styles.stat}>
                        <span className={styles.statValue}>
                            {formatDuration(trace.workflow.total_duration_ms as number)}
                        </span>
                        <span className={styles.statLabel}>耗时</span>
                    </div>
                </div>
            </div>

            {/* 节点列表 */}
            <div className={styles.nodesSection}>
                <h4 className={styles.sectionTitle}>执行节点</h4>
                <div className={styles.nodesList}>
                    {trace.nodes.map((node, index) => (
                        <div
                            key={node.id as string}
                            className={`${styles.nodeCard} ${selectedNode === node.id ? styles.selected : ''
                                }`}
                            onClick={() => {
                                setSelectedNode(node.id as string);
                                onNodeClick?.(node.id as string);
                            }}
                        >
                            <div className={styles.nodeIndex}>{index + 1}</div>
                            <div className={styles.nodeInfo}>
                                <div className={styles.nodeHeader}>
                                    <span className={styles.nodeName}>{node.node_name as string}</span>
                                    <span className={`badge badge-${getNodeStatusColor(node.status as string)}`}>
                                        {node.status as string}
                                    </span>
                                </div>
                                <div className={styles.nodeMeta}>
                                    <span><Hourglass size={12} className={styles.nodeMetaIcon} /> {formatDuration(node.duration_ms as number)}</span>
                                    <span><Bot size={12} className={styles.nodeMetaIcon} /> {(node.llm_calls as unknown[]).length} 次调用</span>
                                    <span><Package size={12} className={styles.nodeMetaIcon} /> {(node.output_artifact_ids as string[]).length} 个产物</span>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* 时间线 */}
            <div className={styles.timelineSection}>
                <h4 className={styles.sectionTitle}>执行时间线</h4>
                <div className={styles.timeline}>
                    {trace.timeline.map((event, index) => (
                        <div key={index} className={styles.timelineItem}>
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
