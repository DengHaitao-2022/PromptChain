# Research: PromptChain Provider Architecture Upgrade

## Research Scope

本阶段只解决支撑最小 provider 升级所必需的技术决策，不扩展到插件系统或跨层重构。研究范围包括：

- 当前 PromptChain provider 实现与配置现状
- Google provider 的最小接入方式
- 统一调用入口与结构化输出兼容性
- provider registry 的最小组织方式
- 错误语义、测试验证点与迁移影响面

## Current Baseline Facts

### 仓库现状

1. `backend/services/llm_provider.py` 已有 `LLMProvider` 抽象基类、`OpenAIProvider`、`AnthropicProvider`、`OllamaProvider` 和 `LLMProviderFactory`。
2. 当前 factory 内部采用静态 `_providers` 映射和 `_instances` 单例缓存，但只覆盖 `openai / anthropic / ollama`。
3. 统一调用入口已经稳定存在：
   - `get_llm()`
   - `get_structured_llm()`
   - `get_current_model_info()`
4. `backend/nodes/*.py` 普遍直接依赖上述三个入口；改变调用面会产生跨节点回归风险。
5. `backend/core/config.py` 目前只暴露 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`OLLAMA_BASE_URL`，未显式声明 `GEMINI_API_KEY`。
6. `backend/.env.example` 仍写明“当前代码仅支持 openai / anthropic / ollama”，并把 Google key 场景标记为未支持。
7. `backend/pyproject.toml` 当前已包含 `langchain-openai`、`langchain-anthropic`，但未包含 Google 的 LangChain 集成包。
8. `backend/models/admin_models.py` 已有 `ModelProviderType.GOOGLE`，`frontend/src/app/console/settings/models/page.tsx` 已有 `google` 标签，`frontend/src/components/WorkflowEditor/panels/NodeConfigPanel.tsx` 也已出现 Gemini 模型选项，这说明管理域与展示层并不缺少 Google / Gemini 字面支持，本轮阻塞点主要集中在运行时 provider 层。
9. `backend/tests/` 当前没有 provider 专用测试文件，Google 接入若不新增单元验证，将无法证明 registry 改造未让 openai / anthropic / ollama 回归。

### 官方资料事实

1. LangChain 官方 Google 集成文档显示，Gemini 聊天模型对应的 Python 包是 `langchain-google-genai`，主要类为 `ChatGoogleGenerativeAI`。
2. `ChatGoogleGenerativeAI` 支持结构化输出，LangChain 官方文档将其标记为支持 `with_structured_output(...)`。
3. `ChatGoogleGenerativeAI` 既可以从环境变量读取 API Key，也支持通过 `google_api_key` 构造参数显式传入。
4. 最新集成文档说明该集成会优先读取 `GOOGLE_API_KEY`，并把 `GEMINI_API_KEY` 作为 fallback；但 PromptChain 不应把关键行为完全建立在第三方包的环境变量回退策略上。

### 参考来源

- [LangChain Google 集成文档](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai)
- [ChatGoogleGenerativeAI API Reference](https://api.python.langchain.com/en/latest/google_genai/chat_models/langchain_google_genai.chat_models.ChatGoogleGenerativeAI.html)
- [LangChain Models 文档: with_structured_output](https://docs.langchain.com/oss/python/langchain/models)

## Research Tasks Executed

1. 审查 `backend/services/llm_provider.py`，确认当前 provider 抽象、factory 和统一调用入口的边界。
2. 审查 `backend/core/config.py`、`backend/.env.example`、`backend/pyproject.toml`，确认配置与依赖缺口。
3. 审查 `backend/nodes/*.py` 和 `backend/services/__init__.py`，确认调用面和潜在回归范围。
4. 读取 LangChain 官方 Google 集成文档，确认 Google provider 的最小接入包、构造方式与结构化输出能力。

## Decisions

### 1. 保持统一调用入口不变

- **Decision**: `get_llm()`、`get_structured_llm()`、`get_current_model_info()` 保持原样，所有新能力都收敛到 provider 层内部。
- **Rationale**: 当前内容节点已经广泛依赖这三个入口。若改签名或改调用语义，会把一次 provider 增量升级放大成全链路修改。
- **Alternatives considered**:
  - 新增 `get_google_llm()` 等 provider 专属入口：被拒绝，因为会破坏统一抽象。
  - 改为 `provider/model` 复合字符串调用：被拒绝，因为超出本轮范围，且会牵动所有调用点。

### 2. provider registry 继续放在 `backend/services/llm_provider.py`

- **Decision**: 继续在单文件内维护静态 provider registry，只把当前 `_providers` 整理成更清晰的 registry 结构，不拆包、不扫描、不热加载。
- **Rationale**: 当前代码已经在该文件内完成 provider 抽象与工厂职责。最小实现应在现有结构上演进，而不是引入 OpenClaw 式插件系统。
- **Alternatives considered**:
  - 新建 `backend/services/providers/` 多文件目录：被拒绝，因为会引入额外迁移与导出同步成本。
  - 动态插件注册：被拒绝，因为当前只有 4 个 provider，复杂度明显过度。

### 3. Google provider 使用 `langchain-google-genai` + `ChatGoogleGenerativeAI`

- **Decision**: 新增 Google provider 时，采用 LangChain 官方集成 `langchain-google-genai`，provider 类内部使用 `ChatGoogleGenerativeAI`。
- **Rationale**: 这是 LangChain 官方给出的 Gemini 集成路径，且已确认支持结构化输出，能与现有抽象直接对接。
- **Alternatives considered**:
  - 直接使用 Google 原生 SDK：被拒绝，因为会绕开现有 LangChain 抽象，增加适配成本。
  - 使用已废弃或旧版 Google 生成式库：被拒绝，因为官方已明确迁移到当前集成包。

### 4. PromptChain 显式消费 `GEMINI_API_KEY`

- **Decision**: PromptChain 在配置层显式声明 `GEMINI_API_KEY`，Google provider 初始化时直接读取该值，并通过 `google_api_key` 参数传给 `ChatGoogleGenerativeAI`。
- **Rationale**: 即便上游文档说明 `GEMINI_API_KEY` 可以作为环境变量 fallback，PromptChain 仍应在自己的配置层显式消费该字段，避免把关键配置行为耦合到第三方包的隐式回退逻辑。
- **Alternatives considered**:
  - 仅依赖 `GOOGLE_API_KEY`：被拒绝，因为与本轮用户要求不一致。
  - 只在文档里声明 `GEMINI_API_KEY`，运行时依赖第三方自动发现：被拒绝，因为配置可读性与版本稳定性不足。

### 5. 结构化输出继续沿用 `with_structured_output`

- **Decision**: `get_structured_llm()` 不新增 Google 分支逻辑，继续通过 `model.with_structured_output(schema)` 生成结构化模型。
- **Rationale**: LangChain 官方文档确认 Google 集成支持 structured output。沿用现有统一路径可以把改动面压到最小。
- **Alternatives considered**:
  - 对 Google provider 单独设计结构化输出适配：被拒绝，因为没有必要。
  - 暂时禁用 Google 的结构化输出：被拒绝，因为会导致节点兼容性缺口。

### 6. 错误语义按三层处理，不增加 eager auth ping

- **Decision**:
  - provider 不支持：在 factory 选择阶段同步报错
  - 缺少凭证：在 provider 初始化阶段同步报错
  - 无效凭证 / 认证失败：在首次真实请求阶段报错，并保留 provider 上下文
- **Rationale**: 当前 `get_llm()` 只负责返回 LangChain 模型实例，不负责立即发起网络请求。若为了提前探测无效凭证而在构造阶段增加 eager auth ping，会引入额外网络成本与行为变化，不符合最小改动原则。
- **Alternatives considered**:
  - 每次 `get_llm()` 都执行鉴权探测：被拒绝，因为会让模型构造变成网络调用。
  - 完全不定义认证失败语义：被拒绝，因为 quickstart 与排障体验会继续模糊。

### 7. 测试以单元级覆盖为主，不做 live API 验证

- **Decision**: 本轮新增测试以 provider registry、配置缺失、统一入口回归和 Google provider 构造路径为主，全部使用 monkeypatch / stub，避免依赖真实 API key。
- **Rationale**: 这次目标是最小 provider 架构升级，不是联调外部环境。live 调用的不稳定性不应成为这轮实现的主要门槛。
- **Alternatives considered**:
  - 增加真实 Google key 端到端测试：被拒绝，因为不可在仓库内稳定复现。
  - 完全不补测试：被拒绝，因为无法证明 openai / anthropic / ollama 未回归。

### 8. `backend/services/__init__.py` 仅在确有需要时同步

- **Decision**: 计划默认只修改 `backend/core/config.py`、`backend/services/llm_provider.py`、`backend/.env.example`、`backend/pyproject.toml` 与 `backend/tests/*`；仅当导出一致性被实际依赖时，才追加修改 `backend/services/__init__.py`。
- **Rationale**: 当前调用方主要通过 `services` 包导入统一函数，而不是直接导入 `GoogleProvider`。最小改动应优先避免无必要扩散。
- **Alternatives considered**:
  - 强制同步所有导出：被接受为“可选补充”，但不是本轮默认必做项。

## Consolidated Impacts

- 不涉及数据库 schema 变更。
- 不涉及前端契约与页面改动。
- 不涉及后台管理 provider 枚举的额外迁移，现有 `google` 文案与枚举可直接复用。
- 不涉及工作流 API / Trace API / WebSocket 契约变更。
- 会新增一个后端依赖包，并更新 provider 支持列表与 quickstart 说明。
- 会影响运行时模型解析路径，因此必须补最小回归测试。

## Remaining Clarifications

无。当前规格、仓库事实与官方文档依据足以进入 Phase 1 设计与任务拆分。
