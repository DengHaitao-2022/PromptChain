'use client';

/**
 * 控制台布局。
 *
 * 承载统一的控制台壳体、导航与权限守卫。
 */

import { ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import type { LucideIcon } from 'lucide-react';
import {
  Bot,
  ChevronRight,
  ClipboardList,
  LibraryBig,
  KeyRound,
  LayoutDashboard,
  ScrollText,
  Settings2,
  Users,
  Waypoints,
  Workflow,
} from 'lucide-react';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { ThemeSwitcher } from '@/components/ThemeSwitcher/ThemeSwitcher';
import { getAccessibleConsoleFallback, getRoleLabel } from '@/lib/auth';
import styles from './console.module.css';

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
  // 带 resource/action 的导航项会跟随当前角色权限自动显隐。
  resource?: 'workflow' | 'workflow_run' | 'member' | 'model_provider' | 'secret' | 'audit_log' | 'knowledge_base';
  action?: 'read';
};

const NAV_ITEMS: NavItem[] = [
  {
    label: '工作台',
    href: '/console',
    icon: LayoutDashboard,
    exact: true,
  },
  {
    label: '工作流',
    href: '/console/workflows',
    icon: Workflow,
    resource: 'workflow',
    action: 'read',
  },
  {
    label: '运行记录',
    href: '/console/runs',
    icon: ClipboardList,
    resource: 'workflow_run',
    action: 'read',
  },
  {
    label: '知识库',
    href: '/console/knowledge',
    icon: LibraryBig,
    resource: 'knowledge_base',
    action: 'read',
  },
  {
    label: '自主 Agent',
    href: '/console/agents',
    icon: Bot,
    resource: 'workflow_run',
    action: 'read',
  },
];

const SETTINGS_ITEMS: NavItem[] = [
  {
    label: '成员管理',
    href: '/console/settings/members',
    icon: Users,
    resource: 'member',
    action: 'read',
  },
  {
    label: '模型配置',
    href: '/console/settings/models',
    icon: Bot,
    resource: 'model_provider',
    action: 'read',
  },
  {
    label: '密钥管理',
    href: '/console/settings/keys',
    icon: KeyRound,
    resource: 'secret',
    action: 'read',
  },
  {
    label: '审计日志',
    href: '/console/settings/audit',
    icon: ScrollText,
    resource: 'audit_log',
    action: 'read',
  },
];

function isVisible(
  item: NavItem,
  hasPermission: (resource: NonNullable<NavItem['resource']>, action: 'read') => boolean,
) {
  // 未声明权限的入口默认可见，例如控制台首页和设置总览。
  if (!item.resource || !item.action) {
    return true;
  }

  return hasPermission(item.resource, item.action);
}

function Sidebar({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { hasPermission } = useAuth();
  const visibleNavItems = NAV_ITEMS.filter((item) => isVisible(item, hasPermission));
  const visibleManagedSettingsItems = SETTINGS_ITEMS.filter((item) => isVisible(item, hasPermission));
  const visibleSettingsItems =
    visibleManagedSettingsItems.length > 0
      ? [
          {
            label: '设置总览',
            href: '/console/settings',
            icon: Settings2,
            exact: true,
          },
          ...visibleManagedSettingsItems,
        ]
      : [];
  // 当前位于设置页时默认展开分组，避免用户丢失所在位置。
  const [settingsOpen, setSettingsOpen] = useState(pathname.startsWith('/console/settings'));

  useEffect(() => {
    if (pathname.startsWith('/console/settings')) {
      setSettingsOpen(true);
    }
  }, [pathname]);

  // 移动端导航完成后自动收起侧栏，减少页面跳转后的遮挡。
  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  function isActive(href: string, exact?: boolean) {
    if (exact) {
      return pathname === href;
    }

    return pathname.startsWith(href);
  }

  const settingsActive = pathname.startsWith('/console/settings');

  return (
    <>
      <div
        className={`${styles.backdrop} ${isOpen ? styles.backdropOpen : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className={`${styles.sidebar} ${isOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.sidebarHeader}>
          <Link href="/console" className={styles.logoLink} onClick={onClose}>
            <span className={styles.logoBadge} aria-hidden="true">
              <Waypoints size={18} strokeWidth={2} />
            </span>
            <span className={styles.logoCopy}>
              <span className={styles.logoText}>PromptChain</span>
              <span className={styles.logoSubtext}>Control Surface</span>
            </span>
          </Link>
        </div>

        <nav className={styles.nav}>
          <div className={styles.navSection}>
            <span className={styles.sectionLabel}>工作台</span>
            {visibleNavItems.map((item) => {
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navItem} ${isActive(item.href, item.exact) ? styles.active : ''}`}
                  title={item.label}
                >
                  <span className={styles.navIcon} aria-hidden="true">
                    <Icon size={18} strokeWidth={1.9} />
                  </span>
                  <span className={styles.navLabel}>{item.label}</span>
                </Link>
              );
            })}
          </div>

          {visibleSettingsItems.length > 0 && (
            <div className={styles.navSection}>
              <span className={styles.sectionLabel}>系统设置</span>

              <button
                className={`${styles.navItem} ${styles.navGroup} ${settingsActive ? styles.active : ''}`}
                onClick={() => setSettingsOpen((open) => !open)}
                type="button"
                aria-expanded={settingsOpen}
                title="设置"
              >
                <span className={styles.navIcon} aria-hidden="true">
                  <Settings2 size={18} strokeWidth={1.9} />
                </span>
                <span className={styles.navLabel}>设置</span>
                <ChevronRight
                  size={16}
                  strokeWidth={2}
                  className={`${styles.arrow} ${settingsOpen ? styles.arrowOpen : ''}`}
                  aria-hidden="true"
                />
              </button>

              {settingsOpen && (
                <div className={styles.subNav}>
                  {visibleSettingsItems.map((item) => {
                    const Icon = item.icon;

                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={`${styles.navItem} ${styles.subNavItem} ${
                          isActive(item.href, item.exact) ? styles.active : ''
                        }`}
                        title={item.label}
                      >
                        <span className={styles.navIcon} aria-hidden="true">
                          <Icon size={16} strokeWidth={1.9} />
                        </span>
                        <span className={styles.navLabel}>{item.label}</span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </nav>

        <div className={styles.sidebarFooter}>
          <ThemeSwitcher iconOnly className={styles.sidebarThemeToggle} />
        </div>
      </aside>
    </>
  );
}

function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const router = useRouter();
  const { user, workspace, workspaces, role, logout, switchWorkspace } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  async function handleWorkspaceChange(workspaceId: string) {
    if (!workspaceId) {
      return;
    }

    // 切换工作空间会刷新服务端 Cookie 中的 workspace 上下文。
    setSwitching(true);
    try {
      await switchWorkspace(workspaceId);
    } catch (error) {
      const message = error instanceof Error ? error.message : '切换工作空间失败';
      window.alert(message);
    } finally {
      setSwitching(false);
    }
  }

  async function handleLogout() {
    await logout();
    router.replace('/login');
  }

  return (
    <header className={styles.topbar}>
      <div className={styles.topbarCopy}>
        <span className={styles.topbarEyebrow}>控制台</span>
        <p className={styles.topbarHint}>{workspace?.name || '选择工作空间以继续浏览运行态数据'}</p>
      </div>

      <div className={styles.topbarActions}>
        <div className={styles.workspaceSelector}>
          <select
            value={workspace?.id || ''}
            onChange={(event) => void handleWorkspaceChange(event.target.value)}
            className={styles.workspaceSelect}
            disabled={switching}
          >
            {workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.userMenu}>
          <button className={styles.userButton} onClick={() => setDropdownOpen((open) => !open)} type="button">
            <span className={styles.avatar}>{user?.display_name?.[0] || user?.email?.[0] || '?'}</span>
            <span className={styles.userMeta}>
              <span className={styles.userName}>{user?.display_name || user?.email}</span>
              <span className={styles.userRole}>{getRoleLabel(role)}</span>
            </span>
          </button>

          {dropdownOpen && (
            <div className={styles.dropdown}>
              <div className={styles.dropdownHeader}>
                <div>{user?.display_name || user?.email}</div>
                <div className={styles.dropdownEmail}>{user?.email}</div>
                <div className={styles.dropdownRole}>{getRoleLabel(role)}</div>
              </div>
              <div className={styles.dropdownDivider} />
              <button className={styles.dropdownItem} onClick={() => void handleLogout()} type="button">
                退出登录
              </button>
            </div>
          )}
        </div>

        <button className={styles.menuButton} onClick={onMenuClick} aria-label="Toggle menu" type="button">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ pointerEvents: 'none' }}><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>
        </button>
      </div>
    </header>
  );
}

function ConsoleContent({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { isLoading, isAuthenticated, role, workspace, hasWorkspaceAccess, canAccessConsolePath } = useAuth();
  const hasPageAccess = canAccessConsolePath(pathname);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (isLoading) {
      return;
    }

    // 守卫顺序必须从认证到工作空间再到页面权限，避免暴露无权页面内容。
    if (!isAuthenticated) {
      router.replace('/login');
      return;
    }

    if (!hasWorkspaceAccess) {
      if (pathname !== '/console') {
        router.replace('/console');
      }
      return;
    }

    if (!hasPageAccess) {
      router.replace(getAccessibleConsoleFallback(role));
    }
  }, [hasPageAccess, hasWorkspaceAccess, isAuthenticated, isLoading, pathname, role, router]);

  if (isLoading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
        <p>加载中...</p>
      </div>
    );
  }

  if (!isAuthenticated || (hasWorkspaceAccess && !hasPageAccess)) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
        <p>正在校验访问权限...</p>
      </div>
    );
  }

  return (
    <div className={styles.layout}>
      <Sidebar isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />
      <div className={styles.main}>
        <TopBar onMenuClick={() => setIsMobileMenuOpen(true)} />
        <main className={styles.content}>
          {!hasWorkspaceAccess && pathname === '/console' ? (
            <div className={styles.loading}>
              <div className={styles.spinner} />
              <p>{workspace ? '正在同步工作空间权限...' : '当前暂无可访问的工作空间'}</p>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}

export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    // 控制台独立挂载认证上下文，公开页面无需承担登录态初始化成本。
    <AuthProvider>
      <ConsoleContent>{children}</ConsoleContent>
    </AuthProvider>
  );
}
