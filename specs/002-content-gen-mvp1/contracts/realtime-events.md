# Realtime Event Contract

## 0. Current Baseline (`dev@df88a42`)

- `backend/graph/executor.py` 已在节点执行、Gate 等待、手动 pause/resume、completed/failed 上调用 `emit_*`。
- `backend/routes/websocket_routes.py` 已承担 transport 层广播；REST 轮询与 trace timeline 仍是状态对账权威。
- 当前剩余漂移是 fact-check Gate 的事件命名：执行路径广播值仍是 `fact_check_approval`，而前端共享静态类型与本文档目标值仍以 `fact_check` 为准。

## 1. Channels

| Channel | Purpose |
|---|---|
| `/ws/workflow/{workflow_run_id}` | 推送特定任务的节点状态和工作流状态 |
| `/ws/user/{user_id}` | 推送用户维度的审批通知和分配消息 |

## 2. Workflow Channel Events

### Connection Event

```json
{
  "type": "connected",
  "workflow_run_id": "wf_123",
  "message": "已连接到工作流状态推送"
}
```

### Node Events

| Event Type | Purpose | Required Fields |
|---|---|---|
| `node_started` | 节点开始执行 | `workflow_run_id`, `node_id`, `data` |
| `node_completed` | 节点执行完成 | `workflow_run_id`, `node_id`, `data` |
| `node_failed` | 节点执行失败 | `workflow_run_id`, `node_id`, `data` |

### Workflow Events

| Event Type | Purpose | Required Fields | Contract State |
|---|---|---|---|
| `workflow_paused` | 工作流被用户主动暂停 | `workflow_run_id`, `data.reason?`, `data.paused_at?`, `data.current_node?` | Shipped in dev |
| `workflow_completed` | 工作流完成 | `workflow_run_id`, `data` | Shipped in dev |
| `workflow_failed` | 工作流失败 | `workflow_run_id`, `data` | Shipped in dev |
| `workflow_gate_waiting` | 进入 Gate 等待 | `workflow_run_id`, `data.gate_type`, `data.questions`, `data.current_node?`, `data.opened_at?` | Shipped in dev; fact-check gate naming still needs final normalization |
| `workflow_resumed` | 从手动暂停恢复 | `workflow_run_id`, `data.resumed_at?`, `data.current_node?` | Shipped in dev |

`workflow_gate_waiting.data.gate_type` allowed values:

- `clarification`
- `outline_approval`
- `fact_check`

## 3. User Channel Events

| Event Type | Purpose | Required Fields |
|---|---|---|
| `connected` | 建立用户通知连接 | `user_id`, `message` |
| `approval_required` | 有新的审批任务 | `approval_task_id`, `workflow_run_id`, `node_name`, `content_preview` |
| `approval_timeout` | 审批即将超时 | 目标保留字段待实现时补齐 |
| `workflow_assigned` | 有新的工作流分配 | 目标保留字段待实现时补齐 |

## 4. Source-of-Truth Rule

1. WebSocket 不是运行态的唯一事实源。
2. `GET /api/workflow/{workflow_run_id}` 仍是状态读取的权威接口。
3. 客户端在收到关键事件后，应使用 REST 状态接口进行对账，防止漏事件或顺序错乱。
4. `frontend/src/lib/api.ts` 中导出的 `WorkflowRealtimeEvent` 是前端消费端的静态契约基线，即使个别事件的后端 emit 尚未全部打通。

## 5. Delivery Rules

1. 每个节点开始、完成、失败都应有对应事件。
2. 进入澄清、提纲审批、事实核查审批时，必须产生能够驱动前端提示的事件。
3. 手动暂停与 Gate 等待必须在事件层可区分。
4. 断线重连后，客户端必须能通过 REST 状态恢复当前视图。
5. 当前若实时 emit 缺失，`GET /api/trace/{workflow_run_id}` 中的 `workflow_gate_waiting` / `workflow_paused` / `workflow_resumed` timeline 事件应作为回放与对账补偿。

## 6. Migration Notes

- 当前仓库已经有 WebSocket 路由和 `emit_*` 工具，节点开始/完成/失败、Gate 等待、pause/resume、completed/failed 的执行路径 emit 已接线到 `backend/graph/executor.py`。
- 当前剩余工作不是“是否发事件”，而是“是否把 event payload 命名彻底收口到共享契约”，尤其是 fact-check Gate 的 `gate_type`。
- 前端仍需保留轮询或手动刷新作为兜底；`GET /api/workflow/{workflow_run_id}` 与 `GET /api/trace/{workflow_run_id}` 继续是权威对账入口。
