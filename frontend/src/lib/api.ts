/**
 * PromptChain API 客户端
 *
 * 与后端 FastAPI 通信的统一接口
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ===== 统一错误系统 =====

export type ApiErrorCode = string;

export type ApiErrorAction =
  | 'reauthenticate'
  | 'forbidden'
  | 'not_found'
  | 'retry_later'
  | 'contact_admin'
  | 'fix_input'
  | 'unknown';

export interface ApiErrorEnvelope {
  success: false;
  code: ApiErrorCode;
  message: string;
  request_id: string;
  details?: Record<string, unknown> | unknown[];
  data: null;
}

export class ApiClientError extends Error {
  public code: ApiErrorCode;
  public action: ApiErrorAction;
  public httpStatus: number;
  public requestId: string;
  public details?: Record<string, unknown> | unknown[];
  public isRetryable: boolean;

  constructor(
    message: string,
    code: ApiErrorCode,
    action: ApiErrorAction,
    httpStatus: number,
    requestId: string = '',
    details?: Record<string, unknown> | unknown[]
  ) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
    this.action = action;
    this.httpStatus = httpStatus;
    this.requestId = requestId;
    this.details = details;
    this.isRetryable = action === 'retry_later';
  }
}

function isUnifiedErrorEnvelope(payload: unknown): payload is ApiErrorEnvelope {
  if (typeof payload !== 'object' || payload === null) return false;
  const obj = payload as Record<string, unknown>;
  return (
    obj.success === false &&
    typeof obj.code === 'string' &&
    typeof obj.message === 'string'
  );
}

function isLegacyResultEnvelope(payload: unknown): boolean {
  if (typeof payload !== 'object' || payload === null) return false;
  const obj = payload as Record<string, unknown>;
  return (
    typeof obj.code === 'number' &&
    obj.code !== 0 &&
    typeof obj.message === 'string'
  );
}

function resolveErrorAction(code: string, status: number): ApiErrorAction {
  if (code.startsWith('AUTH_')) {
    if (
      [
        'AUTH_UNAUTHENTICATED',
        'AUTH_INVALID_CREDENTIALS',
        'AUTH_EMAIL_NOT_VERIFIED',
        'AUTH_ACCOUNT_SUSPENDED',
        'AUTH_LOGIN_LOCKED',
      ].includes(code)
    ) {
      return 'reauthenticate';
    }
  }

  if (code === 'WORKSPACE_ACCESS_DENIED') return 'forbidden';
  if (code.endsWith('_NOT_FOUND')) return 'not_found';
  if (code.startsWith('INFRA_')) return 'retry_later';
  if (code === 'COMMON_BAD_REQUEST') return 'fix_input';

  if (status >= 500) return 'contact_admin';
  if (status === 401) return 'reauthenticate';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 400) return 'fix_input';

  return 'unknown';
}

export async function parseApiErrorResponse(response: Response): Promise<ApiClientError> {
  const status = response.status;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return new ApiClientError(
      `HTTP ${status} Error`,
      'UNKNOWN_ERROR',
      resolveErrorAction('UNKNOWN_ERROR', status),
      status
    );
  }

  // 1. 优先处理统一的新版错误 envelope
  if (isUnifiedErrorEnvelope(payload)) {
    return new ApiClientError(
      payload.message,
      payload.code,
      resolveErrorAction(payload.code, status),
      status,
      payload.request_id,
      payload.details as Record<string, unknown> | unknown[] | undefined
    );
  }

  // 2. 兼容旧版 Result 返回，将 code 非 0 包装为 ApiClientError
  if (isLegacyResultEnvelope(payload)) {
    const obj = payload as Record<string, unknown>;
    return new ApiClientError(
      (obj.message as string) || 'Legacy Error',
      `LEGACY_ERROR_${obj.code}`,
      resolveErrorAction(`LEGACY_ERROR_${obj.code}`, status),
      status,
      '',
      obj.data as Record<string, unknown> | unknown[] | undefined
    );
  }

  // 3. Fallback 兜底纯文本 detail
  let message = `HTTP Error ${status}`;
  let details: unknown = undefined;

  const obj = (typeof payload === 'object' && payload !== null) ? (payload as Record<string, unknown>) : {};

  if ('detail' in obj) {
    if (typeof obj.detail === 'string') {
      message = obj.detail;
    } else {
      message = 'Validation Error';
      details = obj.detail;
    }
  } else if ('message' in obj && typeof obj.message === 'string') {
    message = obj.message;
  }

  return new ApiClientError(
    message,
    'UNCLASSIFIED_ERROR',
    resolveErrorAction('UNCLASSIFIED_ERROR', status),
    status,
    '',
    details as Record<string, unknown> | unknown[] | undefined
  );
}

// ===== 类型定义 =====
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
    intent_card?: IntentCard;
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

export interface TimelineEvent {
  timestamp: string;
  event: string;
  node?: string;
  artifact_id?: string;
  model?: string;
  tokens?: number;
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

export type WorkflowRealtimeEvent =
  | WorkflowConnectedEvent
  | WorkflowNodeEvent
  | WorkflowLifecycleEvent
  | WorkflowGateWaitingEvent;

// ===== API 请求函数 =====

export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
    ...options,
  });

  if (!response.ok) {
    throw await parseApiErrorResponse(response);
  }

  // Handle successful status codes that contain error envelopes
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    // If it's not JSON but OK, just return null or empty (this might not be perfectly safe but works if APIs return valid JSON)
    return {} as T;
  }

  if (isUnifiedErrorEnvelope(payload)) {
    throw new ApiClientError(
      payload.message,
      payload.code,
      resolveErrorAction(payload.code, response.status),
      response.status,
      payload.request_id,
      payload.details as Record<string, unknown> | unknown[] | undefined
    );
  }

  if (isLegacyResultEnvelope(payload)) {
    const obj = payload as Record<string, unknown>;
    throw new ApiClientError(
      (obj.message as string) || 'Legacy Error',
      `LEGACY_ERROR_${obj.code}`,
      resolveErrorAction(`LEGACY_ERROR_${obj.code}`, response.status),
      response.status,
      '',
      obj.data as Record<string, unknown> | unknown[] | undefined
    );
  }

  return payload as T;
}

// 统一 Result 包装类型
type ApiResult<T> = {
  code: number;
  message: string;
  data: T | null;
};

// 针对统一 Result 返回格式的请求函数
export async function requestResult<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  // request 会处理 HTTP 非 ok，以及 envelope 内嵌错误格式的情况
  // 正常会拿到 { code: 0, message: "xxx", data: T } 的结果
  const result = await request<ApiResult<T>>(endpoint, options);

  // 针对仍然是 Result 格式的兼容（如果未在 request() 里被识别出来）
  if (result.code !== undefined && result.code !== 0) {
    throw new ApiClientError(
      result.message || 'Request failed',
      `LEGACY_ERROR_${result.code}`,
      resolveErrorAction(`LEGACY_ERROR_${result.code}`, 200),
      200,
      '',
      result.data as Record<string, unknown> | unknown[] | undefined
    );
  }

  if (result.data == null) {
    throw new ApiClientError(
      result.message || 'Request returned empty data',
      'EMPTY_DATA',
      'unknown',
      200
    );
  }

  return result.data;
}

// 工作流定义 API
export const workflowDefinitionApi = {
  // 获取工作流列表（使用统一 Result 包装）
  list: () =>
    requestResult<{ workflows: WorkflowDefinition[] }>('/api/workflows'),

  // 获取特定工作流的版本（使用统一 Result 包装）
  getVersions: (workflowId: string) =>
    requestResult<{ versions: WorkflowVersion[] }>(
      `/api/workflows/${workflowId}/versions`
    ),
};

// 工作流 API
export const workflowApi = {
  // 启动新工作流
  start: (userInput: string, workflowDefinitionId?: string, workflowVersionId?: string) =>
    request<WorkflowResponse>('/api/workflow/start', {
      method: 'POST',
      body: JSON.stringify({
        user_input: userInput,
        workflow_definition_id: workflowDefinitionId,
        workflow_version_id: workflowVersionId,
      }),
    }),

  // 获取运行记录列表
  getRuns: () => request<{ data: { runs: WorkflowRunSummary[] } }>('/api/workflow/runs'),

  // 获取工作流状态
  getStatus: (workflowRunId: string) =>
    request<WorkflowResponse>(`/api/workflow/${workflowRunId}`),

  // 审批提纲
  approveOutline: (
    workflowRunId: string,
    action: 'approve' | 'modify' | 'regenerate',
    feedback?: string,
    modifiedOutline?: Outline
  ) =>
    request<WorkflowResponse>(`/api/workflow/${workflowRunId}/approve-outline`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        feedback,
        modified_outline: modifiedOutline,
      }),
    }),

  // 澄清回答
  clarify: (workflowRunId: string, clarifications: Record<string, string>) =>
    request<WorkflowResponse>(`/api/workflow/${workflowRunId}/clarify`, {
      method: 'POST',
      body: JSON.stringify({ clarifications }),
    }),

  // 审批事实核查
  approveFactCheck: (
    workflowRunId: string,
    decisions: Record<string, FactCheckDecision>,
    manualCorrections: Record<string, string> = {}
  ) =>
    request<WorkflowResponse>(`/api/workflow/${workflowRunId}/approve-fact-check`, {
      method: 'POST',
      body: JSON.stringify({
        decisions,
        manual_corrections: manualCorrections,
      }),
    }),

  // 手动暂停
  pause: (workflowRunId: string, reason?: string) =>
    request<WorkflowResponse>(`/api/workflow/${workflowRunId}/pause`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  // 恢复手动暂停
  resume: (workflowRunId: string) =>
    request<WorkflowResponse>(`/api/workflow/${workflowRunId}/resume`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  // 获取重跑选项
  getRerunOptions: (workflowRunId: string) =>
    request<{ options: Record<string, unknown>[] }>(
      `/api/workflow/${workflowRunId}/rerun-options`
    ),

  // 执行重跑
  rerun: (
    workflowRunId: string,
    fromNode: string,
    updatedInput?: Record<string, unknown>,
    reason?: string
  ) =>
    request<Record<string, unknown>>(`/api/workflow/${workflowRunId}/rerun`, {
      method: 'POST',
      body: JSON.stringify({
        from_node: fromNode,
        updated_input: updatedInput,
        reason,
      }),
    }),
};

// Trace API
export const traceApi = {
  // 获取工作流追踪
  getWorkflowTrace: (workflowRunId: string) =>
    request<WorkflowTrace>(`/api/trace/${workflowRunId}`),

  // 获取节点详情
  getNodeDetail: (nodeRunId: string) =>
    request<Record<string, unknown>>(`/api/trace/node/${nodeRunId}`),
};

// Artifact API
export const artifactApi = {
  // 获取 Artifact
  get: (artifactId: string) =>
    request<Record<string, unknown>>(`/api/artifact/${artifactId}`),

  // 获取版本历史
  getHistory: (artifactId: string) =>
    request<{ history: Record<string, unknown>[] }>(
      `/api/artifact/${artifactId}/history`
    ),
};

// 健康检查
export const healthCheck = () =>
  request<{ status: string; service: string; version: string }>('/');
