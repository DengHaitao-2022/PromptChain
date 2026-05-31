# Workflow API（核心内容生成链路）

## 统一响应模型

所有 workflow 运行态接口返回：

```json
{
  "workflow_run_id": "string",
  "status": "running|paused|needs_clarification|awaiting_outline_approval|awaiting_fact_check_approval|completed|failed",
  "state": {}
}
```

## 状态流转（简化）

`start -> (needs_clarification?) -> awaiting_outline_approval -> generate_content -> check_facts -> awaiting_fact_check_approval? -> completed`

手动暂停是独立控制流：`running -> paused -> running`。它不等同于 Gate 等待。

## 接口清单

### 1) `POST /api/workflow/start`

- 鉴权：需要当前工作空间具备 `workflow.execute`
- 请求体：

```json
{
  "user_input": "写一篇关于 AI Agent 架构的文章",
  "workflow_definition_id": "wf_def_123",
  "workflow_version_id": "wf_ver_123",
  "model_provider_id": "provider_123",
  "model_name": "gemini-2.5-pro"
}
```

`workflow_definition_id`、`workflow_version_id`、`model_provider_id`、`model_name` 均为可选字段。

- 成功响应（示例）：

```json
{
  "workflow_run_id": "wf_123",
  "status": "running",
  "state": {}
}
```

### 2) `GET /api/workflow/{workflow_run_id}`

- 鉴权：校验工作空间与运行归属；普通用户只能访问自己的运行记录，`admin` / `owner` 可查看同工作空间运行
- Path 参数：`workflow_run_id: string`
- 典型错误：`404`（workflow 不存在）

### 3) `POST /api/workflow/{workflow_run_id}/clarify`

- 用途：提交澄清回答（`needs_clarification` 阶段）
- 请求体：

```json
{
  "clarifications": {
    "audience": "后端工程师",
    "tone": "正式严谨"
  }
}
```

### 4) `POST /api/workflow/{workflow_run_id}/pause`

- 用途：用户主动暂停正在自动执行的工作流
- 请求体：

```json
{
  "reason": "需要先确认输入材料"
}
```

- 约束：Gate 等待态、`completed`、`failed` 不可暂停
- 成功后 `status` 为 `paused`，`state.pause` 保留最近暂停上下文

### 5) `POST /api/workflow/{workflow_run_id}/resume`

- 用途：恢复用户主动暂停的工作流
- 请求体：`{}`
- 约束：仅 `paused` 状态可恢复；Gate 等待态需走对应审批/澄清接口

### 6) `POST /api/workflow/{workflow_run_id}/approve-outline`

- 用途：提纲审批
- 请求体：

```json
{
  "action": "approve",
  "feedback": "",
  "modified_outline": null
}
```

- `action` 枚举：`approve | modify | regenerate`

### 7) `POST /api/workflow/{workflow_run_id}/approve-fact-check`

- 用途：审批高风险事实项（人机门控关键接口）
- 请求体：

```json
{
  "decisions": {
    "claim_1": "confirm",
    "claim_2": "manual"
  },
  "manual_corrections": {
    "claim_2": "修正后的事实描述"
  }
}
```

- `decisions` 枚举值：`confirm | use_suggestion | manual`

### 8) `GET /api/workflow/{workflow_run_id}/rerun-options`

- 用途：获取可重跑节点

### 9) `POST /api/workflow/{workflow_run_id}/rerun`

- 用途：从指定节点重跑
- 请求体：

```json
{
  "from_node": "generate_outline",
  "updated_input": {},
  "reason": "用户要求调整结构"
}
```

### 10) `GET /api/workflow/{workflow_run_id}/rerun-history`

- 用途：查询重跑历史

### 11) `GET /api/workflow/runs`

- 用途：获取当前用户在当前工作空间可见的运行记录列表
- 权限：需要 `workflow_run.read`
- 可见范围：普通用户只看本人运行，`admin` / `owner` 可看同工作空间运行

### 12) `GET /api/workflow/{workflow_run_id}/events`

- 用途：工作流详情页 SSE 快照流
- 事件：`snapshot`、`token`、`section_started`、`section_completed`、`stream_error`、`heartbeat`、`done`
- 说明：SSE 是实时体验增强通道；最终状态仍以 `GET /api/workflow/{workflow_run_id}` 与 Trace 为准

### 13) `GET /api/workflow/{workflow_run_id}/exports/docx`

- 用途：导出已完成工作流的最终产物 DOCX
- 前置：运行状态必须是 `completed`
- 典型错误：`409`（未完成不可导出）、`404`（没有可导出的最终产物）

## `state` 关键字段约定

- `clarification_questions`: 当前需要回答的问题列表（流程判断入口）
- `outline`: 提纲对象
- `fact_check_report`: 事实核查报告
- `pause`: 最近一次手动暂停/恢复上下文
- `gate`: 当前 Gate 类型、问题、回答和等待信息
- `runtime_plan` / `runtime_progress`: 已发布编排定义编译后的受限运行计划与进度摘要
- `final_artifact_id`: 最终产物 ID
- `quality_metrics`: 质量、token 与耗时聚合指标
- `final_content`: 章节内容预览映射，形如：

```json
{
  "section_1": {
    "preview": "前100字符...",
    "word_count": 523
  }
}
```

## 澄清优先级约定

- `high`: 必答
- `medium`: 建议回答
- `low`: 可选
