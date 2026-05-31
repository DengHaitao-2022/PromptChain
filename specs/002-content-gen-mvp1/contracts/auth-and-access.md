# Auth & Access Contract

## 0. Current Baseline (`dev@699bf53`)

- `viewer` 现在已经具备 `workflow.read` + `workflow.execute`，可运行已发布工作流并处理自己的 Gate。
- 运行态、trace、artifact 访问现在同时校验 `workspace_id` 与 `user_id` 归属；`admin` / `owner` 才能跨用户查看同工作空间数据。
- 当前工作空间级“暂停访问”通过 membership role 编码实现，是 workspace-scoped 行为，不再直接依赖全局 `User.status`。
- `register -> verify-email -> login` 与 `forgot-password -> reset-password -> login` 的 auth-flow 页面和接口闭环已在 `dev`。
- 鉴权域当前剩余主线只剩 `T042` 验收闭环，不再是 auth-flow 缺失。
- 统一错误体系正在 PR #5 中推进；合入前，当前主线错误响应仍按 FastAPI `HTTPException` 与局部 `Result` 兼容风格对待。

## 1. Session Transport

认证采用 Cookie 会话：

| Cookie | Purpose | Notes |
|---|---|---|
| `access_token` | 短期访问令牌 | HttpOnly，默认 15 分钟 |
| `refresh_token` | 刷新令牌 | HttpOnly，默认 7 天 |

### Rules

- 浏览器请求必须携带 Cookie
- 前端受保护请求默认使用 `credentials: include`
- 邮箱未验证账号不得登录

## 2. Auth Endpoints

| Method | Path | Status | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/register` | Existing | 注册新用户 |
| `POST` | `/api/auth/login` | Existing | 登录并写入 Cookie |
| `POST` | `/api/auth/refresh` | Existing | 刷新访问令牌 |
| `POST` | `/api/auth/logout` | Existing | 清除 Cookie 并退出 |
| `POST` | `/api/auth/verify-email` | Existing | 完成邮箱验证 |
| `POST` | `/api/auth/resend-verification-email` | Existing | 重发邮箱验证邮件 |
| `POST` | `/api/auth/forgot-password` | Existing | 发起密码重置 |
| `POST` | `/api/auth/reset-password` | Existing | 提交新密码 |
| `GET` | `/api/me` | Existing | 获取当前用户、工作空间和角色 |

## 3. Workspace & Membership Endpoints

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/api/workspaces` | Existing | 获取工作空间列表 |
| `POST` | `/api/workspaces` | Existing | 创建工作空间 |
| `GET` | `/api/workspaces/{workspace_id}` | Existing | 获取工作空间详情 |
| `PATCH` | `/api/workspaces/{workspace_id}` | Existing | 更新工作空间 |
| `GET` | `/api/workspaces/{workspace_id}/members` | Existing | 查看成员列表 |
| `POST` | `/api/workspaces/{workspace_id}/invite` | Existing | 邀请成员 |
| `POST` | `/api/workspaces/accept-invite` | Existing | 接受邀请 |
| `PATCH` | `/api/memberships/{membership_id}` | Existing | 修改成员角色 |
| `DELETE` | `/api/memberships/{membership_id}` | Existing | 移除成员 |

## 4. Role Model

### Technical Roles

| Role | Current Meaning | Target Meaning for MVP1 |
|---|---|---|
| `viewer` | 只读 | 普通用户：运行已发布工作流、查看本人任务与产物、处理 Gate |
| `editor` | 编辑 + 运行 | 工作流设计者：创建/编辑/校验/发布工作流，并可运行任务 |
| `admin` | 管理 | 管理员：管理成员、模型、密钥、查看全局运行记录 |
| `owner` | 全权 | 管理员超集，保留工作空间最高权限 |

### Business Persona Mapping

| Business Persona | Target Technical Role |
|---|---|
| 普通用户 | `viewer` |
| 工作流设计者 | `editor` |
| 管理员 | `admin` / `owner` |

## 5. Access Rules

1. 普通用户只能运行已发布工作流，并仅能查看本人任务和待处理 Gate。
2. 设计者可维护自己创建或被授权的工作流。
3. 管理员可查看全部工作流与任务，并进行成员和系统级管理。
4. 未登录用户访问受保护页面时必须被重定向或拒绝。
5. 越权访问不得返回非授权资源的敏感内容。
6. `trace` / `artifact` / `rerun` 等运行态相关接口必须继承相同的工作空间和任务归属校验。

## 6. Compatibility Notes

- `viewer` 执行权限、控制台导航守卫、成员管理页与运行态归属校验都已经进入主线。
- 认证前端页与成功/失败态已进入主线；`T042` 只负责验证登录、菜单隔离与授权边界是否与 quickstart 一致。
- `GET /api/me` 继续作为前端初始化身份、当前工作空间与角色菜单的权威入口。
