# Quickstart: Provider Architecture Upgrade

本文档描述 `003-provider-architecture` 的最小验收路径。目标不是证明所有外部环境都无问题，而是确认 PromptChain 已经从“代码不支持 google provider”升级到“代码支持 google provider，剩余问题只可能来自环境或凭证有效性”。

## 1. 适用范围

本 quickstart 只覆盖以下能力：

- Google provider 已纳入受支持列表
- `GEMINI_API_KEY` 能被代码显式消费
- `get_llm()`、`get_structured_llm()`、`get_current_model_info()` 调用面不变
- openai / anthropic / ollama 未发生明显回归

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
cd /Users/hi/Developer/03-personal/PromptChain/backend
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
cd /Users/hi/Developer/03-personal/PromptChain/backend
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

## 6. Smoke Test C：错误语义

### 不支持的 provider

```bash
cd /Users/hi/Developer/03-personal/PromptChain/backend
DEFAULT_LLM_PROVIDER=foo uv run python - <<'PY'
from services import get_llm
get_llm()
PY
```

预期结果：

- 错误明确指出 `foo` 不受支持
- 错误包含当前支持列表

### 缺少 Google 凭证

```bash
cd /Users/hi/Developer/03-personal/PromptChain/backend
DEFAULT_LLM_PROVIDER=google GEMINI_API_KEY= uv run python - <<'PY'
from services import get_llm
get_llm()
PY
```

预期结果：

- 错误明确指出缺少 Google 所需凭证

### 无效凭证 / 认证失败

```bash
cd /Users/hi/Developer/03-personal/PromptChain/backend
uv run python - <<'PY'
from services import get_llm

llm = get_llm(temperature=0)
print(llm.invoke("ping"))
PY
```

预期结果：

- 若 key 无效，错误应表现为认证失败或上游拒绝，而不是“provider 不支持”或“缺少凭证”
- 本轮不承诺消除网络、账号权限、配额等外部环境问题

## 7. Regression Focus

自动化验证至少覆盖：

- openai / anthropic / ollama 仍可通过 registry 解析
- `get_current_model_info()` 在现有 provider 下保持既有语义
- 缺少凭证时的错误消息可区分 provider

## 8. 完成判定

以下条件同时满足时，可认为本特性达成 quickstart 目标：

1. `DEFAULT_LLM_PROVIDER=google` 不再触发“代码不支持 google provider”
2. `GEMINI_API_KEY` 能被代码显式读取并用于 provider 初始化
3. 统一调用入口保持不变
4. 现有三类 provider 无明显回归
5. 剩余失败仅来自外部环境、凭证有效性或服务可用性
