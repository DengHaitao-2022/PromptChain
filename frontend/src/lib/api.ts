/**
 * PromptChain API 客户端
 *
 * 与后端 FastAPI 通信的统一接口
 */

import { apiUrl, serviceUrl } from './api-config';
import { authenticatedFetch } from './auth';

// 类型定义
export type WorkflowStatus =
  | 'running'
  | 'paused'
  | 'needs_clarification'
  | 'awaiting_outline_approval'
  | 'awaiting_fact_check_approval'
  | 'completed'
  | 'failed';

export type ClarificationPriority = 'high' | 'medium' | 'low';
export type FactCheckDecision = 'confirm' | 'use_suggestion' | 'manual';
export type WorkflowGateType = 'clarification' | 'outline_approval' | 'fact_check';

export interface WorkflowResponse {
  workflow_run_id: string;
  status: WorkflowStatus;
  state: {
    clarification_questions?: ClarificationQuestion[];
    outline?: Outline;
    fact_check_report?: FactCheckReport;
    final_content?: Record<string, { preview: string; word_count: number }>;
    current_node?: string;
    error?: string;
    pause?: WorkflowPauseState;
    gate?: WorkflowGateState;
    [key: string]: unknown;
  };
}

export interface ClarificationQuestion {
  field: string;
  question: string;
  priority: ClarificationPriority;
  default_assumption?: string;
}

export interface WorkflowPauseState {
  reason?: string | null;
  paused_at?: string | null;
  resumed_at?: string | null;
  source?: 'user' | string;
}

export interface WorkflowGateQuestion extends Record<string, unknown> {
  question?: string;
}

export interface WorkflowGateState {
  gate_type: WorkflowGateType;
  trigger_reason?: string | null;
  questions: WorkflowGateQuestion[];
  answers?: Record<string, unknown> | null;
  opened_at?: string | null;
  handled_at?: string | null;
  waiting_duration_ms?: number | null;
  resolution?: string | null;
}

export interface IntentCard {
  goal: string;
  topic: string;
  audience: string;
  scenario: string;
  tone: string;
  length: number;
  must_include: string[];
  must_exclude: string[];
  clarification_questions?: ClarificationQuestion[];
}

export interface OutlineSection {
  id: string;
  title: string;
  summary: string;
  target_words: number;
  subsections: OutlineSection[];
}

export interface Outline {
  title: string;
  abstract: string;
  sections: OutlineSection[];
  total_target_words: number;
  is_approved: boolean;
  version: number;
}

export interface FactClaim {
  id: string;
  text: string;
  category: string;
  section_id: string;
}

export type EvidenceStatus = 'supported' | 'unsupported' | 'conflicting' | 'not_checked';

export interface VerificationResult {
  claim_id: string;
  is_verified: boolean;
  confidence: number;
  evidence_status?: EvidenceStatus;
  source?: string | null;
  risk_level: 'low' | 'medium' | 'high';
  suggested_correction: string | null;
  verification_question: string;
  verification_answer: string;
}

export interface FactCheckReport {
  claims: FactClaim[];
  results: VerificationResult[];
  total_claims: number;
  verified_count: number;
  unverified_count?: number;
  high_risk_count: number;
}

export type KnowledgeScope = 'workspace' | 'personal' | 'run_upload';
export type KnowledgeBaseStatus = 'active' | 'disabled' | 'archived';
export type KnowledgeDocumentLifecycleStatus = 'active' | 'disabled' | 'archived';
export type KnowledgeDocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';
export type RetrievalMode = 'vector' | 'keyword' | 'hybrid';

export interface EvidenceChunk {
  chunk_id: string;
  document_id: string;
  knowledge_base_id: string;
  document_name: string;
  scope: KnowledgeScope;
  page_number?: number | null;
  heading_path: string[];
  score: number;
  vector_score?: number | null;
  keyword_score?: number | null;
  rerank_score?: number | null;
  content: string;
  metadata: Record<string, unknown>;
  redacted?: boolean;
}

export interface EvidencePack {
  query: string;
  rewritten_queries: string[];
  scopes: KnowledgeScope[];
  chunks: EvidenceChunk[];
  conflicts: Array<{
    topic: string;
    chunk_ids: string[];
    reason: string;
  }>;
  unverified_points: string[];
  retrieval_mode: RetrievalMode;
  generated_at: string;
}

export interface RetrievalConfig {
  enabled: boolean;
  use_workspace_kb: boolean;
  use_personal_kb: boolean;
  use_run_upload: boolean;
  top_k: number;
  min_score: number;
  mode: RetrievalMode;
  enable_query_rewrite: boolean;
  enable_multi_query: boolean;
  enable_rerank: boolean;
  enable_context_compression: boolean;
  enable_conflict_detection: boolean;
}

export interface KnowledgeBase {
  id: string;
  workspace_id: string;
  owner_user_id?: string | null;
  workflow_run_id?: string | null;
  scope: KnowledgeScope;
  name: string;
  description?: string | null;
  status: KnowledgeBaseStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  kb_id: string;
  workspace_id: string;
  owner_user_id?: string | null;
  workflow_run_id?: string | null;
  file_name: string;
  file_type: string;
  storage_uri?: string | null;
  checksum: string;
  version: number;
  status: KnowledgeDocumentLifecycleStatus;
  parse_status: KnowledgeDocumentStatus;
  index_status: KnowledgeDocumentStatus;
  error_message?: string | null;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeSearchRequest {
  workspace_id?: string | null;
  query: string;
  scopes: KnowledgeScope[];
  top_k?: number;
  min_score?: number;
  mode?: RetrievalMode;
  filters?: Record<string, unknown>;
  enable_query_rewrite?: boolean;
  enable_multi_query?: boolean;
  enable_rerank?: boolean;
  enable_context_compression?: boolean;
  enable_conflict_detection?: boolean;
  workflow_run_id?: string | null;
  node_run_id?: string | null;
}

export interface RetrievalEvaluationCase {
  id?: string | null;
  query: string;
  expected_document_ids: string[];
  expected_chunk_ids: string[];
}

export interface RetrievalEvaluationRequest {
  cases: RetrievalEvaluationCase[];
  scopes: KnowledgeScope[];
  top_k?: number;
  min_score?: number;
  mode?: RetrievalMode;
  filters?: Record<string, unknown>;
  enable_query_rewrite?: boolean;
  enable_multi_query?: boolean;
  enable_rerank?: boolean;
  enable_context_compression?: boolean;
  enable_conflict_detection?: boolean;
}

export interface RetrievalEvaluationResponse {
  summary: {
    total_cases: number;
    hit_count: number;
    hit_rate: number;
    mean_reciprocal_rank: number;
    mean_precision_at_k: number;
    empty_expected_count: number;
  };
  results: Array<{
    case_id?: string | null;
    query: string;
    expected_document_ids: string[];
    expected_chunk_ids: string[];
    retrieved_document_ids: string[];
    retrieved_chunk_ids: string[];
    hit: boolean;
    first_relevant_rank?: number | null;
    reciprocal_rank: number;
    precision_at_k: number;
  }>;
}

export interface WorkflowTrace {
  workflow: Record<string, unknown>;
  nodes: Record<string, unknown>[];
  artifacts: Record<string, Record<string, unknown>>;
  timeline: TimelineEvent[];
}

export interface WorkflowEventSnapshot {
  workflow: WorkflowResponse;
  trace: WorkflowTrace;
}

export interface WorkflowTokenEvent {
  workflow_run_id: string;
  node: string;
  section_id?: string;
  section_title?: string;
  delta: string;
  mode?: 'generate' | 'refine' | string;
  timestamp?: string;
}

export interface WorkflowSectionEvent {
  workflow_run_id: string;
  node: string;
  section_id: string;
  section_title?: string;
  content_length?: number;
  mode?: 'generate' | 'refine' | string;
  timestamp?: string;
}

export interface WorkflowStreamErrorEvent {
  workflow_run_id: string;
  node: string;
  section_id?: string;
  section_title?: string;
  detail: string;
  mode?: 'generate' | 'refine' | string;
  timestamp?: string;
}

export interface WorkflowEventHandlers {
  onSnapshot?: (snapshot: WorkflowEventSnapshot) => void;
  onDone?: (payload: { workflow_run_id?: string; status?: WorkflowStatus | string }) => void;
  onError?: (error: Error) => void;
  onHeartbeat?: () => void;
  onToken?: (event: WorkflowTokenEvent) => void;
  onSectionStarted?: (event: WorkflowSectionEvent) => void;
  onSectionCompleted?: (event: WorkflowSectionEvent) => void;
  onStreamError?: (event: WorkflowStreamErrorEvent) => void;
}

export interface TimelineEvent {
  timestamp: string;
  event: string;
  node?: string;
  node_run_id?: string;
  artifact_id?: string;
  model?: string;
  tokens?: number;
  duration_ms?: number;
  status?: string;
  current_node?: string;
  gate_type?: WorkflowGateType;
  questions?: WorkflowGateQuestion[];
}

export interface WorkflowConnectedEvent {
  type: 'connected';
  workflow_run_id: string;
  message: string;
}

export interface WorkflowNodeEvent {
  type: 'node_started' | 'node_completed' | 'node_failed';
  workflow_run_id: string;
  node_id: string;
  data?: Record<string, unknown>;
}

export interface WorkflowLifecycleEvent {
  type: 'workflow_paused' | 'workflow_completed' | 'workflow_failed' | 'workflow_resumed';
  workflow_run_id: string;
  data?: Record<string, unknown>;
}

export interface WorkflowGateWaitingEvent {
  type: 'workflow_gate_waiting';
  workflow_run_id: string;
  data: {
    gate_type: WorkflowGateType;
    questions: WorkflowGateQuestion[];
    [key: string]: unknown;
  };
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description?: string | null;
  is_published?: boolean;
}

export interface WorkflowVersion {
  id: string;
  version: number;
  change_log?: string | null;
}

export interface ModelProviderSummary {
  id: string;
  provider: string;
  name: string;
  description: string | null;
  enabled: boolean;
  is_default: boolean;
  runtime_supported: boolean;
  config: {
    model?: string;
    model_name?: string;
    base_url?: string;
    api_key?: string;
    [key: string]: string | number | boolean | null | undefined;
  };
  created_at: string;
  updated_at: string;
}

export interface StartWorkflowOptions {
  modelProviderId?: string;
  modelName?: string;
  retrievalConfig?: RetrievalConfig;
  runUploadFiles?: File[];
}

export interface WorkflowRunSummary {
  id: string;
  workflow_name: string;
  status: WorkflowStatus | string;
  current_node: string | null;
  user_input: string;
  started_at: string;
  completed_at: string | null;
  total_duration_ms: number | null;
}

export interface RerunOption {
  node_name: string;
  node_run_id: string;
  status?: string;
  completed_at?: string | null;
  output_artifacts?: Record<string, unknown>[];
  can_rerun: boolean;
}

export interface RerunHistoryItem {
  id: string;
  workflow_name?: string;
  status?: WorkflowStatus | string;
  user_input?: string;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  metadata?: {
    is_rerun?: boolean;
    original_workflow_run_id?: string;
    rerun_from_node?: string;
    rerun_reason?: string;
    rerun_at?: string;
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
}

export interface RerunResponse {
  original_workflow_run_id: string;
  new_workflow_run_id: string;
  rerun_from_node: string;
  status: WorkflowStatus | string;
  state: WorkflowResponse['state'];
}

export type AuditOutcome = 'success' | 'failure' | 'unknown';

export interface AuditLogEntry {
  id: string;
  event_id: string;
  workspace_id: string;
  user_id: string;
  request_id: string | null;
  trace_id: string | null;
  span_id: string | null;
  event_category: string | null;
  event_type: string | null;
  action: string;
  outcome: AuditOutcome | string;
  target_type: string | null;
  target_id: string | null;
  actor_snapshot: Record<string, unknown>;
  target_snapshot: Record<string, unknown>;
  detail: Record<string, unknown>;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  schema_version: string;
  created_at: string | null;
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditLogQuery {
  page?: number;
  pageSize?: number;
  action?: string;
  outcome?: string;
  userId?: string;
  targetType?: string;
  targetId?: string;
  requestId?: string;
  startTime?: string;
  endTime?: string;
}

export type WorkflowRealtimeEvent =
  | WorkflowConnectedEvent
  | WorkflowNodeEvent
  | WorkflowLifecycleEvent
  | WorkflowGateWaitingEvent;

// API 请求函数
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = apiUrl(endpoint);

  const response = await authenticatedFetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

async function requestBlob(
  endpoint: string,
  options: RequestInit = {}
): Promise<Blob> {
  const url = apiUrl(endpoint);

  const response = await authenticatedFetch(url, {
    ...options,
    headers: {
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.blob();
}

// 统一 Result 包装类型
type ApiResult<T> = {
  code: number;
  message: string;
  data: T | null;
};

// 针对统一 Result 返回格式的请求函数
async function requestResult<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const result = await request<ApiResult<T>>(endpoint, options);

  if (result.code !== 0) {
    throw new Error(result.message || 'Request failed');
  }

  if (result.data == null) {
    throw new Error(result.message || 'Request returned empty data');
  }

  return result.data;
}

// 工作流定义 API
export const workflowDefinitionApi = {
  // 获取工作流列表（使用统一 Result 包装）
  list: () =>
    requestResult<{ workflows: WorkflowDefinition[] }>('/workflows'),

  // 获取首页匿名可见的已发布工作流列表（使用统一 Result 包装）
  listPublic: () =>
    requestResult<{ workflows: WorkflowDefinition[] }>('/workflows/public'),

  // 获取特定工作流的版本（使用统一 Result 包装）
  getVersions: (workflowId: string) =>
    requestResult<{ versions: WorkflowVersion[] }>(
      `/workflows/${workflowId}/versions`
    ),

  // 获取首页匿名可见工作流的已发布版本（使用统一 Result 包装）
  getPublicVersions: (workflowId: string) =>
    requestResult<{ versions: WorkflowVersion[] }>(
      `/workflows/public/${workflowId}/versions`
    ),
};

// 模型配置 API
export const modelProviderApi = {
  list: () =>
    request<{
      providers: ModelProviderSummary[];
      supported_providers: string[];
    }>('/admin/model-providers'),
};

// 工作流 API
export const workflowApi = {
  // 启动新工作流
  start: (
    userInput: string,
    workflowDefinitionId?: string,
    workflowVersionId?: string,
    options: StartWorkflowOptions = {}
  ) => {
    if (options.runUploadFiles?.length) {
      const formData = new FormData();
      formData.append('user_input', userInput);
      if (workflowDefinitionId) {
        formData.append('workflow_definition_id', workflowDefinitionId);
      }
      if (workflowVersionId) {
        formData.append('workflow_version_id', workflowVersionId);
      }
      if (options.modelProviderId) {
        formData.append('model_provider_id', options.modelProviderId);
      }
      if (options.modelName) {
        formData.append('model_name', options.modelName);
      }
      if (options.retrievalConfig) {
        formData.append('retrieval_config', JSON.stringify(options.retrievalConfig));
      }
      for (const file of options.runUploadFiles) {
        formData.append('files', file);
      }

      return authenticatedFetch(apiUrl('/workflow/start-with-uploads'), {
        method: 'POST',
        body: formData,
      }).then(async (response) => {
        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(error.detail || `HTTP ${response.status}`);
        }
        return response.json() as Promise<WorkflowResponse>;
      });
    }

    return request<WorkflowResponse>('/workflow/start', {
      method: 'POST',
      body: JSON.stringify({
        user_input: userInput,
        workflow_definition_id: workflowDefinitionId,
        workflow_version_id: workflowVersionId,
        model_provider_id: options.modelProviderId,
        model_name: options.modelName,
        retrieval_config: options.retrievalConfig,
      }),
    });
  },

  // 获取运行记录列表
    getRuns: () => request<{ runs: WorkflowRunSummary[] }>('/workflow/runs'),

  // 获取工作流状态
  getStatus: (workflowRunId: string) =>
    request<WorkflowResponse>(`/workflow/${workflowRunId}`),

  // 打开工作流详情页 SSE 快照流
  openEventStream: (workflowRunId: string, handlers: WorkflowEventHandlers = {}) => {
    const source = new EventSource(apiUrl(`/workflow/${workflowRunId}/events`), {
      withCredentials: true,
    });

    const parsePayload = <T>(event: MessageEvent<string>): T | null => {
      try {
        return JSON.parse(event.data) as T;
      } catch (error) {
        handlers.onError?.(
          error instanceof Error ? error : new Error('SSE 数据解析失败')
        );
        return null;
      }
    };

    source.addEventListener('snapshot', (event) => {
      const snapshot = parsePayload<WorkflowEventSnapshot>(
        event as MessageEvent<string>
      );
      if (snapshot) {
        handlers.onSnapshot?.(snapshot);
      }
    });

    source.addEventListener('done', (event) => {
      const payload = parsePayload<{ workflow_run_id?: string; status?: WorkflowStatus | string }>(
        event as MessageEvent<string>
      );
      if (payload) {
        handlers.onDone?.(payload);
      }
      source.close();
    });

    source.addEventListener('heartbeat', () => {
      handlers.onHeartbeat?.();
    });

    source.addEventListener('token', (event) => {
      const payload = parsePayload<WorkflowTokenEvent>(event as MessageEvent<string>);
      if (payload) {
        handlers.onToken?.(payload);
      }
    });

    source.addEventListener('section_started', (event) => {
      const payload = parsePayload<WorkflowSectionEvent>(event as MessageEvent<string>);
      if (payload) {
        handlers.onSectionStarted?.(payload);
      }
    });

    source.addEventListener('section_completed', (event) => {
      const payload = parsePayload<WorkflowSectionEvent>(event as MessageEvent<string>);
      if (payload) {
        handlers.onSectionCompleted?.(payload);
      }
    });

    source.addEventListener('stream_error', (event) => {
      const payload = parsePayload<WorkflowStreamErrorEvent>(event as MessageEvent<string>);
      if (payload) {
        handlers.onStreamError?.(payload);
      }
    });

    source.addEventListener('error', () => {
      handlers.onError?.(new Error('工作流实时连接已断开'));
      source.close();
    });

    return source;
  },

  // 审批提纲
  approveOutline: (
    workflowRunId: string,
    action: 'approve' | 'modify' | 'regenerate',
    feedback?: string,
    modifiedOutline?: Outline
  ) =>
    request<WorkflowResponse>(`/workflow/${workflowRunId}/approve-outline`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        feedback,
        modified_outline: modifiedOutline,
      }),
    }),

  // 澄清回答
  clarify: (workflowRunId: string, clarifications: Record<string, string>) =>
    request<WorkflowResponse>(`/workflow/${workflowRunId}/clarify`, {
      method: 'POST',
      body: JSON.stringify({ clarifications }),
    }),

  // 审批事实核查
  approveFactCheck: (
    workflowRunId: string,
    decisions: Record<string, FactCheckDecision>,
    manualCorrections: Record<string, string> = {}
  ) =>
    request<WorkflowResponse>(`/workflow/${workflowRunId}/approve-fact-check`, {
      method: 'POST',
      body: JSON.stringify({
        decisions,
        manual_corrections: manualCorrections,
      }),
    }),

  // 手动暂停
  pause: (workflowRunId: string, reason?: string) =>
    request<WorkflowResponse>(`/workflow/${workflowRunId}/pause`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  // 恢复手动暂停
  resume: (workflowRunId: string) =>
    request<WorkflowResponse>(`/workflow/${workflowRunId}/resume`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  // 获取重跑选项
  getRerunOptions: (workflowRunId: string) =>
    request<{ options: RerunOption[] }>(
      `/workflow/${workflowRunId}/rerun-options`
    ),

  // 获取重跑历史
  getRerunHistory: (workflowRunId: string) =>
    request<{ history: RerunHistoryItem[] }>(
      `/workflow/${workflowRunId}/rerun-history`
    ),

  // 执行重跑
  rerun: (
    workflowRunId: string,
    fromNode: string,
    updatedInput?: Record<string, unknown>,
    reason?: string
  ) =>
    request<RerunResponse>(`/workflow/${workflowRunId}/rerun`, {
      method: 'POST',
      body: JSON.stringify({
        from_node: fromNode,
        updated_input: updatedInput,
        reason,
      }),
    }),

  exportDocx: (workflowRunId: string) =>
    requestBlob(`/workflow/${workflowRunId}/exports/docx`),
};

// Trace API
export const traceApi = {
  // 获取工作流追踪
  getWorkflowTrace: (workflowRunId: string) =>
    request<WorkflowTrace>(`/trace/${workflowRunId}`),

  // 获取节点详情
  getNodeDetail: (nodeRunId: string) =>
    request<Record<string, unknown>>(`/trace/node/${nodeRunId}`),
};

// 审计日志 API
export const auditLogApi = {
  list: (query: AuditLogQuery = {}) => {
    const params = new URLSearchParams();
    params.set('page', String(query.page ?? 1));
    params.set('page_size', String(query.pageSize ?? 20));

    const optionalParams: Array<[string, string | undefined]> = [
      ['action', query.action],
      ['outcome', query.outcome],
      ['user_id_filter', query.userId],
      ['target_type', query.targetType],
      ['target_id', query.targetId],
      ['request_id', query.requestId],
      ['start_time', query.startTime],
      ['end_time', query.endTime],
    ];

    optionalParams.forEach(([key, value]) => {
      if (value?.trim()) {
        params.set(key, value.trim());
      }
    });

    return request<AuditLogListResponse>(`/admin/audit-logs?${params.toString()}`);
  },
};

// 知识库 API
export const knowledgeApi = {
  list: (workspaceId: string, scopes?: KnowledgeScope[]) => {
    const params = new URLSearchParams();
    if (scopes?.length) {
      params.set('scopes', scopes.join(','));
    }
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return request<{ knowledge_bases: KnowledgeBase[] }>(
      `/workspaces/${workspaceId}/knowledge-bases${suffix}`
    );
  },

  create: (
    workspaceId: string,
    body: { name: string; description?: string | null; scope: KnowledgeScope }
  ) =>
    request<KnowledgeBase>(`/workspaces/${workspaceId}/knowledge-bases`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  update: (
    knowledgeBaseId: string,
    body: { name?: string; description?: string | null; status?: KnowledgeBaseStatus }
  ) =>
    request<KnowledgeBase>(`/knowledge-bases/${knowledgeBaseId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  delete: (knowledgeBaseId: string) =>
    request<{ message: string }>(`/knowledge-bases/${knowledgeBaseId}`, {
      method: 'DELETE',
    }),

  listDocuments: (knowledgeBaseId: string) =>
    request<{ documents: KnowledgeDocument[] }>(
      `/knowledge-bases/${knowledgeBaseId}/documents`
    ),

  uploadDocument: (knowledgeBaseId: string, file: File, metadata?: Record<string, unknown>) => {
    const formData = new FormData();
    formData.append('file', file);
    if (metadata) {
      formData.append('metadata_json', JSON.stringify(metadata));
    }

    return authenticatedFetch(apiUrl(`/knowledge-bases/${knowledgeBaseId}/documents`), {
      method: 'POST',
      body: formData,
    }).then(async (response) => {
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      return response.json() as Promise<KnowledgeDocument>;
    });
  },

  deleteDocument: (documentId: string) =>
    request<{ message: string }>(`/documents/${documentId}`, {
      method: 'DELETE',
    }),

  reindexDocument: (documentId: string) =>
    request<KnowledgeDocument>(`/documents/${documentId}/reindex`, {
      method: 'POST',
    }),

  updateDocument: (documentId: string, body: { status: KnowledgeDocumentLifecycleStatus }) =>
    request<KnowledgeDocument>(`/documents/${documentId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  search: (body: KnowledgeSearchRequest) =>
    request<{ evidence_pack: EvidencePack; retrieval_log_id?: string | null }>(
      '/knowledge/search',
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    ),

  evaluate: (body: RetrievalEvaluationRequest) =>
    request<RetrievalEvaluationResponse>('/knowledge/evaluate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};

// Artifact API
export const artifactApi = {
  // 获取 Artifact
  get: (artifactId: string) =>
    request<Record<string, unknown>>(`/artifact/${artifactId}`),

  // 获取版本历史
  getHistory: (artifactId: string) =>
    request<{ history: Record<string, unknown>[] }>(
      `/artifact/${artifactId}/history`
    ),
};

// 健康检查
export const healthCheck = () =>
  fetch(serviceUrl('/'), {
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  }).then(async (response) => {
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json() as Promise<{ status: string; service: string; version: string }>;
  });
