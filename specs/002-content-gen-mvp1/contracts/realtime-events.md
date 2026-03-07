# Realtime Event Contract

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

| Event Type | Purpose | Required Fields |
|---|---|---|
| `workflow_paused` | 工作流被用户主动暂停或进入可见暂停态 | `workflow_run_id`, `data` |
| `workflow_completed` | 工作流完成 | `workflow_run_id`, `data` |
| `workflow_failed` | 工作流失败 | `workflow_run_id`, `data` |
| `workflow_gate_waiting` | Target New：进入 Gate 等待 | `workflow_run_id`, `data.gate_type`, `data.questions` |
| `workflow_resumed` | Target New：从手动暂停或 Gate 恢复 | `workflow_run_id`, `data` |

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

## 5. Delivery Rules

1. 每个节点开始、完成、失败都应有对应事件。
2. 进入澄清、提纲审批、事实核查审批时，必须产生能够驱动前端提示的事件。
3. 手动暂停与 Gate 等待必须在事件层可区分。
4. 断线重连后，客户端必须能通过 REST 状态恢复当前视图。

## 6. Migration Notes

- 当前仓库已经有 WebSocket 路由和 `emit_*` 工具，但主工作流执行链路尚未完整调用这些工具。
- 在这一集成完成前，前端仍需保留轮询或手动刷新作为兜底。
