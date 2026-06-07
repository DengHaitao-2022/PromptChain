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
export type WorkflowGateType =
  | 'clarification'
  | 'outline_approval'
  | 'fact_check'
  | 'tool_risk_approval';
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

function legacyResultStatus(code: number): number {
  if (code >= 50000) {
    return 500;
  }
  if (code >= 40900) {
    return 409;
  }
  if (code >= 40400) {
    return 404;
  }
  if (code >= 40300) {
    return 403;
  }
  if (code >= 40100) {
    return 401;
  }
  return 400;
}

function createApiErrorFromEnvelope(
  payload: Record<string, unknown>,
  fallbackStatus: number
): PromptChainApiError | null {
  const code = asString(payload.code);
  if (!code) {
    return null;
  }

  return new PromptChainApiError({
    code,
    message: asString(payload.message) ?? code,
    requestId: asString(payload.request_id) ?? asString(payload.requestId),
    details: normalizeDetails(payload.details, code),
    status:
      typeof payload.status === 'number' && Number.isFinite(payload.status)
        ? payload.status
        : fallbackStatus,
  });
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
    const requestId = getRequestId(response, payload);
    return (
      createApiErrorFromEnvelope(
        {
          ...payload,
          request_id: requestId,
          status: response.status,
        },
        response.status
      ) ??
      new PromptChainApiError({
        code: 'COMMON_HTTP_ERROR',
        message: `HTTP ${response.status}`,
        requestId,
        details: null,
        status: response.status,
      })
    );
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
  questions?: WorkflowGateQuestion[];
  answers?: Record<string, unknown> | null;
  opened_at?: string | null;
  handled_at?: string | null;
  waiting_duration_ms?: number | null;
  resolution?: string | null;
  tool_call_id?: string;
  tool_name?: string;
  risk_level?: string;
  reason?: string | null;
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

export interface KnowledgeUsageStats {
  workspace_id: string;
  total_searches: number;
  total_chunks_returned: number;
  average_chunks_per_search: number;
  conflict_search_count: number;
  unverified_search_count: number;
  last_search_at?: string | null;
  scope_counts: Record<string, number>;
  mode_counts: Record<string, number>;
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

export interface WorkflowAppErrorEvent {
  success?: false;
  code: string;
  message: string;
  request_id?: string | null;
  requestId?: string | null;
  details?: ApiErrorDetails;
  data?: null;
  status?: number;
  workflow_run_id?: string;
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
    questions?: WorkflowGateQuestion[];
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

export type AgentRunStatus =
  | 'planning'
  | 'running'
  | 'paused'
  | 'awaiting_gate'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface AgentRun {
  id: string;
  user_id: string;
  workspace_id: string;
  goal: string;
  status: AgentRunStatus;
  autonomy_level: string;
  budget_limit: Record<string, unknown>;
  current_plan_id: string | null;
  current_step_id: string | null;
  final_artifact_id: string | null;
  gate: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentPlanNode {
  id: string;
  title: string;
  step_type: string;
  description: string;
  depends_on: string[];
  tool_name?: string | null;
  expected_output: string;
  acceptance_criteria: string[];
  risk_level: string;
  status: string;
}

export interface AgentPlan {
  id: string;
  run_id: string;
  version: number;
  status: string;
  goal_card: {
    goal: string;
    task_type: string;
    constraints: string[];
    deliverables: string[];
    risk_boundaries: string[];
    success_criteria: string[];
    quality_dimensions: string[];
    uncertainty_questions: string[];
  };
  plan_graph: {
    nodes: AgentPlanNode[];
    edges: Array<{ source: string; target: string; condition?: string | null }>;
    quality_gates: Record<string, unknown>[];
    max_steps: number;
    max_replans: number;
  };
  created_by: string;
  reason: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AgentStep {
  id: string;
  run_id: string;
  plan_id: string;
  node_id: string;
  parent_step_id: string | null;
  step_type: string;
  title: string;
  description: string;
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  artifact_ids: string[];
  started_at: string | null;
  ended_at: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentToolCall {
  id: string;
  run_id: string;
  step_id: string | null;
  tool_name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  status: string;
  risk_level: string;
  error_message: string | null;
  latency_ms: number | null;
  cost: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentEvalResult {
  id: string;
  run_id: string;
  step_id: string | null;
  target_type: string;
  score: number;
  passed: boolean;
  issues: Record<string, unknown>[];
  suggestions: Record<string, unknown>[];
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AgentMemory {
  id: string;
  workspace_id: string;
  run_id: string | null;
  memory_type: string;
  content: string;
  embedding_id: string | null;
  source_trace_id: string | null;
  confidence: number;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AgentReplanRecord {
  id: string;
  run_id: string;
  old_plan_id: string;
  new_plan_id: string;
  trigger_reason: string;
  failed_step_id: string | null;
  reflection: Record<string, unknown>;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AgentToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  risk_level: string;
  permission: string;
  idempotent: boolean;
}

export interface AgentRunDetail {
  run: AgentRun;
  plans: AgentPlan[];
  steps: AgentStep[];
  tool_calls: AgentToolCall[];
  eval_results: AgentEvalResult[];
  replan_records: AgentReplanRecord[];
  memories: AgentMemory[];
  tool_definitions: AgentToolDefinition[];
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
    const code = `COMMON_RESULT_${result.code}`;
    throw new PromptChainApiError({
      code,
      message: result.message || '请求失败',
      requestId: null,
      details: normalizeDetails(result.data, code),
      status: legacyResultStatus(result.code),
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

    source.addEventListener('app_error', (event) => {
      const payload = parsePayload<WorkflowAppErrorEvent>(event as MessageEvent<string>);
      if (!payload || !isRecord(payload)) {
        return;
      }

      const errorPayload: Record<string, unknown> = payload;
      const apiError =
        createApiErrorFromEnvelope(errorPayload, payload.status ?? 500) ??
        new PromptChainApiError({
          code: 'COMMON_HTTP_ERROR',
          message: '工作流实时连接返回错误',
          requestId: null,
          details: null,
          status: 500,
        });
      handlers.onError?.(apiError);
      source.close();
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

// Autonomous Agent API
export const agentApi = {
  start: (goal: string, options: { autoExecute?: boolean; autonomyLevel?: string; budgetLimit?: Record<string, unknown>; plannerMode?: string; modelProviderId?: string; modelProviderName?: string; modelName?: string } = {}) =>
    request<AgentRunDetail>('/agents/runs', {
      method: 'POST',
      body: JSON.stringify({
        goal,
        auto_execute: options.autoExecute ?? true,
        autonomy_level: options.autonomyLevel ?? 'supervised',
        budget_limit: options.budgetLimit ?? {},
        planner_mode: options.plannerMode ?? 'auto',
        model_provider_id: options.modelProviderId,
        model_provider_name: options.modelProviderName,
        model_name: options.modelName,
      }),
    }),

  getRuns: () => request<{ runs: AgentRun[] }>('/agents/runs'),

  getDetail: (runId: string) => request<AgentRunDetail>(`/agents/runs/${runId}`),

  resume: (runId: string) =>
    request<AgentRunDetail>(`/agents/runs/${runId}/resume`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  pause: (runId: string, reason = '') =>
    request<AgentRunDetail>(`/agents/runs/${runId}/pause`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  cancel: (runId: string, reason = '') =>
    request<AgentRunDetail>(`/agents/runs/${runId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  clarify: (runId: string, clarification: string) =>
    request<AgentRunDetail>(`/agents/runs/${runId}/clarify`, {
      method: 'POST',
      body: JSON.stringify({ clarification }),
    }),

  updatePlan: (runId: string, planGraph: AgentPlan['plan_graph'], reason = 'human_plan_edit') =>
    request<AgentRunDetail>(`/agents/runs/${runId}/plan`, {
      method: 'PUT',
      body: JSON.stringify({ plan_graph: planGraph, reason }),
    }),

  skipNode: (runId: string, nodeId: string, reason = 'human_skip_node') =>
    request<AgentRunDetail>(`/agents/runs/${runId}/skip-node`, {
      method: 'POST',
      body: JSON.stringify({ node_id: nodeId, reason }),
    }),

  decideGate: (runId: string, approved: boolean, note = '') =>
    request<AgentRunDetail>(`/agents/runs/${runId}/gate`, {
      method: 'POST',
      body: JSON.stringify({ approved, note }),
    }),

  getTools: () => request<{ tools: AgentToolDefinition[] }>('/agents/tools'),
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

  stats: () => request<KnowledgeUsageStats>('/knowledge/stats'),
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
