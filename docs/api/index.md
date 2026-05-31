# PromptChain API 文档总览（v1）

- 规范版本：`1.0.0`
- 更新时间：`2026-05-23`
- 唯一事实源（SSOT）：`docs/api/openapi.v1.yaml`

## 文档索引

- [Workflow 运行链路](./workflow.md)
- [Workflow 可视化编排与版本](./workflow-definition.md)
- [运行监控与结果回放（Trace/Artifact/WebSocket）](./monitoring.md)
- [认证与用户上下文](./auth.md)
- [工作空间与成员管理](./workspace.md)
- [后台管理与模型配置](./admin.md)

## 鉴权约定

- 使用 HttpOnly Cookie：`access_token`、`refresh_token`
- 受保护接口通过 `cookieAuth` 声明
- 前端请求需带 `credentials: include`

## 工作流状态机（对外）

- `running`
- `paused`
- `needs_clarification`
- `awaiting_outline_approval`
- `awaiting_fact_check_approval`
- `completed`
- `failed`

## 统一错误响应

当前 `dev@699bf53` 主线仍保留 FastAPI `HTTPException` 与局部 `Result` 兼容风格。MVP2 统一错误体系正在 PR #5 中推进，尚未合入主线。

当前主线常见错误形态：

```json
{
  "detail": "error message",
  "code": "optional_error_code"
}
```

PR #5 候选统一错误 envelope：

```json
{
  "success": false,
  "code": "WORKFLOW_NOT_FOUND",
  "message": "资源不存在",
  "data": null,
  "request_id": "req_...",
  "details": {}
}
```

## 状态码策略

- `200`: 成功
- `400`: 参数错误或状态不合法
- `401`: 未登录/登录过期
- `403`: 权限不足
- `404`: 资源不存在
- `409`: 状态冲突
- `500`: 服务内部错误

## 版本策略

- 主规范文件：`openapi.v1.yaml`
- 工具链消费文件：`openapi.v1.json`（由 YAML 导出）
- 不兼容改动需升级主版本（`v2`）

## 与系统设计映射

- 登录与权限/角色管理：`auth.md` + `workspace.md`
- Prompt Chain 可视化编排：`workflow-definition.md`
- 一键生成长文/脚本：`workflow.md`
- 不确定点检测与人机门控：`workflow.md`
- 任务运行监控与结果回放：`monitoring.md`
- 后台模型与运营管理：`admin.md`
