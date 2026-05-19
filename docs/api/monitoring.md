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

## 运行记录与导出

### 1) `GET /api/workflow/runs`

- 用途：获取当前用户在当前工作空间可见的运行记录列表
- 权限：需要 `workflow_run.read`
- 可见范围：
  - 普通用户仅可查看本人运行记录
  - `admin` / `owner` 可查看同工作空间运行记录

### 2) `GET /api/workflow/{workflow_run_id}/rerun-options`

- 用途：获取可从哪些节点发起重跑
- 说明：可重跑节点受当前运行计划和节点状态共同限制

### 3) `POST /api/workflow/{workflow_run_id}/rerun`

- 用途：创建从指定节点开始的新运行
- 说明：不会覆盖原运行，而是创建新的 `WorkflowRun` 并保留原运行历史

### 4) `GET /api/workflow/{workflow_run_id}/rerun-history`

- 用途：查看原运行与派生重跑运行的链路

### 5) `GET /api/workflow/{workflow_run_id}/exports/docx`

- 用途：导出已完成工作流的最终产物 DOCX
- 限制：仅 `completed` 状态支持导出

## SSE 快照流

### `GET /api/workflow/{workflow_run_id}/events`

- 用途：工作流详情页的实时状态与增量内容通道
- 事件：
  - `snapshot`
  - `token`
  - `section_started`
  - `section_completed`
  - `stream_error`
  - `heartbeat`
  - `done`
- 说明：SSE 用于增强实时体验；REST 状态接口与 Trace 仍是最终对账入口。

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
