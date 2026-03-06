'use client';

/**
 * 认证上下文 Provider
 *
 * 提供全局认证状态管理
 */

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import {
    User,
    Workspace,
    AuthState,
    login as apiLogin,
    logout as apiLogout,
    getCurrentUser,
    hasPermission as checkPermission,
    isAtLeastRole,
} from '@/lib/auth';

// ==================== 类型定义 ====================

interface AuthContextType extends AuthState {
    login: (email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    refreshUser: () => Promise<void>;
    switchWorkspace: (workspaceId: string) => void;
    hasPermission: (resource: string, action: 'read' | 'create' | 'update' | 'delete' | 'execute' | 'manage') => boolean;
    isAtLeast: (role: 'viewer' | 'editor' | 'admin' | 'owner') => boolean;
}

// ==================== Context 创建 ====================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ==================== Provider 组件 ====================

interface AuthProviderProps {
    children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
    const [state, setState] = useState<AuthState>({
        user: null,
        workspace: null,
        workspaces: [],
        isLoading: true,
        isAuthenticated: false,
    });

    // 初始化：检查当前登录状态
    useEffect(() => {
        async function initAuth() {
            const authState = await getCurrentUser();
            if (authState) {
                setState(authState);
            } else {
                setState({
                    user: null,
                    workspace: null,
                    workspaces: [],
                    isLoading: false,
                    isAuthenticated: false,
                });
            }
        }
        initAuth();
    }, []);

    // 登录
    const login = useCallback(async (email: string, password: string) => {
        setState(prev => ({ ...prev, isLoading: true }));
        try {
            const result = await apiLogin({ email, password });
            setState({
                user: result.user,
                workspace: result.workspace,
                workspaces: [], // 登录后获取
                isLoading: false,
                isAuthenticated: true,
            });
            // 获取完整的工作空间列表
            const fullState = await getCurrentUser();
            if (fullState) {
                setState(fullState);
            }
        } catch (error) {
            setState(prev => ({ ...prev, isLoading: false }));
            throw error;
        }
    }, []);

    // 登出
    const logout = useCallback(async () => {
        await apiLogout();
        setState({
            user: null,
            workspace: null,
            workspaces: [],
            isLoading: false,
            isAuthenticated: false,
        });
    }, []);

    // 刷新用户信息
    const refreshUser = useCallback(async () => {
        const authState = await getCurrentUser();
        if (authState) {
            setState(authState);
        }
    }, []);

    // 切换工作空间
    const switchWorkspace = useCallback((workspaceId: string) => {
        const workspace = state.workspaces.find(w => w.id === workspaceId);
        if (workspace) {
            setState(prev => ({ ...prev, workspace }));
            // TODO: 调用后端 API 更新当前工作空间，刷新 Token
        }
    }, [state.workspaces]);

    // 权限检查
    const hasPermission = useCallback((resource: string, action: 'read' | 'create' | 'update' | 'delete' | 'execute' | 'manage') => {
        const role = state.workspace?.role;
        return checkPermission(role, resource, action);
    }, [state.workspace?.role]);

    // 角色检查
    const isAtLeast = useCallback((role: 'viewer' | 'editor' | 'admin' | 'owner') => {
        return isAtLeastRole(state.workspace?.role, role);
    }, [state.workspace?.role]);

    const value: AuthContextType = {
        ...state,
        login,
        logout,
        refreshUser,
        switchWorkspace,
        hasPermission,
        isAtLeast,
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

// ==================== Hook ====================

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}

// ==================== 高阶组件：需要认证 ====================

export function withAuth<P extends object>(Component: React.ComponentType<P>) {
    return function AuthenticatedComponent(props: P) {
        const { isAuthenticated, isLoading } = useAuth();

        if (isLoading) {
            return (
                <div style={{
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    height: '100vh'
                }}>
                    <div>加载中...</div>
                </div>
            );
        }

        if (!isAuthenticated) {
            // 重定向到登录页
            if (typeof window !== 'undefined') {
                window.location.href = '/login';
            }
            return null;
        }

        return <Component {...props} />;
    };
}
