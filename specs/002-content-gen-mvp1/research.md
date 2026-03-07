# Research: PromptChain 内容生成系统 MVP1

## Research Scope

本阶段聚焦解决计划中的关键设计决策，覆盖以下方面：

- 运行态 API 契约与状态语义
- 人机门控（Gate）表达方式
- 运行态追踪与持久化策略
- 角色权限与业务角色映射
- 工作流编排与发布版本契约
- 实时推送在运行监控中的定位

所有结论以当前仓库事实和宪章为准，并优先满足契约一致性、可追溯性、HITL 明确性和棕地增量演进。

## Research Tasks Executed

1. 审查 `backend/main.py` 与 `frontend/src/lib/api.ts` 的工作流运行态契约
2. 审查 `backend/graph/content_generation_graph.py` 与相关测试，确认 Gate 状态来源
3. 审查 `backend/models/artifact.py`、`backend/services/artifact_store.py`、`backend/db/postgres_store.py`，确认追踪与持久化现状
4. 审查 `backend/models/auth_models.py` 与 `backend/services/permission_service.py`，确认 RBAC 技术模型
5. 审查 `backend/models/workflow_definition.py`、`backend/routes/workflow_definition_routes.py`、`backend/routes/workflow_version_routes.py`，确认编排与版本能力
6. 审查 `backend/routes/websocket_routes.py`，确认实时事件接口与当前集成程度

## Decisions

### 1. Canonical Workflow Runtime Contract

- **Decision**: 运行态外部契约继续以 `WorkflowResponse` 作为唯一骨架，并扩展为目标状态集合：`running`、`paused`、`needs_clarification`、`awaiting_outline_approval`、`awaiting_fact_check_approval`、`completed`、`failed`。
- **Rationale**: 当前前端 `frontend/src/lib/api.ts`、后端 `backend/main.py` 与契约测试已经围绕 `workflow_run_id + status + state` 结构对齐。要满足规格中的“暂停/恢复”，应在同一骨架中新增 `paused`，而不是引入第二套响应模型。
- **Alternatives considered**:
  - 返回原始 `WorkflowRun.model_dump()`：被拒绝，因为会再次造成后端存储模型与前端消费模型漂移。
  - 仅靠前端从 `state` 猜测状态：被拒绝，因为违背单一语义源和契约优先原则。

### 2. Gate Status Must Stay Explicit

- **Decision**: 澄清、提纲审批、事实核查审批继续保留为三种一等运行态，而不是统一折叠为通用 `paused`。
- **Rationale**: 宪章要求对 HITL 检查点做显式建模。当前图状态和 `_get_workflow_status()` 已经使用 `needs_clarification`、`awaiting_outline_approval`、`awaiting_fact_check_approval`。手动暂停只用于用户主动控制，不应与 Gate 语义混淆。
- **Alternatives considered**:
  - 用一个 `paused` 覆盖所有暂停场景：被拒绝，因为 UI、API 和审计记录将无法区分暂停原因。

### 3. Runtime Traceability Remains Write-Once and Versioned

- **Decision**: `Artifact`、`NodeRun`、`WorkflowRun` 继续作为运行追踪主干；重跑必须创建新的 `WorkflowRun`，并通过 `parent_version`/rerun 元数据保留版本链。
- **Rationale**: 这是当前模型与服务实现的核心设计，也是宪章中“可追溯、可重跑、可回放”的硬约束。任何覆盖式写入都会直接破坏 trace/replay 和论文评测证据。
- **Alternatives considered**:
  - 直接覆盖现有 Artifact 或复用原 WorkflowRun：被拒绝，因为会丢失版本历史与 rerun 来源关系。

### 4. Runtime Persistence Target Is PostgreSQL, Not Memory

- **Decision**: 目标设计中，内容运行态的 `WorkflowRun`、`NodeRun`、`Artifact` 和会话状态必须以 PostgreSQL 为权威持久化载体；当前内存 `ArtifactStore` 仅作为临时开发桩或迁移过渡。
- **Rationale**: 规格要求支持暂停/恢复、Gate 继续执行、回放和重启后不丢失上下文。当前内存存储无法满足这些硬性要求，因此不能作为目标实现的权威方案。
- **Alternatives considered**:
  - 保持当前内存存储并在文档中声明限制：被拒绝，因为与 FR-24、FR-28、NFR-03 冲突。
  - 只持久化 `WorkflowRun`，不持久化 `NodeRun`/`Artifact`/会话状态：被拒绝，因为无法满足可回放和 Gate 恢复。

### 5. Current Workspace RBAC Stays, but Viewer Gains Execute Capability

- **Decision**: 技术层继续保留现有工作空间级角色枚举 `viewer`、`editor`、`admin`、`owner`；为满足规格中的“普通用户可执行但不可编辑”，目标权限矩阵将把“执行已发布工作流”和“查看本人运行记录”能力下放到 `viewer`。
- **Rationale**: 这样可以复用当前用户、成员关系和权限校验模型，避免引入新的角色枚举和数据迁移，同时把业务角色映射为：普通用户 → `viewer`，设计者 → `editor`，管理员 → `admin`/`owner`。
- **Alternatives considered**:
  - 新增单独的 `operator`/`runner` 角色：被拒绝，因为会扩大认证与权限改造面。
  - 让普通用户直接使用 `editor`：被拒绝，因为这会授予不必要的工作流编辑权限。

### 6. Workflow Publication Needs an Explicit Publish Contract

- **Decision**: 目标接口需要新增显式发布动作，将“草稿编辑”和“可运行版本”区分开；推荐增加 `POST /api/workflows/{workflow_id}/publish` 作为发布入口。
- **Rationale**: 规格要求普通用户只能运行已发布工作流。当前模型已有 `is_published` 和版本快照表，但缺少独立发布接口，无法形成清晰的审核与发布边界。
- **Alternatives considered**:
  - 把“保存草稿”视为自动发布：被拒绝，因为普通用户会暴露到未审核流程。
  - 仅依靠版本恢复接口模拟发布：被拒绝，因为语义不清晰，且不利于前端操作闭环。

### 7. Persist Generic Node Types, Add Semantic Meaning in Config

- **Decision**: 工作流定义持久化层继续保留通用节点类型 `input`、`process`、`gate`、`checker`、`output`；业务语义如“开始节点、生成节点、解析节点、条件节点”通过 UI 标签或 `config` 中的语义字段表达。
- **Rationale**: 当前工作流定义模型、编辑器和校验逻辑已经围绕这套通用类型运作，直接更换持久化枚举会破坏既有草稿与版本快照。
- **Alternatives considered**:
  - 立即把持久化节点类型改成业务专用枚举：被拒绝，因为会引入保存格式迁移和编辑器兼容问题。

### 8. Realtime Push Is Supplementary Until Runtime Emits It End-to-End

- **Decision**: 在目标设计中，`GET /api/workflow/{id}` 仍是运行态权威读模型；WebSocket 事件用于提升实时体验，但客户端必须可通过轮询或主动刷新恢复一致性。
- **Rationale**: 当前 WebSocket 路由和 `emit_*` 工具已存在，但节点执行链路尚未完整接入发送逻辑。把 WebSocket 作为唯一事实源会让运行监控建立在未接通的通道上。
- **Alternatives considered**:
  - 让前端只依赖 WebSocket：被拒绝，因为当前实现并不支持这一前提。

### 9. Manual Pause/Resume Requires Dedicated Endpoints

- **Decision**: 目标运行态接口增加 `POST /api/workflow/{workflow_run_id}/pause` 和 `POST /api/workflow/{workflow_run_id}/resume`，仅用于用户主动控制运行；Gate 继续执行仍使用现有的澄清/审批接口。
- **Rationale**: 规格明确要求“启动/暂停/恢复”接口。当前仅有 Gate 场景下的内部 `resume()` 调用，没有面向手动控制的公共接口，也没有面向前端的 `paused` 状态。
- **Alternatives considered**:
  - 复用 `clarify`/`approve-*` 作为通用恢复接口：被拒绝，因为它们依赖特定 Gate 上下文。
  - 只在后端内部支持暂停，不暴露外部接口：被拒绝，因为不满足规格中的用户可操作要求。

## Consolidated Impacts

- 目标实现必须同步修改后端运行态接口、前端类型、Graph 状态映射与回放视图，避免再次出现字段漂移。
- 目标实现必须把运行态持久化从“开发期内存单例”迁移为“可恢复、可回放、可重跑”的权威存储。
- 目标实现必须把发布、暂停/恢复、viewer 执行权限纳入明确契约，而不是仅停留在内部数据模型或 UI 假设中。

## Remaining Clarifications

无。当前规格、仓库事实与研究决策已足够支撑进入设计与任务拆分阶段。
