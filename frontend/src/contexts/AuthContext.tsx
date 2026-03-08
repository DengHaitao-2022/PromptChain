'use client';

/**
 * 认证上下文 Provider
 *
 * 统一维护当前登录用户、工作空间和权限判断。
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
  Dispatch,
  SetStateAction,
  startTransition,
} from 'react';
import {
  AuthState,
  Role,
  Action,
  Resource,
  getCurrentUser,
  login as apiLogin,
  logout as apiLogout,
  switchWorkspace as apiSwitchWorkspace,
  hasPermission as checkPermission,
  isAtLeastRole,
  canAccessConsolePath as checkConsolePathAccess,
} from '@/lib/auth';

const EMPTY_AUTH_STATE: AuthState = {
  user: null,
  workspace: null,
  workspaces: [],
  role: null,
  isLoading: false,
  isAuthenticated: false,
};

interface AuthContextType extends AuthState {
  hasWorkspaceAccess: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  hasPermission: (resource: Resource, action: Action) => boolean;
  isAtLeast: (role: Role) => boolean;
  canAccessConsolePath: (pathname: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

function applyAuthState(
  setState: Dispatch<SetStateAction<AuthState>>,
  authState: AuthState | null,
) {
  startTransition(() => {
    setState(authState ?? EMPTY_AUTH_STATE);
  });
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [state, setState] = useState<AuthState>({
    ...EMPTY_AUTH_STATE,
    isLoading: true,
  });

  const refreshUser = useCallback(async () => {
    const authState = await getCurrentUser();
    applyAuthState(setState, authState);
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      setState((prev) => ({ ...prev, isLoading: true }));
      try {
        await apiLogin({ email, password });
        await refreshUser();
      } catch (error) {
        setState((prev) => ({ ...prev, isLoading: false }));
        throw error;
      }
    },
    [refreshUser],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    applyAuthState(setState, null);
  }, []);

  const switchWorkspace = useCallback(
    async (workspaceId: string) => {
      if (workspaceId === state.workspace?.id) {
        return;
      }

      setState((prev) => ({ ...prev, isLoading: true }));
      try {
        await apiSwitchWorkspace(workspaceId);
        await refreshUser();
      } catch (error) {
        setState((prev) => ({ ...prev, isLoading: false }));
        throw error;
      }
    },
    [refreshUser, state.workspace?.id],
  );

  const hasPermission = useCallback(
    (resource: Resource, action: Action) => checkPermission(state.role, resource, action),
    [state.role],
  );

  const isAtLeast = useCallback(
    (role: Role) => isAtLeastRole(state.role, role),
    [state.role],
  );

  const canAccessConsolePath = useCallback(
    (pathname: string) => checkConsolePathAccess(state.role, pathname),
    [state.role],
  );

  const value: AuthContextType = {
    ...state,
    hasWorkspaceAccess: Boolean(state.workspace && state.role),
    login,
    logout,
    refreshUser,
    switchWorkspace,
    hasPermission,
    isAtLeast,
    canAccessConsolePath,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function withAuth<P extends object>(Component: React.ComponentType<P>) {
  return function AuthenticatedComponent(props: P) {
    const { isAuthenticated, isLoading } = useAuth();

    if (isLoading) {
      return (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
          }}
        >
          <div>加载中...</div>
        </div>
      );
    }

    if (!isAuthenticated) {
      if (typeof window !== 'undefined') {
        window.location.replace('/login');
      }
      return null;
    }

    return <Component {...props} />;
  };
}
