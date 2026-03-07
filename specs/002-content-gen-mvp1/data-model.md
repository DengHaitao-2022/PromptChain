# Data Model: PromptChain 内容生成系统 MVP1

## Model Scope

本数据模型将规格中的概念实体与当前仓库中的实际模型对齐，并给出目标实现所需的补充语义。它分为三层：

1. 身份与访问控制
2. 工作流定义与版本
3. 任务运行、Gate、追踪与回放

## 1. 身份与访问控制

### User（用户）

**Purpose**: 表示系统中的登录主体。
**Current source**: `backend/models/auth_models.py`, `backend/models/auth_orm.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 用户唯一标识 | UUID 字符串，主键 |
| `email` | 登录邮箱 | 必填、唯一、格式有效 |
| `username` | 用户名 | 可选，若存在则唯一 |
| `display_name` | 展示名称 | 可选，最大长度受模型约束 |
| `avatar_url` | 头像地址 | 可选 |
| `status` | 账号状态 | `active` / `inactive` / `suspended` |
| `email_verified` | 邮箱是否验证 | 未验证账号不得登录 |
| `created_at` / `updated_at` / `last_login_at` | 审计时间戳 | 登录、管理动作可更新 |

**Relationships**

- 一个 `User` 可拥有多个 `Workspace`
- 一个 `User` 可在多个 `Workspace` 中拥有 `Membership`
- 一个 `User` 可拥有多个 `RefreshToken`

**State transitions**

- `inactive` → `active`: 邮箱验证完成后
- `active` → `suspended`: 管理员禁用账号
- `suspended` → `active`: 管理员重新启用账号

### Workspace（工作空间）

**Purpose**: RBAC 和资源归属的边界。
**Current source**: `backend/models/auth_models.py`, `backend/models/auth_orm.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 工作空间唯一标识 | UUID 字符串 |
| `name` | 工作空间名称 | 必填，1-100 个字符 |
| `description` | 工作空间描述 | 可选 |
| `logo_url` | 标识图像地址 | 可选 |
| `owner_id` | 所属 owner 用户 ID | 必填 |
| `created_at` / `updated_at` | 时间戳 | 自动维护 |

**Relationships**

- 一个 `Workspace` 包含多个 `Membership`
- 一个 `Workspace` 包含多个 `WorkflowDefinition`
- 工作流、密钥、模型配置、审计日志都挂载在工作空间边界下

### Membership / Role（成员关系与角色）

**Purpose**: 表示用户在工作空间中的技术角色。
**Current source**: `backend/models/auth_models.py`, `backend/models/auth_orm.py`, `backend/services/permission_service.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 成员关系 ID | UUID 字符串 |
| `user_id` | 用户 ID | 必填 |
| `workspace_id` | 工作空间 ID | 必填 |
| `role` | 工作空间角色 | 当前枚举为 `viewer` / `editor` / `admin` / `owner` |
| `joined_at` | 加入时间 | 自动记录 |
| `invited_by` | 邀请人 | 可选 |

**Target permission mapping**

| Business Persona | Technical Role | Target Capability |
|---|---|---|
| 普通用户 | `viewer` | 运行已发布工作流、处理 Gate、查看本人任务与产物，不可编辑工作流 |
| 工作流设计者 | `editor` | 创建、编辑、校验、发布工作流，运行任务 |
| 管理员 | `admin` / `owner` | 管理成员、模型、密钥、全局查看运行记录 |

**Important note**

当前代码中的 `viewer` 仍是只读能力；目标实现需要调整权限矩阵，使其满足规格中的“执行但不可编辑”边界。

## 2. 工作流定义与版本

### WorkflowDefinition（工作流定义）

**Purpose**: 表示一条可视化工作流的当前草稿版本。
**Current source**: `backend/models/workflow_definition.py`, `backend/models/workflow_orm.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 工作流 ID | UUID 字符串 |
| `name` | 工作流名称 | 必填 |
| `description` | 工作流说明 | 可选 |
| `version` | 当前草稿版本号 | 每次更新递增 |
| `nodes` | 节点列表 | 当前以 JSON 形式保存 |
| `edges` | 连线列表 | 当前以 JSON 形式保存 |
| `workspace_id` | 所属工作空间 | 必填 |
| `created_by` | 创建者 | 可选但应尽量记录 |
| `is_published` | 是否已发布 | 当前模型已有字段，目标需要显式发布动作维护 |
| `is_deleted` | 是否软删除 | 删除采用软删除 |
| `created_at` / `updated_at` | 时间戳 | 自动维护 |

**Validation rules**

- 至少包含一个输入入口节点
- 节点 ID 必须唯一
- 边的 `source` / `target` 必须引用存在的节点
- 非输入/输出节点若完全未连接，应给出警告
- 发布前还需要满足“可运行版本”的更严格校验

### WorkflowVersion（工作流版本快照）

**Purpose**: 保存工作流历史版本与已发布版本快照。
**Current source**: `backend/models/workflow_orm.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 版本记录 ID | UUID 字符串 |
| `workflow_id` | 所属工作流 | 必填 |
| `version` | 版本号 | 必填，按整数递增 |
| `nodes` / `edges` | 当时的节点与连线快照 | 不应被后续草稿修改影响 |
| `change_log` | 变更说明 | 可选 |
| `created_by` | 变更执行者 | 可选 |
| `created_at` | 创建时间 | 自动记录 |

**Relationships**

- 一个 `WorkflowDefinition` 对应多个 `WorkflowVersion`
- 普通用户运行任务时必须绑定某个已发布版本，而不是草稿

### WorkflowNode（工作流节点）

**Purpose**: 表示画布上的一个处理节点。
**Current source**: `backend/models/workflow_definition.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 节点 ID | 必填且唯一 |
| `type` | 节点通用类型 | 当前持久化枚举为 `input` / `process` / `gate` / `checker` / `output` |
| `position.x` / `position.y` | 画布位置 | 必填数值 |
| `data.label` | 节点名称 | 用户可见标题 |
| `data.config` | 节点配置 | 存储 Prompt、门控类型、条件等扩展信息 |

**Design note**

规格中的“开始节点、生成节点、解析节点、条件节点”等业务语义，目标上应放入 `data.config` 或前端模板层，不直接替换持久化的基础类型。

### WorkflowEdge（工作流连线）

**Purpose**: 表示两个节点之间的顺序或条件关系。
**Current source**: `backend/models/workflow_definition.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 连线 ID | 必填且唯一 |
| `source` | 起点节点 ID | 必须存在 |
| `target` | 终点节点 ID | 必须存在 |
| `type` | 连线类型 | 默认 `default` |
| `data.condition` | 条件表达式 | 可选，用于条件分支 |
| `data.label` | 用户可见标签 | 可选 |

## 3. 任务运行、Gate、追踪与回放

### WorkflowRun（任务实例）

**Purpose**: 表示用户针对某个工作流版本发起的一次完整执行。
**Current source**: `backend/models/artifact.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 运行 ID | UUID 字符串 |
| `workflow_name` / `workflow_version` | 绑定的流程名称和版本 | 目标上应与发布版本对应 |
| `started_at` / `completed_at` | 时间戳 | 自动记录 |
| `status` | 持久化状态 | 当前为 `running` / `completed` / `failed` / `paused` |
| `current_node` | 当前执行节点 | 可为空 |
| `user_input` | 原始用户输入 | 必填 |
| `final_artifact_id` | 最终产物 ID | 完成后可回填 |
| `total_node_runs` / `total_llm_calls` / `total_tokens` / `total_duration_ms` | 汇总统计 | 用于回放与评测 |
| `metadata` | rerun 等附加信息 | 不应替代主字段语义 |

**Relationships**

- 一个 `WorkflowRun` 对应多个 `NodeRun`
- 一个 `WorkflowRun` 对应多个 `Artifact`
- 一个 `WorkflowRun` 在 rerun 场景下会通过 `metadata` 链接回原运行

### SessionState / GraphState（会话状态）

**Purpose**: 表示运行过程中的即时上下文，用于暂停恢复、Gate 继续执行和回放。
**Current source**: `backend/graph/content_generation_graph.py`

**Representative fields**

- 基础：`user_input`, `workflow_run_id`
- 意图解析：`intent_card`, `needs_clarification`, `clarification_questions`, `user_clarifications`
- 提纲审批：`outline`, `awaiting_outline_approval`, `outline_approved`, `user_decision`
- 内容生成：`draft_sections`, `generated_content`
- 自检修订：`final_content`, `refinement_history`
- 事实核查：`fact_check_report`, `awaiting_fact_check_approval`, `fact_check_decisions`, `manual_corrections`
- 错误处理：`error`

**Target rule**

会话状态必须具有可持久化实现，不能只停留在内存 `MemorySaver`，否则不满足暂停恢复、Gate 继续执行和重启后回放要求。

### NodeRun（节点执行记录）

**Purpose**: 表示某个节点的一次具体执行。
**Current source**: `backend/models/artifact.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 节点运行 ID | UUID 字符串 |
| `workflow_run_id` | 所属任务 | 必填 |
| `node_name` | 节点名称 | 如 `parse_intent`, `approve_outline` |
| `node_type` | 节点类别 | 如 `llm_call`, `validation` |
| `started_at` / `completed_at` / `duration_ms` | 执行时间 | 自动维护 |
| `status` | 节点状态 | `pending` / `running` / `completed` / `failed` / `interrupted` |
| `error_message` | 异常信息 | 失败或中断时记录 |
| `input_artifact_ids` / `output_artifact_ids` | 输入输出产物关系 | 用于回放与可复现 |
| `llm_calls` | LLM 调用明细 | 用于成本和调试 |
| `human_decision` | 人工决策记录 | 适用于审批/修改/重生成 |
| `retry_count` / `is_rerun` / `rerun_from_node_run_id` | 重试与重跑元数据 | 不得丢失 |

**State transitions**

- `pending` → `running`
- `running` → `completed`
- `running` → `failed`
- `running` → `interrupted`（等待 HITL）

### Artifact（中间产物）

**Purpose**: 表示节点执行输出的版本化产物。
**Current source**: `backend/models/artifact.py`

| Field | Meaning | Rules |
|---|---|---|
| `id` | 产物 ID | UUID 字符串 |
| `type` | 产物类型 | 当前支持 `intent_card`、`outline`、`fact_check_report`、`section_content`、`refinement_feedback`、`final_content` |
| `version` | 版本号 | 必须大于等于 1 |
| `content` | 产物内容 | 按类型存储 |
| `content_hash` | 内容摘要 | 自动计算，用于快速比对 |
| `created_at` | 创建时间 | 自动记录 |
| `parent_version` | 父版本产物 ID | 重跑或修改场景下关联旧版本 |
| `workflow_run_id` | 所属任务 | 必填 |
| `node_run_id` | 来源节点运行 | 必填 |
| `metadata` | 扩展元数据 | 不得取代核心版本关系 |

**Versioning rules**

- 同一节点新输出应创建新版本，而不是覆盖旧内容
- rerun/修改场景下必须保留 `parent_version`
- 任务详情与回放应能查到完整版本历史

### GateRecord（概念实体）

**Purpose**: 表示一次人工门控事件的完整记录。
**Current implementation mapping**: 由 `GraphState` 中的 Gate 标志、`clarification_questions`、`fact_check_decisions`、`manual_corrections` 与 `NodeRun.human_decision` 共同表达；当前没有独立 ORM。

| Field | Meaning |
|---|---|
| `gate_type` | 澄清 / 提纲审批 / 事实核查审批 |
| `workflow_run_id` | 所属任务 |
| `trigger_reason` | 缺信息 / 约束冲突 / 事实风险 |
| `questions` | 提问列表（最多 3 个） |
| `answers` | 用户回答或人工决策 |
| `opened_at` / `handled_at` | 打开与处理时间 |
| `resolution` | 继续执行 / 修改 / 重生成 / 驳回 |

**Target rule**

即使继续使用组合建模，Gate 的外部读模型和回放视图也必须能完整展示这些字段。

### ExecutionLog（概念实体）

**Purpose**: 表示节点执行证据。
**Current implementation mapping**: 由 `NodeRun`、`LLMCallRecord`、`HumanDecision` 和 Trace API 组合提供，不存在单独实体表。

## Canonical Runtime Status Model

为满足“单一语义源”，运行态需要区分“持久化状态”和“对外状态”：

### Persisted Workflow Status

| Status | Meaning |
|---|---|
| `running` | 后端正在执行或等待下一步 |
| `paused` | 用户主动暂停，等待明确恢复 |
| `completed` | 已成功结束 |
| `failed` | 已失败结束 |

### Public WorkflowResponse Status

| Status | Source of truth | Meaning |
|---|---|---|
| `running` | GraphState/WorkflowRun | 正常执行中 |
| `paused` | WorkflowRun + pause control | 用户主动暂停 |
| `needs_clarification` | `GraphState.needs_clarification` | 等待澄清输入 |
| `awaiting_outline_approval` | `GraphState.awaiting_outline_approval` | 等待提纲审批 |
| `awaiting_fact_check_approval` | `GraphState.awaiting_fact_check_approval` | 等待事实核查审批 |
| `completed` | `final_content` 或持久化完成态 | 已成功完成 |
| `failed` | WorkflowRun/异常路径 | 已失败 |

**Key rule**: Gate 状态优先级高于普通 `running`，而手动 `paused` 不得替代 Gate 状态。
