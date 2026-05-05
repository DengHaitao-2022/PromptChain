'use client';

import React from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    Activity,
    AlertTriangle,
    ArrowLeft,
    Braces,
    CheckCheck,
    CheckCircle2,
    Clock3,
    FileText,
    ListChecks,
    LoaderCircle,
    MessageSquareQuote,
    ShieldAlert,
    Sparkles,
    Pause,
    Play,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import styles from './page.module.css';
import {
    workflowApi,
    traceApi,
    type WorkflowResponse,
    type Outline,
    type FactCheckReport,
    type WorkflowTrace,
    type WorkflowStatus,
    type WorkflowEventSnapshot,
} from '@/lib/api';
import {
    OutlineEditor,
    FactCheckViewer,
    ClarificationDialog,
    WorkflowProgress,
    IntentCardViewer,
    ContentViewer,
    TraceViewer,
    type WorkflowStep,
} from '@/components';

type StageTone = 'brand' | 'success' | 'warning' | 'danger' | 'muted';

interface StageMetric {
    label: string;
    value: string;
    tone?: Exclude<StageTone, 'muted'>;
}

interface StatusMeta {
    eyebrow: string;
    label: string;
    title: string;
    description: string;
    tone: StageTone;
    icon: LucideIcon;
}

interface FinalContentEntry {
    key: string;
    preview: string;
    wordCount?: number;
    raw: unknown;
}

interface ContentSection {
    id: string;
    title: string;
    content: string;
    wordCount: number;
}

function getStatusMeta(status?: WorkflowStatus): StatusMeta {
    switch (status) {
        case 'needs_clarification':
            return {
                eyebrow: '待补充',
                label: '等待澄清',
                title: '补全需求上下文',
                description: '模型在继续生成前需要你补充关键上下文，以减少误判和无效扩写。',
                tone: 'warning',
                icon: MessageSquareQuote,
            };
        case 'awaiting_outline_approval':
            return {
                eyebrow: '提纲审阅',
                label: '等待提纲审批',
                title: '审阅生成提纲',
                description: '检查结构、章节重点和篇幅分配，确认后工作流会继续进入正文生成。',
                tone: 'brand',
                icon: ListChecks,
            };
        case 'awaiting_fact_check_approval':
            return {
                eyebrow: '风险处理',
                label: '等待事实核查审批',
                title: '处理高风险声明',
                description: '优先确认高风险 claim 的去留和修正策略，再提交最终审阅决定。',
                tone: 'warning',
                icon: ShieldAlert,
            };
        case 'completed':
            return {
                eyebrow: '交付就绪',
                label: '生成完成',
                title: '交付结果已准备好',
                description: '内容已完成生成与审阅，你可以先阅读结果，再决定是否回看原始数据。',
                tone: 'success',
                icon: CheckCircle2,
            };
        case 'failed':
            return {
                eyebrow: '执行失败',
                label: '执行失败',
                title: '工作流未能完成',
                description: '当前执行已中断。请先检查错误信息，再决定是否重新发起或返回首页。',
                tone: 'danger',
                icon: AlertTriangle,
            };
        case 'paused':
            return {
                eyebrow: '已暂停',
                label: '已暂停',
                title: '工作流已手动暂停',
                description: '工作流当前处于暂停状态。你可以选择恢复执行，或根据需要进行操作。',
                tone: 'muted',
                icon: Pause,
            };
        default: // running, or any other state
            return {
                eyebrow: '推进中',
                label: '执行中',
                title: '工作流正在推进',
                description: '系统会自动推进节点；一旦出现需要人工介入的步骤，页面会切换到对应审阅态。',
                tone: 'brand',
                icon: Activity,
            };
    }
}

function formatCount(value: number | undefined): string {
    return typeof value === 'number' ? value.toString() : '-';
}

function normalizeFinalContentEntries(
    finalContent: Record<string, unknown> | undefined
): FinalContentEntry[] {
    if (!finalContent) {
        return [];
    }

    return Object.entries(finalContent).map(([key, value]) => {
        if (typeof value === 'string') {
            return {
                key,
                preview: value,
                raw: value,
            };
        }

        if (value && typeof value === 'object') {
            const preview =
                typeof (value as { preview?: unknown }).preview === 'string'
                    ? ((value as { preview: string }).preview)
                    : JSON.stringify(value, null, 2);
            const wordCount =
                typeof (value as { word_count?: unknown }).word_count === 'number'
                    ? ((value as { word_count: number }).word_count)
                    : undefined;

            return {
                key,
                preview,
                wordCount,
                raw: value,
            };
        }

        return {
            key,
            preview: String(value ?? ''),
            raw: value,
        };
    });
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asStringArray(value: unknown): string[] {
    return Array.isArray(value)
        ? value.filter((item): item is string => typeof item === 'string')
        : [];
}

function countWords(content: string): number {
    const compact = content.replace(/\s+/g, '');
    return compact.length || content.length;
}

function parseGeneratedContent(content: unknown): ContentSection[] {
    if (typeof content !== 'string') return [];

    // 优先按 markdown 标题 ## 切分
    const sections = content.split(/\n## |^## /);

    // 如果切不出来（长度为 1 且第一个元素不含标题），就回退成一个 section
    if (sections.length <= 1) {
        return [{
            id: 'generated_body',
            title: '正文草稿',
            content: content.trim(),
            wordCount: countWords(content),
        }];
    }

    return sections
        .filter(s => s.trim())
        .map((s, index) => {
            const lines = s.split('\n');
            const title = lines[0].trim() || `章节 ${index + 1}`;
            const body = lines.slice(1).join('\n').trim();
            return {
                id: `gen_sec_${index}`,
                title,
                content: body,
                wordCount: countWords(body),
            };
        });
}

function getOutlineTitleMap(outline: unknown): Record<string, string> {
    if (!isRecord(outline) || !Array.isArray(outline.sections)) {
        return {};
    }

    const titleMap: Record<string, string> = {};
    const visit = (sections: unknown[]) => {
        sections.forEach((section) => {
            if (!isRecord(section)) {
                return;
            }
            const id = typeof section.id === 'string' ? section.id : undefined;
            const title = typeof section.title === 'string' ? section.title : undefined;
            if (id && title) {
                titleMap[id] = title;
            }
            if (Array.isArray(section.subsections)) {
                visit(section.subsections);
            }
        });
    };

    visit(outline.sections);
    return titleMap;
}

function getContentText(value: unknown): string {
    if (typeof value === 'string') {
        return value;
    }

    if (!isRecord(value)) {
        return '';
    }

    for (const key of ['compiled_content', 'content', 'text', 'markdown']) {
        if (typeof value[key] === 'string') {
            return value[key] as string;
        }
    }

    if (isRecord(value.sections)) {
        return Object.entries(value.sections)
            .map(([sectionId, sectionContent]) => {
                const text = typeof sectionContent === 'string'
                    ? sectionContent
                    : JSON.stringify(sectionContent, null, 2);
                return `## ${formatEntryLabel(sectionId)}\n${text}`;
            })
            .join('\n\n');
    }

    return '';
}

function getArtifactTimestamp(artifact: Record<string, unknown>): number {
    const createdAt = typeof artifact.created_at === 'string' ? Date.parse(artifact.created_at) : NaN;
    const version = typeof artifact.version === 'number' ? artifact.version : 0;
    return Number.isFinite(createdAt) ? createdAt : version;
}

function getLatestArtifactByType(
    trace: WorkflowTrace | null,
    type: string,
    preferredId?: unknown
): Record<string, unknown> | null {
    if (!trace) {
        return null;
    }

    const artifacts = Object.values(trace.artifacts);
    if (typeof preferredId === 'string' && trace.artifacts[preferredId]) {
        return trace.artifacts[preferredId];
    }

    return artifacts
        .filter((artifact) => artifact.type === type)
        .sort((a, b) => getArtifactTimestamp(b) - getArtifactTimestamp(a))[0] ?? null;
}

function buildSectionsFromFinalArtifact(
    artifact: Record<string, unknown> | null,
    outline: unknown
): ContentSection[] {
    if (!artifact) {
        return [];
    }

    const content = artifact.content;
    const titleMap = getOutlineTitleMap(outline);
    if (isRecord(content) && isRecord(content.sections)) {
        const orderedIds = asStringArray(content.section_order);
        const sectionIds = orderedIds.length > 0
            ? orderedIds
            : Object.keys(content.sections);

        return sectionIds
            .map((sectionId) => {
                const sectionContent = content.sections[sectionId];
                const text = typeof sectionContent === 'string'
                    ? sectionContent
                    : JSON.stringify(sectionContent, null, 2);
                return {
                    id: sectionId,
                    title: titleMap[sectionId] ?? formatEntryLabel(sectionId),
                    content: text,
                    wordCount: countWords(text),
                };
            })
            .filter((section) => section.content.trim());
    }

    const text = getContentText(content);
    return parseGeneratedContent(text);
}

function buildSectionsFromSectionArtifacts(
    trace: WorkflowTrace | null,
    outline: unknown
): ContentSection[] {
    if (!trace) {
        return [];
    }

    const titleMap = getOutlineTitleMap(outline);
    const latestBySection = new Map<string, { section: ContentSection; timestamp: number }>();

    Object.values(trace.artifacts)
        .filter((artifact) => artifact.type === 'section_content')
        .forEach((artifact) => {
            const content = artifact.content;
            if (!isRecord(content)) {
                return;
            }

            const sectionId = typeof content.section_id === 'string'
                ? content.section_id
                : typeof artifact.id === 'string'
                    ? artifact.id
                    : '';
            const text = typeof content.content === 'string' ? content.content : '';
            if (!sectionId || !text.trim()) {
                return;
            }

            const timestamp = getArtifactTimestamp(artifact);
            const current = latestBySection.get(sectionId);
            if (current && current.timestamp >= timestamp) {
                return;
            }

            latestBySection.set(sectionId, {
                timestamp,
                section: {
                    id: sectionId,
                    title:
                        typeof content.section_title === 'string'
                            ? content.section_title
                            : titleMap[sectionId] ?? formatEntryLabel(sectionId),
                    content: text,
                    wordCount: countWords(text),
                },
            });
        });

    const orderedIds = Object.keys(titleMap);
    const sections = Array.from(latestBySection.values()).map((entry) => entry.section);

    return sections.sort((a, b) => {
        const aIndex = orderedIds.indexOf(a.id);
        const bIndex = orderedIds.indexOf(b.id);
        if (aIndex === -1 && bIndex === -1) {
            return 0;
        }
        if (aIndex === -1) {
            return 1;
        }
        if (bIndex === -1) {
            return -1;
        }
        return aIndex - bIndex;
    });
}

function buildContentSections(
    workflow: WorkflowResponse | null,
    trace: WorkflowTrace | null
): ContentSection[] {
    const outline = workflow?.state.outline;
    const finalArtifactId =
        workflow?.state.final_content_artifact_id ??
        trace?.workflow.final_artifact_id;
    const finalArtifact = getLatestArtifactByType(trace, 'final_content', finalArtifactId);
    const finalSections = buildSectionsFromFinalArtifact(finalArtifact, outline);
    if (finalSections.length > 0) {
        return finalSections;
    }

    const sectionArtifacts = buildSectionsFromSectionArtifacts(trace, outline);
    if (sectionArtifacts.length > 0) {
        return sectionArtifacts;
    }

    if (workflow?.state.generated_content) {
        return parseGeneratedContent(workflow.state.generated_content);
    }

    const finalEntries = normalizeFinalContentEntries(
        workflow?.state.final_content as Record<string, unknown> | undefined
    );
    return finalEntries.map((entry) => ({
        id: entry.key,
        title: formatEntryLabel(entry.key),
        content: entry.preview,
        wordCount: entry.wordCount ?? countWords(entry.preview),
    }));
}

function shouldUseLiveUpdates(workflow: WorkflowResponse): boolean {
    return (
        workflow.status === 'running' ||
        workflow.status === 'paused' ||
        Boolean(workflow.state.gate)
    );
}

function formatEntryLabel(key: string): string {
    return key
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

function formatStepStatus(step: WorkflowStep): string {
    switch (step.status) {
        case 'completed':
            return step.durationMs ? `${Math.round(step.durationMs / 1000)}s` : '已完成';
        case 'running':
            return '执行中';
        case 'interrupted':
            return '等待确认';
        case 'failed':
            return '执行失败';
        default:
            return '待开始';
    }
}

export default function WorkflowDetailPage() {
    const params = useParams();
    const router = useRouter();
    const workflowId = params.id as string;

    const [workflow, setWorkflow] = React.useState<WorkflowResponse | null>(null);
    const [trace, setTrace] = React.useState<WorkflowTrace | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState<string | null>(null);
    const [actionLoading, setActionLoading] = React.useState(false);
    const [completedView, setCompletedView] = React.useState<'preview' | 'raw'>('preview');

    const pollIntervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const eventSourceRef = React.useRef<EventSource | null>(null);
    const traceSectionRef = React.useRef<HTMLDivElement | null>(null);
    const [focusedTraceNodeId, setFocusedTraceNodeId] = React.useState<string | null>(null);

    const stopPolling = React.useCallback(() => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    }, []);

    const stopEventStream = React.useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
    }, []);

    const applyEventSnapshot = React.useCallback((snapshot: WorkflowEventSnapshot) => {
        setWorkflow(snapshot.workflow);
        setTrace(snapshot.trace);
        setError(null);
        setLoading(false);
    }, []);

    const startPolling = React.useCallback(() => {
        if (!pollIntervalRef.current) {
            pollIntervalRef.current = setInterval(() => {
                Promise.all([
                    workflowApi.getStatus(workflowId),
                    traceApi.getWorkflowTrace(workflowId),
                ])
                    .then(([workflowResponse, traceResponse]) => {
                        setWorkflow(workflowResponse);
                        setTrace(traceResponse);
                        if (
                            workflowResponse.status !== 'running' &&
                            workflowResponse.status !== 'paused' &&
                            !workflowResponse.state.gate
                        ) {
                            stopPolling();
                        }
                    })
                    .catch(() => {
                        stopPolling();
                    });
            }, 3000);
        }
    }, [workflowId, stopPolling]);

    const startEventStream = React.useCallback(() => {
        if (eventSourceRef.current) {
            return;
        }

        stopPolling();
        const source = workflowApi.openEventStream(workflowId, {
            onSnapshot: (snapshot) => {
                applyEventSnapshot(snapshot);
                if (!shouldUseLiveUpdates(snapshot.workflow)) {
                    source.close();
                    if (eventSourceRef.current === source) {
                        eventSourceRef.current = null;
                    }
                }
            },
            onDone: () => {
                if (eventSourceRef.current === source) {
                    eventSourceRef.current = null;
                }
            },
            onError: () => {
                if (eventSourceRef.current === source) {
                    eventSourceRef.current = null;
                    startPolling();
                }
            },
        });

        eventSourceRef.current = source;
    }, [applyEventSnapshot, startPolling, stopPolling, workflowId]);

    const loadWorkflow = React.useCallback(async () => {
        try {
            const [workflowResponse, traceResponse] = await Promise.all([
                workflowApi.getStatus(workflowId),
                traceApi.getWorkflowTrace(workflowId),
            ]);

            setWorkflow(workflowResponse);
            setTrace(traceResponse);
            setError(null);

            if (shouldUseLiveUpdates(workflowResponse)) {
                startEventStream();
            } else {
                stopEventStream();
                stopPolling();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '加载失败');
            stopEventStream();
            stopPolling();
        } finally {
            setLoading(false);
        }
    }, [workflowId, startEventStream, stopEventStream, stopPolling]);

    React.useEffect(() => {
        loadWorkflow();
        return () => {
            stopEventStream();
            stopPolling();
        };
    }, [loadWorkflow, stopEventStream, stopPolling]);

    React.useEffect(() => {
        if (workflow?.status !== 'completed') {
            setCompletedView('preview');
        }
    }, [workflow?.status]);

    const handleClarification = async (answers: Record<string, string>) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.clarify(workflowId, answers);
            setWorkflow(response);
            const traceResponse = await traceApi.getWorkflowTrace(workflowId);
            setTrace(traceResponse);
            if (shouldUseLiveUpdates(response)) {
                startEventStream();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '提交失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleOutlineApprove = async () => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveOutline(workflowId, 'approve');
            setWorkflow(response);
            const traceResponse = await traceApi.getWorkflowTrace(workflowId);
            setTrace(traceResponse);
            if (shouldUseLiveUpdates(response)) {
                startEventStream();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '审批失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleOutlineModify = async (modifiedOutline: Outline) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveOutline(
                workflowId,
                'modify',
                undefined,
                modifiedOutline
            );
            setWorkflow(response);
            const traceResponse = await traceApi.getWorkflowTrace(workflowId);
            setTrace(traceResponse);
            if (shouldUseLiveUpdates(response)) {
                startEventStream();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '保存失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleOutlineRegenerate = async (feedback: string) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveOutline(
                workflowId,
                'regenerate',
                feedback
            );
            setWorkflow(response);
            const traceResponse = await traceApi.getWorkflowTrace(workflowId);
            setTrace(traceResponse);
            if (shouldUseLiveUpdates(response)) {
                startEventStream();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '重新生成失败');
        } finally {
            setActionLoading(false);
        }
    };

    const handleFactCheckApprove = async (
        decisions: Record<string, 'confirm' | 'use_suggestion' | 'manual'>,
        corrections: Record<string, string>
    ) => {
        setActionLoading(true);
        try {
            const response = await workflowApi.approveFactCheck(
                workflowId,
                decisions,
                corrections
            );
            setWorkflow(response);
            const traceResponse = await traceApi.getWorkflowTrace(workflowId);
            setTrace(traceResponse);
            if (shouldUseLiveUpdates(response)) {
                startEventStream();
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '事实核查审批失败');
        } finally {
            setActionLoading(false);
        }
    };

    const calculateSteps = (): WorkflowStep[] => {
        const stepNames = [
            'parse_intent',
            'generate_outline',
            'generate_content',
            'self_refine',
            'check_facts',
            'finalize',
        ];
        const stepLabels: Record<string, string> = {
            parse_intent: '意图解析',
            generate_outline: '提纲生成',
            generate_content: '内容生成',
            self_refine: '自检修订',
            check_facts: '事实核查',
            finalize: '最终输出',
        };

        if (!workflow) {
            return stepNames.map((name) => ({
                id: name,
                name,
                label: stepLabels[name],
                status: 'pending' as const,
            }));
        }

        const state = workflow.state;
        const currentWorkflowStatus = workflow.status;
        const isGateWaiting = Boolean(state.gate);
        const gateType = state.gate?.gate_type;

        const isStepComplete = (stepName: string) => {
            switch (stepName) {
                case 'parse_intent':
                    return Boolean(state.intent_card);
                case 'generate_outline':
                    return Boolean(state.outline);
                case 'generate_content':
                    return Boolean(state.generated_content);
                case 'self_refine':
                    return Boolean(state.final_content);
                case 'check_facts':
                    return Boolean(state.fact_check_report);
                case 'finalize':
                    return currentWorkflowStatus === 'completed';
                default:
                    return false;
            }
        };

        const runningStepId =
            currentWorkflowStatus === 'running'
                ? stepNames.find((stepName) => !isStepComplete(stepName))
                : undefined;
        const failedStepId =
            currentWorkflowStatus === 'failed'
                ? stepNames.find((stepName) => !isStepComplete(stepName)) ?? 'finalize'
                : undefined;

        return stepNames.map((name) => {
            let status: WorkflowStep['status'] = 'pending';

            if (isStepComplete(name)) {
                status = 'completed';
            }

            if (currentWorkflowStatus === 'paused') {
                // If the entire workflow is paused, all steps that are not completed should be 'paused'
                if (status !== 'completed') {
                    status = 'paused';
                }
            } else if (isGateWaiting) {
                // If gate is waiting, specific steps should be marked as 'gate_waiting'
                if (name === 'parse_intent' && gateType === 'clarification') {
                    status = 'gate_waiting';
                }
                if (name === 'generate_outline' && gateType === 'outline_approval') {
                    status = 'gate_waiting';
                }
                if (name === 'check_facts' && gateType === 'fact_check') {
                    status = 'gate_waiting';
                }
            } else if (currentWorkflowStatus === 'running' && name === runningStepId) {
                status = 'running';
            }

            if (currentWorkflowStatus === 'failed' && name === failedStepId) {
                status = 'failed';
            }

            // Fallback for states that were previously 'interrupted' but now map to 'gate_waiting'
            if (
                currentWorkflowStatus === 'needs_clarification' &&
                name === 'parse_intent' &&
                status !== 'completed'
            ) {
                status = 'gate_waiting';
            }
            if (
                currentWorkflowStatus === 'awaiting_outline_approval' &&
                name === 'generate_outline' &&
                status !== 'completed'
            ) {
                status = 'gate_waiting';
            }
            if (
                currentWorkflowStatus === 'awaiting_fact_check_approval' &&
                name === 'check_facts' &&
                status !== 'completed'
            ) {
                status = 'gate_waiting';
            }


            return {
                id: name,
                name,
                label: stepLabels[name],
                status,
            };
        });
    };

    const steps = calculateSteps();
    const currentStep = steps.find(
        (step) => step.status === 'running' || step.status === 'interrupted' || step.status === 'gate_waiting' || step.status === 'paused'
    )?.id;
    const currentStepLabel = steps.find((step) => step.id === currentStep)?.label;
    const statusMeta = getStatusMeta(workflow?.status);
    const contentSections = React.useMemo(
        () => buildContentSections(workflow, trace),
        [workflow, trace]
    );
    const isContentStreaming =
        Boolean(contentSections.length) &&
        workflow?.status === 'running' &&
        currentStep !== undefined &&
        ['generate_content', 'self_refine', 'check_facts', 'finalize'].includes(currentStep);

    const handleStepClick = React.useCallback((stepId: string) => {
        const node = trace?.nodes.find((item) => (
            item.node_name === stepId ||
            item.name === stepId ||
            item.node === stepId ||
            item.id === stepId
        ));
        const nodeId = typeof node?.id === 'string' ? node.id : null;
        if (nodeId) {
            setFocusedTraceNodeId(nodeId);
        }
        traceSectionRef.current?.scrollIntoView({ block: 'start' });
    }, [trace]);

    const buildStageMetrics = (): StageMetric[] => {
        if (!workflow) {
            return [];
        }

        const { status, state } = workflow;

        if (status === 'needs_clarification') {
            const questions = state.clarification_questions ?? [];
            const required = questions.filter((question) => question.priority === 'high');
            return [
                { label: '澄清问题', value: formatCount(questions.length) },
                { label: '必填问题', value: formatCount(required.length), tone: 'warning' },
            ];
        }

        if (status === 'awaiting_outline_approval' && state.outline) {
            const outline = state.outline as Outline;
            return [
                { label: '章节数量', value: formatCount(outline.sections.length) },
                { label: '目标字数', value: formatCount(outline.total_target_words), tone: 'brand' },
            ];
        }

        if (status === 'awaiting_fact_check_approval' && state.fact_check_report) {
            const report = state.fact_check_report as FactCheckReport;
            return [
                { label: '总声明数', value: formatCount(report.total_claims) },
                { label: '已验证', value: formatCount(report.verified_count), tone: 'success' },
                { label: '高风险', value: formatCount(report.high_risk_count), tone: 'warning' },
            ];
        }

        if (status === 'completed') {
            const totalWords = contentSections.reduce(
                (sum, entry) => sum + (entry.wordCount ?? 0),
                0
            );

            return [
                { label: '交付块数', value: formatCount(contentSections.length), tone: 'success' },
                { label: '累计字数', value: formatCount(totalWords || undefined), tone: 'brand' },
            ];
        }

        return [
            { label: '当前步骤', value: currentStepLabel ?? '自动推进中', tone: 'brand' },
            { label: '已完成节点', value: formatCount(steps.filter((step) => step.status === 'completed').length) },
        ];
    };

    const stageMetrics = buildStageMetrics();

    const renderRunningStage = () => (
        <div className={styles.runningStage}>
            <div className={styles.runningIntro}>
                <div className={styles.runningPulse} aria-hidden="true">
                    <LoaderCircle className={styles.spinIcon} />
                </div>
                <div>
                    <p className={styles.runningEyebrow}>实时编排</p>
                    <h3>系统正在推进当前工作流</h3>
                    <p>
                        当前焦点：
                        <strong>{currentStepLabel ?? '正在解析上下文'}</strong>
                        。一旦出现需要人工介入的步骤，页面会自动切换到对应审阅态。
                    </p>
                </div>
            </div>

            <div className={styles.liveRail}>
                {steps.map((step) => (
                    <div
                        key={step.id}
                        className={`${styles.liveItem} ${
                            step.id === currentStep ? styles.liveItemActive : ''
                        }`}
                    >
                        <span className={styles.liveLabel}>{step.label}</span>
                        <span className={styles.liveMeta}>
                            {step.status === 'paused' ? '已暂停' : formatStepStatus(step)}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );

    const renderPausedStage = () => {
        const pauseInfo = workflow?.state?.pause;
        const pauseReason = pauseInfo?.reason || '手动暂停';
        const pauseTime = pauseInfo?.paused_at ? new Date(pauseInfo.paused_at).toLocaleString() : '未知时间';

        return (
            <div className={styles.failedStage}>
                <div className={styles.failedIconWrap}>
                    <Pause className={styles.failedIcon} aria-hidden="true" />
                </div>
                <div>
                    <h3>工作流已暂停</h3>
                    <p>
                        最近一次暂停原因：{pauseReason}<br />
                        暂停时间：{pauseTime}
                    </p>
                </div>
                <div className={styles.failedActions}>
                    <button type="button" className="btn btn-secondary" onClick={() => void loadWorkflow()}>
                        刷新状态
                    </button>
                    <button
                        type="button"
                        className="btn btn-primary"
                        onClick={async () => {
                            setActionLoading(true);
                            try {
                                await workflowApi.resume(workflowId);
                                const [workflowResponse, traceResponse] = await Promise.all([
                                    workflowApi.getStatus(workflowId),
                                    traceApi.getWorkflowTrace(workflowId),
                                ]);
                                setWorkflow(workflowResponse);
                                setTrace(traceResponse);
                                if (shouldUseLiveUpdates(workflowResponse)) {
                                    startEventStream();
                                }
                            } catch (err) {
                                setError(err instanceof Error ? err.message : '恢复失败');
                            } finally {
                                setActionLoading(false);
                            }
                        }}
                        disabled={actionLoading}
                    >
                        {actionLoading ? '恢复中...' : '恢复执行'}
                    </button>
                </div>
            </div>
        );
    };

    const renderFailedStage = () => (
        <div className={styles.failedStage}>
            <div className={styles.failedIconWrap}>
                <AlertTriangle className={styles.failedIcon} aria-hidden="true" />
            </div>
            <div>
                <h3>执行失败</h3>
                <p>
                    当前执行已中断。请先检查错误信息，再决定是否重新发起或返回首页。
                </p>
                {error && <p className={styles.errorText}>{error}</p>}
            </div>
            <div className={styles.failedActions}>
                <button type="button" className="btn btn-secondary" onClick={() => void loadWorkflow()}>
                    重新加载
                </button>
                <button type="button" className="btn btn-primary" onClick={() => router.push('/')}>
                    返回首页
                </button>
            </div>
        </div>
    );

    const renderCompletedStage = () => {
        const finalArtifact = getLatestArtifactByType(
            trace,
            'final_content',
            workflow?.state.final_content_artifact_id ?? trace?.workflow.final_artifact_id
        );
        const rawFinalContent = finalArtifact?.content ?? workflow?.state.final_content ?? {};
        const finalEntries = contentSections;

        return (
            <div className={styles.completedStage}>
                <div className={styles.completedHero}>
                    <div className={styles.completedBadge}>
                        <CheckCheck className={styles.completedBadgeIcon} aria-hidden="true" />
                    </div>
                    <div className={styles.completedCopy}>
                        <p className={styles.completedEyebrow}>交付就绪</p>
                        <h3>内容产物已完成生成与审阅</h3>
                        <p>
                            内容已完成生成与审阅，你可以先阅读结果，再决定是否回看原始数据。
                        </p>
                    </div>
                    <div className={styles.completedActions}>
                        <button
                            type="button"
                            className={`${styles.viewToggle} ${
                                completedView === 'preview' ? styles.viewToggleActive : ''
                            }`}
                            onClick={() => setCompletedView('preview')}
                        >
                            <FileText className={styles.toggleIcon} aria-hidden="true" />
                            预览结果
                        </button>
                        <button
                            type="button"
                            className={`${styles.viewToggle} ${
                                completedView === 'raw' ? styles.viewToggleActive : ''
                            }`}
                            onClick={() => setCompletedView('raw')}
                        >
                            <Braces className={styles.toggleIcon} aria-hidden="true" />
                            原始数据
                        </button>
                        <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => router.push('/')}
                        >
                            返回首页
                        </button>
                    </div>
                </div>

                {completedView === 'preview' ? (
                    <div className={styles.previewGrid}>
                        {finalEntries.length > 0 ? (
                            finalEntries.map((entry) => (
                                <article key={entry.id} className={styles.previewCard}>
                                    <div className={styles.previewCardHeader}>
                                        <div>
                                            <p className={styles.previewLabel}>
                                                {entry.title}
                                            </p>
                                            {entry.wordCount > 0 && (
                                                <span className={styles.previewMeta}>
                                                    {entry.wordCount} 字
                                                </span>
                                            )}
                                        </div>
                                        <Sparkles
                                            className={styles.previewCardIcon}
                                            aria-hidden="true"
                                        />
                                    </div>
                                    <p className={styles.previewText}>{entry.content}</p>
                                </article>
                            ))
                        ) : (
                            <div className={styles.emptyState}>
                                <FileText className={styles.emptyStateIcon} aria-hidden="true" />
                                <div>
                                    <h3>当前没有可展示的结果片段</h3>
                                    <p>工作流已完成，但 `final_content` 为空或结构不符合预览条件。</p>
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className={styles.rawSurface}>
                        <pre>{JSON.stringify(rawFinalContent ?? {}, null, 2)}</pre>
                    </div>
                )}
            </div>
        );
    };

    const renderCurrentStage = () => {
        if (!workflow) {
            return null;
        }

        const { status, state } = workflow;
        const isOutlineGate = state.gate?.gate_type === 'outline_approval';

        if (status === 'needs_clarification' && state.clarification_questions) {
            return (
                <ClarificationDialog
                    questions={state.clarification_questions}
                    onSubmit={handleClarification}
                    isLoading={actionLoading}
                />
            );
        }

        if (status === 'awaiting_outline_approval' && state.outline) {
            return (
                <OutlineEditor
                    outline={state.outline as Outline}
                    onApprove={handleOutlineApprove}
                    onModify={handleOutlineModify}
                    onRegenerate={handleOutlineRegenerate}
                    isLoading={actionLoading}
                    isReadOnly={!isOutlineGate}
                />
            );
        }

        if (status === 'awaiting_fact_check_approval' && state.fact_check_report) {
            return (
                <FactCheckViewer
                    report={state.fact_check_report as FactCheckReport}
                    onApprove={handleFactCheckApprove}
                    isLoading={actionLoading}
                />
            );
        }

        if (status === 'completed') {
            return renderCompletedStage();
        }

        if (status === 'failed') {
            return renderFailedStage();
        }

        if (status === 'paused') {
            return renderPausedStage();
        }

        // Default to running stage if none of the above
        return renderRunningStage();
    };

    if (loading) {
        return (
            <div className={styles.loadingContainer}>
                <LoaderCircle className={`${styles.spinIcon} ${styles.loadingIcon}`} />
                <p>加载工作流...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.errorContainer} role="alert">
                <div className={styles.errorIconWrap}>
                    <AlertTriangle className={styles.errorIcon} aria-hidden="true" />
                </div>
                <h3>加载失败</h3>
                <p>{error}</p>
                <button className="btn btn-secondary" onClick={() => router.push('/')}>
                    返回首页
                </button>
            </div>
        );
    }

    return (
        <div className={styles.page}>
            <header className={styles.header}>
                <button className={styles.backButton} onClick={() => router.push('/')}>
                    <ArrowLeft className={styles.backIcon} aria-hidden="true" />
                    返回首页
                </button>

                <div className={styles.headerCopy}>
                    <p className={styles.headerEyebrow}>工作流详情</p>
                    <h1 className={styles.title}>工作流详情</h1>
                </div>

                <div className={styles.headerMeta}>
                    {workflow?.status === 'paused' && workflow?.state.pause && (
                        <div className={styles.pauseInfo}>
                            <Pause className={styles.pauseIcon} />
                            <span>
                                已暂停{' '}
                                {workflow.state.pause.reason && `(${workflow.state.pause.reason})`}
                                {workflow.state.pause.paused_at &&
                                    ` 于 ${new Date(workflow.state.pause.paused_at).toLocaleString()}`}
                            </span>
                            {workflow.state.pause.resumed_at && (
                                <span>
                                    ，恢复于{' '}
                                    {new Date(workflow.state.pause.resumed_at).toLocaleString()}
                                </span>
                            )}
                        </div>
                    )}

                    {workflow &&
                        workflow.status !== 'completed' &&
                        workflow.status !== 'failed' &&
                        !workflow.state.gate && (
                            <button
                                className="btn btn-ghost"
                                onClick={async () => {
                                    setActionLoading(true);
                                    try {
                                        if (workflow.status === 'paused') {
                                            await workflowApi.resume(workflowId);
                                        } else {
                                            await workflowApi.pause(workflowId);
                                        }
                                        const [workflowResponse, traceResponse] = await Promise.all([
                                            workflowApi.getStatus(workflowId),
                                            traceApi.getWorkflowTrace(workflowId),
                                        ]);
                                        setWorkflow(workflowResponse);
                                        setTrace(traceResponse);
                                        if (shouldUseLiveUpdates(workflowResponse)) {
                                            startEventStream();
                                        }
                                    } catch (err) {
                                        setError(
                                            err instanceof Error ? err.message : '操作失败'
                                        );
                                    } finally {
                                        setActionLoading(false);
                                    }
                                }}
                                disabled={actionLoading}
                            >
                                {actionLoading ? (
                                    <LoaderCircle className={styles.spinIcon} />
                                ) : workflow.status === 'paused' ? (
                                    <Play />
                                ) : (
                                    <Pause />
                                )}{' '}
                                {workflow.status === 'paused' ? '恢复' : '暂停'}
                            </button>
                        )}

                    <span className={`${styles.headerStatus} ${styles[`tone${statusMeta.tone[0].toUpperCase()}${statusMeta.tone.slice(1)}`]}`}>
                        <statusMeta.icon className={styles.headerStatusIcon} aria-hidden="true" />
                        {statusMeta.label}
                    </span>
                    <code className={styles.workflowId}>{workflowId.slice(0, 8)}...</code>
                </div>
            </header>

            <div className={styles.mainContent}>
                <aside className={styles.sidebar}>
                    <WorkflowProgress
                        steps={steps}
                        currentStep={currentStep}
                        onStepClick={handleStepClick}
                    />
                </aside>

                <main className={styles.stageColumn}>
                    <section className={styles.statusStrip} aria-live="polite">
                        <div className={styles.statusStripMain}>
                            <div className={`${styles.statusIconWrap} ${styles[`tone${statusMeta.tone[0].toUpperCase()}${statusMeta.tone.slice(1)}`]}`}>
                                <statusMeta.icon className={styles.statusIcon} aria-hidden="true" />
                            </div>
                            <div>
                                <p className={styles.statusEyebrow}>{statusMeta.eyebrow}</p>
                                <p className={styles.statusMessage}>
                                    {statusMeta.label}
                                    {currentStepLabel ? ` · ${currentStepLabel}` : ''}
                                </p>
                            </div>
                        </div>
                        <div className={styles.statusHints}>
                            <Clock3 className={styles.hintIcon} aria-hidden="true" />
                            <span>
                                {workflow?.status === 'completed'
                                    ? '交付已准备好，可切换预览和原始数据。'
                                    : '系统会持续更新状态，无需手动刷新。'}
                            </span>
                        </div>
                    </section>

                    <section className={styles.stageShell}>
                        <div className={styles.stageHeader}>
                            <div className={styles.stageHeaderMain}>
                                <p className={styles.stageEyebrow}>{statusMeta.label}</p>
                                <h2 className={styles.stageTitle}>{statusMeta.title}</h2>
                                <p className={styles.stageDescription}>{statusMeta.description}</p>
                            </div>

                            {stageMetrics.length > 0 && (
                                <div className={styles.stageMetrics}>
                                    {stageMetrics.map((metric) => (
                                        <div
                                            key={metric.label}
                                            className={`${styles.metricCard} ${
                                                metric.tone
                                                    ? styles[`tone${metric.tone[0].toUpperCase()}${metric.tone.slice(1)}`]
                                                    : ''
                                            }`}
                                        >
                                            <span className={styles.metricLabel}>{metric.label}</span>
                                            <strong className={styles.metricValue}>{metric.value}</strong>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className={styles.stageBody}>{renderCurrentStage()}</div>
                    </section>

                    {(workflow?.state.intent_card || workflow?.state.outline || contentSections.length > 0 || trace) && (
                        <section className={styles.stageShell} style={{ marginTop: '2rem' }}>
                            <div className={styles.stageHeader}>
                                <div className={styles.stageHeaderMain}>
                                    <h2 className={styles.stageTitle}>过程与产物</h2>
                                    <p className={styles.stageDescription}>工作流执行过程中的关键分析、提纲、生成内容与执行追踪</p>
                                </div>
                            </div>
                            <div className={styles.stageBody}>
                                {Boolean(workflow?.state.intent_card) && (
                                    <div className={styles.contentBlock} style={{ marginBottom: '2rem' }}>
                                        <h3 style={{ marginBottom: '1rem', fontSize: '1.125rem', fontWeight: 600 }}>意图分析</h3>
                                        <IntentCardViewer intentCard={workflow!.state.intent_card as any} />
                                    </div>
                                )}
                                {workflow?.state.outline && workflow.status !== 'awaiting_outline_approval' && (
                                    <div className={styles.contentBlock} style={{ marginBottom: '2rem' }}>
                                        <h3 style={{ marginBottom: '1rem', fontSize: '1.125rem', fontWeight: 600 }}>生成提纲</h3>
                                        <OutlineEditor
                                            outline={workflow.state.outline as Outline}
                                            onApprove={handleOutlineApprove}
                                            onModify={handleOutlineModify}
                                            onRegenerate={handleOutlineRegenerate}
                                            isLoading={false}
                                            isReadOnly={true}
                                        />
                                    </div>
                                )}
                                {contentSections.length > 0 && (
                                    <div className={styles.contentBlock} style={{ marginBottom: '2rem' }}>
                                        <h3 style={{ marginBottom: '1rem', fontSize: '1.125rem', fontWeight: 600 }}>生成内容</h3>
                                        <ContentViewer
                                            title={workflow.state.outline?.title || '生成内容'}
                                            abstract={workflow.state.outline?.abstract || ''}
                                            sections={contentSections}
                                            isStreaming={isContentStreaming}
                                        />
                                    </div>
                                )}
                                {trace && (
                                    <div ref={traceSectionRef} className={styles.contentBlock}>
                                        <h3 style={{ marginBottom: '1rem', fontSize: '1.125rem', fontWeight: 600 }}>执行追踪</h3>
                                        <TraceViewer
                                            trace={trace}
                                            focusedNodeId={focusedTraceNodeId}
                                            onNodeClick={setFocusedTraceNodeId}
                                        />
                                    </div>
                                )}
                            </div>
                        </section>
                    )}
                </main>
            </div>
        </div>
    );
}
