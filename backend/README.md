# 基于 Prompt Chain 的自动化内容生成系统 - 后端

## 技术栈
- **框架**: FastAPI
- **工作流引擎**: LangGraph
- **LLM**: 多 Provider 兼容（OpenAI, Anthropic, Google Gemini, GitHub Models, Ollama）
- **数据存储**: PostgreSQL（运行态主路径）/ 内存回退（开发模式）
- **包管理**: uv (快速、可复现)
- **代码质量**: ruff + pre-commit

## 快速开始

### 前置要求
- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (推荐使用 `brew install uv`)

### 开发环境设置

```bash
# 安装依赖并创建虚拟环境
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 API Keys

# 启动服务
uv run uvicorn app:app --reload --port 8000

# 或者激活虚拟环境后直接运行
source .venv/bin/activate  # macOS/Linux
uvicorn app:app --reload --port 8000
```

### 常用命令

```bash
# 添加新依赖
uv add package-name

# 添加开发依赖
uv add --dev pytest pytest-asyncio

# 运行Python脚本
uv run python script.py

# 运行后端测试（包含异步测试插件）
uv run --extra dev pytest -q

# 更新依赖
uv sync

# 代码格式化
ruff format .

# 代码检查
ruff check .

# 安装 Git hooks（首次）
pre-commit install

# 手动运行所有检查
pre-commit run --all-files
```

### 数据库迁移

生产环境 schema 由 Alembic 管理，不由应用启动自动改库：

```bash
cd backend
uv run alembic upgrade head
```

本地开发仍保留 `create_all` 兼容路径；生产部署建议设置 `DATABASE_AUTO_SCHEMA_INIT=false`，并在应用启动前完成 Alembic upgrade。更多边界见 `../docs/database-migration.md`。

## 项目结构

```
backend/
├── app.py                  # FastAPI 应用入口（应用工厂+路由注册）
├── pyproject.toml           # 项目配置和依赖
├── ruff.toml                # Ruff 配置
├── .pre-commit-config.yaml  # Pre-commit hooks
│
├── core/                    # 横切关注点
│   ├── __init__.py
│   └── config.py            # 统一配置（环境变量集中管理）
│
├── graph/                   # LangGraph 工作流定义
│   ├── state.py             # GraphState 数据合约
│   ├── conditions.py        # 条件路由函数
│   ├── builder.py           # 图构建与 finalize_output
│   ├── executor.py          # ContentGenerationWorkflow 执行器
│   ├── runtime_plan.py      # 已发布 DSL 到受限运行计划的编译
│   └── content_generation_graph.py  # 兼容 re-export 入口
│
├── nodes/                   # LangGraph 节点实现
│   ├── intent_parser.py
│   ├── outline_generator.py
│   ├── content_generator.py
│   ├── self_refiner.py
│   └── fact_checker.py
│
├── models/                  # Pydantic 数据模型 + ORM 模型
│   ├── artifact.py / intent_card.py / outline.py / fact_check.py
│   ├── auth_models.py / auth_orm.py
│   ├── admin_models.py / admin_orm.py
│   ├── workflow_definition.py / workflow_orm.py
│   └── result.py
│
├── routes/                  # API 路由
│   ├── workflow_routes.py   # 内容工作流 API（启动/审批/暂停/重跑/SSE/DOCX导出）
│   ├── workflow_helpers.py  # 工作流共享模型和工具函数
│   ├── trace_routes.py      # Trace / Artifact API
│   ├── auth_routes.py       # 认证路由
│   ├── workspace_routes.py  # 工作空间路由
│   ├── admin_routes.py      # 后台管理路由
│   ├── workflow_definition_routes.py  # 工作流定义 CRUD
│   ├── workflow_version_routes.py     # 版本管理
│   └── websocket_routes.py  # WebSocket 实时推送
│
├── services/                # 核心服务层
│   ├── auth_service.py / email_service.py / permission_service.py
│   ├── artifact_store.py / trace_service.py / rerun_service.py
│   ├── workflow_export_service.py
│   ├── llm_provider.py / llm_retry.py / llm_errors.py
│   └── workflow_definition_service.py
│
├── db/                      # 数据库层
│   ├── postgres_store.py
│   └── init.sql
│
└── tests/                   # 测试
```

## 当前实现边界

- 当前主线基线为 `dev@699bf53`。
- 内容运行态默认走 PostgreSQL-backed store；`RUNTIME_STORE_BACKEND=memory` 仅用于开发回退。
- 内容工作流 API 已覆盖启动、澄清、提纲审批、事实核查审批、手动暂停/恢复、运行列表、SSE 快照流、节点重跑、重跑历史和 DOCX 导出。
- 工作流定义/版本 API 已覆盖 CRUD、校验、编译预览、发布、版本对比与恢复。
- 统一错误体系仍在 PR #5，尚未进入 `dev`；当前主线仍以 FastAPI `HTTPException` / `Result` 兼容风格为主。
- 生产 CI/CD 与部署基线仍在 PR #4；当前 PR 检查已通过，但合入前仍只能视为候选部署基线。
