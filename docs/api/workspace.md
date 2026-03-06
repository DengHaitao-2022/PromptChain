# Workspace API

## 接口清单

### 1) `GET /api/workspaces`

- 用途：获取当前用户所有工作空间
- 鉴权：必须登录

### 2) `POST /api/workspaces`

- 用途：创建工作空间，创建者自动成为 `owner`
- 请求体：

```json
{
  "name": "My Workspace",
  "description": "团队空间"
}
```

### 3) `GET /api/workspaces/{workspace_id}`

- 用途：获取工作空间详情
- 典型错误：`403`（非成员）、`404`

### 4) `PATCH /api/workspaces/{workspace_id}`

- 用途：更新工作空间
- 需要权限：`workspace.update`

### 5) `GET /api/workspaces/{workspace_id}/members`

- 用途：获取成员列表

### 6) `POST /api/workspaces/{workspace_id}/invite`

- 用途：邀请成员
- 需要权限：`member.manage`
- 请求体：

```json
{
  "email": "member@example.com",
  "role": "viewer"
}
```

### 7) `POST /api/workspaces/accept-invite?token=...`

- 用途：接受邀请链接

### 8) `PATCH /api/memberships/{membership_id}`

- 用途：修改成员角色
- 请求体：`{ "role": "editor" }`

### 9) `DELETE /api/memberships/{membership_id}`

- 用途：移除成员

## 约束与权限

- 全部接口需要登录态（Cookie）
- 不能直接修改/移除 `owner`
- 成员管理相关接口需要 `member.manage`
