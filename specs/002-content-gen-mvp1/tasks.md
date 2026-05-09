# Tasks: PromptChain 内容生成系统 MVP1

**Input**: Design documents from `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: 本任务清单不采用独立 TDD phase；仅在契约和关键回归点已有测试文件时安排测试更新任务，其余通过每个用户故事的独立验收路径和 `quickstart.md` 验证。
**Organization**: 任务按用户故事组织，确保每个故事都能独立实现、独立验证、独立演示。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（文件不冲突、无未完成前置依赖）
- **[Story]**: 对应 `spec.md` 中的用户故事标签
- 所有任务描述都包含精确文件路径

## Current Status Snapshot (`dev@6caaa24`)

说明：
- 本节才是当前派工事实源；下方 Phase/Task 原表保留为规划痕迹，不再直接代表主线进度。
- “已在 dev”表示代码或文档结果已经进入 `dev@6caaa24`。
- “静态通过”表示主线代码已合入，或已完成 review / 契约核对，但当前 `dev` 尚未补 live smoke 证据。
- “验收基线已回填”表示 quickstart/tasks 已按当前 `dev` 更新，可直接作为 acceptance review 基线；完成签收仍需人工 smoke。
- 2026-04-10 已在实际工作区 `dev@698b80d` 执行 current-dev smoke；结果见 [`quickstart.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/quickstart.md) 与 [`acceptance/current-dev-2026-04-10.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/acceptance/current-dev-2026-04-10.md)。
- 2026-04-12 已在候选分支 `fix-homepage-mvp1@e994c86` 执行 homepage 专项 smoke；结果见 [`acceptance/fix-homepage-mvp1-2026-04-12.md`](/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/acceptance/fix-homepage-mvp1-2026-04-12.md)。
- 下方原表中的文件路径反映的是规划阶段的修改落点；若当前代码结构已迁移，以 `dev@6caaa24` 的真实目录结构为准。

| 状态 | Task IDs | 当前说明 |
|---|---|---|
| 历史基线已在 `dev` | `T001`, `T002`, `T003` | 环境示例、启动说明、初始化 SQL 已存在于主线，后续仅在环境契约漂移时再改 |
| 已在 `dev` | `T004`, `T005`, `T006`, `T007`, `T008`, `T009`, `T010`, `T011`, `T012`, `T013`, `T014`, `T015`, `T016`, `T018`, `T019`, `T020`, `T021`, `T022`, `T023`, `T025`, `T026`, `T027`, `T028`, `T029`, `T030`, `T032`, `T033`, `T034`, `T035`, `T036`, `T038`, `T039`, `T040`, `T041`, `T045`, `T046` | 运行态契约/持久化、Gate、首页与详情页主链路、工作流发布闭环、RBAC 与成员管理、Google provider、homepage runtime client、console/runs 真列表，以及本轮默认前置的中文文案/错误路径收口都已进入主线 |
| 静态通过，待 runtime smoke | `T037` | `console/runs`、trace、artifact history 与 rerun 入口都已在 `dev`，但当前 `dev` 的监控/回放/重跑 smoke 尚未重新执行 |
| current-dev smoke 已执行，环境阻塞 | `T017`, `T024`, `T031`, `T042` | 2026-04-10 在 `dev@698b80d` 已实际执行 smoke；由于 PostgreSQL 不可达，四项均未进入 live 验收，通过状态不能回写 |
| 文档/契约已同步 latest dev | `T043`, `T044`, `T047`, `T048` | 契约、协作方式、入口结构与 quickstart 已按 `dev@6caaa24` 回写，可直接用于 acceptance review 准备 |

补充事实：
- latest `dev` 已包含 Google provider 支持，以及首页 runtime client 与 `console/runs` 真数据接线；不再把 `T005 / T011 / T036` 视为实现残口。
- 当前实现侧已无“先补功能才能验收”的已知 blocker，但 2026-04-10 的 current-dev smoke 已确认存在环境 blocker：本地 PostgreSQL 不可达，且默认 provider 指向空的 `anthropic` key。
- 2026-04-12 的 homepage 候选 smoke 已确认：viewer 可见已发布 workflow、可取版本、只见当前已发布版本、首页可启动 workflow，且不再出现 `workflows` undefined。
- 下一轮如继续推进，应先恢复 Docker / PostgreSQL / Redis，并修正 live LLM provider，再按 `quickstart.md` 中的 Smoke D / E / F / A / B / C 重跑，不要重新打开实现任务。

### Acceptance Closure Snapshot

| Story | Task | 当前归类 | 当前说明 |
|---|---|---|---|
| US1 | `T017` | homepage blocker 已解除，待最终 sign-off | `fix-homepage-mvp1` 已证明首页 workflow/version/start 链路恢复；完整标准生成链路的最终签收仍沿用主验收口径 |
| US2 | `T024` | homepage blocker 已解除，待最终 sign-off | 首页入口已恢复 Gate/恢复链路的验证前提；完整 Gate/pause-resume 最终签收仍沿用主验收口径 |
| US3 | `T031` | current-dev smoke 已执行，blocked | editor/viewer 发布闭环未进入 live smoke；受 PostgreSQL blocker 连带阻断 |
| US5 | `T042` | current-dev smoke 已执行，blocked | 认证页面静态可达、`/api/me` 未登录返回正常，但 auth/access live 回归被 PostgreSQL blocker 截断 |

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 对齐本地环境、配置入口和演示基础，避免后续实现阶段在环境问题上反复返工。

- [ ] T001 Update runtime persistence and demo-related defaults in `backend/.env.example`
- [ ] T002 [P] Refresh MVP1 local startup and demo instructions in `backend/README.md` and `frontend/README.md`
- [ ] T003 [P] Add role/workspace/demo seed guidance for MVP1 acceptance flows in `backend/db/init.sql`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 完成所有用户故事共享的契约、持久化和权限基线。

**⚠️ CRITICAL**: 本阶段完成前，不应开始任何用户故事实现。

- [ ] T004 Normalize canonical `WorkflowResponse` status extraction and state simplification in `backend/main.py`
- [ ] T005 [P] Mirror canonical runtime request/response types in `frontend/src/lib/api.ts`
- [ ] T006 Extend PostgreSQL-backed runtime persistence for `WorkflowRun` / `NodeRun` / `Artifact` in `backend/db/postgres_store.py`
- [ ] T007 Switch runtime store selection away from in-memory defaults in `backend/services/artifact_store.py` and `backend/services/__init__.py`
- [ ] T008 Persist graph session/checkpoint state for Gate continuation and manual pause/resume in `backend/graph/content_generation_graph.py`
- [ ] T009 [P] Align `viewer` / `editor` / `admin` / `owner` capability baselines in `backend/services/permission_service.py` and `frontend/src/lib/auth.ts`
- [ ] T010 Update existing runtime contract coverage in `backend/tests/test_workflow_response_contract.py`, `backend/tests/test_clarification_contract.py`, `backend/tests/test_fact_check_approval_api.py`, and `frontend/src/lib/__contract_tests__/workflow-contract.types.ts`

**Checkpoint**: 运行态契约、持久化通道和 RBAC 基线已统一，用户故事可以开始推进。

---

## Phase 3: User Story 1 - 普通用户发起并完成内容生成任务 (Priority: P1) 🎯 MVP

**Goal**: 普通用户能够选择已发布工作流、提交结构化输入、运行标准内容生成链路，并查看终稿与关键中间产物。
**Independent Test**: 使用普通用户账号从首页发起一个已发布工作流，任务到达终态后可在详情页看到意图卡、提纲、终稿、当前节点/最终状态信息。

- [ ] T011 [US1] Expand start-workflow request handling for published workflow/version selection in `backend/routes/workflow_routes.py`, `backend/routes/workflow_helpers.py`, and `frontend/src/lib/api.ts`
- [ ] T012 [P] [US1] Carry published workflow/version references on runtime records in `backend/models/artifact.py` and `backend/db/postgres_store.py`
- [ ] T013 [US1] Load published workflow context into start/resume execution paths in `backend/graph/content_generation_graph.py`
- [ ] T014 [US1] Persist intent, outline, section content, refinement feedback, and final content through PostgreSQL-backed node paths in `backend/nodes/intent_parser.py`, `backend/nodes/outline_generator.py`, `backend/nodes/content_generator.py`, and `backend/nodes/self_refiner.py`
- [ ] T015 [US1] Build published-workflow selector and structured task creation form in `frontend/src/app/page.tsx`
- [ ] T016 [US1] Refresh task detail rendering for intent card, outline, final content, and current node in `frontend/src/app/workflow/[id]/page.tsx`, `frontend/src/components/IntentCardViewer/IntentCardViewer.tsx`, `frontend/src/components/OutlineEditor/OutlineEditor.tsx`, and `frontend/src/components/ContentViewer/ContentViewer.tsx`
- [ ] T017 [US1] Validate the standard generation smoke path from `specs/002-content-gen-mvp1/quickstart.md` against `frontend/src/app/page.tsx`, `backend/routes/workflow_routes.py`, and `backend/routes/workflow_helpers.py`

**Checkpoint**: User Story 1 可独立演示，且不依赖 Gate、编辑器或回放功能即可交付基本价值。

---

## Phase 4: User Story 2 - 用户处理 Gate 并继续执行任务 (Priority: P1)

**Goal**: 系统能在缺信息、约束冲突和事实风险时明确暂停，并在用户处理澄清、提纲审批、事实核查审批后从中断处继续。
**Independent Test**: 运行一个会触发 Gate 的任务，确认会进入等待状态、给出 1-3 个问题或审批项，提交后继续执行到终态且状态流转正确。

- [ ] T018 [US2] Normalize clarification, outline approval, and fact-check approval transitions in `backend/graph/content_generation_graph.py`
- [ ] T019 [P] [US2] Align clarification question generation and enum priority exposure in `backend/nodes/intent_parser.py` and `backend/main.py`
- [ ] T020 [P] [US2] Persist Gate decisions and approval artifacts for outline and fact-check checkpoints in `backend/nodes/outline_generator.py` and `backend/nodes/fact_checker.py`
- [ ] T021 [US2] Add user-driven pause and resume endpoints that stay separate from Gate semantics in `backend/main.py`
- [ ] T022 [P] [US2] Wire clarify, outline approval, fact-check approval, pause, and resume client calls in `frontend/src/lib/api.ts`
- [ ] T023 [US2] Implement Gate and paused-state interactions in `frontend/src/app/workflow/[id]/page.tsx`, `frontend/src/components/ClarificationDialog/ClarificationDialog.tsx`, and `frontend/src/components/FactCheckViewer/FactCheckViewer.tsx`
- [ ] T024 [US2] Validate clarification, approval, and manual pause/resume flows from `specs/002-content-gen-mvp1/quickstart.md` against `backend/routes/workflow_routes.py`, `backend/routes/workflow_helpers.py`, and `frontend/src/app/workflow/[id]/page.tsx`

**Checkpoint**: User Story 2 可在已有运行链路上独立验证，且能清楚区分 Gate 等待与手动暂停。

---

## Phase 5: User Story 3 - 工作流设计者创建并发布内容生成流程 (Priority: P2)

**Goal**: 设计者可以在可视化编辑器里创建/保存草稿、校验流程并显式发布，普通用户只能看到已发布版本。
**Independent Test**: 使用设计者账号创建一个最小工作流，保存草稿、校验非法配置、发布成功，再切到普通用户确认只能运行已发布版本。

- [ ] T025 [US3] Add explicit publish endpoint and publish-side service logic in `backend/routes/workflow_definition_routes.py` and `backend/services/workflow_definition_service.py`
- [ ] T026 [P] [US3] Extend workflow validation for publish-grade checks in `backend/models/workflow_definition.py` and `backend/services/workflow_definition_service.py`
- [ ] T027 [P] [US3] Ensure workflow version snapshots and restore metadata support publication flow in `backend/models/workflow_orm.py` and `backend/routes/workflow_version_routes.py`
- [ ] T028 [US3] Add save/publish API wiring and editor-side request handling in `frontend/src/components/WorkflowEditor/hooks/useWorkflowApi.ts`
- [ ] T029 [US3] Add draft/published state UI, validation feedback, and publish action handling in `frontend/src/app/console/workflows/edit/page.tsx` and `frontend/src/components/WorkflowEditor/index.tsx`
- [ ] T030 [P] [US3] Surface workflow publish status and run availability in `frontend/src/app/console/workflows/page.tsx`
- [ ] T031 [US3] Validate draft-save-validate-publish flow from `specs/002-content-gen-mvp1/quickstart.md` against `frontend/src/app/console/workflows/edit/page.tsx` and `backend/routes/workflow_definition_routes.py`

**Checkpoint**: User Story 3 完成后，工作流编辑和发布闭环可独立演示，不需要依赖回放或管理员能力。

---

## Phase 6: User Story 4 - 用户或管理员监控并回放任务过程 (Priority: P2)

**Goal**: 用户或管理员可以查看任务当前节点、运行状态、时间线、回放详情、Artifact 历史和 rerun 结果。
**Independent Test**: 打开一个运行中任务和一个已结束任务，确认可查看进度；对已结束任务可查看回放、Artifact 历史并从指定节点发起 rerun。

- [ ] T032 [US4] Enrich workflow status and trace payloads with current node, pause metadata, and Gate timeline context in `backend/main.py`
- [ ] T033 [P] [US4] Emit node, workflow, Gate, and resume events from execution paths in `backend/graph/content_generation_graph.py` and `backend/routes/websocket_routes.py`
- [ ] T034 [P] [US4] Expand replay, artifact-history, and rerun data assembly in `backend/services/trace_service.py` and `backend/services/rerun_service.py`
- [ ] T035 [P] [US4] Refresh progress and timeline components for running/paused/gate/replay states in `frontend/src/components/WorkflowProgress/WorkflowProgress.tsx` and `frontend/src/components/TraceViewer/TraceViewer.tsx`
- [ ] T036 [US4] Update monitoring, replay, and rerun actions in `frontend/src/app/console/runs/page.tsx` and `frontend/src/app/workflow/[id]/page.tsx`
- [ ] T037 [US4] Validate monitoring, replay, artifact history, and rerun smoke flows from `specs/002-content-gen-mvp1/quickstart.md` against `frontend/src/app/console/runs/page.tsx` and `backend/services/trace_service.py`

**Checkpoint**: User Story 4 完成后，系统具备完整的演示与复盘能力，但它依赖前面已存在的运行数据。

---

## Phase 7: User Story 5 - 管理员维护账号与访问边界 (Priority: P3)

**Goal**: 管理员能够看到正确的成员/账号管理入口，执行角色调整和账号边界控制，同时普通用户和设计者不能越权访问。
**Independent Test**: 用三类角色分别登录，确认菜单和资源范围差异；管理员可调整成员角色并禁用/启用账号，非管理员访问管理能力时被拒绝。

- [ ] T038 [US5] Enforce role-scoped access checks for workflow execution, workflow editing, and admin-only resources in `backend/services/permission_service.py`, `backend/routes/workflow_definition_routes.py`, and `backend/main.py`
- [ ] T039 [P] [US5] Surface current user role and workspace context consistently in `backend/routes/auth_routes.py` and `frontend/src/contexts/AuthContext.tsx`
- [ ] T040 [P] [US5] Update client-side permission matrix and navigation guards in `frontend/src/lib/auth.ts` and `frontend/src/app/console/layout.tsx`
- [ ] T041 [US5] Complete admin member/user management flows for role updates and account enable/disable in `backend/routes/admin_routes.py`, `backend/routes/workspace_routes.py`, and `frontend/src/app/console/settings/members/page.tsx`
- [ ] T042 [US5] Validate auth-flow, menu isolation, and authorization boundaries from `specs/002-content-gen-mvp1/quickstart.md` against `frontend/src/app/login/page.tsx`, `frontend/src/app/register/page.tsx`, `frontend/src/app/verify-email/page.tsx`, `frontend/src/app/forgot-password/page.tsx`, `frontend/src/app/reset-password/page.tsx`, `frontend/src/app/console/layout.tsx`, and `backend/routes/auth_routes.py`

**Checkpoint**: User Story 5 完成后，权限边界和管理员控制能力可独立验证，不依赖编辑器或回放页面。

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 收尾跨故事问题，确保文档、契约、文案和最终 smoke flow 一致。

- [ ] T043 [P] Reconcile shipped runtime and realtime contracts in `specs/002-content-gen-mvp1/contracts/runtime-api.md` and `specs/002-content-gen-mvp1/contracts/realtime-events.md`
- [ ] T044 [P] Reconcile shipped publication and access contracts in `specs/002-content-gen-mvp1/contracts/workflow-definition-api.md` and `specs/002-content-gen-mvp1/contracts/auth-and-access.md`
- [ ] T045 Review Chinese user-facing copy across `frontend/src/app/page.tsx`, `frontend/src/app/workflow/[id]/page.tsx`, `frontend/src/app/console/workflows/edit/page.tsx`, and `frontend/src/app/console/settings/members/page.tsx`
- [ ] T046 Harden error-path handling for publish, pause/resume, and role failures in `backend/routes/workflow_routes.py`, `backend/routes/workflow_helpers.py`, `backend/routes/workflow_definition_routes.py`, and `backend/routes/auth_routes.py`
- [ ] T047 Update final acceptance steps and demo notes in `specs/002-content-gen-mvp1/quickstart.md`
- [ ] T048 Refresh feature-level implementation context in `AGENTS.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 无依赖，可立即开始。
- **Phase 2 (Foundational)**: 依赖 Phase 1，且阻塞全部用户故事。
- **Phase 3 (US1)**: 依赖 Phase 2；是最小可交付 MVP。
- **Phase 4 (US2)**: 依赖 Phase 2；建议在 US1 核心运行链路可用后并入，以复用运行态和任务详情页面。
- **Phase 5 (US3)**: 依赖 Phase 2；可与 US1/US2 并行推进。
- **Phase 6 (US4)**: 依赖 Phase 2，且最好在 US1/US2 提供稳定运行数据后推进。
- **Phase 7 (US5)**: 依赖 Phase 2；可与 US3 并行推进。
- **Phase 8 (Polish)**: 依赖所有目标故事完成。

### User Story Dependencies

- **US1 (P1)**: 只依赖 Foundational。
- **US2 (P1)**: 只依赖 Foundational；实际验证时复用 US1 的运行链路。
- **US3 (P2)**: 只依赖 Foundational。
- **US4 (P2)**: 依赖 Foundational；建议在 US1/US2 能产出真实运行记录后交付。
- **US5 (P3)**: 只依赖 Foundational。

### Dependency Graph

```text
Setup
  ↓
Foundational
  ├── US1
  ├── US2
  ├── US3
  └── US5
       ↓
      US4 (recommended after US1 + US2 produce runtime data)
  ↓
Polish
```

---

## Parallel Execution Examples

### Setup

```bash
T002 backend/README.md + frontend/README.md
T003 backend/db/init.sql
```

### User Story 1

```bash
T012 backend/models/artifact.py + backend/db/postgres_store.py
T015 frontend/src/app/page.tsx
```

### User Story 2

```bash
T019 backend/nodes/intent_parser.py + backend/main.py
T020 backend/nodes/outline_generator.py + backend/nodes/fact_checker.py
T022 frontend/src/lib/api.ts
```

### User Story 3

```bash
T026 backend/models/workflow_definition.py + backend/services/workflow_definition_service.py
T027 backend/models/workflow_orm.py + backend/routes/workflow_version_routes.py
T030 frontend/src/app/console/workflows/page.tsx
```

### User Story 4

```bash
T033 backend/graph/content_generation_graph.py + backend/routes/websocket_routes.py
T034 backend/services/trace_service.py + backend/services/rerun_service.py
T035 frontend/src/components/WorkflowProgress/WorkflowProgress.tsx + frontend/src/components/TraceViewer/TraceViewer.tsx
```

### User Story 5

```bash
T039 backend/routes/auth_routes.py + frontend/src/contexts/AuthContext.tsx
T040 frontend/src/lib/auth.ts + frontend/src/app/console/layout.tsx
```

---

## Implementation Strategy

### Strict MVP Scope

1. Complete Phase 1 and Phase 2
2. Complete Phase 3 (US1)
3. Stop and validate the standard generation flow independently

### Demo-Ready MVP Scope

1. Complete Phase 1 and Phase 2
2. Complete Phase 3 (US1)
3. Complete Phase 4 (US2)
4. Validate generation + Gate continuation as the core differentiator

### Incremental Delivery Order

1. **US1**: 先交付“能跑通”的内容生成主链路
2. **US2**: 再交付 Gate 与暂停/恢复，形成可控闭环
3. **US3**: 再交付设计者可视化编排与发布
4. **US4**: 再交付监控、回放和 rerun
5. **US5**: 最后补齐管理员和权限边界完善

### Notes

- 所有任务都包含精确文件路径，适合直接分派给 LLM 执行
- `[P]` 任务仅用于不同文件域、无未完成前置依赖的工作
- 每个用户故事都保留独立验收标准，避免跨故事耦合后无法演示
- 本清单优先遵循契约一致性、可追溯性、HITL 显式化和棕地增量变更原则
