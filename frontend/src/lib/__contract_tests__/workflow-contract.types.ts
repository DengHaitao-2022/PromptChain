import { workflowApi, type WorkflowResponse } from '@/lib/api';

/**
 * 契约类型自动化校验 (Type-level test)
 * 如果后端契约变更导致类型不匹配，此处 tsc 将报错
 */

// 1. 验证 WorkflowResponse 骨架
const assertResponse = (r: WorkflowResponse) => r;

// 验证所有枚举状态
assertResponse({ workflow_run_id: 'wf_1', status: 'running', state: {} });
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
    ]
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
