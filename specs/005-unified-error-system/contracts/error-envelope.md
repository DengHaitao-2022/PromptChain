# Contract: Unified Error Envelope

## Purpose

定义 PromptChain 在 MVP2 统一错误体系中对外暴露的失败响应契约。目标是让前端、管理台和其他调用方不再依赖自由文本或不同模块各自的错误格式。

## Contract Goals

- 所有失败响应都使用统一结构
- 所有失败响应都提供稳定错误标识
- 所有失败响应都提供请求追踪标识
- 基础设施异常对外脱敏
- 调用方可基于错误标识和处理建议做稳定分支

## Required Fields

| Field | Meaning | Required |
|---|---|---|
| `success` | 统一成功标记 | Yes |
| `code` | 稳定错误标识 | Yes |
| `message` | 可读说明 | Yes |
| `request_id` | 请求追踪标识 | Yes |
| `details` | 可选结构化上下文 | No |
| `data` | 成功数据载荷 | 失败场景通常为空 |

## Semantics

### `success`

- 失败时必须固定为 `false`
- 成功时的统一 envelope 设计可与本特性一并规划，但 MVP2 第一阶段至少要确保失败响应统一

### `code`

- 必须来自错误码注册表
- 必须稳定
- 不得把中文文案当作机器可判定标识

### `message`

- 必须面向用户或调用方可理解
- 可以变化文案，但不能改变 `code` 语义

### `request_id`

- 必须存在于所有失败响应中
- 必须可与后端日志关联

### `details`

- 仅包含安全、必要、可结构化消费的信息
- 不得包含数据库报错、堆栈、第三方原始异常等底层敏感信息

## Consumer Guarantees

调用方可以稳定依赖以下事实：

1. 同一错误语义在不同接口中使用相同 `code`
2. 调用方可基于 `code` 判断：
   - 用户修正输入
   - 重新登录或重新获取权限
   - 稍后重试
   - 联系管理员
3. 文案变化不会破坏调用方逻辑

## Migration Boundary

该契约优先覆盖以下 API 域：

- `auth`
- `workflow runtime`
- `trace`
- `workspace`
- `admin`

工作流定义和版本管理域当前已有 `Result` 草案，但不应长期保持局部特例；后续应被统一契约吸收。
