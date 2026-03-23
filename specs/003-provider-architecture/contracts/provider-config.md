# Provider Config Contract

## 0. Current Baseline

- `backend/core/config.py` 当前只显式声明 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`OLLAMA_BASE_URL`。
- `backend/.env.example` 当前声明代码仅支持 `openai / anthropic / ollama`。
- Google provider 支持尚未进入配置层权威列表，因此 quickstart 仍把 Google 视为未支持路径。

## 1. Canonical Config Fields

本轮完成后，provider 配置层的最小权威字段应为：

| Field | Required When | Meaning |
|---|---|---|
| `DEFAULT_LLM_PROVIDER` | Always | 当前默认 provider 名称 |
| `DEFAULT_MODEL_NAME` | Optional | 全局默认模型覆盖值 |
| `OPENAI_API_KEY` | `DEFAULT_LLM_PROVIDER=openai` 或显式使用 `openai` 时 | OpenAI 凭证 |
| `ANTHROPIC_API_KEY` | `DEFAULT_LLM_PROVIDER=anthropic` 或显式使用 `anthropic` 时 | Anthropic 凭证 |
| `GEMINI_API_KEY` | `DEFAULT_LLM_PROVIDER=google` 或显式使用 `google` 时 | Google Gemini 凭证 |
| `OLLAMA_BASE_URL` | `DEFAULT_LLM_PROVIDER=ollama` 或显式使用 `ollama` 时 | Ollama 服务地址 |

## 2. Supported Provider Values

`DEFAULT_LLM_PROVIDER` 对外允许值：

- `openai`
- `anthropic`
- `ollama`
- `google`

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

- 新增 `GEMINI_API_KEY` 不应破坏现有 OpenAI、Anthropic、Ollama 的配置方式。
- `DEFAULT_MODEL_NAME` 继续保持“统一覆盖当前 provider 默认模型”的语义。
- 本轮不改变其他服务配置、数据库配置或认证配置字段。
