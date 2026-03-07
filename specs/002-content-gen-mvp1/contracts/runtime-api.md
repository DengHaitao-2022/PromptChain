# Runtime API Contract

## 1. Canonical Envelope

所有工作流运行态接口统一返回 `WorkflowResponse`：

```json
{
  "workflow_run_id": "wf_123",
  "status": "running",
  "state": {}
}
```

### Target Status Enum

| Status | Meaning |
|---|---|
| `running` | 正在自动执行 |
| `paused` | 用户主动暂停 |
| `needs_clarification` | 等待澄清 |
| `awaiting_outline_approval` | 等待提纲审批 |
| `awaiting_fact_check_approval` | 等待事实核查审批 |
| `completed` | 已成功完成 |
| `failed` | 已失败 |

### Target State Fields

| Field | Shape | Notes |
|---|---|---|
| `clarification_questions` | `ClarificationQuestion[]` | Gate 最多 3 个问题，优先级枚举为 `high` / `medium` / `low` |
| `outline` | `Outline` | 提纲审批时返回 |
| `fact_check_report` | `FactCheckReport` | 高风险事实核查审批时返回 |
| `final_content` | `Record<sectionId, { preview, word_count }>` | 完成后返回内容摘要 |
| `current_node` | `string` | 运行进度展示使用 |
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

## 3. Endpoint Contract

| Method | Path | Status | Purpose | Request | Response |
|---|---|---|---|---|---|
| `POST` | `/api/workflow/start` | Existing | 启动新任务 | `{ "user_input": "..." }` | `WorkflowResponse` |
| `GET` | `/api/workflow/{workflow_run_id}` | Existing | 读取当前任务状态 | None | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/clarify` | Existing | 提交澄清回答 | `{ "clarifications": { "field": "answer" } }` | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/approve-outline` | Existing | 处理提纲审批 | `ApproveOutlineRequest` | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/approve-fact-check` | Existing | 处理事实核查审批 | `ApproveFactCheckRequest` | `WorkflowResponse` |
| `POST` | `/api/workflow/{workflow_run_id}/pause` | Target New | 用户主动暂停任务 | `{ "reason": "optional" }` | `WorkflowResponse` with `status=paused` |
| `POST` | `/api/workflow/{workflow_run_id}/resume` | Target New | 恢复用户手动暂停的任务 | `{}` | `WorkflowResponse` |
| `GET` | `/api/workflow/{workflow_run_id}/rerun-options` | Existing | 查询可重跑节点 | None | `{ "options": [...] }` |
| `POST` | `/api/workflow/{workflow_run_id}/rerun` | Existing | 从指定节点创建 rerun 任务 | `{ "from_node": "...", "updated_input": {}, "reason": "" }` | `{ "original_workflow_run_id", "new_workflow_run_id", "rerun_from_node", "status", "state" }` |
| `GET` | `/api/workflow/{workflow_run_id}/rerun-history` | Existing | 查看重跑历史 | None | `{ "history": [...] }` |
| `GET` | `/api/trace/{workflow_run_id}` | Existing | 获取任务全链路回放数据 | None | `WorkflowTrace` |
| `GET` | `/api/trace/node/{node_run_id}` | Existing | 获取节点详情 | None | `NodeDetail` |
| `GET` | `/api/artifact/{artifact_id}` | Existing | 获取单个产物 | None | `Artifact` |
| `GET` | `/api/artifact/{artifact_id}/history` | Existing | 获取产物历史版本 | None | `{ "history": [...] }` |

## 4. Compatibility Rules

1. `WorkflowResponse` 是前后端共同维护的唯一运行态骨架。
2. `paused` 只表示用户主动暂停，不表示 Gate。
3. `needs_clarification`、`awaiting_outline_approval`、`awaiting_fact_check_approval` 必须继续作为独立状态存在。
4. `clarification_questions.priority` 必须对外保持枚举值，而不是泄漏后端数值优先级。
5. 任何新增状态或字段都必须同时更新：
   - `backend/main.py`
   - `backend/graph/content_generation_graph.py`
   - `frontend/src/lib/api.ts`
   - 契约测试

## 5. Migration Notes

- 当前代码尚无公共 `pause` / `resume` 接口，也未对外暴露 `paused` 状态；这是本计划定义的新增契约。
- 当前运行态读模型仍主要依赖轮询接口；WebSocket 仅为补充通道，不替代本契约。
