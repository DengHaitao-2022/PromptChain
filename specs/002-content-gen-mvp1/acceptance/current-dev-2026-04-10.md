# MVP1 Current-dev 验收记录（2026-04-10）

## 执行基线

- 执行时间：2026-04-10（Asia/Shanghai）
- 执行工作区：`/Users/hi/Developer/03-personal/PromptChain`
- 执行分支：`dev`
- 实际执行 commit：`698b80d`
- 用户提供的参考基线：`cb79009`
- 说明：本次验收证据只绑定当前工作区实际 head `698b80d`，不回写到用户口述但未在本地工作区出现的 commit

## 环境快照

- 前端：
  - 以 `npm run dev` 启动成功，`http://localhost:3000/login`、`/register`、`/forgot-password` 可返回 `200 OK`
- 后端：
  - `http://localhost:8000/openapi.json` 返回 `200 OK`
  - `http://localhost:8000/api/me` 在无 Cookie 时返回 `401 Unauthorized`
- 基础设施：
  - `docker compose ps` 返回 `Cannot connect to the Docker daemon at unix:///Users/hi/.orbstack/run/docker.sock`
  - 调试后端 `uv run uvicorn app:app --port 8001` 复现 `POST /api/auth/register` 与 `POST /api/auth/forgot-password` 均返回 `500 Internal Server Error`
  - 调试后端日志明确给出根因：`ConnectionRefusedError: [Errno 61] Connection refused`，连接目标为本地 PostgreSQL `localhost:5432`
- LLM 相关：
  - `backend/.env` 中 `GEMINI_API_KEY` 已配置
  - `backend/.env` 中 `DEFAULT_LLM_PROVIDER=anthropic`
  - `backend/.env` 中 `ANTHROPIC_API_KEY` 为空
  - 结论：即使数据库恢复，Smoke E / F 在当前默认环境下仍需要把 provider 切到 `google`，或补齐有效 `ANTHROPIC_API_KEY`

## Smoke 结果总表

| Smoke | 关联故事 | 状态 | 验证类型 | 环境前提 | 关键证据位置 | 结论 |
|---|---|---|---|---|---|---|
| Smoke A | US5 / `T042` | blocked | 静态通过 + 运行阻塞 | 前端可达；后端可达；PostgreSQL 必须可连接 | 本文件《Smoke A》；`quickstart.md` 新增 current-dev 摘要 | `/register` 页面可达，但首个 DB 依赖接口 `POST /api/auth/register` 即返回 `500`，阻塞注册/验证/登录闭环 |
| Smoke B | US5 / `T042` | blocked | 静态通过 + 运行阻塞 | 与 Smoke A 相同 | 本文件《Smoke B》 | `/forgot-password` 页面可达，但 `POST /api/auth/forgot-password` 同样因 PostgreSQL 连接拒绝返回 `500` |
| Smoke C | US5 / `T042` | blocked | 静态通过 | 需要至少 1 组 `viewer/editor/admin` 已验证会话与可查询运行态数据 | 本文件《Smoke C》 | `/api/me` 无 Cookie 时按预期返回 `401`，但无法建立任一已验证会话，也无法执行角色/越权 live smoke |
| Smoke D | US3 / `T031` | blocked | 静态通过 | 需要 editor 会话、工作流持久化与发布链路可写 | 本文件《Smoke D》 | 当前环境无法完成登录与工作流存储读写，因此无法验证草稿/校验/发布 |
| Smoke E | US1 / `T017`、US2 / `T024` | blocked | 静态通过 | 需要已发布工作流、可登录 viewer 会话、PostgreSQL 可用、有效 LLM provider | 本文件《Smoke E》 | 主要阻塞是 PostgreSQL 不可达；次级阻塞是当前默认 provider 指向 `anthropic` 且无有效 key |
| Smoke F | US2 / `T024` | blocked | 静态通过 | 依赖 Smoke E 的长任务可启动 | 本文件《Smoke F》 | 长任务无法启动，因此无法验证 pause / resume |

## Smoke A

### 已执行证据

```text
curl -i http://localhost:3000/register
HTTP/1.1 200 OK
X-Powered-By: Next.js
```

```text
curl -i -X POST http://localhost:8001/api/auth/register \
  -H 'Content-Type: application/json' \
  --data '{"email":"acceptance-owner-smokea@example.com","password":"Password1234","display_name":"Smoke A"}'

HTTP/1.1 500 Internal Server Error
Internal Server Error
```

```text
uvicorn(8001) log excerpt
POST /api/auth/register -> 500 Internal Server Error
ConnectionRefusedError: [Errno 61] Connection refused
```

### 判定

- `pass / fail / blocked`：`blocked`
- 阻塞原因：数据库前提未满足，首个注册接口无法访问 PostgreSQL
- 备注：当前只拿到了页面静态可达性，未进入“未验证邮箱登录拦截”“验证成功后登录”“/api/me 返回当前工作空间”这些 live 验收点

## Smoke B

### 已执行证据

```text
curl -i http://localhost:3000/forgot-password
HTTP/1.1 200 OK
X-Powered-By: Next.js
```

```text
curl -i -X POST http://localhost:8001/api/auth/forgot-password \
  -H 'Content-Type: application/json' \
  --data '{"email":"acceptance-owner-smokea@example.com"}'

HTTP/1.1 500 Internal Server Error
Internal Server Error
```

```text
uvicorn(8001) log excerpt
POST /api/auth/forgot-password -> 500 Internal Server Error
ConnectionRefusedError: [Errno 61] Connection refused
```

### 判定

- `pass / fail / blocked`：`blocked`
- 阻塞原因：数据库前提未满足，忘记密码链路无法查找用户或创建重置 token

## Smoke C

### 已执行证据

```text
curl -i http://localhost:8000/api/me
HTTP/1.1 401 Unauthorized
{"detail":"未登录或登录已过期"}
```

### 判定

- `pass / fail / blocked`：`blocked`
- 阻塞原因：无法创建任一已验证用户会话，因此无法继续验证：
  - `viewer / editor / admin` 菜单隔离
  - 管理页前后端越权拦截
  - 他人 `workflow / trace / artifact` 资源访问边界
- 当前能确认的仅是未登录态 `/api/me` 返回值符合预期

## Smoke D

### 判定

- `pass / fail / blocked`：`blocked`
- 阻塞原因：缺少可登录 editor 会话，且工作流相关持久化也依赖 PostgreSQL
- 影响：无法验证草稿保存、非法流程校验、发布，以及 viewer 仅看见已发布版本

## Smoke E

### 判定

- `pass / fail / blocked`：`blocked`
- 主阻塞：PostgreSQL 不可达，无法取得会话、工作流列表与运行态记录
- 次阻塞：当前 `backend/.env` 默认 provider 为 `anthropic`，但 `ANTHROPIC_API_KEY` 为空；虽然 `GEMINI_API_KEY` 已配置，但未处于当前默认 provider
- 影响：US1 的标准生成链路与 US2 的 Gate 中断/恢复均未能进入 live 执行

## Smoke F

### 判定

- `pass / fail / blocked`：`blocked`
- 阻塞原因：依赖 Smoke E 先成功启动长任务；当前连任务创建都无法进入 live 阶段

## 故事级结论

| Story | current-dev 状态 | 说明 |
|---|---|---|
| US1 / `T017` | blocked | 标准生成链路未执行；当前只保留静态覆盖事实 |
| US2 / `T024` | blocked | Gate 与 pause/resume 未执行 live smoke；当前只保留静态覆盖事实 |
| US3 / `T031` | blocked | 编辑器发布闭环未执行 live smoke；当前只保留静态覆盖事实 |
| US5 / `T042` | blocked | auth/access 回归未完成；当前只确认了页面路由可达与 `/api/me` 未登录返回 |

## 建议的下一次重跑前提

1. 启动本地 Docker/OrbStack，使 PostgreSQL 与 Redis 可用
2. 保持前端 `npm run dev` 与后端 `uv run uvicorn app:app --reload --port 8000` 可访问
3. 对 US1 / US2 相关 smoke，把默认 provider 切到 `google`，或补齐有效 `ANTHROPIC_API_KEY`
4. 环境恢复后，按 `Smoke D -> E -> F -> A -> B -> C` 顺序重跑
