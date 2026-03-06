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
工作流定义在 `backend/graph/content_generation_graph.py`：

`parse_intent -> (clarify?) -> generate_outline -> (HITL审批) -> generate_content -> self_refine -> check_facts -> (高风险HITL确认) -> finalize`

关键节点文件：
- `backend/nodes/intent_parser.py`
- `backend/nodes/outline_generator.py`
- `backend/nodes/content_generator.py`
- `backend/nodes/self_refiner.py`
- `backend/nodes/fact_checker.py`

核心状态模型：`GraphState`（同文件内 `TypedDict`）。

### 2.2 后端 API 入口
主入口：`backend/main.py`

已注册路由组：
- 认证：`/api/auth/*`（`routes/auth_routes.py`）
- 工作空间：`/api/workspaces*`（`routes/workspace_routes.py`）
- 管理后台：`/api/admin/*`（`routes/admin_routes.py`）
- 工作流定义：`/api/workflows*`（`routes/workflow_definition_routes.py`）
- 工作流版本：`/api/workflows/*/versions*`（`routes/workflow_version_routes.py`）
- 实时推送：`/ws/*`（`routes/websocket_routes.py`）

同时保留一组内容工作流接口（`main.py` 直接定义）：
- `POST /api/workflow/start`
- `POST /api/workflow/{id}/approve-outline`
- `POST /api/workflow/{id}/clarify`
- `GET /api/workflow/{id}`
- `GET /api/trace/{id}`
- `GET /api/trace/node/{node_run_id}`
- `GET /api/workflow/{id}/rerun-options`
- `POST /api/workflow/{id}/rerun`

### 2.3 前端主链路
- 首页启动工作流：`frontend/src/app/page.tsx`
- 工作流详情页（轮询状态 + 审批交互）：`frontend/src/app/workflow/[id]/page.tsx`
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
- 内存存储：`backend/services/artifact_store.py`
- PostgreSQL 存储：`backend/db/postgres_store.py`

当前内容工作流链路（graph/nodes/trace/rerun）默认走**内存存储单例**；认证、权限、后台管理、工作流定义走 PostgreSQL。

这意味着：
- 内容运行数据重启后会丢失
- Dashboard 与内容工作流运行数据可能不一致

---

## 4. 鉴权与权限

### 4.1 认证
- HttpOnly Cookie：`access_token` + `refresh_token`
- Access Token 默认 15 分钟，Refresh Token 7 天
- 注册后需邮箱验证激活账号

关键文件：
- `backend/routes/auth_routes.py`
- `backend/services/auth_service.py`
- `backend/services/email_service.py`

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
uv run uvicorn main:app --reload --port 8000
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

---

## 6. 当前实现状态评估（已识别缺口）

1. 内容工作流与前端契约存在不一致
- 前端 `workflowApi.getStatus()` 期望 `WorkflowResponse{workflow_run_id,status,state}`。
- 后端 `GET /api/workflow/{id}` 当前返回 `WorkflowRun.model_dump()`，字段结构不一致。

2. 澄清字段不一致
- 后端状态字段是 `clarification_questions`（且 priority 为 1-5 数值）。
- 前端详情页判断 `state.uncertainties`，并按 `high/medium/low` 处理。

3. 事实核查审批未打通
- 前端 `FactCheckViewer` 回调仅 `console.log`。
- 后端无对应 `approve_fact_check` HTTP 路由暴露（仅节点函数存在）。

4. Workflow Definition / Version 路由的 session 获取方式异常
- `session = await get_session()` 使用了异步生成器样式函数，写法不标准，运行时风险高。

5. 控制台多个页面仍是占位实现
- `console/workflows`、`console/runs` 仍有 mock/空列表逻辑。
- 编辑器保存按钮仍是 TODO。

6. WebSocket 推送未接入节点执行
- 有连接管理与 emit 工具函数，但主工作流执行未实际调用 emit。

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

### 7.3 当前仓库偏好（来自项目记忆）
- 更偏向产出总结文档
- 不自动生成测试脚本
- 不默认自动运行/编译

---

## 8. Agent 修改建议（执行顺序）

当你要继续开发时，建议按以下顺序推进：

1. 先统一 API 契约
- 以 `frontend/src/lib/api.ts` 为目标契约，修正 `backend/main.py` 响应结构。

2. 再打通审批闭环
- 增加事实核查审批接口并接入前端 `FactCheckViewer`。

3. 统一状态字段语义
- `clarification_questions` vs `uncertainties` 二选一并全链路一致。

4. 决定内容链路持久化策略
- 要么全量切 PostgreSQL Store；要么显式标注“仅内存开发模式”。

5. 最后完善控制台页
- 接真实列表 API，去掉 mock/TODO。

---

## 9. 快速定位索引

- 后端入口：`backend/main.py`
- 工作流图：`backend/graph/content_generation_graph.py`
- 节点实现：`backend/nodes/*.py`
- 路由层：`backend/routes/*.py`
- 服务层：`backend/services/*.py`
- DB/ORM：`backend/db/postgres_store.py`, `backend/models/*_orm.py`
- 前端页面：`frontend/src/app/**/*`
- 前端组件：`frontend/src/components/**/*`
- 前端 API：`frontend/src/lib/api.ts`, `frontend/src/lib/auth.ts`


---

## 10. 可能使用到的 Skills 清单（按本项目技术栈）

### 10.1 流程与协作
- `using-superpowers`：会话起始时用于识别并调用合适 skill（规范流程入口）。
  - 文件：`/Users/hi/.agents/skills/using-superpowers/SKILL.md`
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

