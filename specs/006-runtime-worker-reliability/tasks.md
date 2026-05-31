# Tasks: Runtime Worker Reliability

**Input**: Design documents from `/specs/006-runtime-worker-reliability/`
**Prerequisites**: `spec.md`, `plan.md`
**Current phase**: specification only. Do not modify `backend/*` or `frontend/*` in this phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when files do not overlap
- **[Story]**: `US1`, `US2`, `US3`

## Phase 1: Contract and Schema Design

**Purpose**: 固定 worker 可靠性最小语义，不触碰 executor。

- [ ] T001 [US1] 定义 `RuntimeJob` 状态枚举和合法转换表，输出到 future implementation design
- [ ] T002 [US1] 设计 `runtime_jobs` 表字段、索引和约束，明确 `workflow_run_id` 一对一关系
- [ ] T003 [US1] 设计 PostgreSQL 原子 claim 语句，包含 `status`、`lease_expires_at`、`worker_id`、`lease_token`
- [ ] T004 [US1] 设计 worker 启动恢复扫描规则，覆盖 queued、retry_scheduled、lease_expired

## Phase 2: MVP Worker Boundary

**Purpose**: 单 worker 可恢复执行，保持现有 executor 作为内部驱动能力。

- [ ] T005 [US1] 新增 runtime job repository/service，负责 enqueue、claim、heartbeat、complete、fail
- [ ] T006 [US1] 新增 worker loop 入口，先支持单 worker 轮询 PostgreSQL
- [ ] T007 [US1] 将 API start 的后台执行改为 enqueue runtime job，不再直接依赖 API 进程内 `asyncio.create_task`
- [ ] T008 [US1] Worker claim 后调用现有 workflow drive 边界，并在 Gate/Completed/Failed 时释放 lease

## Phase 3: Cancel and Timeout

**Purpose**: 支持用户取消和系统超时，不让运行长期卡住。

- [ ] T009 [US2] 定义 cancel_requested 写入语义和合法状态转换
- [ ] T010 [US2] Worker 在节点安全边界检查 cancel signal，并写入 cancelled 原因
- [ ] T011 [US2] 定义 lease timeout 扫描规则，超时后进入 retry_scheduled 或 dead_letter
- [ ] T012 [US2] 明确 Gate 等待态取消策略，避免人工 Gate 被后台继续推进

## Phase 4: Retry and Dead Letter

**Purpose**: 最小失败恢复与审计终态。

- [ ] T013 [US3] 定义 retry policy：最大次数、退避策略、下一次可执行时间
- [ ] T014 [US3] Worker 失败时写入 `last_error`、`attempt`、`next_run_at`
- [ ] T015 [US3] 超过 retry 上限后写入 dead_letter_reason，并阻止自动再次执行
- [ ] T016 [US3] 设计运维查询入口或内部 service 方法，返回 queue/lease/heartbeat/retry/dead-letter 摘要

## Phase 5: Multi Worker Readiness

**Purpose**: 在 MVP 单 worker 后，为多副本部署补锁语义。

- [ ] T017 [US1] 为 claim 增加 fencing token，防止旧 worker lease 过期后覆盖新 owner
- [ ] T018 [US1] 增加并发 claim 验收，证明同一 run 只能被一个 worker 获取
- [ ] T019 [US3] 定义 Redis wake-up signal 的职责边界：只通知，不作为状态权威
- [ ] T020 [US3] Worker 启动时先扫 PostgreSQL，再订阅 Redis signal，避免 Redis 消息丢失

## Phase 6: Verification and Rollout

**Purpose**: 按小切片验证，不一次性替换整个运行态。

- [ ] T021 [US1] 验证 worker crash 后 lease 到期可恢复 claim
- [ ] T022 [US2] 验证 cancel 请求不会继续生成新的节点产物
- [ ] T023 [US2] 验证 timeout 后进入 retry 或 dead-letter，且可审计原因完整
- [ ] T024 [US3] 验证 worker owner、lease、heartbeat、attempt、last_error 可查询
- [ ] T025 [US3] 编写上线步骤：先旁路 shadow worker，再切 API start 到 enqueue，最后移除进程内 task 路径

## Dependencies & Execution Order

- Phase 1 阻塞全部实现。
- Phase 2 是 MVP 第一阶段，只要求单 worker 可恢复。
- Phase 3 依赖 Phase 2 的 worker heartbeat 和状态写入。
- Phase 4 依赖 Phase 3 的 timeout/fail 分类。
- Phase 5 在单 worker 稳定后再做，避免过早复杂化。
- Phase 6 贯穿每个切片，不能等全部功能写完才验证。

## MVP Cut

第一轮实现只做：

1. `runtime_jobs` schema
2. 单 worker claim/heartbeat
3. API start enqueue
4. worker crash 后恢复
5. cancel_requested 在节点边界生效

暂缓：

- 多 worker 并发执行优化
- 复杂 retry 策略
- 独立运维 UI
- Redis 延迟队列细节优化
