# Contract: Error Code Registry

## Purpose

定义 PromptChain 在 MVP2 中采用的错误码注册原则，确保错误标识具备稳定性、可读性、可扩展性和跨模块复用能力。

## Registry Rules

1. 每个错误标识全局唯一
2. 每个错误标识必须归属于明确的错误域
3. 每个错误标识必须有清晰的外部语义和调用方处理建议
4. 相同错误语义不得在不同模块中重复发明多个标识
5. 文案可变，错误标识不可随意变化

## Domain Namespaces

推荐第一阶段至少覆盖：

| Namespace | Scope |
|---|---|
| `COMMON_*` | 通用请求错误、参数错误、未知错误 |
| `AUTH_*` | 登录、注册、令牌、邮箱验证、密码重置 |
| `WORKSPACE_*` | 工作空间上下文、成员关系、越权访问 |
| `WORKFLOW_*` | 工作流运行、状态冲突、Gate、版本选择 |
| `TRACE_*` | trace、artifact、回放、节点详情 |
| `ADMIN_*` | 管理后台资源与配置权限 |
| `INFRA_*` | 数据库、缓存、模型服务、邮件等外部依赖故障 |

## Minimum Registry Entry Shape

| Field | Meaning |
|---|---|
| `code` | 稳定错误标识 |
| `domain` | 错误域 |
| `http_status` | 对应 HTTP 语义 |
| `description` | 面向维护者的稳定说明 |
| `consumer_action` | 前端或调用方应采取的处理方向 |

## Compatibility Rules

- 历史接口若仍返回旧格式，迁移期间必须存在映射路径
- 新接口不得再引入未注册的临时错误格式
- 若旧的数字 `code` 方案保留，也必须与稳定语义注册表形成明确映射，不能继续单独演化

## Deferred Items

以下内容不属于本特性的第一阶段强制范围：

- 完整的国际化错误文案体系
- 自动生成的错误码文档站点
- 覆盖所有内部脚本和非对外接口
