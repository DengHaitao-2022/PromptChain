'use client';

/**
 * 控制台布局
 *
 * 包含侧边栏导航和顶部用户信息
 */

import { ReactNode, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import styles from './console.module.css';

// 导航菜单项
const NAV_ITEMS = [
    {
        label: '工作台',
        href: '/console',
        icon: '📊',
        exact: true,
    },
    {
        label: '工作流',
        href: '/console/workflows',
        icon: '⚡',
    },
    {
        label: '运行记录',
        href: '/console/runs',
        icon: '📋',
    },
];

const SETTINGS_ITEMS = [
    {
        label: '成员管理',
        href: '/console/settings/members',
        icon: '👥',
    },
    {
        label: '模型配置',
        href: '/console/settings/models',
        icon: '🤖',
    },
    {
        label: '密钥管理',
        href: '/console/settings/keys',
        icon: '🔑',
    },
    {
        label: '审计日志',
        href: '/console/settings/audit',
        icon: '📜',
    },
];

// 侧边栏组件
function Sidebar() {
    const pathname = usePathname();
    const [settingsOpen, setSettingsOpen] = useState(pathname.startsWith('/console/settings'));

    function isActive(href: string, exact?: boolean) {
        if (exact) {
            return pathname === href;
        }
        return pathname.startsWith(href);
    }

    return (
        <aside className={styles.sidebar}>
            <div className={styles.logo}>
                <Link href="/console">
                    <span className={styles.logoText}>PromptChain</span>
                </Link>
            </div>

            <nav className={styles.nav}>
                <div className={styles.navSection}>
                    {NAV_ITEMS.map((item) => (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`${styles.navItem} ${isActive(item.href, item.exact) ? styles.active : ''}`}
                        >
                            <span className={styles.navIcon}>{item.icon}</span>
                            <span className={styles.navLabel}>{item.label}</span>
                        </Link>
                    ))}
                </div>

                <div className={styles.navSection}>
                    <button
                        className={`${styles.navItem} ${styles.navGroup}`}
                        onClick={() => setSettingsOpen(!settingsOpen)}
                    >
                        <span className={styles.navIcon}>⚙️</span>
                        <span className={styles.navLabel}>设置</span>
                        <span className={`${styles.arrow} ${settingsOpen ? styles.arrowOpen : ''}`}>›</span>
                    </button>

                    {settingsOpen && (
                        <div className={styles.subNav}>
                            {SETTINGS_ITEMS.map((item) => (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className={`${styles.navItem} ${styles.subNavItem} ${isActive(item.href) ? styles.active : ''}`}
                                >
                                    <span className={styles.navIcon}>{item.icon}</span>
                                    <span className={styles.navLabel}>{item.label}</span>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>
            </nav>
        </aside>
    );
}

// 顶部栏组件
function TopBar() {
    const { user, workspace, workspaces, logout, switchWorkspace } = useAuth();
    const [dropdownOpen, setDropdownOpen] = useState(false);

    return (
        <header className={styles.topbar}>
            <div className={styles.workspaceSelector}>
                <select
                    value={workspace?.id || ''}
                    onChange={(e) => switchWorkspace(e.target.value)}
                    className={styles.workspaceSelect}
                >
                    {workspaces.map((ws) => (
                        <option key={ws.id} value={ws.id}>
                            {ws.name}
                        </option>
                    ))}
                </select>
            </div>

            <div className={styles.userMenu}>
                <button
                    className={styles.userButton}
                    onClick={() => setDropdownOpen(!dropdownOpen)}
                >
                    <span className={styles.avatar}>
                        {user?.display_name?.[0] || user?.email?.[0] || '?'}
                    </span>
                    <span className={styles.userName}>{user?.display_name || user?.email}</span>
                </button>

                {dropdownOpen && (
                    <div className={styles.dropdown}>
                        <div className={styles.dropdownHeader}>
                            <div>{user?.display_name || user?.email}</div>
                            <div className={styles.dropdownEmail}>{user?.email}</div>
                            <div className={styles.dropdownRole}>
                                {workspace?.role === 'owner' ? '拥有者' :
                                    workspace?.role === 'admin' ? '管理员' :
                                        workspace?.role === 'editor' ? '编辑者' : '查看者'}
                            </div>
                        </div>
                        <div className={styles.dropdownDivider} />
                        <button
                            className={styles.dropdownItem}
                            onClick={() => {
                                logout();
                                window.location.href = '/login';
                            }}
                        >
                            退出登录
                        </button>
                    </div>
                )}
            </div>
        </header>
    );
}

// 布局内容（需要认证状态）
function ConsoleContent({ children }: { children: ReactNode }) {
    const { isLoading, isAuthenticated } = useAuth();

    if (isLoading) {
        return (
            <div className={styles.loading}>
                <div className={styles.spinner} />
                <p>加载中...</p>
            </div>
        );
    }

    if (!isAuthenticated) {
        if (typeof window !== 'undefined') {
            window.location.href = '/login';
        }
        return null;
    }

    return (
        <div className={styles.layout}>
            <Sidebar />
            <div className={styles.main}>
                <TopBar />
                <main className={styles.content}>
                    {children}
                </main>
            </div>
        </div>
    );
}

// 导出布局组件
export default function ConsoleLayout({ children }: { children: ReactNode }) {
    return (
        <AuthProvider>
            <ConsoleContent>{children}</ConsoleContent>
        </AuthProvider>
    );
}
