# Data Model: PromptChain Provider Architecture Upgrade

## Model Scope

本特性不引入数据库实体，也不修改持久化模型。这里的数据模型仅描述 provider 层内部需要保持稳定的配置对象、注册项、读取结果和错误状态，作为实现与测试的共同语义基础。

> 当前主线说明（2026-05-23）：003 特性最初锁定 Google provider 最小接入；当前 `dev@699bf53` 主线的 provider registry 已继续扩展到 `openai / anthropic / google / github / ollama`，并通过 `GITHUB_MODEL_TOKEN` 支持 GitHub Models。

## 1. Provider Settings

### ProviderSettings

**Purpose**: 表示运行时可读取的 provider 配置集合。
**Current source**: `backend/core/config.py`

| Field | Meaning | Rules |
|---|---|---|
| `default_provider` | 当前默认 provider | 允许值为 `openai` / `anthropic` / `ollama` / `google` / `github` |
| `default_model_name` | 当前默认模型覆盖值 | 可为空；若为空则回退到 provider 自身默认模型 |
| `openai_api_key` | OpenAI 凭证 | 仅 `openai` 需要 |
| `anthropic_api_key` | Anthropic 凭证 | 仅 `anthropic` 需要 |
| `gemini_api_key` | Google Gemini 凭证 | 仅 `google` 需要 |
| `github_model_token` | GitHub Models 凭证 | 仅 `github` 需要 |
| `ollama_base_url` | Ollama 服务地址 | 仅 `ollama` 需要 |

**Validation rules**

- `default_provider` 必须属于 registry 中声明支持的 provider 集合
- 选择某 provider 时，若其要求凭证，则对应凭证字段必须存在
- `default_model_name` 是覆盖值，不改变 provider 支持范围

## 2. Provider Registry

### ProviderRegistryEntry

**Purpose**: 描述系统支持的单个 provider 的最小注册信息。
**Current source**: `backend/services/llm_provider.py`

| Field | Meaning | Rules |
|---|---|---|
| `provider_name` | provider 标识 | 唯一，作为配置与路由使用的 canonical key |
| `provider_class` | provider 实现类 | 必须实现统一 `LLMProvider` 接口 |
| `credential_field` | 对应凭证字段名 | 无凭证 provider 可为空 |
| `default_model_name` | provider 级默认模型 | 当全局默认模型未设置时使用 |
| `supports_structured_output` | 是否支持统一结构化输出路径 | 003 原始四个 provider 与当前主线新增的 `github` 都应保持统一路径 |

**Canonical provider set**

- `openai`
- `anthropic`
- `ollama`
- `google`
- `github`

## 3. Model Access

### ModelRequest

**Purpose**: 表示统一入口的一次模型请求意图。

| Field | Meaning | Rules |
|---|---|---|
| `provider` | 调用方显式指定的 provider | 可为空；为空时使用 `default_provider` |
| `model` | 调用方显式指定的模型名 | 可为空；为空时按覆盖值/默认值解析 |
| `kwargs` | 传给底层 chat model 的运行参数 | 不应破坏统一调用入口语义 |

### ModelInfo

**Purpose**: 表示 `get_current_model_info()` 返回的稳定读模型。

| Field | Meaning | Rules |
|---|---|---|
| `provider` | 当前 provider 标识 | 必须来自 registry |
| `model` | 当前模型标识 | 若 provider 初始化失败，允许回退到环境中的 `DEFAULT_MODEL_NAME` |

## 4. Error Model

### ProviderErrorState

**Purpose**: 表示 provider 解析过程中可区分的失败类型。

| State | Meaning | Trigger |
|---|---|---|
| `provider_not_supported` | 请求了未注册 provider | provider 名称不在 registry 中 |
| `credential_missing` | provider 所需凭证缺失 | 初始化 provider 时未找到必需配置 |
| `authentication_failed` | provider 凭证无效或鉴权失败 | 首次真实请求到达上游 SDK 时被拒绝 |

### ProviderErrorPayload

**Purpose**: 统一错误消息中最小必须表达的信息。

| Field | Meaning | Rules |
|---|---|---|
| `provider` | 出错 provider 名称 | 必填 |
| `error_type` | 错误类型 | 必须属于上面的三类之一 |
| `message` | 面向维护者的可读消息 | 必须能直接指导排障 |
| `credential_name` | 缺失或相关的凭证字段名 | 仅配置缺失场景必填 |
| `upstream_summary` | 上游异常摘要 | 仅认证失败场景可选 |

## 5. Resolution Flow

### Provider Resolution State Transitions

1. 读取 `ProviderSettings`
2. 解析目标 provider
3. 在 registry 中查找对应 `ProviderRegistryEntry`
4. 构造具体 provider 实例
5. 返回标准模型或结构化模型

### Failure Branches

- 第 2-3 步失败：进入 `provider_not_supported`
- 第 4 步失败且缺凭证：进入 `credential_missing`
- 第 5 步之后首次真实请求失败：进入 `authentication_failed`

## 6. Persistence Impact

本特性不新增数据库表、不修改 ORM 模型、不引入数据迁移。所有新模型都只存在于配置、运行时 provider registry 和测试语义中。
