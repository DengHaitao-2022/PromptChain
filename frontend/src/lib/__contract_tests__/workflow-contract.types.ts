import {
  ApiClientError,
  parseApiErrorResponse,
  request,
  requestResult,
  workflowDefinitionApi,
  workflowApi,
  type ApiErrorAction,
  type ApiErrorEnvelope,
  type WorkflowRealtimeEvent,
  type WorkflowDefinition,
  type WorkflowResponse
} from '@/lib/api';

/**
 * 契约类型自动化校验 (Type-level test)
 * 如果后端契约变更导致类型不匹配，此处 tsc 将报错
 */

// 1. 验证 WorkflowResponse 骨架
const assertResponse = (r: WorkflowResponse) => r;

// 验证所有枚举状态
assertResponse({ workflow_run_id: 'wf_1', status: 'running', state: {} });
assertResponse({ workflow_run_id: 'wf_1', status: 'paused', state: {} });
assertResponse({ workflow_run_id: 'wf_1', status: 'needs_clarification', state: {} });
assertResponse({ workflow_run_id: 'wf_1', status: 'awaiting_outline_approval', state: {} });
assertResponse({ workflow_run_id: 'wf_1', status: 'awaiting_fact_check_approval', state: {} });
assertResponse({ workflow_run_id: 'wf_1', status: 'completed', state: {} });
assertResponse({ workflow_run_id: 'wf_1', status: 'failed', state: {} });

// 2. 验证 state 内部统一字段
assertResponse({
  workflow_run_id: 'wf_1',
  status: 'needs_clarification',
  state: {
    clarification_questions: [
      {
        field: 'target_audience',
        question: 'Who is the audience?',
        priority: 'high',
        default_assumption: 'General'
      }
    ],
    gate: {
      gate_type: 'clarification',
      questions: [
        {
          field: 'target_audience',
          question: 'Who is the audience?'
        }
      ]
    }
  }
});

assertResponse({
  workflow_run_id: 'wf_1',
  status: 'paused',
  state: {
    current_node: 'generate_content',
    pause: {
      reason: '人工暂停',
      paused_at: '2026-03-08T10:00:00Z'
    }
  }
});

const assertRealtimeEvent = (event: WorkflowRealtimeEvent) => event;

assertRealtimeEvent({
  type: 'workflow_gate_waiting',
  workflow_run_id: 'wf_1',
  data: {
    gate_type: 'fact_check',
    questions: []
  }
});

assertRealtimeEvent({
  type: 'workflow_resumed',
  workflow_run_id: 'wf_1',
  data: {
    resumed_at: '2026-03-08T10:05:00Z'
  }
});

// 3. 验证 approveFactCheck 方法签名
// @ts-expect-error: 缺少必要参数
workflowApi.approveFactCheck('wf_123');

// 正常调用
workflowApi.approveFactCheck(
  'wf_123',
  { 'claim_1': 'confirm', 'claim_2': 'manual' },
  { 'claim_2': 'Corrected text' }
);

// 最小调用
workflowApi.approveFactCheck('wf_123', { 'claim_1': 'use_suggestion' });

// 4. 验证 pause / resume 方法签名
// @ts-expect-error: 缺少 workflowRunId
workflowApi.pause();

workflowApi.pause('wf_123');
workflowApi.pause('wf_123', '人工暂停');
workflowApi.resume('wf_123');

// 5. 验证统一错误 envelope 与 typed client error
const assertApiErrorAction = (action: ApiErrorAction) => action;
assertApiErrorAction('reauthenticate');
assertApiErrorAction('forbidden');
assertApiErrorAction('not_found');
assertApiErrorAction('retry_later');
assertApiErrorAction('contact_admin');
assertApiErrorAction('fix_input');
assertApiErrorAction('unknown');

const assertErrorEnvelope = (error: ApiErrorEnvelope) => error;
assertErrorEnvelope({
  success: false,
  code: 'WORKFLOW_VALIDATION_FAILED',
  message: '工作流未通过发布校验',
  request_id: 'req-type-contract-001',
  details: null,
  data: null
});

const clientError = new ApiClientError(
  '请先登录后再继续',
  'AUTH_UNAUTHENTICATED',
  'reauthenticate',
  401,
  'req-type-contract-002',
  null
);

clientError.code satisfies string;
clientError.action satisfies ApiErrorAction;
clientError.httpStatus satisfies number;
clientError.requestId satisfies string;
clientError.isRetryable satisfies boolean;

parseApiErrorResponse(new Response('{}', { status: 500 })) satisfies Promise<ApiClientError>;
request<WorkflowResponse>('/api/workflow/wf_1') satisfies Promise<WorkflowResponse>;
requestResult<{ workflows: WorkflowDefinition[] }>('/api/workflows') satisfies Promise<{
  workflows: WorkflowDefinition[];
}>;
workflowDefinitionApi.list() satisfies Promise<{ workflows: WorkflowDefinition[] }>;
