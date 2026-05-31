# Auth API

## 接口清单

### 1) `POST /api/auth/register`

- 用途：注册用户并触发邮箱验证
- 请求体：

```json
{
  "email": "user@example.com",
  "password": "Password123",
  "username": "alice",
  "display_name": "Alice"
}
```

- 成功：`{ "message": "注册成功，请查收验证邮件" }`

### 2) `POST /api/auth/login`

- 用途：登录并写入 `access_token`/`refresh_token` Cookie
- 请求体：

```json
{
  "email": "user@example.com",
  "password": "Password123"
}
```

- 成功响应含 `user/workspace/role`
- 典型错误：
  - `401`: 邮箱或密码错误
  - `403`: 邮箱未验证

### 3) `POST /api/auth/refresh`

- 用途：基于 `refresh_token` Cookie 刷新 access token
- 典型错误：`401`

### 4) `POST /api/auth/logout`

- 用途：撤销 refresh token 并清除 Cookie

### 5) `POST /api/auth/verify-email`

- 请求体：`{ "token": "..." }`

### 6) `POST /api/auth/resend-verification-email`

- 用途：重发邮箱验证邮件
- 请求体：`{ "email": "user@example.com" }`
- 说明：未验证账号会重新生成验证 token；已验证或不存在账号按防枚举策略返回中性消息

### 7) `POST /api/auth/forgot-password`

- 请求体：`{ "email": "user@example.com" }`
- 说明：邮箱不存在也返回成功消息（防枚举）

### 8) `POST /api/auth/reset-password`

- 请求体：

```json
{
  "token": "...",
  "password": "NewPassword123"
}
```

### 9) `GET /api/me`

- 用途：获取当前登录用户与工作空间上下文
- 鉴权：必须登录（Cookie）

## 前端调用约定

- 所有认证相关请求必须 `credentials: include`
- 不在浏览器持久化 Bearer token
