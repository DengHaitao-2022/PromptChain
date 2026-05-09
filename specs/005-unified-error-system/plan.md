# Implementation Plan: PromptChain 统一错误体系

**Branch**: `005-unified-error-system` | **Date**: `2026-04-12` | **Spec**: [`spec.md`](./spec.md)
**Input**: Feature specification from `/specs/005-unified-error-system/spec.md`

## Summary

本计划聚焦一次 MVP2 平台基础能力升级：为 PromptChain 建立统一错误模型、错误码注册表、异常分层和全局异常映射，使 auth、workflow runtime、trace、workspace、admin 等核心 API 域能够返回一致、可判定、可追踪、可脱敏的错误响应。实现路径保持在现有 `FastAPI + LangGraph + SQLAlchemy + Next.js` 架构内，通过后端统一错误契约、全局 handler、请求追踪标识、核心路由迁移和前端错误消费约定完成闭环，不扩展成全量架构重写或大型运维平台。

## Technical Context

**Language/Version**: Python 3.14+（后端），TypeScript 5+（前端错误消费契约）
**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy, LangGraph, Next.js App Router, React, TypeScript
**Storage**: PostgreSQL 为现有运行态与业务数据权威存储；本特性第一阶段不要求新增数据库表
**Testing**: 后端 `pytest` 契约/单元测试 + 前端类型级与最小消费回归；手动 quickstart 覆盖典型错误场景
**Target Platform**: 浏览器 + 本地/服务器运行的 FastAPI 服务
**Project Type**: 棕地全栈 Web 应用中的后端契约治理特性
**Performance Goals**: 错误治理不能明显增加正常请求链路开销；统一错误映射不应把普通失败场景变成显著重逻辑路径
**Constraints**: 必须优先覆盖核心 API 域；不得直接把底层基础设施异常透传给前端；不得要求一次性迁移所有历史接口；前端不得继续依赖自由文本 `detail` 作为长期判定依据；保持 KISS / YAGNI / SOLID，避免泛化成“大一统平台重构”
**Scale/Scope**: 主要覆盖 `backend/app.py`、`backend/models/result.py` 或其替代统一 envelope、后端核心异常与 handler、新的错误码注册表、核心路由域的错误映射，以及前端 `frontend/src/lib/api.ts` 级别的错误消费契约；不要求第一阶段覆盖全部内部工具和所有历史边角接口

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Gate

| Principle | Status | Evidence / Planned Control |
|-----------|--------|----------------------------|
| Contract-First Workflow Surfaces | PASS | 本特性直接解决运行态和管理域 API 契约不统一问题，先定义统一错误外观，再推进实现 |
| Traceable, Versioned Content Execution | PASS | 本特性不改变 `WorkflowRun / NodeRun / Artifact` 结构，只增强请求级错误追踪与错误响应一致性 |
| Human Gates Over Unsafe Assumptions | PASS | 统一错误体系不会改变 Gate 业务语义，只规范其错误表达 |
| Single Semantic Source of Truth | PASS | 错误码注册表、异常分层和全局 handler 将成为统一语义源，减少路由各自为战 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | 采用分阶段迁移，先统一基础契约与核心域，不一次性重写所有模块 |

### Post-Design Re-check

| Principle | Status | Evidence / Designed Output |
|-----------|--------|----------------------------|
| Contract-First Workflow Surfaces | PASS | `contracts/error-envelope.md` 和 `contracts/error-code-registry.md` 已固定统一错误外观与注册规则 |
| Traceable, Versioned Content Execution | PASS | `data-model.md` 明确本特性只增加请求/错误追踪语义，不侵入运行态持久化模型 |
| Human Gates Over Unsafe Assumptions | PASS | 设计输出不改变任何 Gate 业务判断，只统一其失败响应 |
| Single Semantic Source of Truth | PASS | `research.md`、`data-model.md` 和 contracts 已统一错误域、错误分层和调用方处理语义 |
| Brownfield Discipline and Small, Reviewable Changes | PASS | `quickstart.md` 与最小实现路径都明确分阶段迁移，避免“大爆改” |

## Project Structure

### Documentation (this feature)

```text
specs/005-unified-error-system/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── error-envelope.md
│   └── error-code-registry.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── app.py
├── core/
│   ├── config.py
│   └── [new error modules]
├── models/
│   └── result.py
├── routes/
│   ├── auth_routes.py
│   ├── workflow_routes.py
│   ├── trace_routes.py
│   ├── workspace_routes.py
│   ├── admin_routes.py
│   ├── workflow_definition_routes.py
│   └── workflow_version_routes.py
├── services/
│   ├── auth_service.py
│   └── permission_service.py
└── tests/

frontend/
└── src/
    └── lib/
        └── api.ts
```

**Structure Decision**: 统一错误体系的核心逻辑收敛在后端 `app.py + core/* + models/result.py` 一侧，前端只消费稳定契约，不把错误判断逻辑散落在业务页面中。第一阶段优先覆盖核心 API 域，逐步回收局部 `Result`、`HTTPException` 与 `detail` 风格。

## Minimal Implementation Path

### Slice 1: 统一错误外观与注册表

1. 固定统一失败响应契约：稳定错误标识、可读说明、请求追踪标识、可选安全详情。
2. 建立错误码注册表，按域拆分 `AUTH / WORKSPACE / WORKFLOW / TRACE / ADMIN / INFRA / COMMON`。
3. 定义调用方处理方向：修正输入、重新登录、权限不足、资源不存在、稍后重试、联系管理员。

### Slice 2: 异常分层与全局异常映射

1. 在后端建立最小异常分层：
   - `DomainError`
   - `ApplicationError`
   - `InfrastructureError`
2. 在 `backend/app.py` 统一挂接：
   - 全局异常处理器
   - 请求级 `request_id`
   - 统一错误响应转换
3. 基础设施异常对外脱敏，对内保留原始 cause。

### Slice 3: 核心 API 域迁移

1. 优先迁移：
   - `auth_routes.py`
   - `workflow_routes.py`
   - `trace_routes.py`
   - `workspace_routes.py`
   - `admin_routes.py`
2. 再收敛：
   - `workflow_definition_routes.py`
   - `workflow_version_routes.py`
   - `models/result.py`
3. 明确哪些场景属于：
   - 业务错误
   - 权限错误
   - 资源不存在
   - 状态冲突
   - 基础设施故障

### Slice 4: 前后端错误消费统一

1. 前端统一按稳定错误标识处理，而不是继续依赖 `detail` 文案。
2. 将当前 `frontend/src/lib/api.ts` 升级为前端错误消费的单一事实源。
3. 页面层只消费已归一化的错误语义，不重复散落映射逻辑。

### Slice 5: 验证与迁移收口

1. 建立最小后端契约测试，覆盖 auth / permission / not-found / infra error。
2. 以 `quickstart.md` 的 Smoke A-E 验证：
   - 未登录
   - 权限不足
   - 资源不存在
   - 基础设施异常脱敏
   - 前端错误分支
3. 把旧接口未迁移项明确记录为迁移缺口，而不是假装全量完成。

## Validation Strategy

### Automated Test Points

- 后端契约测试覆盖：
  - 统一错误结构
  - 稳定错误标识
  - `request_id`
  - 不同异常层级到 HTTP 语义的映射
  - 基础设施异常脱敏
- 前端最小验证覆盖：
  - `api.ts` 能基于稳定错误标识归类错误
  - 页面不再依赖中文 `detail` 直接做长期逻辑判断

### Manual Quickstart Points

- 按 `quickstart.md` 跑 Smoke A-E
- 验证 auth、权限、资源不存在和 infra 故障都已经被统一契约吸收
- 验证至少一个前端场景能按稳定错误标识显示/处理错误

### Explicit Non-Goals for Verification

- 不要求第一阶段覆盖全部历史接口
- 不要求在本轮引入完整告警平台或独立审计产品
- 不要求通过统一错误体系直接解决全部业务状态设计问题

## Migration Impact

### Code Impact

- 主要修改面：
  - `backend/app.py`
  - `backend/models/result.py` 或其替代统一 envelope
  - 新的后端错误码/异常/handler 模块
  - 核心路由域和少量服务层异常抛出方式
  - `frontend/src/lib/api.ts`

### Runtime / Operational Impact

- 会新增请求级追踪标识与统一错误日志关联方式
- 基础设施故障对外可见性将被收紧
- 前端错误处理将从“文案驱动”迁移到“错误标识驱动”

### Cross-Layer Impact

- 后端必须对错误语义给出单一事实源
- 前端需更新统一消费逻辑，但不应把错误映射逻辑散落回页面
- 文档层需同步更新 quickstart 和 API 契约说明

## Complexity Tracking

当前不存在需要额外豁免的宪章违例。方案采用“先统一外观、再迁移核心域、最后收尾旧接口”的最小路径，避免一次性大重构。
