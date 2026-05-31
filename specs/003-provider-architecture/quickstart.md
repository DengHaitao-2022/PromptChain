# Quickstart: Provider Architecture Upgrade

本文档描述 `003-provider-architecture` 的 US1 最小验收路径。目标是确认 PromptChain 已经从“代码不支持 google provider”升级到“代码支持 google provider”，而不是在本轮证明所有 provider 回归与鉴权语义都已收口。

> 当前主线说明（2026-05-23）：当前 `dev@699bf53` 已在 Google provider 基础上继续支持 GitHub Models provider。若要验证当前完整 provider 集合，应额外检查 `openai / anthropic / google / github / ollama`。

## 1. 适用范围

本 quickstart 只覆盖以下能力：

- Google provider 已纳入受支持列表
- `GEMINI_API_KEY` 能被代码显式消费
- `get_llm()`、`get_structured_llm()`、`get_current_model_info()` 调用面不变

GitHub Models 的 `GITHUB_MODEL_TOKEN` 验收不属于 003 原始 US1 范围，但属于当前主线 provider 集合。

## 2. 前置条件

- 已合入本特性的最小实现
- `backend/pyproject.toml` 已包含 Google 所需的 LangChain 集成依赖
- 已在 `backend/.env` 中填写相应 provider 的最小配置

## 3. Google 最小配置

在 `backend/.env` 中至少设置：

```bash
GEMINI_API_KEY=your-google-key
DEFAULT_LLM_PROVIDER=google
DEFAULT_MODEL_NAME=gemini-2.5-flash
```

说明：

- `DEFAULT_MODEL_NAME` 可选；若未设置，则回退到 Google provider 内置默认模型
- 本轮不要求支持 `GOOGLE_API_KEY` 作为 PromptChain 的主配置字段

## 4. Smoke Test A：provider 解析成功

目标：确认代码层已支持 `google`，且无需改调用面。

```bash
cd backend
uv sync
uv run python - <<'PY'
from services import get_current_model_info, get_llm

print(get_current_model_info())
llm = get_llm(temperature=0)
print(type(llm).__name__)
PY
```

预期结果：

- `get_current_model_info()` 返回 `provider=google`
- `get_llm()` 能返回 Google chat model 实例
- 若此步骤失败，不应再是“provider 不支持”或“代码未接入 google”

## 5. Smoke Test B：结构化输出路径可构造

目标：确认 `get_structured_llm()` 在 Google provider 下仍可构造。

```bash
cd backend
uv run python - <<'PY'
from pydantic import BaseModel
from services import get_structured_llm

class Ping(BaseModel):
    answer: str

llm = get_structured_llm(Ping, temperature=0)
print(type(llm).__name__)
PY
```

预期结果：

- 调用方无需新增 Google 专属入口
- 若失败，应聚焦 Google 集成包或 provider 适配，而不是节点调用面

## 6. US1 边界说明

本 quickstart 不在当前 US1 范围内证明以下事项：

- openai / anthropic / ollama 的自动化兼容回归
- invalid credential / authentication failure 的明确语义区分
- 外部网络、账号权限、配额或服务可用性问题

这些内容分别留给后续 US2 / US3 和独立验证流程处理。

## 7. 完成判定

以下条件同时满足时，可认为本特性达成 quickstart 目标：

1. `DEFAULT_LLM_PROVIDER=google` 不再触发“代码不支持 google provider”
2. `GEMINI_API_KEY` 能被代码显式读取并用于 provider 初始化
3. 统一调用入口保持不变
4. Smoke Test A / B 若失败，原因不再是“代码尚未接入 google provider”
