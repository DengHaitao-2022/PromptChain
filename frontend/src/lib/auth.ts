/**
 * 认证工具库
 *
 * 提供登录、登出、用户信息获取等功能
 * Token 由后端通过 HttpOnly Cookie 管理，前端只需调用 API
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

// ==================== 类型定义 ====================

export interface User {
  id: string;
  email: string;
  username?: string;
  display_name?: string;
  avatar_url?: string;
  status: 'active' | 'inactive' | 'suspended';
  email_verified: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  description?: string;
  logo_url?: string;
  owner_id: string;
  role: 'owner' | 'admin' | 'editor' | 'viewer';
  created_at: string;
}

export interface AuthState {
  user: User | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
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

// ==================== API 调用 ====================

/**
 * 登录
 */
export async function login(data: LoginRequest): Promise<{
  user: User;
  workspace: Workspace | null;
}> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // 重要：包含 Cookie
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '登录失败');
  }

  return response.json();
}

/**
 * 注册
 */
export async function register(data: RegisterRequest): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '注册失败');
  }

  return response.json();
}

/**
 * 登出
 */
export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    console.error('登出失败');
  }
}

/**
 * 刷新 Token
 */
export async function refreshToken(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * 获取当前用户信息
 */
export async function getCurrentUser(): Promise<AuthState | null> {
  try {
    const response = await fetch(`${API_BASE}/me`, {
      credentials: 'include',
    });

    if (!response.ok) {
      // 尝试刷新 Token
      if (response.status === 401) {
        const refreshed = await refreshToken();
        if (refreshed) {
          // 重试获取用户信息
          const retryResponse = await fetch(`${API_BASE}/me`, {
            credentials: 'include',
          });
          if (retryResponse.ok) {
            const data = await retryResponse.json();
            return {
              user: data.user,
              workspace: data.workspace,
              workspaces: data.workspaces,
              isLoading: false,
              isAuthenticated: true,
            };
          }
        }
      }
      return null;
    }

    const data = await response.json();
    return {
      user: data.user,
      workspace: data.workspace,
      workspaces: data.workspaces,
      isLoading: false,
      isAuthenticated: true,
    };
  } catch {
    return null;
  }
}

/**
 * 验证邮箱
 */
export async function verifyEmail(token: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/auth/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '验证失败');
  }

  return response.json();
}

/**
 * 忘记密码
 */
export async function forgotPassword(email: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '操作失败');
  }

  return response.json();
}

/**
 * 重置密码
 */
export async function resetPassword(token: string, password: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || '重置失败');
  }

  return response.json();
}

// ==================== 权限检查 ====================

type Role = 'owner' | 'admin' | 'editor' | 'viewer';
type Action = 'read' | 'create' | 'update' | 'delete' | 'execute' | 'manage';

const ROLE_PERMISSIONS: Record<Role, Record<string, Action[]>> = {
  viewer: {
    workflow: ['read'],
    workflow_run: ['read'],
    template: ['read'],
    member: ['read'],
  },
  editor: {
    workflow: ['read', 'create', 'update', 'execute'],
    workflow_run: ['read', 'create'],
    template: ['read', 'create', 'update'],
    member: ['read'],
  },
  admin: {
    workflow: ['read', 'create', 'update', 'delete', 'execute'],
    workflow_run: ['read', 'create', 'delete'],
    template: ['read', 'create', 'update', 'delete'],
    model_provider: ['read', 'create', 'update', 'delete', 'manage'],
    secret: ['read', 'create', 'delete', 'manage'],
    api_key: ['read', 'create', 'delete', 'manage'],
    member: ['read', 'create', 'update', 'delete', 'manage'],
  },
  owner: {
    workflow: ['read', 'create', 'update', 'delete', 'execute', 'manage'],
    workflow_run: ['read', 'create', 'delete', 'manage'],
    template: ['read', 'create', 'update', 'delete', 'manage'],
    model_provider: ['read', 'create', 'update', 'delete', 'manage'],
    secret: ['read', 'create', 'update', 'delete', 'manage'],
    api_key: ['read', 'create', 'update', 'delete', 'manage'],
    member: ['read', 'create', 'update', 'delete', 'manage'],
    workspace: ['read', 'update', 'delete', 'manage'],
  },
};

/**
 * 检查用户是否有指定权限
 */
export function hasPermission(role: Role | undefined, resource: string, action: Action): boolean {
  if (!role) return false;
  const permissions = ROLE_PERMISSIONS[role];
  if (!permissions) return false;
  const resourcePermissions = permissions[resource];
  if (!resourcePermissions) return false;
  return resourcePermissions.includes(action);
}

/**
 * 检查用户是否至少是指定角色
 */
export function isAtLeastRole(currentRole: Role | undefined, requiredRole: Role): boolean {
  if (!currentRole) return false;
  const roleOrder: Role[] = ['viewer', 'editor', 'admin', 'owner'];
  return roleOrder.indexOf(currentRole) >= roleOrder.indexOf(requiredRole);
}
