# 常用模式和最佳实践

- 前端技术栈: Next.js 15 + TypeScript + Radix UI + 原生CSS
CSS模块类名: 使用camelCase格式 (如inputContainer, mainTextarea)
组件结构: components/{ComponentName}/{ComponentName}.tsx + .module.css + index.ts
API客户端: src/lib/api.ts 集中管理所有后端接口和类型定义
- 交互式 Codex CLI/TUI 中，仓库 `.codex/prompts/*.md` 会注册为 slash command，调用格式是 `/prompts:<prompt-name>`，例如 `/prompts:speckit.specify`；不要使用裸命令 `/speckit.specify`。`codex exec` 不等价于交互式 slash command 入口，不能用来判断自定义 prompt 是否已注册或可用。验证证据：在隔离仓库中执行 `/prompts:speckit.specify 添加一个最小化测试功能` 成功创建分支 `001-minimal-test`，并生成 `specs/001-minimal-test/spec.md` 与 `specs/001-minimal-test/checklists/requirements.md`。
- 运行态契约基线：`backend/main.py` 是 `WorkflowResponse` 公开语义的归一化入口，`frontend/src/lib/api.ts` 必须镜像同一套类型。公开 `status` 固定为 `running / paused / needs_clarification / awaiting_outline_approval / awaiting_fact_check_approval / completed / failed`；`state` 额外稳定暴露 `current_node`、`pause`、`gate`、`error`。`GET /api/trace/{id}` 的 `workflow.status` 也必须使用同一公开状态，并在缺少实时 emit 时通过 timeline 补偿 `workflow_paused` / `workflow_resumed` / `workflow_gate_waiting`。
- 模式：`specs/002-content-gen-mvp1` 推荐使用 1 个协调 agent + 5 个执行 agent。Agent0 负责运行态契约与集成守门，独占 `backend/main.py`、`frontend/src/lib/api.ts`、契约测试与 `specs/002-content-gen-mvp1/contracts/*`；Agent1 负责运行态持久化与图编排，独占 `backend/db/postgres_store.py`、`backend/services/artifact_store.py`、`backend/services/__init__.py`、`backend/models/artifact.py`、`backend/graph/content_generation_graph.py`；Agent2 负责内容节点与 Gate 后端，独占 `backend/nodes/*`；Agent3 负责用户运行台与回放前端，独占 `frontend/src/app/page.tsx`、`frontend/src/app/workflow/[id]/page.tsx`、`frontend/src/app/console/runs/page.tsx` 及相关 viewer/progress/trace 组件；Agent4 负责工作流编辑器与发布链路，独占工作流定义/版本后端与 `frontend/src/components/WorkflowEditor/*`、`frontend/src/app/console/workflows/*`；Agent5 负责权限与管理后台，独占 `backend/services/permission_service.py`、`backend/routes/auth_routes.py`、`backend/routes/admin_routes.py`、`backend/routes/workspace_routes.py`、`frontend/src/lib/auth.ts`、`frontend/src/contexts/AuthContext.tsx`、`frontend/src/app/console/layout.tsx`、`frontend/src/app/console/settings/members/page.tsx`。关键规则：`backend/main.py`、`frontend/src/lib/api.ts`、`backend/graph/content_generation_graph.py`、`frontend/src/app/workflow/[id]/page.tsx` 视为单 owner 热点文件，同一时刻只允许一个 agent 写入。推荐顺序：先由 Agent0 + Agent1 + Agent5(T009) 完成 Phase 2，再并行推进 US1/US2/US3/US5，最后推进 US4。
- PromptChain MVP1 协作拓扑以实际角色编号为准：使用 1 个 coordinator + Agent 0-5 六条执行线。若文档中出现“1 个协调 agent + 5 个执行 agent”的旧表述，但同时列出了 Agent 0-5，应以 Agent 0-5 六条执行线为准。四个热点文件仍为单 owner：backend/main.py、frontend/src/lib/api.ts、backend/graph/content_generation_graph.py、frontend/src/app/workflow/[id]/page.tsx。
- ## 后端推荐目录结构（2026-03-10 重构后）

```
backend/
├── app.py                  # FastAPI 应用入口（应用工厂+路由注册，<100行）
├── pyproject.toml / ruff.toml / .pre-commit-config.yaml
│
├── core/                    # 横切关注点
│   ├── __init__.py
│   └── config.py            # 统一配置（环境变量集中管理）
│
├── graph/                   # LangGraph 工作流定义
│   └── content_generation_graph.py  # 图定义 + 执行器
│
├── nodes/                   # LangGraph 节点实现
│   ├── intent_parser.py / outline_generator.py
│   ├── content_generator.py / self_refiner.py / fact_checker.py
│
├── models/                  # Pydantic + ORM 模型
│   ├── artifact.py / intent_card.py / outline.py / fact_check.py
│   ├── auth_models.py / auth_orm.py
│   ├── admin_models.py / admin_orm.py
│   ├── workflow_definition.py / workflow_orm.py
│   └── result.py
│
├── routes/                  # API 路由
│   ├── workflow_routes.py   # 内容工作流 API
│   ├── workflow_helpers.py  # 共享模型+工具函数
│   ├── trace_routes.py      # Trace / Artifact API
│   ├── auth_routes.py / workspace_routes.py / admin_routes.py
│   ├── workflow_definition_routes.py / workflow_version_routes.py
│   └── websocket_routes.py
│
├── services/                # 核心服务层
├── db/                      # 数据库层（postgres_store + init.sql）
└── tests/                   # 测试
```

关键约定：
- 入口从 `main.py` 改为 `app.py`，启动命令：`uv run uvicorn app:app --reload --port 8000`
- main.py 保留作为向后兼容的重导入
- 所有环境配置集中在 `core/config.py`
- 路由共享逻辑在 `routes/workflow_helpers.py`（请求/响应模型+工具函数）
- ## graph/ 模块拆分结构（2026-03-10）

`content_generation_graph.py`（822行）已拆分为 4 个子模块：
- `graph/state.py` — GraphState TypedDict 数据合约（62行）
- `graph/conditions.py` — should_clarify / should_regenerate_outline / should_proceed_after_fact_check（35行）
- `graph/builder.py` — build_content_generation_graph() + finalize_output()（171行）
- `graph/executor.py` — ContentGenerationWorkflow 类 + get_workflow() 单例（599行）

`graph/__init__.py` 重新导出所有符号，外部 `from graph import get_workflow` 无需修改。
`content_generation_graph.py` 保留为向后兼容 shim。
