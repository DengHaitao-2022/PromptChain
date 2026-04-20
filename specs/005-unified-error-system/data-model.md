# Data Model: PromptChain 统一错误体系

## Model Scope

本特性不新增业务数据库表，也不改变内容生成运行态数据模型。这里的数据模型仅描述统一错误体系需要稳定维护的对外契约、错误注册项、异常分类和请求追踪语义。

## 1. Error Envelope

### ErrorEnvelope

**Purpose**: 表示所有失败响应共用的统一外部结构。

| Field | Meaning | Rules |
|---|---|---|
| `success` | 请求是否成功 | 失败响应固定为 `false` |
| `code` | 机器可判定的稳定错误标识 | 必须来自错误码注册表 |
| `message` | 面向用户或调用方的可读说明 | 不依赖底层异常原文 |
| `data` | 成功数据载荷 | 失败时通常为空 |
| `request_id` | 本次请求的追踪标识 | 所有失败响应都必须存在 |
| `details` | 可选结构化上下文 | 只暴露安全且必要的信息 |

**Validation rules**

- `code` 必须稳定，不因文案变化而变化
- `message` 必须可读，但不应承担机器判定职责
- `details` 只能包含可安全暴露的字段

## 2. Error Code Registry

### ErrorCodeEntry

**Purpose**: 描述一个稳定错误标识的语义边界。

| Field | Meaning | Rules |
|---|---|---|
| `code` | 错误标识 | 全局唯一 |
| `domain` | 所属错误域 | 例如 `AUTH` / `WORKFLOW` / `TRACE` / `WORKSPACE` / `INFRA` |
| `category` | 错误类别 | 业务规则 / 应用流程 / 基础设施 |
| `http_status` | 对应的 HTTP 语义 | 同类错误应保持一致映射 |
| `message_template` | 默认可读说明 | 可按场景插入安全变量 |
| `retry_hint` | 调用方处理建议 | 用于区分修正输入、重新登录、稍后重试等 |

### Canonical Error Domains

- `AUTH`
- `WORKSPACE`
- `WORKFLOW`
- `TRACE`
- `ADMIN`
- `INFRA`
- `COMMON`

## 3. Exception Taxonomy

### DomainError

**Purpose**: 表示业务规则不满足或领域状态非法。

典型场景：
- 凭证错误
- 资源不存在
- 状态冲突
- 权限域内业务约束不满足

### ApplicationError

**Purpose**: 表示应用流程层的失败，如请求上下文缺失、契约不满足、跨模块流程冲突。

### InfrastructureError

**Purpose**: 表示数据库、缓存、模型服务、邮件服务等外部依赖故障。

**Validation rules**

- 三类异常必须能映射到统一 `ErrorEnvelope`
- `InfrastructureError` 的外部响应必须脱敏

## 4. Request Trace Context

### RequestErrorContext

**Purpose**: 为每次错误响应提供可追踪上下文。

| Field | Meaning | Rules |
|---|---|---|
| `request_id` | 请求唯一标识 | 每个请求唯一 |
| `path` | 请求路径 | 用于日志定位 |
| `method` | 请求方法 | 用于排障 |
| `error_code` | 最终外部错误标识 | 必须来自注册表 |
| `internal_cause` | 内部原始异常摘要 | 仅内部日志保存，不直接外露 |

## 5. Consumer Handling Model

### ErrorHandlingAction

**Purpose**: 表示调用方应采取的处理方向。

| Action | Meaning |
|---|---|
| `fix_input` | 需要用户修正输入 |
| `reauthenticate` | 需要重新登录或重新获取权限 |
| `retry_later` | 可稍后重试 |
| `contact_admin` | 需要联系管理员或查看日志 |
| `not_found` | 资源不存在或已不可访问 |

## 6. Persistence Impact

本特性当前不要求新增数据库表。错误码注册表、异常映射规则和请求追踪上下文优先作为应用层与文档层模型存在；后续若需要审计化持久化，可在独立特性中扩展。
