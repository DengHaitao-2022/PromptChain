# Workflow Contract Unification 设计方案

**日期**: 2026-03-06
**范围**: API 契约统一、澄清字段统一、事实核查审批闭环、接口文档规范化

## 1. 目标与总体架构

本次改造采用 **Design-first**：先定义并冻结规范，再驱动后端与前端实现。

### 目标

1. 统一工作流运行态契约
- 统一 `start/getStatus/clarify/approve-outline/approve-fact-check/rerun` 响应结构为 `WorkflowResponse`。
- `GET /api/workflow/{id}` 改为返回运行态视图：`workflow_run_id + status + state`。

2. 统一澄清字段语义
- 统一对外流程字段为 `state.clarification_questions`。
- `intent_card.uncertainties` 仅作为意图卡内部信息，不作为页面流程判断入口。
- 对外优先级统一枚举：`high | medium | low`。

3. 打通事实核查审批闭环
- 新增 `POST /api/workflow/{id}/approve-fact-check`。
- 修复状态机对 `awaiting_fact_check_approval` 的状态识别。
- 前端 `FactCheckViewer` 从 `console.log` 改为真实 API 调用。

### 文档交付

- 机器可读规范：`OpenAPI 3.1`（YAML + JSON）
- 人类可读文档：`Markdown` 接口文档（按域拆分）

## 2. 分阶段实施与里程碑

### 阶段 1：规范基线
- 产出并冻结 `OpenAPI` 初版（覆盖本次三项范围）。
- 输出 `Markdown` 接口文档。
- 里程碑：前后端评审通过，冻结 `v1`。

### 阶段 2：后端契约落地
- 统一 `GET /api/workflow/{id}` 返回 `WorkflowResponse`。
- 新增 `approve-fact-check` 路由并接 `approve_fact_check` 节点。
- 状态机补 `awaiting_fact_check_approval` 分支。
- `clarification_questions` 统一输出结构和优先级映射。
- 里程碑：workflow 核心接口契约测试通过。

### 阶段 3：前端对齐
- `workflowApi` 新增 `approveFactCheck`。
- 详情页统一使用 `state.clarification_questions`。
- `FactCheckViewer` 接入真实审批调用。
- 优先级类型与文档一致。
- 里程碑：全链路（启动→澄清→提纲审批→事实核查审批→完成）走通。

### 阶段 4：文档收口
- 更新 `openapi.v1` 到实现一致版本。
- 更新 `Markdown` 示例与变更记录。
- 里程碑：文档-实现一致性检查通过。

## 3. 接口设计细化

### 核心端点

1. `POST /api/workflow/start`
2. `GET /api/workflow/{workflowRunId}`
3. `POST /api/workflow/{workflowRunId}/clarify`
4. `POST /api/workflow/{workflowRunId}/approve-outline`
5. `POST /api/workflow/{workflowRunId}/approve-fact-check`（新增）
6. `POST /api/workflow/{workflowRunId}/rerun`
7. `GET /api/workflow/{workflowRunId}/rerun-options`

### 统一响应骨架

```json
{
  "workflow_run_id": "string",
  "status": "running|needs_clarification|awaiting_outline_approval|awaiting_fact_check_approval|completed|failed",
  "state": {}
}
```

### 关键模型

- `ClarificationQuestion`
  - `field: string`
  - `question: string`
  - `priority: high | medium | low`
  - `default_assumption?: string`

- `FactCheckApprovalRequest`

```json
{
  "decisions": { "claim_id_1": "confirm|use_suggestion|manual" },
  "manual_corrections": { "claim_id_1": "修正内容" }
}
```

### 错误响应

统一错误体：

```json
{
  "detail": "error message"
}
```

建议错误码：`400 / 404 / 409 / 500`。

## 4. 接口文档格式规范（推荐）

采用 **OpenAPI 3.1 + Markdown 双轨**：

- `docs/api/openapi.v1.yaml`（主规范）
- `docs/api/openapi.v1.json`（工具链消费）
- `docs/api/index.md`（总览）
- `docs/api/workflow.md`（workflow 领域）
- 其他领域文档按模块拆分（如 `auth.md`、`workspace.md`）

每个端点的 Markdown 模板固定包含：
- Endpoint 与用途
- 鉴权要求
- 参数表（Path/Query/Body）
- 成功示例
- 错误示例
- 前置条件与状态流转

## 5. 测试与验收标准

### 契约一致性
- 后端响应必须与 `openapi.v1.yaml` 一致。
- `start` 与 `getStatus` 必须同形。
- 前端不再用 `state.uncertainties` 驱动澄清流程。

### 状态机正确性
- 高风险事实核查场景返回 `awaiting_fact_check_approval`。
- 调用 `approve-fact-check` 后状态可继续推进。
- 错误阶段调用审批接口返回明确 4xx。

### 前端闭环
- 详情页完整走通审批链路。
- `FactCheckViewer` 调用真实 API。
- 优先级展示与接口定义一致。

### 文档完整性
- OpenAPI 与 Markdown 同步存在。
- 每个核心接口有成功/失败示例。
- 有版本信息和更新时间。

---

该文档作为本次改造的冻结设计基线；后续实现与测试均以此为准。
