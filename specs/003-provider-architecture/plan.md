# Implementation Plan: PromptChain Provider Architecture Upgrade

**Branch**: `003-provider-architecture` | **Date**: `2026-03-13` | **Spec**: [`spec.md`](./spec.md)
**Input**: Feature specification from `/specs/003-provider-architecture/spec.md`

## Summary

本计划聚焦一次后端最小增量升级：在不改变 `get_llm()`、`get_structured_llm()`、`get_current_model_info()` 三个统一入口的前提下，为 PromptChain 当前的 LangChain provider 抽象补齐 `google` 支持，并在 `backend/core/config.py` 中正式接入 `GEMINI_API_KEY`。实现路径保持在现有 `FastAPI + LangGraph + SQLAlchemy` 架构内，通过 `backend/services/llm_provider.py` 的静态 provider registry、一个最小 `GoogleProvider`、显式配置字段、文档更新和单元回归测试完成闭环，不扩展为插件系统、热加载、模型别名或密钥轮换能力。

## Technical Context

**Language/Version**: Python 3.14+
**Primary Dependencies**: FastAPI, LangGraph, SQLAlchemy, Pydantic 2, `langchain`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, 新增 `langchain-google-genai`, `python-dotenv`
**Storage**: N/A（本特性不新增持久化模型；仅涉及运行时配置与 provider 构造）
**Testing**: `pytest` + monkeypatch / stub 的后端单元测试；quickstart 提供手动 smoke 路径，不要求 live API 稳定通过
**Target Platform**: 本地开发环境与后端服务进程（`uv run uvicorn app:app --reload --port 8000`）
**Project Type**: 棕地后端服务增量改造（单仓库全栈项目中的后端内部服务层）
**Performance Goals**: 保持当前 provider 构造与统一入口语义不变；不新增 eager 鉴权探测；不把模型构造变成额外网络请求
**Constraints**: 必须保持 `get_llm` / `get_structured_llm` / `get_current_model_info` 调用面不变；`backend/core/config.py` 成为 `GEMINI_API_KEY` 代码权威入口；不得引入新服务框架、完整插件系统、热加载、模型别名或密钥轮换；必须维持 openai / anthropic / ollama 兼容；错误语义至少覆盖“不支持 provider / 缺少凭证 / 无效凭证或认证失败”；quickstart 目标是消除“代码不支持 google provider”阻塞，而不是兜底所有环境问题
**Scale/Scope**: 仅覆盖 `backend/services/llm_provider.py`、`backend/core/config.py`、`backend/.env.example`、`backend/pyproject.toml`、README/quickstart 文档与新增的后端 provider 单元测试；不改工作流节点调用方式、不改 API 契约、不改前端代码

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Gate

| Principle | Status | Evidence / Planned Control |
|-----------|--------|----------------------------|
| Contract-First Workflow Surfaces | PASS | 本特性不改 REST / WebSocket / 前端契约，只改后端内部 provider 服务契约；相关边界已写入 `contracts/provider-config.md` 与 `contracts/provider-service.md` |
| Traceable, Versioned Content Execution | PASS | 不修改 `Artifact` / `NodeRun` / `WorkflowRun` 数据链；`get_current_model_info()` 仍保留 provider/model 读模型，避免运行记录退化 |
| Human Gates Over Unsafe Assumptions | PASS | 本特性不改变澄清、提纲审批、事实核查审批三类 Gate，也不更改其 UI/API 表示 |
| Single Semantic Source of Truth | PASS | provider 支持列表、配置字段与错误语义集中收敛到 `llm_provider.py` registry 与 `backend/core/config.py`，避免调用方自行分叉语义 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | 计划只在现有后端服务、配置、依赖、文档和测试域内做小改动，不引入新框架或跨层重构 |

### Post-Design Re-check

| Principle | Status | Evidence / Designed Output |
|-----------|--------|----------------------------|
| Contract-First Workflow Surfaces | PASS | `research.md`、`contracts/provider-config.md`、`contracts/provider-service.md` 已固定 provider 配置字段、统一入口稳定面与错误语义 |
| Traceable, Versioned Content Execution | PASS | `data-model.md` 保持 `ModelInfo` 的 provider/model 读模型，并明确本轮不触碰 trace / artifact 持久化 |
| Human Gates Over Unsafe Assumptions | PASS | 设计输出明确标注本轮不涉及 HITL Gate 流程，因此无新增 Gate 契约漂移 |
| Single Semantic Source of Truth | PASS | `data-model.md` 与 contracts 统一了 provider 集合、错误分类与解析顺序，不把 `google` 支持散落在节点或路由层 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | `quickstart.md`、测试验证点和迁移影响面都限定在最小文件边界，并显式排除插件系统等超范围能力 |

## Project Structure

### Documentation (this feature)

```text
specs/003-provider-architecture/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── provider-config.md
│   └── provider-service.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── core/
│   └── config.py
├── services/
│   ├── __init__.py
│   └── llm_provider.py
├── tests/
│   └── test_llm_provider.py      # 计划新增
├── .env.example
└── pyproject.toml

README.md

specs/
└── 003-provider-architecture/
```

**Structure Decision**: 保持当前后端单体结构，不新建 provider 插件目录。provider registry 与具体 provider 实现继续留在 `backend/services/llm_provider.py`，配置权威入口继续留在 `backend/core/config.py`，文档与验收路径落在当前 feature 目录。`backend/services/__init__.py` 只在需要补齐导出时最小同步，不作为主修改面。

## Minimal Implementation Path

### Slice 1: 配置与依赖基线

1. 在 `backend/pyproject.toml` 增加 `langchain-google-genai`，不调整现有框架或服务边界。
2. 在 `backend/core/config.py` 中显式加入 `GEMINI_API_KEY` 配置项，保持 `DEFAULT_LLM_PROVIDER` 与 `DEFAULT_MODEL_NAME` 语义不变。
3. 在 `backend/.env.example` 与 README / `quickstart.md` 中把支持列表更新为 `openai / anthropic / ollama / google`，删除“代码尚未支持 google provider”的过期提示。

### Slice 2: provider registry 与 GoogleProvider

1. 在 `backend/services/llm_provider.py` 内把当前 `_providers` 静态映射整理为最小 registry，继续使用同文件懒加载缓存。
2. 新增 `GoogleProvider`，使用 LangChain 官方 `ChatGoogleGenerativeAI`，并显式通过 `google_api_key` 传入 `GEMINI_API_KEY`。
3. 保留 `get_structured_llm()` 的统一路径，继续依赖 `with_structured_output(...)`，不为 Google 单独开分支。
4. `get_current_model_info()` 继续返回 `{provider, model}`，当 provider 初始化失败时保留当前的默认模型回退语义。

### Slice 3: 错误语义与兼容回归

1. 把“不支持 provider”与“缺少凭证”从当前模糊 `ValueError` 文本整理为明确错误语义；若引入异常类，也应保持最小化并尽量兼容现有 `ValueError` 捕获习惯。
2. “无效凭证 / 认证失败”不通过 eager auth ping 预检，而是在首次真实请求阶段保留为 provider 运行期错误类别；本轮只要求它不再被误报成“不支持 provider”或“缺少凭证”。
3. 验证 openai / anthropic / ollama 原有路径未回归，不修改节点、路由或前端调用面。

## Validation Strategy

### Automated Test Points

- 新增 `backend/tests/test_llm_provider.py`，覆盖以下最小断言：
  - registry 支持列表包含 `openai / anthropic / ollama / google`
  - `get_llm(provider="google")` 能构造 `ChatGoogleGenerativeAI` 路径，且显式传递 `google_api_key`
  - `get_structured_llm()` 在 google provider 下仍调用 `with_structured_output(...)`
  - `get_current_model_info()` 在默认 provider / 默认模型覆盖 / provider 初始化失败时保持既有回退语义
  - 不支持的 provider 会返回包含非法值与支持列表的错误
  - 缺少 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GEMINI_API_KEY` 时可区分对应 provider 与字段名
  - openai / anthropic / ollama 仍能通过统一入口解析，不因 registry 重构回归

### Manual Quickstart Points

- `quickstart.md` 重点验证：
  - `DEFAULT_LLM_PROVIDER=google` 时，代码不再报“provider 不支持”
  - `GEMINI_API_KEY` 被正式消费
  - 结构化输出路径仍可构造
  - 无效凭证失败被视为运行时认证/上游问题，而不是代码尚未支持

### Explicit Non-Goals for Verification

- 不要求在本轮跑真实 Google live API 作为 merge gate
- 不要求解决网络、账号权限、配额、区域限制等外部环境问题
- 不要求前端、数据库或工作流节点层的额外回归场景

## Migration Impact

### Code Impact

- 主要修改面：`backend/core/config.py`、`backend/services/llm_provider.py`
- 配套修改面：`backend/pyproject.toml`、`backend/.env.example`、README、`specs/003-provider-architecture/*`
- 测试新增面：`backend/tests/test_llm_provider.py`

### Runtime / Operational Impact

- 需要一次 `uv sync` 以安装新的 Google LangChain 集成依赖
- 使用 Google 的开发者新增 `GEMINI_API_KEY` 配置；现有 OpenAI / Anthropic / Ollama 用户配置方式保持不变
- `DEFAULT_LLM_PROVIDER=google` 从“无代码支持”升级为“代码支持，剩余风险只在环境与凭证有效性”

### Cross-Layer Impact

- 无数据库迁移、无 ORM 改动、无 API 路由变更、无 WebSocket 契约变更
- 前端无需改动；仓库现有 `backend/models/admin_models.py`、`frontend/src/app/console/settings/models/page.tsx` 与 `frontend/src/components/WorkflowEditor/panels/NodeConfigPanel.tsx` 已存在 `google / Gemini` 相关枚举或展示项，不构成本轮阻塞
- 运行态 trace 只继续读取 `get_current_model_info()` 的结果，不需要前后端联合迁移

## Complexity Tracking

当前不存在需要额外豁免的宪章违例。本计划选择的方案都以最小改动、最小扩散、最小回归面为前提。
