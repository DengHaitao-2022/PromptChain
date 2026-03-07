# Auth & Access Contract

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

## 6. Compatibility Notes

- 当前权限表中 `viewer` 尚未具备执行权限；这是本计划需要补齐的权限矩阵调整。
- `GET /api/me` 应继续作为前端初始化身份和角色菜单的权威入口。
