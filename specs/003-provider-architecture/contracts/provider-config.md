# Provider Config Contract

## 0. Current Baseline

- 003 原始基线中，`backend/core/config.py` 只显式声明 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`OLLAMA_BASE_URL`。
- 当前 `dev@699bf53` 主线已显式声明 `GEMINI_API_KEY` 与 `GITHUB_MODEL_TOKEN`。
- 当前 `backend/.env.example` 声明代码支持 `openai / anthropic / google / github / ollama`。

## 1. Canonical Config Fields

本轮完成后，provider 配置层的最小权威字段应为：

| Field | Required When | Meaning |
|---|---|---|
| `DEFAULT_LLM_PROVIDER` | Always | 当前默认 provider 名称 |
| `DEFAULT_MODEL_NAME` | Optional | 全局默认模型覆盖值 |
| `OPENAI_API_KEY` | `DEFAULT_LLM_PROVIDER=openai` 或显式使用 `openai` 时 | OpenAI 凭证 |
| `ANTHROPIC_API_KEY` | `DEFAULT_LLM_PROVIDER=anthropic` 或显式使用 `anthropic` 时 | Anthropic 凭证 |
| `GEMINI_API_KEY` | `DEFAULT_LLM_PROVIDER=google` 或显式使用 `google` 时 | Google Gemini 凭证 |
| `GITHUB_MODEL_TOKEN` | `DEFAULT_LLM_PROVIDER=github` 或显式使用 `github` 时 | GitHub Models 凭证 |
| `OLLAMA_BASE_URL` | `DEFAULT_LLM_PROVIDER=ollama` 或显式使用 `ollama` 时 | Ollama 服务地址 |

## 2. Supported Provider Values

`DEFAULT_LLM_PROVIDER` 对外允许值：

- `openai`
- `anthropic`
- `ollama`
- `google`
- `github`

任何不在此列表中的值都必须被视为配置错误，而不是隐式回退。

## 3. Resolution Rules

1. 若调用方显式传入 `provider`，优先使用调用方值。
2. 否则使用 `DEFAULT_LLM_PROVIDER`。
3. 若调用方显式传入 `model`，优先使用调用方值。
4. 否则若设置了 `DEFAULT_MODEL_NAME`，使用该覆盖值。
5. 否则回退到 provider 自带默认模型。

## 4. Config Ownership Rules

1. `backend/core/config.py` 是 provider 环境变量的代码权威入口。
2. `backend/.env.example` 必须与代码支持列表一致，不允许继续保留“代码尚未支持 google provider”的过期提示。
3. 本轮不引入插件配置文件、不引入 provider 扫描目录、不引入动态模型目录。

## 5. Compatibility Notes

- 新增 `GEMINI_API_KEY` 与后续 `GITHUB_MODEL_TOKEN` 不应破坏现有 OpenAI、Anthropic、Ollama 的配置方式。
- `DEFAULT_MODEL_NAME` 继续保持“统一覆盖当前 provider 默认模型”的语义。
- 本轮不改变其他服务配置、数据库配置或认证配置字段。
