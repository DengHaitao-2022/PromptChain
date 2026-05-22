/**
 * 认证与权限工具库
 *
 * 前后端共享同一套角色语义，前端只负责菜单守卫与交互层兜底，
 * 最终授权仍以服务端校验为准。
 */

import { apiUrl } from './api-config';

const PREFERRED_WORKSPACE_STORAGE_KEY = 'promptchain:workspace_id';

// 合并并发 401 触发的刷新请求，避免多个接口同时刷新 Access Token。
let refreshTokenRequest: Promise<boolean> | null = null;

export type UserStatus = 'active' | 'inactive' | 'suspended';
export type WorkspaceAccessStatus = 'active' | 'suspended';
export type Role = 'owner' | 'admin' | 'editor' | 'viewer';
export type Action = 'read' | 'create' | 'update' | 'delete' | 'execute' | 'export' | 'manage';
export type Resource =
  | 'workflow'
  | 'workflow_run'
  | 'template'
  | 'model_provider'
  | 'secret'
  | 'api_key'
  | 'member'
  | 'workspace'
  | 'audit_log';

export interface User {
  id: string;
  email: string;
  username?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  status: UserStatus;
  email_verified: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  description?: string | null;
  logo_url?: string | null;
  owner_id: string;
  role: Role;
  joined_at?: string;
  created_at: string;
}

export interface WorkspaceMember {
  id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  role: Role;
  workspace_access: WorkspaceAccessStatus;
  account_status: UserStatus;
  email_verified: boolean;
  joined_at: string;
}

export interface AuthState {
  user: User | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
  role: Role | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  username?: string;
  display_name?: string;
}

export interface AuthResponse {
  message?: string;
  user: User;
  workspace: Workspace | null;
  role: Role | null;
  workspaces: Workspace[];
}

export interface InviteMemberRequest {
  email: string;
  role: Exclude<Role, 'owner'>;
}

export interface ConsoleRouteGuard {
  prefix: string;
  resource?: Resource;
  action?: Action;
}

// 前端权限表用于菜单显隐和交互兜底；最终授权仍以服务端 RBAC 为准。
export const ROLE_PERMISSIONS: Record<Role, Partial<Record<Resource, Action[]>>> = {
  viewer: {
    workflow: ['read', 'execute'],
    workflow_run: ['read', 'create'],
    template: ['read'],
    workspace: ['read'],
  },
  editor: {
    workflow: ['read', 'create', 'update', 'execute'],
    workflow_run: ['read', 'create'],
    template: ['read', 'create', 'update'],
    workspace: ['read'],
  },
  admin: {
    workflow: ['read', 'create', 'update', 'delete', 'execute', 'export', 'manage'],
    workflow_run: ['read', 'create', 'delete', 'export'],
    template: ['read', 'create', 'update', 'delete', 'manage'],
    model_provider: ['read', 'create', 'update', 'delete', 'manage'],
    secret: ['read', 'create', 'update', 'delete', 'manage'],
    api_key: ['read', 'create', 'update', 'delete', 'manage'],
    member: ['read', 'create', 'update', 'delete', 'manage'],
    workspace: ['read', 'update', 'manage'],
    audit_log: ['read', 'export'],
  },
  owner: {
    workflow: ['read', 'create', 'update', 'delete', 'execute', 'export', 'manage'],
    workflow_run: ['read', 'create', 'delete', 'export', 'manage'],
    template: ['read', 'create', 'update', 'delete', 'manage'],
    model_provider: ['read', 'create', 'update', 'delete', 'manage'],
    secret: ['read', 'create', 'update', 'delete', 'manage'],
    api_key: ['read', 'create', 'update', 'delete', 'manage'],
    member: ['read', 'create', 'update', 'delete', 'manage'],
    workspace: ['read', 'update', 'delete', 'manage'],
    audit_log: ['read', 'export'],
  },
};

// 控制台路由采用最长前缀匹配，确保更具体的页面先命中自己的权限规则。
const CONSOLE_ROUTE_GUARDS: ConsoleRouteGuard[] = [
  { prefix: '/console/workflows/edit', resource: 'workflow', action: 'create' },
  { prefix: '/console/settings/members', resource: 'member', action: 'read' },
  { prefix: '/console/settings/models', resource: 'model_provider', action: 'read' },
  { prefix: '/console/settings/keys', resource: 'secret', action: 'read' },
  { prefix: '/console/settings/audit', resource: 'audit_log', action: 'read' },
  { prefix: '/console/runs', resource: 'workflow_run', action: 'read' },
  { prefix: '/console/workflows', resource: 'workflow', action: 'read' },
  { prefix: '/console/settings' },
  { prefix: '/console' },
];

function normalizeAuthState(data: AuthResponse): AuthState {
  // 将服务端选定的工作空间写入本地偏好，供后续刷新 Token 时恢复上下文。
  persistPreferredWorkspace(data.workspace?.id ?? null);
  return {
    user: data.user,
    workspace: data.workspace,
    workspaces: data.workspaces ?? [],
    role: data.role ?? data.workspace?.role ?? null,
    isLoading: false,
    isAuthenticated: true,
  };
}

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const error = (await response.json()) as { detail?: string; message?: string };
    return error.detail || error.message || fallback;
  } catch {
    return fallback;
  }
}

interface AuthenticatedFetchOptions extends RequestInit {
  skipAuthRefresh?: boolean;
}

function getPreferredWorkspace(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return window.localStorage.getItem(PREFERRED_WORKSPACE_STORAGE_KEY);
}

function persistPreferredWorkspace(workspaceId: string | null) {
  if (typeof window === 'undefined') {
    return;
  }

  if (!workspaceId) {
    window.localStorage.removeItem(PREFERRED_WORKSPACE_STORAGE_KEY);
    return;
  }

  window.localStorage.setItem(PREFERRED_WORKSPACE_STORAGE_KEY, workspaceId);
}

/**
 * 登录
 */
export async function login(data: LoginRequest): Promise<AuthResponse> {
  const response = await fetch(apiUrl('/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '登录失败'));
  }

  return response.json();
}

/**
 * 注册
 */
export async function register(data: RegisterRequest): Promise<{ message: string }> {
  const response = await fetch(apiUrl('/auth/register'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '注册失败'));
  }

  return response.json();
}

/**
 * 登出
 */
export async function logout(): Promise<void> {
  persistPreferredWorkspace(null);
  await fetch(apiUrl('/auth/logout'), {
    method: 'POST',
    credentials: 'include',
  });
}

/**
 * 刷新 Token
 */
export async function refreshToken(): Promise<boolean> {
  if (refreshTokenRequest) {
    return refreshTokenRequest;
  }

  // Refresh Token 存在 HttpOnly Cookie 中，前端只负责携带工作空间偏好。
  refreshTokenRequest = (async () => {
    try {
      const workspaceId = getPreferredWorkspace();
      const response = await fetch(apiUrl('/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      return response.ok;
    } catch {
      return false;
    } finally {
      refreshTokenRequest = null;
    }
  })();

  return refreshTokenRequest;
}

/**
 * 统一处理带 Cookie 的认证请求：Access Token 过期时自动刷新一次再重试。
 */
export async function authenticatedFetch(
  input: string,
  options: AuthenticatedFetchOptions = {},
): Promise<Response> {
  const { skipAuthRefresh = false, ...fetchOptions } = options;

  const execute = () =>
    fetch(input, {
      credentials: 'include',
      ...fetchOptions,
    });

  const response = await execute();
  if (skipAuthRefresh || response.status !== 401) {
    return response;
  }

  // 只刷新并重试一次，防止认证失效时形成无限请求循环。
  const refreshed = await refreshToken();
  if (!refreshed) {
    return response;
  }

  return execute();
}

/**
 * 获取当前用户信息
 */
export async function getCurrentUser(): Promise<AuthState | null> {
  try {
    const response = await authenticatedFetch(apiUrl('/me'));

    if (!response.ok) {
      return null;
    }

    return normalizeAuthState((await response.json()) as AuthResponse);
  } catch {
    return null;
  }
}

/**
 * 切换工作空间
 */
export async function switchWorkspace(workspaceId: string): Promise<void> {
  const response = await authenticatedFetch(apiUrl('/workspace-context/switch'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '切换工作空间失败'));
  }

  persistPreferredWorkspace(workspaceId);
}

/**
 * 验证邮箱
 */
export async function verifyEmail(token: string): Promise<{ message: string }> {
  const response = await fetch(apiUrl('/auth/verify-email'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '验证失败'));
  }

  return response.json();
}

/**
 * 忘记密码
 */
export async function forgotPassword(email: string): Promise<{ message: string }> {
  const response = await fetch(apiUrl('/auth/forgot-password'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '操作失败'));
  }

  return response.json();
}

/**
 * 重置密码
 */
export async function resetPassword(token: string, password: string): Promise<{ message: string }> {
  const response = await fetch(apiUrl('/auth/reset-password'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '重置失败'));
  }

  return response.json();
}

/**
 * 获取工作空间成员
 */
export async function listWorkspaceMembers(workspaceId: string): Promise<WorkspaceMember[]> {
  const response = await authenticatedFetch(apiUrl(`/workspaces/${workspaceId}/members`));

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '加载成员失败'));
  }

  const data = (await response.json()) as { members?: WorkspaceMember[] };
  return data.members ?? [];
}

/**
 * 邀请成员
 */
export async function inviteWorkspaceMember(
  workspaceId: string,
  payload: InviteMemberRequest,
): Promise<{ message: string }> {
  const response = await authenticatedFetch(apiUrl(`/workspaces/${workspaceId}/invite`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '邀请失败'));
  }

  return response.json();
}

/**
 * 接受工作空间邀请
 */
export async function acceptWorkspaceInvite(token: string): Promise<{ message: string }> {
  const response = await authenticatedFetch(
    apiUrl(`/workspaces/accept-invite?token=${encodeURIComponent(token)}`),
    {
      method: 'POST',
    },
  );

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '接受邀请失败'));
  }

  return response.json();
}

/**
 * 修改成员角色
 */
export async function updateWorkspaceMemberRole(
  membershipId: string,
  role: Exclude<Role, 'owner'>,
): Promise<{ message: string }> {
  const response = await authenticatedFetch(apiUrl(`/memberships/${membershipId}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '更新角色失败'));
  }

  return response.json();
}

/**
 * 移除成员
 */
export async function removeWorkspaceMember(membershipId: string): Promise<{ message: string }> {
  const response = await authenticatedFetch(apiUrl(`/memberships/${membershipId}`), {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '移除成员失败'));
  }

  return response.json();
}

/**
 * 更新成员在当前工作空间中的访问状态
 */
export async function updateWorkspaceMemberAccess(
  userId: string,
  status: WorkspaceAccessStatus,
): Promise<{ message: string; workspace_access?: WorkspaceAccessStatus }> {
  const response = await authenticatedFetch(apiUrl(`/admin/users/${userId}/status`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response, '更新工作空间访问状态失败'));
  }

  return response.json();
}

/**
 * 兼容旧命名，实际语义已经收口为当前工作空间访问控制。
 */
export async function updateWorkspaceUserStatus(
  userId: string,
  status: WorkspaceAccessStatus,
): Promise<{ message: string; workspace_access?: WorkspaceAccessStatus }> {
  return updateWorkspaceMemberAccess(userId, status);
}

/**
 * 检查用户是否有指定权限
 */
export function hasPermission(role: Role | null | undefined, resource: Resource, action: Action): boolean {
  if (!role) return false;
  const permissions = ROLE_PERMISSIONS[role];
  const resourcePermissions = permissions?.[resource];
  return !!resourcePermissions?.includes(action);
}

/**
 * 检查用户是否至少是指定角色
 */
export function isAtLeastRole(currentRole: Role | null | undefined, requiredRole: Role): boolean {
  if (!currentRole) return false;
  const roleOrder: Role[] = ['viewer', 'editor', 'admin', 'owner'];
  return roleOrder.indexOf(currentRole) >= roleOrder.indexOf(requiredRole);
}

export function getRoleLabel(role: Role | null | undefined): string {
  switch (role) {
    case 'owner':
      return '拥有者';
    case 'admin':
      return '管理员';
    case 'editor':
      return '编辑者';
    case 'viewer':
      return '查看者';
    default:
      return '未分配';
  }
}

export function canAccessConsolePath(role: Role | null | undefined, pathname: string): boolean {
  if (!role) {
    return pathname === '/console';
  }

  // 寻找最精确匹配的路由守卫，避免 `/console/settings` 抢先覆盖子页面规则。
  const guard = CONSOLE_ROUTE_GUARDS
    .filter((item) => pathname.startsWith(item.prefix))
    .reduce<ConsoleRouteGuard | undefined>(
      (best, current) => (!best || current.prefix.length > best.prefix.length ? current : best),
      undefined,
    );

  if (!guard || !guard.resource || !guard.action) {
    return pathname.startsWith('/console');
  }

  return hasPermission(role, guard.resource, guard.action);
}

export function getAccessibleConsoleFallback(role: Role | null | undefined): string {
  if (!role) return '/console';

  if (hasPermission(role, 'workflow_run', 'read')) {
    return '/console';
  }

  return '/login';
}
