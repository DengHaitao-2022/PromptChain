# PromptChain Agent 工作指引

## 1. 项目定位
PromptChain 是一个以 `Prompt Chain + LangGraph` 为核心的 AI 内容生成系统，目标是把“用户需求 -> 可发布内容”拆解为可追踪、可审批、可重跑的工作流。

当前仓库是一个前后端分离单体：
- 后端：FastAPI + LangGraph + SQLAlchemy
- 前端：Next.js App Router + React + TypeScript
- 基础设施：PostgreSQL + Redis（docker-compose）

---

## 2. 一眼看懂架构

### 2.1 后端主链路（内容生成）
当前内容生成图已经拆分为以下 canonical 模块：

- `backend/graph/state.py`：`GraphState`
- `backend/graph/conditions.py`：条件路由函数
- `backend/graph/builder.py`：图构建与 `finalize_output`
- `backend/graph/executor.py`：`ContentGenerationWorkflow` 与 `get_workflow()`

兼容入口 `backend/graph/content_generation_graph.py` 仍然存在，但只负责 re-export，不再是主修改落点。

主链路仍为：

`parse_intent -> (clarify?) -> generate_outline -> (HITL审批) -> generate_content -> self_refine -> check_facts -> (高风险HITL确认) -> finalize`

关键节点文件：
- `backend/nodes/intent_parser.py`
- `backend/nodes/outline_generator.py`
- `backend/nodes/content_generator.py`
- `backend/nodes/self_refiner.py`
- `backend/nodes/fact_checker.py`

### 2.2 后端 API 入口
应用入口：`backend/app.py`（应用工厂 + 路由注册）
统一配置：`backend/core/config.py`

已注册路由组：
- 认证：`/api/auth/*`（`routes/auth_routes.py`）
- 工作空间：`/api/workspaces*`（`routes/workspace_routes.py`）
- 管理后台：`/api/admin/*`（`routes/admin_routes.py`）
- 工作流定义：`/api/workflows*`（`routes/workflow_definition_routes.py`）
- 工作流版本：`/api/workflows/*/versions*`（`routes/workflow_version_routes.py`）
- 实时推送：`/ws/*`（`routes/websocket_routes.py`）

内容工作流接口当前已迁移到独立路由模块：
- `backend/routes/workflow_routes.py`
  - `POST /api/workflow/start`
  - `POST /api/workflow/{id}/pause`
  - `POST /api/workflow/{id}/resume`
  - `POST /api/workflow/{id}/approve-outline`
  - `POST /api/workflow/{id}/approve-fact-check`
  - `POST /api/workflow/{id}/clarify`
  - `GET /api/workflow/{id}`
  - `GET /api/workflow/{id}/rerun-options`
  - `POST /api/workflow/{id}/rerun`
  - `GET /api/workflow/{id}/rerun-history`
- `backend/routes/trace_routes.py`
  - `GET /api/trace/{id}`
  - `GET /api/trace/node/{node_run_id}`
  - `GET /api/artifact/{artifact_id}`
  - `GET /api/artifact/{artifact_id}/history`
- `backend/routes/workflow_helpers.py`
  - 共享请求/响应模型
  - 状态规范化
  - 运行态访问控制与 trace 补偿

`backend/main.py` 当前仅保留 `uvicorn main:app` 兼容入口。

### 2.3 前端主链路
- 首页启动工作流：`frontend/src/app/page.tsx`
- 工作流详情页（轮询状态 + 审批交互）：`frontend/src/app/workflow/[id]/page.tsx`
- 认证闭环页面：`frontend/src/app/register/page.tsx`、`frontend/src/app/login/page.tsx`、`frontend/src/app/verify-email/page.tsx`、`frontend/src/app/forgot-password/page.tsx`、`frontend/src/app/reset-password/page.tsx`
- 控制台布局与认证状态：`frontend/src/app/console/layout.tsx` + `frontend/src/contexts/AuthContext.tsx`
- 可视化编辑器：`frontend/src/components/WorkflowEditor/*`（React Flow）

API 客户端集中在：
- `frontend/src/lib/api.ts`（内容工作流/trace/artifact）
- `frontend/src/lib/auth.ts`（认证与 RBAC）

---

## 3. 数据与服务分层

### 3.1 产物追踪模型（内容链路）
- `Artifact`：版本化产物，Write-Once，不覆盖
- `NodeRun`：节点执行记录（LLM 调用、耗时、人为决策）
- `WorkflowRun`：工作流顶层运行记录

定义文件：`backend/models/artifact.py`

### 3.2 两套存储实现（非常关键）
- 内存回退实现：`backend/services/artifact_store.py` 中的 `ArtifactStore`
- PostgreSQL 主实现：`backend/db/postgres_store.py`

当前内容工作流链路默认走 **PostgreSQL-backed runtime store**。只有显式设置 `RUNTIME_STORE_BACKEND=memory` 时才回退到内存实现。

这意味着：
- `dev@699bf53` 的默认基线已经具备运行态持久化
- 内存 store 现在只是开发回退，不再是主线事实
- `backend/orm/*` 已进入当前仓库历史，可作为 ORM 目录事实源；本地未跟踪内容仍不应反向覆盖仓库现实

---

## 4. 鉴权与权限

### 4.1 认证
- HttpOnly Cookie：`access_token` + `refresh_token`
- Access Token 默认 15 分钟，Refresh Token 7 天
- 注册后需邮箱验证激活账号
- `register -> verify-email -> login` 与 `forgot-password -> reset-password -> login` 的页面闭环已在 `dev@699bf53`

关键文件：
- `backend/routes/auth_routes.py`
- `backend/services/auth_service.py`
- `backend/services/email_service.py`
- `frontend/src/app/register/page.tsx`
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/verify-email/page.tsx`
- `frontend/src/app/forgot-password/page.tsx`
- `frontend/src/app/reset-password/page.tsx`

### 4.2 RBAC
角色：`viewer / editor / admin / owner`

权限映射在：
- 后端：`backend/services/permission_service.py`
- 前端：`frontend/src/lib/auth.ts`（镜像一份权限表）

---

## 5. 环境与启动

### 5.1 基础设施（仓库根目录）
```bash
docker compose up -d postgres redis
```

### 5.2 后端
```bash
cd backend
uv sync
uv run uvicorn app:app --reload --port 8000
```

环境样例：`backend/.env.example`
核心变量：
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
- `DEFAULT_LLM_PROVIDER`
- `DEFAULT_MODEL_NAME`
- `DATABASE_URL`

### 5.3 前端
```bash
cd frontend
npm install
npm run dev
```

本地变量：`frontend/.env.local`
- `NEXT_PUBLIC_API_URL=http://localhost:8000`

### 5.4 Spec Kit 与 Superpowers 使用约定

#### Spec Kit（已全局安装）

- 当前机器上 `specify` 已全局可用，可直接检查：

```bash
specify check
```

- 若需要在现有仓库中重新补齐/刷新 speckit 模板，优先使用：

```bash
specify init --here --ai codex
```

- 若当前目录非空且明确需要强制合并模板，再使用：

```bash
specify init --here --ai codex --force
```

- 在 Codex 交互环境中，speckit 命令应优先使用 **slash prompt** 形式，而不是裸 `/speckit.*`：
  - `/prompts:speckit.constitution`
  - `/prompts:speckit.specify`
  - `/prompts:speckit.clarify`
  - `/prompts:speckit.plan`
  - `/prompts:speckit.tasks`
  - `/prompts:speckit.analyze`
  - `/prompts:speckit.checklist`
  - `/prompts:speckit.implement`

- Codex 中不要假设 `/speckit.specify` 这种裸命令可用；本仓库应统一使用 `/prompts:speckit.*`。
- 若要基于 Spec-Driven Development 开新特性，推荐顺序是：
  1. `/prompts:speckit.constitution`
  2. `/prompts:speckit.specify`
  3. `/prompts:speckit.clarify`
  4. `/prompts:speckit.plan`
  5. `/prompts:speckit.tasks`
  6. `/prompts:speckit.analyze`
  7. `/prompts:speckit.implement`

#### Superpowers

- 当前仓库默认启用 superpowers 工作流；进入任何新任务时，先按 `using-superpowers` 选择和加载合适 skill。
- process skill 优先于 implementation skill：
  - 设计/新功能前先 `brainstorming`
  - 多步骤落地前先 `writing-plans`
  - 按计划执行时用 `subagent-driven-development` 或 `executing-plans`
  - 收尾前用 `verification-before-completion`
  - 评审前后分别用 `requesting-code-review` / `receiving-code-review`
- 若任务是多 agent 协作、队列规划、分支/依赖编排，优先结合：
  - `using-superpowers`
  - `task-coordination-strategies`
- 若任务是 bug / 回归 /异常行为定位，优先结合：
  - `using-superpowers`
  - `systematic-debugging`
  - `verification-before-completion`
- Superpowers 的默认理念在本仓库内继续有效：
  - 先澄清 what/why，再做 how
  - evidence before claims
  - KISS / YAGNI / SOLID 优先
  - 能通过 worktree 隔离的实现，不在主工作区直接展开

---

## 6. 当前实现状态评估（以 `dev@699bf53` 为准）

1. 运行态主链路已在主线
- `WorkflowResponse`、pause/resume、clarify、outline approval、fact-check approval、rerun、rerun-history 都已在 `backend/routes/workflow_routes.py` 落地。
- 运行态访问控制和 trace 归属校验已在 `backend/routes/workflow_helpers.py`、`backend/routes/trace_routes.py` 收口。

2. auth-flow 已在主线
- `register -> verify-email -> login` 与 `forgot-password -> reset-password -> login` 页面链路已并入 `dev`。
- `GET /api/me` 继续作为前端初始化身份、当前工作空间与角色菜单的权威入口。

3. 内容生成首页与详情页闭环已在主线
- 首页 `frontend/src/app/page.tsx` 已支持已发布工作流与版本选择，并可直接启动任务。
- 首页已通过 `frontend/src/lib/api.ts` 的 `workflowApi` 读取工作流、版本、模型供应商并启动任务，不再把首页直接 `fetch` 视为主线残口。
- 详情页 `frontend/src/app/workflow/[id]/page.tsx` 已接通 Gate、pause/resume、trace、意图卡、提纲、终稿、事实核查审批、节点重跑、流式内容跟随与 DOCX 导出。

4. 工作流编辑/发布闭环已在主线
- `backend/routes/workflow_definition_routes.py`、`backend/routes/workflow_version_routes.py` 与 `frontend/src/app/console/workflows/*` 已支持 CRUD、validate、publish、compare、restore 和已发布状态展示。

5. RBAC 与成员管理已在主线
- `viewer / editor / admin / owner` 权限矩阵、控制台布局守卫、成员管理页、工作空间级运行态归属保护均已并入 `dev`。

6. 运行记录与回放入口已进入主线
- `frontend/src/app/console/runs/page.tsx` 已通过 `workflowApi.getRuns()` 读取真实运行记录，并提供详情跳转入口。
- 详情页已提供 trace、artifact history、rerun options、rerun history 与 DOCX 导出入口。

7. 当前剩余主线以验收和平台化收口为主
- `T037`：`console/runs`、trace、artifact history、rerun 与 DOCX 导出仍需要在当前 `dev@699bf53` 上重新执行 live smoke。
- `T017/T024/T031/T042`：US1/US2/US3/US5 还缺可复用的最终验收归档；其中 `T042` 是 auth/access 验收，不代表 auth-flow 尚未实现。
- `005-unified-error-system` 的后端统一错误体系与 `frontend/src/lib/api.ts` 错误归一化已在 PR #5，CodeQL 通过但当前 merge state 不是 clean，尚未合入 `dev`；不得写成主线已完成。
- 生产 CI/CD 与部署基线已在 PR #4，当前 PR 检查已通过但尚未合入 `dev`，合入前仍只可视为候选分支。

---

## 7. 代码风格与协作约束

### 7.1 后端
- Python 3.14+
- Ruff 统一风格（`backend/ruff.toml`）
- 建议提交前执行：
  - `ruff check .`
  - `ruff format .`

### 7.2 前端
- TypeScript 严格模式（`strict: true`）
- 页面层偏 `app/*`，复杂逻辑放 hooks/lib/components
- API 访问默认 `credentials: include`（依赖 Cookie）
- 页面元素的用户可见文本（如标题、按钮、导航、表单标签、占位提示、空状态、错误提示）默认尽量使用中文；仅在专有名词、协议字段、代码标识或必须保留英文的场景下使用英文。
- 前端全局主题架构统一采用 `Design Token` 分层：`primitive -> semantic -> legacy alias`。`CSS Variables` 集中落在 `frontend/src/app/globals.css`，运行时主题状态统一由 `frontend/src/lib/theme.ts` 与 `frontend/src/contexts/ThemeContext.tsx` 管理，根布局通过 `data-theme` / `data-theme-preference` 与首屏初始化脚本完成主题切换、系统偏好兜底和 `localStorage` 持久化。新增页面或组件应优先消费语义 token，禁止继续散落硬编码颜色值或自建平行主题状态。
- 凡涉及 `frontend/` 下任何代码文件的新增、修改、重构、样式调整、交互实现、动画实现、页面实现、组件实现、hooks/lib 客户端实现，默认工作流改为：Codex 产出可直接粘贴的任务提示词、文件边界、验收标准和 CR gate，由用户在 IDE 的智能助手中实际执行编码；这条规则同样适用于 `frontend/src/lib/api.ts`、`frontend/src/lib/auth.ts` 等前端契约与客户端代码。
- 若用户在 IDE 智能助手中执行前端任务，Codex 不再强制要求 Gemini CLI 或固定模型顺序；Gemini CLI 仅作为可选实现渠道，不再是默认执行路径。
- Codex 在前端任务中的职责仅限于统筹分工、定义接口约束、准备任务说明、检查 diff、做 CR、执行验收和控制合并 gate；除非用户明确授权，否则 Codex 不直接编写前端业务代码，也不直接代替用户调用 IDE 智能助手。
- 凡涉及前端代码落地的开发任务，必须使用 `git worktree` 隔离工作区；优先进入对应已有的 `code/feat/*` 分支 worktree，如不存在则先新建 `code/feat/*` 分支与 worktree 后再开发。
- 每个前端任务在申请评审前，必须在共享日志中记录对应 worktree、分支、执行者（例如 IDE 智能助手）和执行说明；没有这条记录，不得进入 `spec-review`、`code-review` 或合并流程。

### 7.3 当前仓库偏好（来自项目记忆）
- 更偏向产出总结文档
- 不自动生成测试脚本
- 不默认自动运行/编译

### 7.4 当前协作事实源
- 主线事实固定以当前 `dev` 分支 head 为准；本轮文档同步基线为 `699bf53`。
- 多 agent 协作只认以下 canonical 文件：
  - `specs/002-content-gen-mvp1/subagent-events.jsonl`
  - `specs/002-content-gen-mvp1/subagent-locks.json`
  - `specs/002-content-gen-mvp1/gemini-executions.jsonl`
  - `specs/002-content-gen-mvp1/subagent-handoffs.jsonl`
- `specs/002-content-gen-mvp1/subagent-tasks.md` 当前只保留“主线现状快照 + 下一轮派工入口”，不再复用旧 owner 表直接分派任务。
- 根工作区中的 `.cunzhi-memory/*` 等本地运行态/未跟踪内容不是主线事实源；已跟踪的 `backend/orm/*` 属于当前主线结构。

---

## 8. Agent 修改建议（执行顺序）

当你要继续开发时，建议按以下顺序推进：

1. 先做 `dev@699bf53` 的 MVP1 最终 smoke
- 优先复核首页启动、Gate、pause/resume、trace/artifact history、rerun、DOCX 导出和 auth/access。

2. 再推进 PR #5 的 merge gate
- `code/feat-unified-error-system-current` 仍是 open PR；合入前继续按 PR + CI/CD gate 处理，不在本地直接写成主线事实。

3. 再处理 PR #4 的合并前 gate
- `code/feat-production-ci-deploy-foundation` 当前 PR 检查已通过，但尚未合入 `dev`；合入前不应作为生产部署基线归档。

4. 最后继续 MVP2 后续队列
- `005-unified-error-system` 合入后，再派发 legacy-alignment / frontend-consumer 的剩余错误体系收口。

---

## 9. 快速定位索引

- 应用入口：`backend/app.py`
- 统一配置：`backend/core/config.py`
- 工作流图入口：`backend/graph/executor.py`, `backend/graph/builder.py`, `backend/graph/state.py`, `backend/graph/conditions.py`
- 兼容 graph shim：`backend/graph/content_generation_graph.py`
- 节点实现：`backend/nodes/*.py`
- 路由层：`backend/routes/*.py`
  - 内容工作流 API：`routes/workflow_routes.py`
  - Trace/Artifact API：`routes/trace_routes.py`
  - 共享模型/工具：`routes/workflow_helpers.py`
- 服务层：`backend/services/*.py`
- DB/ORM：`backend/db/postgres_store.py`, `backend/orm/*`, `backend/models/*_orm.py`
- 前端页面：`frontend/src/app/**/*`
- 前端组件：`frontend/src/components/**/*`
- 前端 API：`frontend/src/lib/api.ts`, `frontend/src/lib/auth.ts`


---

## 10. 可能使用到的 Skills 清单（按本项目技术栈）

### 10.1 流程与协作
- `using-superpowers`：会话起始时用于识别并调用合适 skill（规范流程入口）。
  - 文件：`/Users/hi/.agents/skills/using-superpowers/SKILL.md`
- `collaborative-code`：用于 PromptChain 仓库内的协同开发编排，覆盖 intake、spec、planning、tasking、implementation、review、PR/CI-CD 与 handoff，并固化 DAG 派工、worktree/scope 管控、review gate 和 PR gate。
  - 文件：`/Users/hi/Developer/03-personal/PromptChain/skills/collaborative-code/SKILL.md`
- `brainstorming`：在功能设计/行为变更前先完成需求澄清与方案比较。
  - 文件：`/Users/hi/.agents/skills/brainstorming/SKILL.md`
- `writing-plans`：有明确需求后产出可执行的多步骤实施计划。
  - 文件：`/Users/hi/.agents/skills/writing-plans/SKILL.md`
- `executing-plans`：按既有实施计划推进落地与检查点执行。
  - 文件：`/Users/hi/.agents/skills/executing-plans/SKILL.md`
- `workflow-patterns`：按 Conductor/TDD 流程组织任务与阶段验证。
  - 文件：`/Users/hi/.agents/skills/workflow-patterns/SKILL.md`
- `verification-before-completion`：在宣称完成前执行验证，避免“未证实完成”。
  - 文件：`/Users/hi/.agents/skills/verification-before-completion/SKILL.md`
- `requesting-code-review`：功能完成后发起结构化代码审查。
  - 文件：`/Users/hi/.agents/skills/requesting-code-review/SKILL.md`
- `receiving-code-review`：处理审查意见时做技术校验与风险判断。
  - 文件：`/Users/hi/.agents/skills/receiving-code-review/SKILL.md`

### 10.2 后端（FastAPI / Python）
- `fastapi-templates`：构建/扩展 FastAPI 服务结构、依赖注入与错误处理。
  - 文件：`/Users/hi/.agents/skills/fastapi-templates/SKILL.md`
- `async-python-patterns`：异步 I/O、并发、任务编排相关实现。
  - 文件：`/Users/hi/.agents/skills/async-python-patterns/SKILL.md`
- `python-project-structure`：模块边界、目录组织与公共 API 设计。
  - 文件：`/Users/hi/.agents/skills/python-project-structure/SKILL.md`
- `python-configuration`：环境变量与配置分层治理（本地/测试/生产）。
  - 文件：`/Users/hi/.agents/skills/python-configuration/SKILL.md`
- `python-error-handling`：输入校验、异常分层与部分失败处理。
  - 文件：`/Users/hi/.agents/skills/python-error-handling/SKILL.md`
- `python-resilience`：重试、超时、退避策略等可靠性增强。
  - 文件：`/Users/hi/.agents/skills/python-resilience/SKILL.md`
- `python-observability`：结构化日志、指标、链路追踪接入。
  - 文件：`/Users/hi/.agents/skills/python-observability/SKILL.md`
- `python-type-safety`：类型标注、协议、泛型与静态检查。
  - 文件：`/Users/hi/.agents/skills/python-type-safety/SKILL.md`
- `python-testing-patterns`：pytest 测试分层、fixture、mock 策略。
  - 文件：`/Users/hi/.agents/skills/python-testing-patterns/SKILL.md`

### 10.3 LLM / 工作流（Prompt Chain + LangGraph）
- `langchain-architecture`：LLM 应用架构、Agent/工具/记忆整合。
  - 文件：`/Users/hi/.agents/skills/langchain-architecture/SKILL.md`
- `rag-implementation`：RAG 管线建设（检索、重排、生成闭环）。
  - 文件：`/Users/hi/.agents/skills/rag-implementation/SKILL.md`
- `prompt-engineering-patterns`：提示词模板优化、稳定性与可控性提升。
  - 文件：`/Users/hi/.agents/skills/prompt-engineering-patterns/SKILL.md`
- `embedding-strategies`：嵌入模型与分块策略选型。
  - 文件：`/Users/hi/.agents/skills/embedding-strategies/SKILL.md`
- `hybrid-search-implementation`：向量+关键词混合检索提升召回与准确。
  - 文件：`/Users/hi/.agents/skills/hybrid-search-implementation/SKILL.md`

### 10.4 前端（Next.js / React）
- `nextjs-app-router-patterns`：Next.js App Router 路由与数据获取实践。
  - 文件：`/Users/hi/.agents/skills/nextjs-app-router-patterns/SKILL.md`
- `react-state-management`：全局状态与服务端状态管理选型与落地。
  - 文件：`/Users/hi/.agents/skills/react-state-management/SKILL.md`
- `frontend-design`：页面/组件视觉与交互质量提升。
  - 文件：`/Users/hi/.agents/skills/frontend-design/SKILL.md`
- `web-component-design`：可复用组件 API 设计与组合模式。
  - 文件：`/Users/hi/.agents/skills/web-component-design/SKILL.md`
- `responsive-design`：响应式布局与跨端适配。
  - 文件：`/Users/hi/.agents/skills/responsive-design/SKILL.md`
- `accessibility-compliance`：可访问性（WCAG/ARIA/键盘导航）实现。
  - 文件：`/Users/hi/.agents/skills/accessibility-compliance/SKILL.md`
- `wcag-audit-patterns`：可访问性审计与缺陷整改。
  - 文件：`/Users/hi/.agents/skills/wcag-audit-patterns/SKILL.md`
- `webapp-testing`：本地 Web 应用交互验证与回归检查。
  - 文件：`/Users/hi/.agents/skills/webapp-testing/SKILL.md`

### 10.5 API / 安全 / 数据
- `api-design-principles`：REST/GraphQL API 契约与演进策略。
  - 文件：`/Users/hi/.agents/skills/api-design-principles/SKILL.md`
- `auth-implementation-patterns`：认证授权（JWT/OAuth2/RBAC）实现。
  - 文件：`/Users/hi/.agents/skills/auth-implementation-patterns/SKILL.md`
- `openapi-spec-generation`：OpenAPI 规范生成与契约校验。
  - 文件：`/Users/hi/.agents/skills/openapi-spec-generation/SKILL.md`
- `secrets-management`：密钥/凭据管理与轮换规范。
  - 文件：`/Users/hi/.agents/skills/secrets-management/SKILL.md`
- `postgresql-table-design`：PostgreSQL 表结构、索引与约束设计。
  - 文件：`/Users/hi/.agents/skills/postgresql-table-design/SKILL.md`
- `database-migration`：数据库迁移与零停机变更策略。
  - 文件：`/Users/hi/.agents/skills/database-migration/SKILL.md`
- `sql-optimization-patterns`：慢查询分析与 SQL 性能优化。
  - 文件：`/Users/hi/.agents/skills/sql-optimization-patterns/SKILL.md`

### 10.6 测试、发布与可观测
- `test-driven-development`：功能/修复按 TDD 方式推进。
  - 文件：`/Users/hi/.agents/skills/test-driven-development/SKILL.md`
- `systematic-debugging`：问题定位时使用系统化调试流程。
  - 文件：`/Users/hi/.agents/skills/systematic-debugging/SKILL.md`
- `debugging-strategies`：复杂缺陷的证据收集与根因分析。
  - 文件：`/Users/hi/.agents/skills/debugging-strategies/SKILL.md`
- `e2e-testing-patterns`：端到端测试体系建设（Playwright/Cypress）。
  - 文件：`/Users/hi/.agents/skills/e2e-testing-patterns/SKILL.md`
- `deployment-pipeline-design`：CI/CD 分阶段发布与质量门禁。
  - 文件：`/Users/hi/.agents/skills/deployment-pipeline-design/SKILL.md`
- `github-actions-templates`：GitHub Actions 自动化流水线模板。
  - 文件：`/Users/hi/.agents/skills/github-actions-templates/SKILL.md`
- `changelog-automation`：版本发布日志自动生成。
  - 文件：`/Users/hi/.agents/skills/changelog-automation/SKILL.md`
- `distributed-tracing`：分布式链路追踪与跨服务性能定位。
  - 文件：`/Users/hi/.agents/skills/distributed-tracing/SKILL.md`
- `prometheus-configuration`：指标采集与告警规则配置。
  - 文件：`/Users/hi/.agents/skills/prometheus-configuration/SKILL.md`
- `grafana-dashboards`：可观测面板与运营指标可视化。
  - 文件：`/Users/hi/.agents/skills/grafana-dashboards/SKILL.md`
- `slo-implementation`：SLO/SLI 与错误预算治理。
  - 文件：`/Users/hi/.agents/skills/slo-implementation/SKILL.md`

### 10.7 文档与交付
- `doc-coauthoring`：方案文档、技术设计与提案的协作撰写。
  - 文件：`/Users/hi/.agents/skills/doc-coauthoring/SKILL.md`
- `readme-generator`：README 结构化完善与示例补全。
  - 文件：`/Users/hi/.codex/skills/readme-generator/SKILL.md`

---

## 11. AURA-X-KYS 多智能体协作协议（适配当前 Codex / MCP 工作流）

本节用于指导多个智能体在本项目中的长期协作。它保留你提供的 AURA-X-KYS 思路，但对当前环境做了适配：既强调 `寸止` 与 `记忆`，也避免和现有工具链、上层系统约束以及实际开发节奏发生冲突。

### 11.1 协议目标

- 让多个智能体在长期协作时保持一致的工程判断。
- 将稳定规则、偏好、模式和项目上下文沉淀到可复用记忆中。
- 在需求不清、方案分歧、风险较高时，通过结构化交互而不是主观猜测推进。
- 所有代码与方案评估，默认以 `KISS / YAGNI / SOLID` 为最高设计标准。

### 11.2 不可覆盖原则

1. **核心设计哲学优先**：所有实现、重构、抽象和方案比较，默认优先满足 `KISS`、`YAGNI`、`SOLID`。若某方案更复杂、抽象更多、引入暂不需要的能力，应默认视为次优。
2. **仓库事实优先于记忆**：当 `AGENTS.md`、当前代码、测试、配置与历史记忆冲突时，以当前仓库事实和最新用户指令为准；记忆应在确认后被修正，而不是反向覆盖代码现实。
3. **关键决策必须显式化**：遇到需求不明确、存在多个可行方案、计划需要变更、变更风险较高时，必须显式请求用户决策，禁止在关键节点自作主张。
4. **知识权威性优先**：本地代码上下文优先通过语义搜索和代码检索确认；第三方库、框架、API、标准等不稳定知识优先通过官方文档或 `context7` 获取。
5. **默认静默执行，但不牺牲闭环**：除非用户明确要求、任务完成必须验证，或上层系统要求，不主动扩展为额外文档、测试、编译、运行；但若缺少验证会导致结果不可信，则应主动补最小必要验证。
6. **中文优先**：页面元素用户可见文本、必要注释、日志说明、交互文案默认尽量使用中文；仅在专有名词、协议字段、代码标识、第三方 API 约定或必须保留英文的场景使用英文。
7. **前端执行权归用户的 IDE 智能助手**：凡属 `frontend/` 目录下的代码实现任务，默认由用户在 IDE 中运行智能助手完成实际编码；Codex 只负责输出可粘贴任务提示词、做统筹、审查、验收和合并 gate，不直接代写前端代码。

### 11.3 记忆协议（长期协作核心）

#### 11.3.1 启动阶段

- 每次进入新任务或新会话时，优先调用 `记忆` MCP：`mcp__cunzhi__ji(action=\"回忆\", project_path=\"/Users/hi/Developer/03-personal/PromptChain\")`。
- 先读取项目已有规则、偏好、模式和上下文，再开始方案判断，避免多个智能体反复踩同一类坑。
- **关键规则**：即使当前 agent 在其他 `git worktree` 中工作，也必须统一使用 canonical 项目路径 `/Users/hi/Developer/03-personal/PromptChain` 调用 `记忆` MCP；不得把 worktree 路径当作新的 `project_path`，否则长期记忆会被切裂成多个孤岛。

#### 11.3.2 记忆分类

- `rule`：稳定规则、不可轻易违背的工程约束。
- `preference`：用户或项目明确偏好，例如中文文案、风格、交互方式。
- `pattern`：已验证有效、可复用的实现模式、修复模式、集成套路。
- `context`：高价值项目背景、关键设计决策、尚未关闭的重要上下文。

#### 11.3.3 必须写入记忆的场景

- 用户明确说出“请记住：”。
- 形成新的稳定规则、偏好或协作约定。
- 完成一次具有复用价值的架构决策、疑难修复或集成方案。
- 多智能体任务交接前，需要保留高价值上下文，避免后续 agent 从零恢复。
- 发现旧记忆已过时，并且已通过当前代码或用户确认获得新结论。

#### 11.3.4 不应写入记忆的内容

- 临时调试细节、一次性命令输出、短期计划草稿。
- 未经确认的猜测、待验证假设。
- 与单次任务强绑定、对未来复用价值很低的噪声信息。

#### 11.3.5 多智能体交接最小记忆集

当任务需要跨 agent 长期协作时，交接前优先沉淀以下信息：

- 本次已确认的技术决策及其原因。
- 受影响模块、关键文件边界和未完成部分。
- 已识别风险、待验证点、已排除方案。
- 对后续 agent 真正有帮助的下一步建议。

### 11.4 寸止协作协议（结构化决策网关）

- 当前环境中，`寸止` 的首选实现为 `mcp__cunzhi__zhi`。
- 当出现以下情况时，优先使用 `寸止` 发起结构化交互，而不是直接自由提问：
  - 需求不明确。
  - 存在两个及以上合理方案。
  - 计划、策略、执行边界需要调整。
  - 改动涉及高风险模块、跨模块重构、数据迁移、权限或外部接口。
  - 多步骤任务即将结束，需要用户做最终收口确认。
- 每个候选方案都应包含：
  - 方案摘要。
  - 基于 `KISS / YAGNI / SOLID` 的优点。
  - 基于 `KISS / YAGNI / SOLID` 的缺点或成本。
  - 明确的“推荐”选项。
- 若 `寸止` 不可用，或问题极其简单、无需结构化选项，可直接用简洁中文向用户提问；但仍应保持“关键决策显式确认”的原则。

### 11.5 任务评估与执行模式

#### 11.5.1 任务复杂度分级

- `Level 1`：原子任务。单点修复、一个明确小函数、单文件小改动。
- `Level 2`：标准任务。一个完整功能或少量跨文件改动。
- `Level 3`：复杂任务。大型重构、新模块接入、性能与架构问题。
- `Level 4`：探索任务。需求开放、目标不清、需要共同定义问题。

#### 11.5.2 推荐执行模式

- `AUTONOMOUS`：高置信度、低风险、`Level 1-2` 任务可采用。先回忆记忆，再直接执行，最后集中汇报和确认。
- `INTERACTIVE`：`Level 3-4`、低置信度、需求不清、方案分歧或风险较高的任务应采用。关键节点通过 `寸止` 或显式确认推进。

#### 11.5.3 标准执行顺序

1. 先回忆项目记忆。
2. 再看 `AGENTS.md`、当前代码和相关文件。
3. 本地上下文优先通过 `mcp__cunzhi__sou`、`rg`、文件读取确认。
4. 需要外部知识时，再使用 `context7` 或权威文档。
5. 形成方案后按复杂度选择自主执行或结构化确认。

### 11.6 多智能体并行协作约定

- 优先按模块、目录、能力边界拆分任务，减少多个 agent 同时修改同一文件。
- 在进入实现前先明确文件边界：谁负责后端、谁负责前端、谁负责文档、谁负责验证。
- 若执行中发现共享文件已被其他 agent 修改，且会影响当前任务判断，应立即停下并重新对齐，不做覆盖式编辑。
- 对于跨模块任务，先统一接口契约与共享类型，再分别推进各自子任务。
- 长任务结束前，优先把高价值结论沉淀进记忆，而不是只留在会话里。
- 实时协作状态不得依赖各自 worktree 内的相对路径副本；凡属锁表、事件流、Gemini 执行记录、handoff 记录，统一写入根仓库下的 canonical 绝对路径。
- 当前 canonical 协作文件固定为：
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-events.jsonl`
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-locks.json`
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/gemini-executions.jsonl`
  - `/Users/hi/Developer/03-personal/PromptChain/specs/002-content-gen-mvp1/subagent-handoffs.jsonl`
- 关键点不在于文件名，而在于所有 agent 必须使用同一个绝对路径；禁止在各自 worktree 内用相对路径写出多个副本。
- 这些协作文件属于 coordinator 维护的运行态工件，不属于业务功能交付物；业务 agent 可以按规则追加，但不得把它们混入功能提交说明中。
- coordinator 必须把 worktree 同步检查纳入固定例行工作：至少在任务派发前、`dev` 前进后、分支申请评审前检查每个活跃 worktree 的 `base_commit`、相对 `dev` 的 ahead/behind、以及 dirty 状态，并记录到共享协作文件。
- coordinator 不默认替各分支执行 `merge`、`rebase` 或其他代码同步操作；实际同步由对应分支 owner 负责，除非用户明确授权 coordinator 代为执行。
- `.cunzhi-memory/*` 若出现在某个 worktree 中，只视为本地缓存或导出结果，不视为多 agent 共享事实源。

### 11.7 工具优先级约定

- 项目记忆：`mcp__cunzhi__ji`
- 结构化用户交互：`mcp__cunzhi__zhi`
- 项目语义搜索：`mcp__cunzhi__sou`
- 官方/最新文档：`mcp__context7__resolve-library-id` + `mcp__context7__query-docs`
- 前端代码实现：默认由用户在 IDE 智能助手中执行，Codex 负责给出可粘贴提示词、文件边界和验收标准
- 前端隔离开发：`git worktree`
- 共享实时协作文件：根仓库 `specs/002-content-gen-mvp1/` 下的 canonical 绝对路径文件
- 本地文件编辑：优先使用补丁式修改，保持变更小而清晰

### 11.8 代码与文案落地规则

- 不为“未来可能需要”的需求提前抽象；先做当前闭环，再看复用。
- 注释应少而准；只有在意图不明显、跨模块约束复杂或后续维护成本高时，才添加简洁中文注释。
- 若方案依赖外部官方文档或 `context7` 的关键信息，应在回复、设计说明或提交说明中注明来源；不要在业务代码里机械堆砌 `Source` 注释。
- 页面元素文本、提示语、空状态、错误文案、确认文案默认优先中文。
- 遇到不确定但影响实现质量的前提条件，应优先澄清，而不是自行脑补。

### 11.9 长期协作的记忆写入模板

推荐在需要写入长期记忆时，尽量压缩成以下格式：

- `规则`：什么必须做 / 不能做。
- `原因`：为什么这是稳定规则。
- `范围`：影响哪些模块、哪些任务类型。
- `例外`：什么情况下可以不遵守。

示例：

- `rule`：前端用户可见文本默认使用中文。
- `preference`：默认不主动运行编译和测试，除非用户要求或验证必须。
- `pattern`：内容工作流状态字段应以 `frontend/src/lib/api.ts` 契约为准进行对齐。
- `context`：内容主链路当前默认使用 PostgreSQL-backed runtime store；内存 Artifact Store 只作为 `RUNTIME_STORE_BACKEND=memory` 的开发回退。

## Active Technologies
- Python 3.14+（backend）, TypeScript 5 + React 19 + Next.js 16（frontend） + FastAPI, LangGraph, SQLAlchemy, Pydantic 2, Next.js App Router, React, `@xyflow/react`, Radix UI (002-content-gen-mvp1)
- 现状为 PostgreSQL 统一承载认证/工作空间/工作流定义与内容运行态 `WorkflowRun` / `NodeRun` / `Artifact`；内存存储仅作开发期回退 (002-content-gen-mvp1)
- Python 3.14+ + FastAPI, LangGraph, SQLAlchemy, Pydantic 2, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-ollama` (003-provider-architecture)
- N/A（本特性只改配置与 provider 解析，不涉及数据库或持久化模型） (003-provider-architecture)
- Python 3.14+ + FastAPI, LangGraph, SQLAlchemy, Pydantic 2, `langchain`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-ollama`, `python-dotenv` (003-provider-architecture)
- N/A（本特性不新增持久化模型；仅涉及运行时配置与 provider 构造） (003-provider-architecture)

## Recent Changes
- 002-content-gen-mvp1: Added Python 3.14+（backend）, TypeScript 5 + React 19 + Next.js 16（frontend） + FastAPI, LangGraph, SQLAlchemy, Pydantic 2, Next.js App Router, React, `@xyflow/react`, Radix UI
