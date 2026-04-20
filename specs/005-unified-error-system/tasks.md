# Tasks: PromptChain 统一错误体系

**Input**: Design documents from `/specs/005-unified-error-system/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

**Tests**: 本特性要求最小后端契约验证与前端错误消费验证，因此包含测试任务；不要求端到端构建或运行。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this belongs to (`US1`, `US2`, `US3`)
- 所有任务都包含精确文件路径

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立 `005` 的实现骨架与统一错误模块落点。

- [ ] T001 创建统一错误体系模块目录与导出骨架：`backend/core/errors/__init__.py`
- [ ] T002 [P] 建立错误码注册表骨架与命名空间定义：`backend/core/errors/codes.py`
- [ ] T003 [P] 建立统一错误响应模型与请求级错误上下文骨架：`backend/core/errors/models.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 完成统一错误体系的后端基础设施；所有用户故事都依赖这一层。

**⚠️ CRITICAL**: 在本阶段完成前，不开始任何 API 域迁移。

- [ ] T004 定义异常分层基类与核心异常类型：`backend/core/errors/exceptions.py`
- [ ] T005 [P] 实现错误码到 HTTP 语义和外部 envelope 的统一映射逻辑：`backend/core/errors/mapping.py`
- [ ] T006 [P] 实现请求级 `request_id` 上下文与基础设施异常脱敏工具：`backend/core/errors/context.py`
- [ ] T007 实现全局异常处理器并接入统一错误响应：`backend/core/errors/handlers.py`
- [ ] T008 在 `backend/app.py` 挂接请求追踪、全局异常处理器与统一错误响应入口
- [ ] T009 评估并收敛现有 `backend/models/result.py`，决定其是否作为统一 envelope 兼容层保留

**Checkpoint**: 统一错误模型、错误码注册表、异常分层、请求追踪和全局 handler 已具备，核心 API 域可以开始分批迁移。

---

## Phase 3: User Story 1 - 前端和调用方获得稳定可判定的错误响应 (Priority: P1) 🎯 MVP

**Goal**: auth、workflow runtime、trace 三条主链路对外返回统一错误结构，前端能够按稳定错误标识处理核心失败场景。

**Independent Test**: 分别触发未登录、权限不足、资源不存在三类失败，请求和前端消费都不再依赖自由文本 `detail` 判断。

### Implementation for User Story 1

- [ ] T010 [US1] 迁移认证错误路径到统一错误体系：`backend/routes/auth_routes.py`
- [ ] T011 [US1] 迁移运行态核心错误路径到统一错误体系：`backend/routes/workflow_routes.py`
- [ ] T012 [US1] 迁移 trace / artifact 错误路径到统一错误体系：`backend/routes/trace_routes.py`
- [ ] T013 [US1] 在共享运行态辅助层收敛访问控制与错误翻译入口：`backend/routes/workflow_helpers.py`
- [ ] T014 [US1] 在前端统一解析错误 envelope、稳定错误标识和处理方向：`frontend/src/lib/api.ts`

**Checkpoint**: auth、workflow runtime、trace 已成为统一错误体系的第一批核心域；前端能够消费稳定错误标识。

---

## Phase 4: User Story 2 - 后端对领域错误与基础设施错误做一致映射 (Priority: P1)

**Goal**: 服务层和管理域不再混用 `ValueError / HTTPException / 裸 Exception`，而是通过统一异常分层和映射策略暴露一致的外部错误契约。

**Independent Test**: 触发业务规则错误、权限错误和基础设施错误三类失败，外部结构一致、基础设施异常脱敏且具备 `request_id`。

### Implementation for User Story 2

- [ ] T015 [P] [US2] 迁移工作空间与成员管理错误路径到统一错误体系：`backend/routes/workspace_routes.py`
- [ ] T016 [P] [US2] 迁移后台管理错误路径到统一错误体系：`backend/routes/admin_routes.py`
- [ ] T017 [US2] 将认证服务中的裸 `ValueError` 收敛为统一异常分层：`backend/services/auth_service.py`
- [ ] T018 [US2] 将权限服务中的直接 `HTTPException` 收敛为统一异常分层：`backend/services/permission_service.py`
- [ ] T019 [US2] 为数据库/模型服务/邮件等基础设施故障补齐脱敏映射入口：`backend/core/errors/mapping.py`

**Checkpoint**: 业务错误、权限错误和基础设施错误已能通过统一映射对外表达，不再由各路由自行决定错误风格。

---

## Phase 5: User Story 3 - 团队维护统一错误码注册表和复用规则 (Priority: P2)

**Goal**: 工作流定义/版本等遗留局部风格与统一错误体系接轨，并形成稳定注册表与迁移边界。

**Independent Test**: 新增或修改一个错误场景时，团队可以查到错误码归属、调用方处理建议和迁移边界，而不需要重新发明错误格式。

### Implementation for User Story 3

- [ ] T020 [P] [US3] 迁移工作流定义域到统一错误 envelope：`backend/routes/workflow_definition_routes.py`
- [ ] T021 [P] [US3] 迁移工作流版本域到统一错误 envelope：`backend/routes/workflow_version_routes.py`
- [ ] T022 [US3] 收敛 `backend/models/result.py` 与统一错误体系的兼容关系，消除“局部统一响应特例”
- [ ] T023 [US3] 固化错误码注册表、消费者处理语义与迁移说明：`backend/core/errors/codes.py`

**Checkpoint**: 统一错误体系不再只是核心域局部能力，而是具备可复用的注册表和迁移规则。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 用最小验证和文档收口当前 feature，不扩大实现面。

- [ ] T024 [P] 后端契约测试覆盖 auth / permission / not-found / infra error：`backend/tests/`
- [ ] T025 [P] 前端错误消费最小验证或类型级回归：`frontend/src/lib/api.ts`
- [ ] T026 更新本特性的 quickstart 验收说明，明确已迁移域与剩余迁移缺口：`specs/005-unified-error-system/quickstart.md`
- [ ] T027 对照 contracts / data-model / plan 做最终范围校验，确保未把未迁移接口误记为已完成：`specs/005-unified-error-system/plan.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: 无依赖，可立即开始
- **Phase 2**: 依赖 Phase 1；阻塞所有用户故事
- **Phase 3-5**: 全部依赖 Phase 2 完成
- **Phase 6**: 依赖目标用户故事实现完成

### User Story Dependencies

- **US1**: 可以在 Phase 2 后立即开始，是 MVP 第一优先级
- **US2**: 依赖统一错误骨架完成，但不要求 US1 全部完成后才开始；可在不同文件域并行
- **US3**: 依赖 US1/US2 的统一契约已基本成型，再去收敛遗留 `Result` 风格更稳妥

### Within Each User Story

- 先迁移后端主错误路径，再做前端统一消费或兼容收口
- 先完成统一错误语义，再补测试和 quickstart 验证
- 避免在迁移过程中一边改错误结构、一边扩大业务逻辑范围

### Parallel Opportunities

- `T002` 与 `T003` 可并行
- `T005` 与 `T006` 可并行
- `T015` 与 `T016` 可并行
- `T020` 与 `T021` 可并行
- `T024` 与 `T025` 可并行，但都依赖相应实现完成

## Implementation Strategy

### MVP First (US1 Only)

1. 完成 Phase 1
2. 完成 Phase 2
3. 完成 US1（T010-T014）
4. **STOP and VALIDATE**：验证未登录、权限不足、资源不存在三类失败场景

### Incremental Delivery

1. 先统一错误骨架和全局映射
2. 再让 auth / runtime / trace 成为第一批核心域
3. 再迁 workspace / admin / 旧 `Result` 风格
4. 最后补最小验证与迁移文档收口

## Notes

- 本特性优先解决“统一错误契约”，不是重写全部业务层
- `backend/app.py` 与 `frontend/src/lib/api.ts` 都属于热点文件，评审前必须单独核对 diff 边界
- 若某些旧接口在本轮未迁移，必须明确记录为迁移缺口，不能在 quickstart 或 plan 中默认为已统一
