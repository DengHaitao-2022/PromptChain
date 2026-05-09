# Monitoring & Replay API（运行监控与结果回放）

> 对应系统设计能力：任务运行监控与结果回放。

## Trace 与 Artifact

### 1) `GET /api/trace/{workflow_run_id}`

- 用途：获取工作流完整执行追踪
- 返回：
  - `workflow`: 顶层运行信息
  - `nodes`: 节点执行序列
  - `artifacts`: 产物字典
  - `timeline`: 事件时间线（节点开始/完成、llm_call、artifact_created 等）

### 2) `GET /api/trace/node/{node_run_id}`

- 用途：获取单节点执行详情
- 返回：`node`、`input_artifacts`、`output_artifacts`（含版本历史）

### 3) `GET /api/artifact/{artifact_id}`

- 用途：获取单个产物详情

### 4) `GET /api/artifact/{artifact_id}/history`

- 用途：获取产物版本链

## WebSocket 推送

### 1) `/ws/workflow/{workflow_run_id}`

- 连接后首次消息：

```json
{
  "type": "connected",
  "workflow_run_id": "wf_123",
  "message": "已连接到工作流状态推送"
}
```

- 典型事件：
  - `node_started`
  - `node_completed`
  - `node_failed`
  - `workflow_completed`
  - `workflow_paused`

### 2) `/ws/user/{user_id}`

- 用途：推送用户级通知（审批任务、分配任务等）
- 典型事件：
  - `approval_required`
  - `approval_timeout`
  - `workflow_assigned`

## 心跳约定

- 客户端可发送 `ping`，服务端回 `pong`
- 服务端超时检查会主动发送 `ping`
