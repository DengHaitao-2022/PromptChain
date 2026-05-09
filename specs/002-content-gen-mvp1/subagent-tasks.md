# Subagent Tasks: PromptChain 内容生成系统 MVP1（现状快照）

**Input**: `tasks.md`, `contracts/*`, `quickstart.md`, canonical 协作日志
**Output**: 下一轮可直接派工的主线事实、残余缺口与协作规则

## Dispatch Baseline

- 当前派工事实源固定为 `dev@c396a48`、[tasks.md](./tasks.md) 顶部状态快照，以及 canonical 协作文件。
- 旧的 `1 个 coordinator + Agent 0-5` owner 表与批次编排已经完成历史使命；它们解释了“代码怎么进 dev”，但不再适合作为“下一轮怎么派工”的依据。
- 如果后续需要重新拆分多 agent 队列，应基于本文件的剩余缺口重新建队列，而不是恢复 2026-03-08 那版 owner 分配。

## Current Mainline Snapshot

| Area | Related Tasks | Current Status | Mainline Fact |
|---|---|---|---|
| 运行态契约与持久化 | `T004`, `T006`, `T007`, `T008`, `T010`, `T012`, `T013`, `T018`, `T021`, `T032`, `T033` | 已在 `dev` | `WorkflowResponse`、pause/resume、Gate continuation、PostgreSQL 默认运行态存储、trace timeline 补偿和 WebSocket emit 都已进入主线 |
| 内容节点与 Gate 数据 | `T014`, `T019`, `T020` | 已在 `dev` | `backend/nodes/*` 已完成意图卡/提纲/正文/事实核查产物持久化与审批结果回写 |
| 认证闭环与会话入口 | `T039`, `T042` | auth-flow 已在 `dev`，验收仍待收口 | `register -> verify-email -> login` 与 `forgot-password -> reset-password -> login` 页面链路、Cookie 会话与 `GET /api/me` 都已进入主线；`T042` 只剩 auth/access 验收闭环 |
| 运行台首页与详情页 | `T015`, `T016`, `T022`, `T023`, `T035` | 已在 `dev` | 首页已支持已发布工作流/版本选择；详情页已接通 Gate、pause/resume、trace、意图卡/提纲/终稿展示 |
| 工作流编辑/发布闭环 | `T025`, `T026`, `T027`, `T028`, `T029`, `T030` | 已在 `dev` | 工作流 CRUD、validate、publish、versions/compare/restore、控制台工作流列表与编辑页都已并主线 |
| 权限与管理后台 | `T009`, `T038`, `T039`, `T040`, `T041` | 已在 `dev` | viewer/editor/admin/owner 权限矩阵、成员管理页、运行态/trace 归属校验已并主线 |
| 运行记录总览页 | `T036`, `T037` | 未收口 | `frontend/src/app/console/runs/page.tsx` 仍是占位实现，当前不要把它当作监控验收入口 |
| 共享前端运行态客户端 | `T005`, `T011` | 部分在 `dev` | 共享类型与 Gate/pause API 已有，但首页仍直接 `fetch` 工作流列表/版本/启动接口，尚未完全收拢到统一客户端 |
| Quickstart / Contracts / 协作文档 | `T043`, `T044`, `T047`, `T048` | 本轮已回填 | 文档现已按 `dev@c396a48` 对齐，不再沿用旧任务表结论 |
| 验收与 polish | `T017`, `T024`, `T031`, `T042`, `T045`, `T046` | 仍待继续 | 当前剩余主线只保留验收、文案与错误路径收口，不再包含 auth-flow、publish/version 或 Gate 主链路的缺失实现 |

## Branch And Worktree State

- 已吸收进 `dev` 的实现分支：
  - `code/feat-editor-publish`
  - `code/feat-runtime-contract-guard`
  - `code/feat-auth-flow-closure`
  - `code/feat-home-ui-ux-redesign`
- 已吸收并清理的历史实现线：
  - `code/feat-content-nodes-gate`
  - `code/feat-runtime-frontend-polish`
  - `code/feat-rbac-admin-boundaries`
  - 各类临时 integration / merge worktree
- 当前 MVP1 不存在仍在推进中的核心实现分支；下一轮若继续开发，应直接从 `dev@c396a48` 新建干净分支。
- 根工作区中的 `.cunzhi-memory/*`、`specs/002-content-gen-mvp1/*.jsonl`、`update.py` 属于本地运行态或协作工件，不能当作“已经进入 dev”的功能证据；`backend/orm/*` 已是当前仓库跟踪内容，不再视为未入主线目录。

## Next Dispatch Queue

1. `T036 + T037`
   - 目标：把 `frontend/src/app/console/runs/page.tsx` 接到真实数据，补齐运行记录总览页的监控/回放入口。
   - 现状：详情页内 trace/progress 已可用，但总览页仍是 mock。

2. `T005 + T011`
   - 目标：把首页当前的直接 `fetch` 收拢回共享前端客户端，消除 `frontend/src/lib/api.ts` 与页面实现的双轨状态。
   - 现状：后端接口已支持 `workflow_definition_id` / `workflow_version_id`，但共享 helper 还不是首页唯一入口。

3. `T045 + T046`
   - 目标：完成运行台/编辑器/成员页的中文文案与错误路径最终收口。
   - 现状：主要能力已经在 `dev`，但仍有最后一轮 polish 空间。

4. `T017 + T024 + T031 + T042`
   - 目标：把 US1/US2/US3/US5 的验收步骤沉淀成可复用结果，而不是停留在“代码已在主线”的状态。
   - 现状：这几项目前主要缺系统化验收闭环。

## Canonical Collaboration Rules

- 所有实时协作状态都写入以下 canonical 绝对路径，不得在各自 worktree 写相对路径副本：
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl`
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-locks.json`
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/gemini-executions.jsonl`
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-handoffs.jsonl`
- 前端任务默认由用户在 IDE 智能助手中于独立 `git worktree` 内执行；Codex 负责给出可粘贴派工提示词、文件边界、验收标准和 review gate。若实际执行过程需要留痕，记录到 canonical 协作日志，并注明执行者为 IDE 智能助手或其他实际执行渠道。
- 长期记忆统一使用 canonical `project_path=/Users/hi/Developer/03-personal/PromptChain`。
- `coordinator` 仍负责 sync audit、review gate 与 merge gate，但不应再根据旧 owner 表重复派发已吸收进主线的任务。
