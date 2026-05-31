# PromptChain 生产部署基线

本文档描述当前最小生产工程基线：PR CI、后端/前端 Docker 镜像、以及单机 Docker Compose 示例。该基线只覆盖可运行生产镜像和 PR gate，不包含 Kubernetes、云厂商流水线、镜像仓库发布或蓝绿/金丝雀发布。

## CI Gate

PR 进入 `dev` 或 `main` 时会触发 `.github/workflows/pr-ci.yml`：

- 基础设施：校验 workflow YAML 与 `docker-compose.prod.yml` 展开结果。
- 后端：当 PR 修改 `backend/**/*.py` 时，执行与根 `.pre-commit-config.yaml` 对齐的阻塞型 Ruff gate：`uvx ruff==0.14.10 check backend --config backend/ruff.toml` 和 `uvx ruff==0.14.10 format backend --check --config backend/ruff.toml`。
- 前端：当 PR 修改 `frontend/src/**` 或前端构建配置时，执行阻塞型 `npm ci`、`npm run lint`、`npx tsc --noEmit`、`npm run build`。

该 workflow 可在 GitHub 分支保护中配置为必需状态检查。CodeQL 仍由 `.github/workflows/codeql.yml` 独立运行。

当前 `dev` 上仍存在既有后端 pytest 契约/运行态测试债、前端 ESLint 源码债和前端 TypeScript 类型债。为避免生产部署基线 PR 越权修改业务源码，源码质量检查暂按变更范围触发，pytest 暂不纳入本 PR 的阻塞 gate；完成源码质量与测试基线清理后，可将 pytest、Ruff、ESLint、typecheck 和 build 升级为全量阻塞 gate。

## 镜像

### 后端

`backend/Dockerfile` 使用 Python 3.14 slim 基础镜像，复制 `backend/uv.lock` 后通过 `uv sync --frozen --no-dev --no-install-project` 安装依赖，避免镜像构建时重新解析上游依赖；容器启动时通过 `exec uvicorn app:app` 让应用进程接收终止信号：

```bash
docker build -f backend/Dockerfile -t promptchain-backend:local .
docker run --rm -p 8000:8000 --env-file backend/.env promptchain-backend:local
```

健康检查访问：

```bash
curl -fsS http://localhost:8000/
```

### 前端

`frontend/Dockerfile` 使用 Node.js 20 多阶段构建，执行 `npm run build` 后通过 `next start` 提供生产服务：

```bash
docker build -f frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  -t promptchain-frontend:local .
docker run --rm -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:8000 promptchain-frontend:local
```

`NEXT_PUBLIC_API_URL` 会在 Next.js 构建期进入浏览器包；生产地址变化时需要重新构建前端镜像。

健康检查访问：

```bash
curl -fsS http://localhost:3000/
```

## 生产 Compose 示例

`docker-compose.prod.yml` 提供单机生产样例，包含：

- `postgres`
- `redis`
- `backend`
- `frontend`

示例启动：

```bash
cp backend/.env.example .env
# 编辑 .env，至少设置 POSTGRES_PASSWORD、JWT_SECRET_KEY、CORS_ORIGINS、APP_BASE_URL、NEXT_PUBLIC_API_URL 和一个 LLM Provider Key。
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml ps
```

默认端口：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`

## 关键环境变量

| 变量 | 用途 | 示例 |
|---|---|---|
| `POSTGRES_USER` | PostgreSQL 用户 | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL 密码，生产必须显式设置 | `change-me` |
| `POSTGRES_DB` | PostgreSQL 数据库名 | `promptchain` |
| `JWT_SECRET_KEY` | JWT 签名密钥，生产必须使用长随机值 | `change-me-use-a-long-random-secret` |
| `DATABASE_URL` | 后端数据库连接串 | `postgresql+asyncpg://postgres:change-me@postgres:5432/promptchain` |
| `REDIS_URL` | 后端 Redis 连接串 | `redis://redis:6379/0` |
| `WORKFLOW_EVENT_BUS_BACKEND` | 工作流事件总线后端 | `redis` |
| `CORS_ORIGINS` | 允许携带 Cookie 的前端 Origin，不能使用 `*` | `https://promptchain.example.com` |
| `APP_BASE_URL` | 邮件链接和应用基准地址 | `https://promptchain.example.com` |
| `NEXT_PUBLIC_API_URL` | 前端浏览器访问后端 API 的地址 | `https://api.promptchain.example.com` |
| `DEFAULT_LLM_PROVIDER` | 默认模型提供方 | `anthropic` |
| `DEFAULT_MODEL_NAME` | 默认模型名 | `claude-3-5-sonnet-20241022` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `GITHUB_MODEL_TOKEN` | LLM Provider 凭据，至少配置一个 | `...` |
| `SMTP_*` | 邮件发送配置 | `SMTP_HOST=smtp.example.com` |

## 本地验证步骤

建议在提交前至少执行：

```bash
# 后端质量检查
cd backend
uv sync --all-extras --dev --no-install-project
JWT_SECRET_KEY=test-secret uv run pytest
# CI 暂不把 pytest 作为本 PR 的阻塞 gate；本地仍建议使用非生产密钥运行。
# 若本次修改 backend/**/*.py，再执行：
cd ..
uvx ruff==0.14.10 check backend --config backend/ruff.toml
uvx ruff==0.14.10 format backend --check --config backend/ruff.toml

# 前端质量检查；仅当前端源码或构建配置变更时执行
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build

# Compose 配置检查
cd ..
docker compose -f docker-compose.prod.yml config
```

如需完整容器烟测：

```bash
docker compose -f docker-compose.prod.yml up --build -d
curl -fsS http://localhost:8000/
curl -fsS http://localhost:3000/
docker compose -f docker-compose.prod.yml down
```

## 当前未覆盖验证

- 未配置镜像仓库推送、镜像签名或 SBOM。
- 未配置生产环境数据库迁移流水线。
- 未配置 Kubernetes、Ingress、证书自动签发或弹性伸缩。
- 未配置端到端浏览器测试。
- 完整四服务容器烟测已执行到镜像构建阶段，后端镜像可通过 `uv sync --frozen` 完成冻结安装；当前仍被既有前端 TypeScript 错误阻塞，尚未进入前端 healthcheck 阶段。已补充执行 `postgres` / `redis` / `backend` 服务级烟测，后端 `/` 健康检查通过。
- 未覆盖真实 SMTP 与真实 LLM Provider 的生产连通性验证。
- 未覆盖多实例部署下的 WebSocket 粘性会话和反向代理策略。
