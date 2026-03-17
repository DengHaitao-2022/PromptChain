'use client';

import type { HTMLAttributes } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import type { ThemePreference } from '@/lib/theme';
import styles from './ThemeSwitcher.module.css';

type ThemeOption = {
  value: ThemePreference;
  label: string;
  ariaLabel: string;
  icon: typeof Monitor;
};

const THEME_OPTIONS: ThemeOption[] = [
  {
    value: 'system',
    label: '系统',
    ariaLabel: '跟随系统主题',
    icon: Monitor,
  },
  {
    value: 'light',
    label: '浅色',
    ariaLabel: '切换到浅色主题',
    icon: Sun,
  },
  {
    value: 'dark',
    label: '深色',
    ariaLabel: '切换到深色主题',
    icon: Moon,
  },
];

function getResolvedThemeLabel(resolvedTheme: 'light' | 'dark') {
  return resolvedTheme === 'light' ? '浅色生效' : '深色生效';
}

export function ThemeSwitcher({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  const { themePreference, resolvedTheme, setThemePreference } = useTheme();
  const rootClassName = className ? `${styles.root} ${className}` : styles.root;

  return (
    <div className={rootClassName} {...props}>
      <span className={styles.status}>
        {themePreference === 'system' ? `系统 · ${getResolvedThemeLabel(resolvedTheme)}` : getResolvedThemeLabel(resolvedTheme)}
      </span>

      <div className={styles.segment} role="group" aria-label="主题切换">
        {THEME_OPTIONS.map((option) => {
          const Icon = option.icon;
          const isActive = themePreference === option.value;

          return (
            <button
              key={option.value}
              type="button"
              className={styles.button}
              data-active={isActive}
              aria-pressed={isActive}
              aria-label={option.ariaLabel}
              title={option.ariaLabel}
              onClick={() => setThemePreference(option.value)}
            >
              <Icon size={14} strokeWidth={1.9} aria-hidden="true" />
              <span className={styles.label}>{option.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
