# Runtime API Contract

## 0. Current Baseline (`dev@c396a48`)

- 当前后端 canonical 落点是 `backend/routes/workflow_routes.py` 与 `backend/routes/workflow_helpers.py`；`backend/main.py` 只保留兼容入口。
- `POST /api/workflow/start` 现已支持可选的 `workflow_definition_id` 与 `workflow_version_id`，用于从已发布工作流版本启动任务。
- pause/resume、clarify、outline approval、fact-check approval、rerun、rerun-history 均已进入主线。
- 当前契约侧剩余主线主要落在 `T005/T011`：首页仍直接 `fetch` 列表/版本/启动接口，而不是完全复用 `frontend/src/lib/api.ts`。

## 1. Canonical Envelope

所有工作流运行态接口统一返回 `WorkflowResponse`：

```json
{
  "workflow_run_id": "wf_123",
  "status": "running",
  "state": {}
}
```

### Canonical Status Enum

| Status | Meaning |
|---|---|
| `running` | 正在自动执行 |
| `paused` | 用户主动暂停 |
| `needs_clarification` | 等待澄清 |
| `awaiting_outline_approval` | 等待提纲审批 |
| `awaiting_fact_check_approval` | 等待事实核查审批 |
| `completed` | 已成功完成 |
| `failed` | 已失败 |

### Canonical State Fields

| Field | Shape | Notes |
|---|---|---|
| `clarification_questions` | `ClarificationQuestion[]` | Gate 最多 3 个问题，优先级枚举为 `high` / `medium` / `low` |
| `outline` | `Outline` | 提纲审批时返回 |
| `fact_check_report` | `FactCheckReport` | 高风险事实核查审批时返回 |
| `final_content` | `Record<sectionId, { preview, word_count }>` | 完成后返回内容摘要 |
| `current_node` | `string` | 运行进度展示使用 |
| `pause` | `PauseState` | 手动暂停或恢复后保留最近一次暂停上下文 |
| `gate` | `GateState` | 当前 Gate 读模型，统一澄清 / 提纲审批 / 事实核查审批 |
| `error` | `string` | 失败态说明 |

## 2. Schema Fragments

### ClarificationQuestion

```json
{
  "field": "audience",
  "question": "目标读者是谁？",
  "priority": "high",
  "default_assumption": "通用读者"
}
```

### ApproveOutlineRequest

```json
{
  "action": "approve",
  "feedback": "",
  "modified_outline": null
}
```

`action` allowed values:

- `approve`
- `modify`
- `regenerate`

### ApproveFactCheckRequest

```json
{
  "decisions": {
    "claim_1": "confirm",
    "claim_2": "manual"
  },
  "manual_corrections": {
    "claim_2": "修正后的文本"
  }
}
```

`decisions` allowed values:

- `confirm`
- `use_suggestion`
- `manual`

### PauseState

```json
{
  "reason": "等待人工复核",
  "paused_at": "2026-03-08T10:00:00Z",
  "resumed_at": "2026-03-08T10:05:00Z",
  "source": "user"
}
```

### GateState

```json
{
  "gate_type": "clarification",
  "trigger_reason": "missing_information",
  "questions": [
    {
      "field": "audience",
      "question": "目标读者是谁？"
    }
  ],
  "answers": null,
  "opened_at": "2026-03-08T10:01:00Z",
  "handled_at": null,
  "resolution": null
}
```

`gate_type` allowed values:

- `clarification`
- `outline_approval`
- `fact_check`

## 3. Endpoint Contract

| Method | Path | Status | Purpose | Request | Response |
|---|---|---|---|---|---|
| `POST` | `/api/workflow/start` | Existing | 启动新任务 | `{ "user_input": "...", "workflow_definition_id": "optional", "workflow_version_id": "optional" }` | `WorkflowResponse` |
| `GET` | `/api/workflow/{workflow_run_id}` | Existing | 读取当前任务状态 | None | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/clarify` | Existing | 提交澄清回答 | `{ "clarifications": { "field": "answer" } }` | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/approve-outline` | Existing | 处理提纲审批 | `ApproveOutlineRequest` | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/approve-fact-check` | Existing | 处理事实核查审批 | `ApproveFactCheckRequest` | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/pause` | Existing | 用户主动暂停任务 | `{ "reason": "optional" }` | `WorkflowResponse` with `status=paused` |
| `POST` | `/api/workflow/{workflow_run_id}/resume` | Existing | 恢复用户手动暂停的任务 | `{}` | `WorkflowResponse` |
| `GET` | `/api/workflow/{workflow_run_id}/rerun-options` | Existing | 查询可重跑节点 | None | `{ "options": [...] }` |
| `POST` | `/api/workflow/{workflow_run_id}/rerun` | Existing | 从指定节点创建 rerun 任务 | `{ "from_node": "...", "updated_input": {}, "reason": "" }` | `{ "original_workflow_run_id", "new_workflow_run_id", "rerun_from_node", "status", "state" }` |
| `GET` | `/api/workflow/{workflow_run_id}/rerun-history` | Existing | 查看重跑历史 | None | `{ "history": [...] }` |
| `GET` | `/api/trace/{workflow_run_id}` | Existing | 获取任务全链路回放数据 | None | `WorkflowTrace` |
| `GET` | `/api/trace/node/{node_run_id}` | Existing | 获取节点详情 | None | `NodeDetail` |
| `GET` | `/api/artifact/{artifact_id}` | Existing | 获取单个产物 | None | `Artifact` |
| `GET` | `/api/artifact/{artifact_id}/history` | Existing | 获取产物历史版本 | None | `{ "history": [...] }` |

### Trace Normalization Rules

- `GET /api/trace/{workflow_run_id}` 返回中的 `workflow.status` 使用与 `WorkflowResponse.status` 相同的公开状态语义，而不是裸持久化状态。
- `GET /api/trace/{workflow_run_id}` 返回中的 `workflow.current_node`、`workflow.pause`、`workflow.gate` 必须与当前运行态读模型保持一致。
- `timeline` 在缺少显式执行事件时，可以补充以下合成事件：
  - `workflow_paused`
  - `workflow_resumed`
  - `workflow_gate_waiting`

## 4. Error-Path Rules

- `GET /api/workflow/{workflow_run_id}` / `POST /api/workflow/{workflow_run_id}/pause` / `POST /api/workflow/{workflow_run_id}/resume`
  - `404`：任务不存在
- `POST /api/workflow/{workflow_run_id}/clarify`
  - `409`：当前状态不是 `needs_clarification`
  - `409`：当前任务已手动暂停，需先调用 `resume`
- `POST /api/workflow/{workflow_run_id}/approve-outline`
  - `409`：当前状态不是 `awaiting_outline_approval`
  - `409`：当前任务已手动暂停，需先调用 `resume`
- `POST /api/workflow/{workflow_run_id}/approve-fact-check`
  - `409`：当前状态不是 `awaiting_fact_check_approval`
  - `409`：当前任务已手动暂停，需先调用 `resume`
- `POST /api/workflow/{workflow_run_id}/pause`
  - `409`：当前状态处于 Gate 等待，不允许把 Gate 伪装成手动暂停
  - `409`：当前状态已结束（`completed` / `failed`）
- `POST /api/workflow/{workflow_run_id}/resume`
  - `409`：当前状态不为 `paused`
  - `409`：当前状态处于 Gate 等待，应走对应 Gate 接口而不是手动恢复

## 5. Compatibility Rules

1. `WorkflowResponse` 是前后端共同维护的唯一运行态骨架。
2. `paused` 只表示用户主动暂停，不表示 Gate。
3. `needs_clarification`、`awaiting_outline_approval`、`awaiting_fact_check_approval` 必须继续作为独立状态存在。
4. `clarification_questions.priority` 必须对外保持枚举值，而不是泄漏后端数值优先级。
5. `state.pause` 与 `state.gate` 只描述最近一次手动暂停和当前 Gate 上下文，不替代节点级 trace。
6. 任何新增状态或字段都必须同时更新：
   - `backend/routes/workflow_routes.py`
   - `backend/routes/workflow_helpers.py`
   - `backend/graph/executor.py`
   - `frontend/src/lib/api.ts`
   - 契约测试

## 6. Migration Notes

- 当前 canonical envelope 已在 `backend/routes/workflow_routes.py` / `backend/routes/workflow_helpers.py` 生效，不再依赖旧的 `main.py` 路由实现。
- 当前执行模型仍然以单次 HTTP 调用内推进 LangGraph 为主，手动 `pause` 仅对已持久化为 `running` 的任务读模型生效，不能中断一个正在执行中的同一请求。
- 当前默认运行态存储为 PostgreSQL；仅在显式设置 `RUNTIME_STORE_BACKEND=memory` 时退回内存实现。
- 当前运行态读模型仍主要依赖轮询接口；WebSocket 仅为补充通道，不替代本契约。
