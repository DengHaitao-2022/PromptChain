# Tasks: PromptChain Provider Architecture Upgrade

**Input**: Design documents from `/private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: 本特性明确要求最小 provider 回归测试，因此保留 `backend/tests/test_llm_provider.py` 相关测试任务。

**Organization**: 任务按 Setup → Foundational → User Story 顺序组织，严格围绕 provider 架构升级，不扩展为插件系统、热加载、模型别名或密钥轮换。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件、无未完成依赖）
- **[Story]**: 对应用户故事标签（`[US1]`、`[US2]`、`[US3]`）
- 所有任务都包含精确文件路径，适合逐步实现与 review

## Phase 1: Setup (依赖与配置基线)

**Purpose**: 建立 Google provider 所需依赖与配置入口，不触碰运行时 provider 逻辑。

- [ ] T001 [P] Add `langchain-google-genai` to `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/pyproject.toml`
- [ ] T002 [P] Add `GEMINI_API_KEY` and preserve current provider/model defaults in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/core/config.py`
- [ ] T003 [P] Update supported-provider comments and Google env example in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/.env.example`

**Checkpoint**: 依赖与配置基线完成，运行时代码可以开始收口到统一 registry。

---

## Phase 2: Foundational (最小 registry 收口)

**Purpose**: 在不改变公共调用面的前提下，把现有 provider 工厂收口为最小 registry，实现 Google 接入前的共享基础。

**⚠️ CRITICAL**: User Story 实现必须等本阶段完成后再开始。

- [ ] T004 Define canonical supported-provider metadata for `openai / anthropic / ollama` in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py`
- [ ] T005 Refactor `LLMProviderFactory` in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py` to resolve providers through the minimal registry while preserving lazy instance caching
- [ ] T006 Add reusable unsupported-provider and missing-credential error helpers in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py`

**Checkpoint**: registry 已能稳定承载现有 provider，且 `get_llm / get_structured_llm / get_current_model_info` 仍未改签名。

---

## Phase 3: User Story 1 - 开发者启用 Google 作为默认 Provider (Priority: P1) 🎯 MVP

**Goal**: 让仅持有 Google 凭证的开发者可以通过现有统一入口完成最小 provider 配置并触发模型请求。

**Independent Test**: 在 `DEFAULT_LLM_PROVIDER=google` 且提供 `GEMINI_API_KEY` 时，`get_current_model_info()`、`get_llm()`、`get_structured_llm()` 可在不改调用方式的前提下解析 Google provider。

- [ ] T007 [US1] Add `GoogleProvider` with `ChatGoogleGenerativeAI` and explicit `google_api_key` wiring in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py`
- [ ] T008 [US1] Register `google` in the minimal registry and define Google default model resolution in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py`
- [ ] T009 [US1] Preserve the public behavior of `get_llm`, `get_structured_llm`, and `get_current_model_info` while routing through the Google-capable registry in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py`

**Checkpoint**: 代码层已具备 Google provider 最小接入能力，quickstart 不再被“代码不支持 google provider”阻塞。

---

## Phase 4: User Story 2 - 维护者继续使用现有 Provider (Priority: P2)

**Goal**: 在补齐 Google 后，OpenAI、Anthropic、Ollama 仍保持兼容，统一入口行为不回归。

**Independent Test**: 通过最小单元测试验证 `openai / anthropic / ollama / google` 都能沿用同一套 helper 和模型信息读取逻辑。

- [ ] T010 [US2] Create provider regression test scaffold in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/tests/test_llm_provider.py`
- [ ] T011 [US2] Add compatibility tests for registry resolution and helper stability across `openai / anthropic / ollama / google` in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/tests/test_llm_provider.py`
- [ ] T012 [US2] Adjust `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py` only as needed to keep existing provider defaults, caching, and helper behavior passing the regression tests

**Checkpoint**: 现有 provider 的兼容回归有自动化保障，新增 Google 没有把工厂升级成更大范围的重构。

---

## Phase 5: User Story 3 - 维护者快速定位 Provider 配置问题 (Priority: P2)

**Goal**: 明确区分 unsupported provider、missing credential、invalid credential / auth failure 三类错误语义。

**Independent Test**: 人为构造不支持 provider、缺少凭证、无效凭证 / 鉴权失败场景时，错误能被清晰区分，且不引入 eager auth ping。

- [ ] T013 [US3] Add unsupported-provider and missing-credential assertions in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/tests/test_llm_provider.py`
- [ ] T014 [US3] Add invalid-credential or auth-failure propagation assertions with provider context in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/tests/test_llm_provider.py`
- [ ] T015 [US3] Tighten error messages or exception mapping in `/private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py` so unsupported provider, missing credential, and auth failure remain distinguishable without adding eager auth checks

**Checkpoint**: provider 错误语义已可被维护者直接用于排障，且仍符合最小实现范围。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 让 quickstart 与关键文档和最终实现保持一致，不扩散到前端或额外系统设计。

- [ ] T016 [P] Sync Google provider setup, smoke steps, and expected failure boundaries in `/private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/quickstart.md`
- [ ] T017 [P] Sync provider support list and `GEMINI_API_KEY` setup example in `/private/tmp/promptchain-worktrees/003-provider-architecture/README.md`
- [ ] T018 [P] Reconcile implemented config and error semantics in `/private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/contracts/provider-config.md` and `/private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/contracts/provider-service.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup**: 无依赖，可立即开始
- **Phase 2: Foundational**: 依赖 Phase 1 完成；阻塞全部用户故事
- **Phase 3: US1**: 依赖 Phase 2 完成；这是消除 Google provider 阻塞的 MVP
- **Phase 4: US2**: 依赖 US1 完成；需要在 Google 已接入后验证旧 provider 兼容
- **Phase 5: US3**: 依赖 US1 完成；建议在 US2 后执行，因为与同一测试文件和 provider 文件高度重叠
- **Phase 6: Polish**: 依赖 US1、US2、US3 完成；用于同步 quickstart 和最小文档面

### User Story Dependencies

- **US1 (P1)**: 依赖 Foundational；无其他故事前置依赖，是本特性的 MVP
- **US2 (P2)**: 依赖 US1；兼容回归以 Google 接入后的 registry 为基础
- **US3 (P2)**: 依赖 US1；错误语义也建立在 Google 与最小 registry 已到位的前提上

### Within Each User Story

- US1 全部任务都修改 `/backend/services/llm_provider.py`，应顺序执行
- US2 的测试和兼容修正共享 `/backend/tests/test_llm_provider.py` 与 `/backend/services/llm_provider.py`，应顺序执行
- US3 的错误语义测试与实现共享相同文件，也应顺序执行

---

## Parallel Opportunities

- **Phase 1**: `T001`、`T002`、`T003` 可并行，分别修改依赖、配置、示例环境文件
- **Phase 6**: `T016`、`T017`、`T018` 可并行，分别同步 quickstart、README、contracts
- **US1 / US2 / US3 内部**: 无安全并行机会，因为核心任务集中在 `/backend/services/llm_provider.py` 与 `/backend/tests/test_llm_provider.py`

### Parallel Example: Phase 1

```bash
Task: "Add `langchain-google-genai` to /private/tmp/promptchain-worktrees/003-provider-architecture/backend/pyproject.toml"
Task: "Add `GEMINI_API_KEY` in /private/tmp/promptchain-worktrees/003-provider-architecture/backend/core/config.py"
Task: "Update Google env example in /private/tmp/promptchain-worktrees/003-provider-architecture/backend/.env.example"
```

### Parallel Example: User Story 1

```bash
# No safe parallel split inside US1.
# T007 -> T008 -> T009 should stay sequential because all tasks modify:
# /private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py
```

### Parallel Example: User Story 2

```bash
# No safe parallel split inside US2.
# T010 -> T011 -> T012 should stay sequential because they share:
# /private/tmp/promptchain-worktrees/003-provider-architecture/backend/tests/test_llm_provider.py
# /private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py
```

### Parallel Example: User Story 3

```bash
# No safe parallel split inside US3.
# T013 -> T014 -> T015 should stay sequential because they share:
# /private/tmp/promptchain-worktrees/003-provider-architecture/backend/tests/test_llm_provider.py
# /private/tmp/promptchain-worktrees/003-provider-architecture/backend/services/llm_provider.py
```

### Parallel Example: Phase 6

```bash
Task: "Sync quickstart in /private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/quickstart.md"
Task: "Sync README in /private/tmp/promptchain-worktrees/003-provider-architecture/README.md"
Task: "Sync provider contracts in /private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/contracts/provider-config.md and /private/tmp/promptchain-worktrees/003-provider-architecture/specs/003-provider-architecture/contracts/provider-service.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational
3. 完成 Phase 3: US1
4. 停下验证：确认 `DEFAULT_LLM_PROVIDER=google` 已不再被“代码不支持 provider”阻塞

### Incremental Delivery

1. Setup + Foundational：建立最小 provider 升级基线
2. US1：完成 Google provider 接入，先消除 quickstart 阻塞
3. US2：补齐 openai / anthropic / ollama 兼容回归测试
4. US3：补齐错误语义测试和最小实现收口
5. Final Phase：同步 quickstart、README、contracts，保持文档与实现一致

### Review-Friendly Execution

1. 每个 phase 都只围绕少量文件，优先保持单文件增量改动
2. `backend/services/llm_provider.py` 是热点文件，建议每完成一个 phase 就单独 review
3. `backend/tests/test_llm_provider.py` 统一承载最小回归验证，避免把 provider 测试分散到多个测试文件

---

## Notes

- 本清单不生成任何前端任务
- 本清单不引入插件扫描、热加载、模型别名、密钥轮换
- 所有公开 helper 都必须保持 `get_llm / get_structured_llm / get_current_model_info` 调用面不变
- `README.md` 与 provider contracts 只做最小同步，不扩展为新的架构设计文档
