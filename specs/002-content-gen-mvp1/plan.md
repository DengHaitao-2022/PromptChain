# Implementation Plan: PromptChain 内容生成系统 MVP1

**Branch**: `002-content-gen-mvp1` | **Date**: `2026-03-07` | **Spec**: [`spec.md`](./spec.md)
**Input**: Feature specification from `/specs/002-content-gen-mvp1/spec.md`

## Summary

本计划为 PromptChain 内容生成系统 MVP1 提供实现前设计基线。核心目标是在现有前后端分离架构上，统一工作流运行态契约，保留并强化 `Artifact` / `NodeRun` / `WorkflowRun` 追踪链，补齐工作流发布与任务暂停/恢复的外部接口，并把澄清、提纲审批、事实核查审批三类 HITL Gate 作为显式状态贯穿 API、持久化和 UI。Phase 0 研究已确定目标运行态持久化必须迁移到 PostgreSQL；Phase 1 进一步产出数据模型、接口契约和验收路径，为后续 `/speckit.tasks` 的增量实现拆分提供依据。

## Technical Context

**Language/Version**: Python 3.14+（backend）, TypeScript 5 + React 19 + Next.js 16（frontend）
**Primary Dependencies**: FastAPI, LangGraph, SQLAlchemy, Pydantic 2, Next.js App Router, React, `@xyflow/react`, Radix UI
**Storage**: 现状为 PostgreSQL（认证/工作空间/工作流定义）+ 内存 `ArtifactStore`（内容运行态）；目标为 PostgreSQL 统一承载运行态 `WorkflowRun` / `NodeRun` / `Artifact` / 会话状态，内存存储仅作开发期回退
**Testing**: `pytest` + FastAPI `TestClient` 后端契约测试，前端 TypeScript 类型级契约校验，后续实现阶段配合 Ruff / ESLint 校验
**Target Platform**: 浏览器访问的前端控制台 + 服务端 API / WebSocket
**Project Type**: 棕地全栈 Web 应用（前端与后端分离，统一仓库管理）
**Performance Goals**: 登录、任务启动、Gate 提交、暂停/恢复保持交互式响应；90% 示例任务在不计人工等待时间的情况下 10 分钟内到达终态
**Constraints**: 必须保持 `backend/main.py`、GraphState、持久化模型与 `frontend/src/lib/api.ts` 的契约一致；用户可见文案默认中文；浏览器认证继续依赖 Cookie 与 `credentials: include`；手动暂停不得与 Gate 暂停混淆
**Scale/Scope**: 毕业设计 MVP，覆盖登录与权限、工作流编排、内容生成、Gate、人机恢复、监控回放，服务 demo 级多用户/多工作流场景

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Gate

| Principle | Status | Evidence / Planned Control |
|-----------|--------|----------------------------|
| Contract-First Workflow Surfaces | PASS | 计划显式覆盖运行态 `WorkflowResponse`、工作流定义 `Result` 包装、认证/权限接口、WebSocket 事件，以及新增 publish / pause / resume 契约 |
| Traceable, Versioned Content Execution | PASS | 研究前就将 `Artifact`、`NodeRun`、`WorkflowRun` 版本链定义为不可削弱的核心约束 |
| Human Gates Over Unsafe Assumptions | PASS | 明确澄清、提纲审批、事实核查审批三类 Gate，并要求在 UI 与 API 中独立表示 |
| Single Semantic Source of Truth | PASS | 研究目标先统一 status、`clarification_questions`、节点类型和发布状态语义，再推进设计 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | 仅在现有 `backend/`、`frontend/` 和 `specs/002-content-gen-mvp1/` 域内规划增量变更 |

### Post-Design Re-check

| Principle | Status | Evidence / Designed Output |
|-----------|--------|----------------------------|
| Contract-First Workflow Surfaces | PASS | `research.md` 与 `contracts/*.md` 已明确现有/目标接口、兼容边界和新增契约 |
| Traceable, Versioned Content Execution | PASS | `data-model.md` 保留 write-once Artifact、节点运行记录和 rerun 版本链 |
| Human Gates Over Unsafe Assumptions | PASS | 运行态契约与实时事件契约都区分三类 Gate 和手动暂停 |
| Single Semantic Source of Truth | PASS | 计划将 `WorkflowResponse.status + state` 作为运行态读模型，将角色与节点类型的技术表示固定下来 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | 设计产物限定在契约、数据模型、验收路径和 agent context，同步说明需要后续实现的新增接口 |

## Project Structure

### Documentation (this feature)

```text
specs/002-content-gen-mvp1/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── auth-and-access.md
│   ├── realtime-events.md
│   ├── runtime-api.md
│   └── workflow-definition-api.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── main.py
├── graph/
├── nodes/
├── routes/
├── services/
├── models/
├── db/
└── tests/

frontend/
├── src/app/
├── src/components/
├── src/lib/
├── src/contexts/
└── public/

specs/
└── 002-content-gen-mvp1/
```

**Structure Decision**: 保持现有前后端分离单体结构。后端承载认证、工作流执行、持久化与实时事件；前端承载登录、控制台、编辑器、任务详情和 Gate 交互；本次计划产物仅落在当前 feature 目录，不扩散到无关文档域。

## Complexity Tracking

当前不存在需要额外豁免的宪章违例。本计划选择的方案都以现有架构增量扩展为前提。
