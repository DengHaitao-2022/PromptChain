# Workflow Contract v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 以 Design-first 方式完成 workflow 运行态 API 契约统一、澄清字段统一、事实核查审批闭环，并产出可持续维护的 OpenAPI + Markdown 文档基线。

**Architecture:** 以 `docs/api/openapi.v1.yaml` 作为单一契约源，后端接口按契约输出统一 `WorkflowResponse`，前端仅消费规范字段（特别是 `state.clarification_questions` 与事实核查审批接口）。通过后端契约测试 + 前端类型检查确保实现与规范一致。

**Tech Stack:** FastAPI, Pydantic v2, LangGraph, pytest/pytest-asyncio, Next.js 16, TypeScript, ESLint, OpenAPI 3.1

---

### Task 1: 统一 WorkflowResponse 契约（start/getStatus）

**Files:**
- Create: `backend/tests/test_workflow_response_contract.py`
- Modify: `backend/main.py`
- Optional Create: `backend/models/api_contracts.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_workflow_response_contract.py

def test_get_workflow_status_returns_workflow_response_shape(client, monkeypatch):
    # mock store.get_workflow_run -> returns object with id/status
    # mock workflow graph state -> contains clarification_questions
    res = client.get('/api/workflow/wf-123')
    body = res.json()
    assert set(body.keys()) == {'workflow_run_id', 'status', 'state'}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_workflow_response_contract.py::test_get_workflow_status_returns_workflow_response_shape -v`
Expected: FAIL（当前 `GET /api/workflow/{id}` 返回 `WorkflowRun.model_dump()`）

**Step 3: Write minimal implementation**

```python
# backend/main.py
class WorkflowResponse(BaseModel):
    workflow_run_id: str
    status: str
    state: Dict[str, Any]

async def _build_workflow_response(workflow_run_id: str, state: dict, workflow) -> WorkflowResponse:
    simplified_state = _simplify_state(state)
    return WorkflowResponse(
        workflow_run_id=workflow_run_id,
        status=workflow._get_workflow_status(state),
        state=simplified_state,
    )
```

并将 `GET /api/workflow/{workflow_run_id}` 改为返回上述结构。

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_workflow_response_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_workflow_response_contract.py backend/models/api_contracts.py
git commit -m "feat(api): unify workflow response contract"
```

Reference skill: `@test-driven-development`

### Task 2: 打通事实核查审批接口闭环

**Files:**
- Create: `backend/tests/test_fact_check_approval_api.py`
- Modify: `backend/main.py`
- Modify: `backend/graph/content_generation_graph.py`

**Step 1: Write the failing test**

```python
def test_approve_fact_check_endpoint_exists_and_resumes_workflow(client, monkeypatch):
    payload = {
        'decisions': {'c1': 'confirm'},
        'manual_corrections': {}
    }
    res = client.post('/api/workflow/wf-123/approve-fact-check', json=payload)
    assert res.status_code == 200
    assert res.json()['status'] in {'running', 'completed'}
```

另写一个状态测试：`awaiting_fact_check_approval=True` 时 `_get_workflow_status` 必须返回该状态。

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_fact_check_approval_api.py -v`
Expected: FAIL（当前无该路由，且 `_get_workflow_status` 无此分支）

**Step 3: Write minimal implementation**

```python
# backend/main.py
class ApproveFactCheckRequest(BaseModel):
    decisions: Dict[str, str]
    manual_corrections: Dict[str, str] = {}

@app.post('/api/workflow/{workflow_run_id}/approve-fact-check', response_model=WorkflowResponse)
async def approve_fact_check_http(workflow_run_id: str, request: ApproveFactCheckRequest):
    workflow = get_workflow()
    result = await workflow.resume(workflow_run_id, {
        'fact_check_decisions': request.decisions,
        'manual_corrections': request.manual_corrections,
        'awaiting_fact_check_approval': False,
    })
    return WorkflowResponse(
        workflow_run_id=result['workflow_run_id'],
        status=result['status'],
        state=_simplify_state(result['state']),
    )
```

```python
# backend/graph/content_generation_graph.py
if state.get('awaiting_fact_check_approval'):
    return 'awaiting_fact_check_approval'
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_fact_check_approval_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/main.py backend/graph/content_generation_graph.py backend/tests/test_fact_check_approval_api.py
git commit -m "feat(api): add fact-check approval endpoint and status"
```

Reference skill: `@test-driven-development`

### Task 3: 统一澄清字段语义与优先级映射

**Files:**
- Create: `backend/tests/test_clarification_contract.py`
- Modify: `backend/main.py`

**Step 1: Write the failing test**

```python
def test_clarification_questions_are_exposed_with_enum_priority(client, monkeypatch):
    res = client.get('/api/workflow/wf-clarify')
    q = res.json()['state']['clarification_questions'][0]
    assert q['priority'] in {'high', 'medium', 'low'}
    assert 'field' in q and 'question' in q
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_clarification_contract.py -v`
Expected: FAIL（当前可能是数值优先级或字段未统一）

**Step 3: Write minimal implementation**

```python
def _map_priority(level: int) -> str:
    if level <= 2:
        return 'high'
    if level == 3:
        return 'medium'
    return 'low'

def _normalize_clarification_questions(items: list[dict]) -> list[dict]:
    return [
        {
            'field': q.get('field'),
            'question': q.get('question'),
            'priority': _map_priority(int(q.get('priority', 5))),
            'default_assumption': q.get('default_assumption'),
        }
        for q in items
    ]
```

在 `_simplify_state` 或统一 response builder 中确保写入 `state.clarification_questions`。

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_clarification_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_clarification_contract.py
git commit -m "feat(api): normalize clarification questions contract"
```

Reference skill: `@test-driven-development`

### Task 4: 前端 API 客户端与类型契约对齐

**Files:**
- Create: `frontend/src/lib/__contract_tests__/workflow-contract.types.ts`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Write the failing type test**

```ts
// frontend/src/lib/__contract_tests__/workflow-contract.types.ts
import { workflowApi, type WorkflowResponse } from '@/lib/api';

const assertResponse = (r: WorkflowResponse) => r;
assertResponse({ workflow_run_id: 'x', status: 'awaiting_fact_check_approval', state: {} });

workflowApi.approveFactCheck('wf', { c1: 'confirm' }, {});
```

**Step 2: Run type-check to verify it fails**

Run: `cd frontend && npx tsc --noEmit`
Expected: FAIL（当前 `approveFactCheck` 不存在，或类型不匹配）

**Step 3: Write minimal implementation**

```ts
// frontend/src/lib/api.ts
export interface ClarificationQuestion {
  field: string;
  question: string;
  priority: 'high' | 'medium' | 'low';
  default_assumption?: string;
}

approveFactCheck: (
  workflowRunId: string,
  decisions: Record<string, 'confirm' | 'use_suggestion' | 'manual'>,
  manualCorrections: Record<string, string>
) => request<WorkflowResponse>(`/api/workflow/${workflowRunId}/approve-fact-check`, {
  method: 'POST',
  body: JSON.stringify({ decisions, manual_corrections: manualCorrections }),
}),
```

**Step 4: Run type-check to verify it passes**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/__contract_tests__/workflow-contract.types.ts
git commit -m "feat(frontend): align workflow api client with contract"
```

Reference skill: `@test-driven-development`

### Task 5: 前端页面和组件接入新字段与审批接口

**Files:**
- Modify: `frontend/src/app/workflow/[id]/page.tsx`
- Modify: `frontend/src/components/FactCheckViewer/FactCheckViewer.tsx`
- Modify: `frontend/src/components/ClarificationDialog/ClarificationDialog.tsx`
- Modify: `frontend/src/components/IntentCardViewer/IntentCardViewer.tsx`

**Step 1: Write the failing type checks**

在 `workflow/[id]/page.tsx` 将澄清入口改为 `state.clarification_questions`，并调用 `workflowApi.approveFactCheck`，此时先不改组件 props 让 `tsc` 失败。

**Step 2: Run type-check/lint to verify it fails**

Run:
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint`

Expected: FAIL（priority 类型、props 类型、方法签名不一致）

**Step 3: Write minimal implementation**

- `ClarificationDialog` / `IntentCardViewer` 的优先级逻辑统一为 `'high' | 'medium' | 'low'`。
- `FactCheckViewer` 提交时调用页面传入的真实回调。
- 页面中 `onApprove` 改为调用 `workflowApi.approveFactCheck(...)`，成功后刷新 `workflow` 状态。

**Step 4: Run type-check/lint to verify it passes**

Run:
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/app/workflow/[id]/page.tsx frontend/src/components/FactCheckViewer/FactCheckViewer.tsx frontend/src/components/ClarificationDialog/ClarificationDialog.tsx frontend/src/components/IntentCardViewer/IntentCardViewer.tsx
git commit -m "feat(frontend): complete clarification and fact-check approval flow"
```

Reference skill: `@test-driven-development`

### Task 6: 产出并冻结接口文档（OpenAPI + Markdown）

**Files:**
- Create: `docs/api/openapi.v1.yaml`
- Create: `docs/api/openapi.v1.json`
- Create: `docs/api/index.md`
- Create: `docs/api/workflow.md`
- Optional Create: `docs/api/auth.md`, `docs/api/workspace.md`

**Step 1: Write the failing doc-consistency test**

```python
# backend/tests/test_api_docs_presence.py
from pathlib import Path

def test_api_docs_exist():
    assert Path('../docs/api/openapi.v1.yaml').exists()
    assert Path('../docs/api/index.md').exists()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api_docs_presence.py -v`
Expected: FAIL（文档文件尚不存在）

**Step 3: Write minimal implementation**

- 在 `openapi.v1.yaml` 定义本次 workflow 核心接口与 schema。
- 在 `workflow.md` 提供成功/错误示例和状态流转图。
- 在 `index.md` 定义鉴权、错误码、版本策略。

**Step 4: Run verification to verify it passes**

Run:
- `cd backend && uv run pytest tests/test_api_docs_presence.py -v`
- `python -m json.tool docs/api/openapi.v1.json > /dev/null`

Expected: PASS

**Step 5: Commit**

```bash
git add docs/api/openapi.v1.yaml docs/api/openapi.v1.json docs/api/index.md docs/api/workflow.md backend/tests/test_api_docs_presence.py
git commit -m "docs(api): add workflow contract v1 openapi and markdown reference"
```

Reference skill: `@verification-before-completion`

### Task 7: 全量回归与交付收口

**Files:**
- Modify: `docs/api/index.md`（补充最终验证记录）
- Optional Modify: `docs/plans/2026-03-06-workflow-contract-design.md`（补链接）

**Step 1: Write the failing integration checklist**

在 `docs/api/index.md` 新增“验收清单”并先标记为未完成。

**Step 2: Run verification commands**

Run:
- `cd backend && uv run pytest tests/test_workflow_response_contract.py tests/test_fact_check_approval_api.py tests/test_clarification_contract.py tests/test_api_docs_presence.py -v`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint`

Expected: 全部 PASS

**Step 3: Update checklist as completed**

将 `docs/api/index.md` 的验收项改为完成，并记录命令与日期。

**Step 4: Re-run verification**

Run: 同 Step 2
Expected: PASS

**Step 5: Commit**

```bash
git add docs/api/index.md docs/plans/2026-03-06-workflow-contract-design.md
git commit -m "chore(release): finalize workflow contract v1 verification"
```

Reference skill: `@verification-before-completion`

---

## Notes

- DRY: 统一 response builder，避免每个路由重复拼装状态。
- YAGNI: 本阶段不做旧契约兼容层。
- TDD: 每个任务先写失败测试/类型检查，再做最小实现。
- Frequent commits: 每个 Task 独立提交，便于回滚和审查。
