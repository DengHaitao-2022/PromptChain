# Research: PromptChain 统一错误体系

## Research Scope

本阶段只研究 MVP2 统一错误体系所必需的设计决策，不扩展成通用平台重构。研究范围包括：

- 当前仓库中错误响应、异常抛出和异常映射的真实现状
- 统一错误模型、错误码注册表和异常分层的最小落地方式
- 全局异常处理器与请求级追踪标识在现有 FastAPI 应用中的挂接方式
- 前后端错误契约统一的范围边界
- 迁移顺序、回归风险和验证路径

## Current Baseline Facts

### 1. 当前响应风格并不统一

1. `backend/models/result.py` 提供了 `Result / PageResult` 统一响应草案，使用 `code / message / data` 结构。
2. 这套模型主要用于 `backend/routes/workflow_definition_routes.py` 与 `backend/routes/workflow_version_routes.py`。
3. 认证、运行态、追踪、工作空间、管理后台等主链路并未统一采用该模型。
4. `backend/routes/auth_routes.py` 同时使用：
   - `MessageResponse`
   - `MeResponse`
   - 直接抛 `HTTPException(detail="中文文案")`
5. `backend/routes/trace_routes.py` 和 `backend/routes/workflow_routes.py` 更接近 FastAPI 默认错误风格，常见结构为 `{"detail": "..."}`。
6. 这意味着仓库至少存在三套对外响应风格：
   - `Result.success()/Result.not_found()`
   - 直接返回业务模型
   - 裸 `HTTPException.detail`

### 2. 异常来源没有完成分层

1. 服务层大量直接抛 `ValueError`，例如 `backend/services/auth_service.py` 中的“该邮箱已被注册”“登录尝试次数过多”。
2. 权限服务中直接抛 `HTTPException`，例如 `backend/services/permission_service.py` 的权限拒绝路径。
3. 路由层再按各自习惯把 `ValueError -> 400/404`、`Exception -> 500` 做局部转换，例如 `backend/routes/trace_routes.py`。
4. 基础设施故障没有独立异常包装层，数据库、模型服务、邮件等外部依赖失败大多最终冒成通用 `500`。
5. 当前仓库缺少明确的：
   - `DomainError`
   - `ApplicationError`
   - `InfrastructureError`
   这类分层基类。

### 3. 应用入口缺少全局异常治理

1. `backend/app.py` 当前只负责：
   - FastAPI 初始化
   - CORS
   - 路由注册
2. 当前没有看到：
   - 全局 `@application.exception_handler(...)`
   - 自定义统一错误中间件
   - 请求级 `request_id` / `error_id` 注入
   - 统一异常到响应的转换器
3. 因此当前错误语义和错误结构主要由各路由自行决定，无法形成稳定外部契约。

### 4. 当前错误码只有通用数字草案，没有业务错误码体系

1. `backend/models/result.py` 中存在：
   - `0` 成功
   - `40000 / 40100 / 40300 / 40400 / 50000` 等通用数字码
2. 但当前没有看到：
   - 业务错误码注册表
   - 域级命名空间
   - 稳定机器可判定枚举，例如 `AUTH_INVALID_CREDENTIALS`、`WORKFLOW_GATE_CONFLICT`
3. 因此现状只能算“通用数字码草案”，不能算“稳定业务错误体系”。

## Research Tasks Executed

1. 审查 `backend/models/result.py`，确认当前统一响应模型只是局部使用。
2. 审查 `backend/routes/workflow_definition_routes.py`、`backend/routes/auth_routes.py`、`backend/routes/trace_routes.py`，确认多套响应与异常风格并存。
3. 审查 `backend/services/auth_service.py` 与 `backend/services/permission_service.py`，确认 `ValueError / HTTPException / 裸 Exception` 混用。
4. 审查 `backend/app.py`，确认当前没有全局异常处理器和统一错误中间件。

## Decisions

### 1. MVP2 统一错误体系必须以“统一外部契约”为入口

- **Decision**: 第一优先级不是先改内部实现细节，而是先定义统一失败响应的外部契约，包括稳定错误标识、用户可读说明、请求追踪标识和可选上下文。
- **Rationale**: 当前最大问题不是某个具体异常类缺失，而是调用方拿不到稳定错误语义。没有统一外部契约，前后端仍只能依赖自由文本判断错误。
- **Alternatives considered**:
  - 先只重构服务层异常类，不统一响应格式：被拒绝，因为不能直接解决调用方不稳定的问题。

### 2. 错误体系按三层分层最合适

- **Decision**: 最小落地按三层拆分：
  - `DomainError`
  - `ApplicationError`
  - `InfrastructureError`
- **Rationale**: 这已经足以区分业务规则失败、应用流程失败和外部依赖失败，同时不会把体系扩得过于复杂。
- **Alternatives considered**:
  - 继续只用 `ValueError / HTTPException`：被拒绝，因为没有稳定语义。
  - 一次性引入过多异常层级：被拒绝，因为超出 MVP2 第一阶段的最小范围。

### 3. 错误码注册表必须采用“域 + 语义”而不是只靠数字段位

- **Decision**: 错误码应采用稳定、可读、可跨模块复用的域级命名方式，例如：
  - `AUTH_*`
  - `WORKSPACE_*`
  - `WORKFLOW_*`
  - `TRACE_*`
  - `INFRA_*`
- **Rationale**: 仅靠 `40000 / 40100` 这类通用数字难以表达真实语义，也不利于前后端协作和长期维护。
- **Alternatives considered**:
  - 继续仅用 HTTP 状态码 + 中文 detail：被拒绝，因为不稳定且不可机器判定。

### 4. 全局异常映射必须集中在 app 层

- **Decision**: 统一异常到响应的转换应通过 `backend/app.py` 挂接的全局异常处理器完成，而不是继续让每个路由自己拼 `HTTPException`。
- **Rationale**: 只有全局入口才能保证错误结构一致、基础设施异常脱敏一致、日志与响应的追踪信息一致。
- **Alternatives considered**:
  - 每个路由保留本地 try/except：被拒绝，因为会持续产生风格漂移。

### 5. 基础设施异常必须对外脱敏，但保留内部 cause

- **Decision**: 数据库、缓存、模型服务、邮件等外部依赖异常对外只暴露稳定错误语义与追踪标识，不直接透传底层错误文本；内部日志与调试上下文保留原始 cause。
- **Rationale**: 当前通用 `500 detail=str(e)` 既不安全，也不利于稳定前端处理。
- **Alternatives considered**:
  - 对外透传原始异常文本以便开发：被拒绝，因为不适合作为长期 API 契约。

### 6. 迁移必须分阶段，不一次性重写全部路由

- **Decision**: 统一错误体系应采用分阶段迁移：
  1. 定义统一错误契约、错误码注册表和异常基类
  2. 在 `app.py` 挂接全局异常映射与请求追踪标识
  3. 优先覆盖核心 API 域：`auth / workflow runtime / trace / workspace / admin`
  4. 再逐步回收历史 `Result` 与局部 try/except
- **Rationale**: 当前仓库面已较大，一次性重构会扩大回归面。
- **Alternatives considered**:
  - 一次性统一全部路由和服务：被拒绝，因为超出 MVP2 第一波可控范围。

## Consolidated Impacts

- 该特性主要影响后端 API 错误契约和异常治理方式。
- `backend/models/result.py` 可能被重构为统一 envelope 的一部分，也可能被新的错误契约替代，但不应继续保持局部使用状态。
- `backend/app.py` 将成为统一错误映射与请求追踪的挂接点。
- 多个路由模块会被要求迁移到统一错误模型，但可按优先级逐步推进。
- 前端最终需要按稳定错误标识处理错误，而不是继续依赖 `detail` 文案。

## Remaining Clarifications

无。当前输入已经足以支撑进入设计与任务拆分阶段。
