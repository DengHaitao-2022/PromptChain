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
export type ApiErrorDomain =
  | 'AUTH'
  | 'WORKSPACE'
  | 'WORKFLOW'
  | 'TRACE'
  | 'ADMIN'
  | 'INFRA'
  | 'COMMON'
  | 'UNKNOWN';

export type ApiErrorDetails = Record<string, unknown> | unknown[] | null;

export interface ApiErrorOptions {
  code: string;
  message: string;
  requestId: string | null;
  details: ApiErrorDetails;
  status: number;
  cause?: unknown;
}

export class PromptChainApiError extends Error {
  code: string;
  requestId: string | null;
  details: ApiErrorDetails;
  status: number;
  domain: ApiErrorDomain;
  cause?: unknown;

  constructor(options: ApiErrorOptions) {
    super(options.message);
    this.name = 'PromptChainApiError';
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
    this.status = options.status;
    this.domain = getApiErrorDomain(options.code);
    this.cause = options.cause;
  }
}

export function getApiErrorDomain(code: string): ApiErrorDomain {
  const prefix = code.split('_')[0];
  if (
    prefix === 'AUTH' ||
    prefix === 'WORKSPACE' ||
    prefix === 'WORKFLOW' ||
    prefix === 'TRACE' ||
    prefix === 'ADMIN' ||
    prefix === 'INFRA' ||
    prefix === 'COMMON'
  ) {
    return prefix;
  }

  return 'UNKNOWN';
}

export function isPromptChainApiError(error: unknown): error is PromptChainApiError {
  return error instanceof PromptChainApiError;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function normalizeDetails(value: unknown, code: string): ApiErrorDetails {
  if (code.startsWith('INFRA_')) {
    // 基础设施 details 可能包含内部依赖信息，客户端只保留错误码作为稳定判断依据。
    return null;
  }

  if (isRecord(value) || Array.isArray(value)) {
    return value;
  }

  return null;
}

function getRequestId(response: Response, payload: unknown): string | null {
  if (isRecord(payload)) {
    const requestId = asString(payload.request_id) ?? asString(payload.requestId);
    if (requestId) {
      return requestId;
    }
  }

  return response.headers.get('x-request-id');
}

function getLegacyMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return '请求参数校验失败';
  }

  if (isRecord(detail)) {
    return asString(detail.message) ?? asString(detail.detail);
  }

  return null;
}

async function readResponsePayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    return response.json().catch(() => null);
  }

  const text = await response.text().catch(() => '');
  return text.trim() ? text : null;
}

async function createApiError(response: Response): Promise<PromptChainApiError> {
  const payload = await readResponsePayload(response);

  if (isRecord(payload) && payload.success === false && typeof payload.code === 'string') {
    const message = asString(payload.message) ?? `HTTP ${response.status}`;
    return new PromptChainApiError({
      code: payload.code,
      message,
      requestId: getRequestId(response, payload),
      details: normalizeDetails(payload.details, payload.code),
      status: response.status,
    });
  }

  const legacyDetail = isRecord(payload) ? payload.detail : null;
  const legacyMessage =
    (isRecord(payload) ? asString(payload.message) : null) ??
    getLegacyMessage(legacyDetail) ??
    (typeof payload === 'string' && payload.trim() ? payload : null) ??
    `HTTP ${response.status}`;
  const fallbackCode = response.status === 401 ? 'AUTH_UNAUTHENTICATED' : 'COMMON_HTTP_ERROR';
  const code = isRecord(payload) ? asString(payload.code) ?? fallbackCode : fallbackCode;

  return new PromptChainApiError({
    code,
    message: legacyMessage,
    requestId: getRequestId(response, payload),
    details: normalizeDetails(legacyDetail, code),
    status: response.status,
  });
}

function createNetworkApiError(error: unknown): PromptChainApiError {
  return new PromptChainApiError({
    code: 'INFRA_NETWORK_ERROR',
    message: error instanceof Error && error.message ? error.message : '网络请求失败',
    requestId: null,
    details: null,
    status: 0,
    cause: error,
  });
}

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

export interface VerificationResult {
  claim_id: string;
  is_verified: boolean;
  confidence: number;
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
  high_risk_count: number;
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

  let response: Response;
  try {
    response = await authenticatedFetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });
  } catch (error) {
    throw createNetworkApiError(error);
  }

  if (!response.ok) {
    throw await createApiError(response);
  }

  return response.json();
}

async function requestBlob(
  endpoint: string,
  options: RequestInit = {}
): Promise<Blob> {
  const url = apiUrl(endpoint);

  let response: Response;
  try {
    response = await authenticatedFetch(url, {
      ...options,
      headers: {
        ...options.headers,
      },
    });
  } catch (error) {
    throw createNetworkApiError(error);
  }

  if (!response.ok) {
    throw await createApiError(response);
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
    throw new PromptChainApiError({
      code: `COMMON_RESULT_${result.code}`,
      message: result.message || '请求失败',
      requestId: null,
      details: null,
      status: 200,
    });
  }

  if (result.data == null) {
    throw new PromptChainApiError({
      code: 'COMMON_EMPTY_DATA',
      message: result.message || '响应数据为空',
      requestId: null,
      details: null,
      status: 200,
    });
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
  ) =>
    request<WorkflowResponse>('/workflow/start', {
      method: 'POST',
      body: JSON.stringify({
        user_input: userInput,
        workflow_definition_id: workflowDefinitionId,
        workflow_version_id: workflowVersionId,
        model_provider_id: options.modelProviderId,
        model_name: options.modelName,
      }),
    }),

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
  }).catch((error) => {
    throw createNetworkApiError(error);
  }).then(async (response) => {
    if (!response.ok) {
      throw await createApiError(response);
    }

    return response.json() as Promise<{ status: string; service: string; version: string }>;
  });
