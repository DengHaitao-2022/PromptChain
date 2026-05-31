# Implementation Plan: Runtime Worker Reliability

**Branch**: `006-runtime-worker-reliability` | **Date**: `2026-05-20` | **Spec**: [`spec.md`](./spec.md)
**Input**: Feature specification from `/specs/006-runtime-worker-reliability/spec.md`

## Summary

PromptChain 当前运行态依赖 API 进程内 `asyncio.create_task` 推进工作流，并用 `_active_tasks`、`_workflow_locks` 维护进程内状态。该方案适合本地 MVP，但不适合生产多副本、进程重启、取消和超时恢复。本计划先定义 worker 执行边界和最小状态机，再分阶段把执行权迁出 API 进程，保持 PostgreSQL 为运行事实源，Redis 作为调度信号或轻量队列。

## Technical Context

**Language/Version**: Python 3.14+
**Primary Dependencies**: FastAPI, LangGraph, SQLAlchemy async, PostgreSQL, Redis
**Current Runtime Facts**:
- `backend/graph/executor.py` 中 `_schedule_drive()` 使用 `asyncio.create_task`
- `_active_tasks` 和 `_workflow_locks` 是进程内 dict
- `backend/db/postgres_store.py` 已持久化 `WorkflowRun / NodeRun / Artifact`
- LangGraph checkpoint 已持久化到 PostgreSQL
- Redis 基础设施存在，但不是 worker queue 权威

**Storage**: PostgreSQL 继续作为 run 状态、lease、heartbeat、retry 和 checkpoint 的事实源
**Queue**: Redis 仅作为 wake-up signal / delayed retry signal，不单独承载不可恢复状态
**Testing**: 后续实现阶段应补后端单元/集成测试；本阶段只产出 spec/plan/tasks
**Constraints**:
- 第一阶段不直接改 `backend/graph/executor.py`
- 不改 frontend
- 不引入 Temporal 或同级重型平台
- KISS / YAGNI / SOLID 优先，先单 worker MVP，再扩展多 worker

## Queue Options

| 方案 | 优点 | 成本/风险 | 结论 |
|------|------|-----------|------|
| Celery | 成熟、生态完整、retry/worker 管理能力强 | 引入较重，broker/result backend 配置多；对当前 async LangGraph 边界需要适配 | 暂不推荐 MVP |
| Dramatiq | 比 Celery 轻，任务模型清晰，Redis 支持好 | async 支持和现有 FastAPI/LangGraph 状态整合仍需胶水 | 可作为后续候选 |
| RQ | 简单直观，Redis 依赖少 | 偏同步任务模型，lease/heartbeat/恢复语义需要自行补齐 | 不推荐当前核心运行态 |
| Arq | asyncio 原生，Redis 队列，贴合 Python async | 仍需自建 run 状态权威、claim/lease/fencing 语义 | 可作为中期候选 |
| 自研 Redis signal + PostgreSQL claim | 最小依赖，保留 PostgreSQL 单一事实源，贴合现有 checkpoint | 需要自己实现 queue poll、lease、heartbeat、retry 策略 | 推荐 MVP |

## Recommended MVP

推荐采用 **PostgreSQL 原子 claim + Redis wake-up signal**：

- PostgreSQL 表字段或附属表记录 job 状态、owner、lease、heartbeat、retry、cancel/dead-letter 原因。
- Worker 通过 PostgreSQL 原子 UPDATE claim run，Redis 只负责提醒 worker 有新 run 或延迟 retry 到期。
- Worker 启动时先扫描 PostgreSQL 可 claim run，避免 Redis signal 丢失导致任务永久卡住。
- 单 worker MVP 可以先使用轮询 + Redis signal；多 worker 时依赖 PostgreSQL row-level lock / fencing token 保证执行权。

该方案最符合 KISS/YAGNI：不提前引入大平台，也不把 Redis 变成第二套状态真相。

## Data Model Direction

后续实现可二选一，优先推荐独立表以减少 `workflow_runs.metadata_json` 漂移：

### Option A: 独立 runtime_jobs 表（推荐）

字段建议：

- `id`
- `workflow_run_id`
- `status`
- `worker_id`
- `lease_token`
- `lease_expires_at`
- `heartbeat_at`
- `attempt`
- `max_attempts`
- `next_run_at`
- `cancel_requested_at`
- `cancel_reason`
- `last_error`
- `dead_letter_reason`
- `created_at`
- `updated_at`

优点：职责清晰，后续索引和查询简单，不污染 `WorkflowRun` 业务字段。

### Option B: 扩展 workflow_runs.metadata_json

优点：迁移少，快。

缺点：查询和锁语义弱，后续会把运行调度状态藏进 JSON，不利于可观测和约束。

## Lock and Recovery Semantics

### Single Worker MVP

1. API 创建 `WorkflowRun` 和 `RuntimeJob(status=queued)`。
2. Worker 轮询 `queued / retry_scheduled / lease_expired` job。
3. Worker 原子 claim：
   - `status in (...)`
   - `lease_expires_at is null or lease_expires_at < now()`
   - 更新 `worker_id / lease_token / lease_expires_at / heartbeat_at`
4. Worker 调用现有 executor 的同步驱动边界。
5. Worker 在节点边界刷新 heartbeat，并检查 cancel。
6. run 进入 Gate/Completed/Failed/Cancelled/DeadLetter 时释放 lease。

### Multi Worker Extension

- claim 必须依赖 PostgreSQL 条件更新或 `FOR UPDATE SKIP LOCKED`。
- 每个写入必须携带 `lease_token`，避免旧 worker 在 lease 过期后继续覆盖新 worker。
- Redis 不参与锁判定，只发 wake-up signal。
- Worker 启动必须先扫描数据库，保证 Redis 消息丢失可恢复。

## MVP Slices

### Slice 1: 状态模型与 migration

- 新增 runtime job schema。
- 定义状态枚举和合法转换。
- 保留现有 executor，不迁移执行路径。

### Slice 2: 单 worker claim/heartbeat/cancel

- 新增 worker loop。
- API start 只 enqueue，不直接 `create_task`。
- Worker claim 后调用现有 executor 边界。
- 支持 cancel_requested 和 heartbeat。

### Slice 3: timeout/retry/dead-letter

- lease 超时后重新入队。
- 节点失败按策略 retry。
- 超过 retry 上限进入 dead-letter。

### Slice 4: 多 worker readiness

- 加 fencing token。
- 加 `FOR UPDATE SKIP LOCKED` 或条件 UPDATE。
- 补多 worker 并发 claim 验收。

## Constitution Check

| Principle | Status | Evidence |
|-----------|--------|----------|
| Contract-First Workflow Surfaces | PASS | 先定义状态机和 worker contract，再改 executor |
| Traceable, Versioned Content Execution | PASS | PostgreSQL 继续作为 WorkflowRun/NodeRun/Artifact/checkpoint 事实源 |
| Human Gates Over Unsafe Assumptions | PASS | Gate 状态明确停在 worker 执行边界外，人工输入后重新入队 |
| Single Semantic Source of Truth | PASS | Redis 只做 signal，不做状态权威 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | MVP 先单 worker，再扩展多 worker，不引入重型平台 |

## Open Decisions for Implementation Phase

- `RuntimeJob` 独立表字段名最终确认。
- 公开 API 状态是否新增 `cancelled / timed_out`，或先映射到现有 `failed` 并在 metadata 暴露原因。
- Worker 进程入口命令命名，例如 `uv run python -m workers.runtime_worker`。
- 每个节点是否都具备安全取消边界；若没有，先以节点完成后取消为 MVP。

## Non-Goals

- 不在当前阶段编码。
- 不迁移前端状态展示。
- 不一次性重写 LangGraph executor。
- 不引入 Temporal。
