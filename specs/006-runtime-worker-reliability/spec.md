# Feature Specification: Runtime Worker Reliability

**Feature Branch**: `006-runtime-worker-reliability`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "把当前进程内 asyncio task 执行模型演进为可恢复、可取消、可观测的 worker 执行边界；第一阶段不直接大改 executor，全程先做 spec/plan/tasks。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 运行创建后可被 worker 恢复执行 (Priority: P1)

当 API 进程创建 `WorkflowRun` 后，执行权由 worker 边界 claim，而不是依赖同一进程内的 `asyncio.create_task` 长期存活。若 API 进程重启或 worker 中断，系统可以从持久化状态和 checkpoint 中识别可恢复运行。

**Why this priority**: 当前 `_active_tasks` 和 `_workflow_locks` 都是进程内状态，单进程重启会丢失执行边界。先建立 claim/lease/heartbeat 是后续取消、重试和多副本部署的基础。

**Independent Test**: 创建一条运行记录后停止执行进程，再启动 worker；worker 能识别可 claim 的 run，并基于持久化 `WorkflowRun` 与 LangGraph checkpoint 继续推进或进入明确失败状态。

**Acceptance Scenarios**:

1. **Given** 运行记录处于可执行状态且没有有效 lease，**When** worker 拉取任务，**Then** worker 能原子 claim 该 run 并写入 owner、lease 和 heartbeat
2. **Given** worker 在执行中崩溃，**When** lease 超时，**Then** 新 worker 能重新 claim run，而不是永久卡在 running
3. **Given** run 已完成、失败或进入人工 Gate，**When** worker 扫描任务，**Then** 不会重复执行已经终止或等待人工输入的运行

---

### User Story 2 - 用户可以取消或超时终止运行 (Priority: P1)

用户或系统可以对运行中的 workflow 发出取消请求；worker 在安全检查点观察到取消信号后停止继续推进，并把运行落入稳定终态。超时策略也应通过同一状态机表达。

**Why this priority**: 运行态可靠性不是只恢复执行，也要能停止执行。没有 cancel/timeout，任务会在异常模型调用、卡住节点或用户不再需要时浪费资源，并让前端状态长期不可信。

**Independent Test**: 对正在执行的 run 发送 cancel；worker 在下一个可观测边界停止执行，`WorkflowRun` 进入 `cancelled` 或等价公开终态，且不会继续生成新的节点产物。

**Acceptance Scenarios**:

1. **Given** run 正在执行，**When** 用户请求取消，**Then** 系统记录 cancel_requested 并让 worker 在节点边界停止
2. **Given** run 超过 lease 或执行超时时间，**When** worker heartbeat 过期，**Then** 系统能标记 timeout 并允许后续按策略 retry 或 dead-letter
3. **Given** run 已进入人工 Gate，**When** 用户取消，**Then** Gate 被关闭并且不会被后台 worker 继续推进

---

### User Story 3 - 运维可以观察 worker 与队列健康 (Priority: P2)

运维或开发者可以看到每条 run 的 queue/claim/lease/heartbeat/retry/dead-letter 状态，并能定位某条运行为什么没有继续推进。

**Why this priority**: 可恢复执行如果不可观测，会把失败从“任务丢失”变成“任务静默卡住”。最小可观测字段和事件比完整监控平台更符合 KISS/YAGNI。

**Independent Test**: 人工制造一次 worker crash 或节点异常；通过数据库字段和事件日志能判断最后 owner、上次 heartbeat、retry 次数和失败原因。

**Acceptance Scenarios**:

1. **Given** worker claim run，**When** 查看运行记录，**Then** 可以看到 worker owner、lease 到期时间和最近 heartbeat
2. **Given** run 被 retry，**When** 查看运行记录，**Then** 可以看到 retry 计数、上次失败原因和下一次可执行时间
3. **Given** run 超过最大重试次数，**When** 查看运行记录，**Then** run 进入 dead-letter 且保留可审计原因

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统必须定义运行态 worker 状态机，覆盖 create、enqueue、claim、lease、heartbeat、timeout、cancel、retry、dead-letter 和 terminal 状态。
- **FR-002**: 系统必须保证 claim 是原子的，避免两个 worker 同时执行同一条 run。
- **FR-003**: 系统必须在 worker 执行期间维护 lease 和 heartbeat，允许崩溃后恢复。
- **FR-004**: 系统必须区分用户取消、系统超时、节点失败和不可恢复失败，避免全部折叠为普通 failed。
- **FR-005**: 系统必须利用现有 PostgreSQL `WorkflowRun / NodeRun / Artifact / checkpoint` 作为恢复事实源，不引入第二套运行真相。
- **FR-006**: 系统必须明确 Redis queue 的职责边界：可以作为调度信号和延迟队列，但不能成为唯一状态权威。
- **FR-007**: 系统必须支持 MVP 阶段单 worker 部署，并为后续多 worker/多副本扩展保留锁语义。
- **FR-008**: 系统必须提供最小可观测字段或事件，使 run 的 owner、lease、heartbeat、retry 和 dead-letter 可审计。
- **FR-009**: 系统第一阶段不得直接大改 `backend/graph/executor.py`，只产出可实施 spec/plan/tasks。
- **FR-010**: 系统不得引入 Temporal 或同级重型平台，除非 plan 明确证明轻量方案无法满足 MVP。

### Key Entities *(include if feature involves data)*

- **Runtime Job**: 一条可被 worker claim 的执行单元，通常一对一关联 `WorkflowRun`。
- **Worker Lease**: worker 对某条 run 的限时执行权，包含 owner、过期时间和 fencing token。
- **Heartbeat**: worker 在执行中周期性写入的存活信号。
- **Cancel Request**: 用户或系统写入的停止信号，由 worker 在安全边界观察并收敛为终态。
- **Retry Policy**: 节点或 run 失败后的最小重试策略，包含最大次数、下一次可执行时间和失败原因。
- **Dead Letter**: 超过重试上限或遇到不可恢复错误后的审计终态。

## State Machine

```text
created
  -> queued
  -> claimed
  -> running
  -> gate_waiting
  -> queued        # 人工输入完成后重新入队
  -> completed

running
  -> cancel_requested
  -> cancelled

running
  -> timed_out
  -> retry_scheduled
  -> queued

running
  -> failed
  -> retry_scheduled
  -> queued

retry_scheduled
  -> dead_letter   # 超过 retry 上限

claimed/running
  -> lease_expired
  -> queued        # 允许新 worker 重新 claim
```

MVP 可以先把公开终态映射到现有前端可识别状态，但内部必须保留 cancel/timeout/dead-letter 原因，避免丢失恢复语义。

## Assumptions

- 当前 `backend/graph/executor.py` 使用 `asyncio.create_task`、`_active_tasks` 和 `_workflow_locks` 管理进程内执行。
- PostgreSQL 已持久化 `WorkflowRun / NodeRun / Artifact` 和 LangGraph checkpoint，可作为恢复事实源。
- Redis 已在基础设施中存在，适合作为调度信号或轻量队列组件。
- 第一阶段目标是确定 worker 边界和任务切片，不直接改 executor。

## Out of Scope

- 本阶段不修改 `backend/*` 实现代码。
- 本阶段不修改 `frontend/*`。
- 本阶段不引入 Temporal、Airflow、Argo Workflows 等重型平台。
- 本阶段不解决所有节点幂等性问题，只识别幂等边界和后续任务。
- 本阶段不做数据清洗大迁移。

## Success Criteria *(mandatory)*

- **SC-001**: spec/plan/tasks 明确 MVP 状态机和后续实现任务。
- **SC-002**: 队列选型给出 Celery / Dramatiq / RQ / Arq / 自研 Redis queue 的取舍，并推荐最小方案。
- **SC-003**: plan 明确单 worker MVP 与多 worker 扩展边界。
- **SC-004**: tasks 不要求第一阶段直接改 executor，而是先完成迁移/模型/worker 骨架/验收切片。
