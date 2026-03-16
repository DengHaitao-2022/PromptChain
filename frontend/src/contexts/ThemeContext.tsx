'use client';

/**
 * 主题上下文。
 *
 * 统一维护主题偏好、系统主题跟随与本地持久化。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  DEFAULT_THEME_PREFERENCE,
  THEME_STORAGE_KEY,
  applyThemeToDocument,
  getSystemTheme,
  isThemePreference,
  persistThemePreference,
  readResolvedThemeFromDocument,
  readStoredThemePreference,
  readThemePreferenceFromDocument,
  resolveThemePreference,
  type ResolvedTheme,
  type ThemePreference,
} from '@/lib/theme';

interface ThemeContextValue {
  themePreference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setThemePreference: (preference: ThemePreference) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themePreference, setThemePreferenceState] = useState<ThemePreference>(() =>
    readThemePreferenceFromDocument(),
  );
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    readResolvedThemeFromDocument(),
  );
  const preferenceRef = useRef<ThemePreference>(themePreference);

  const syncTheme = useCallback((preference: ThemePreference) => {
    const nextResolvedTheme = resolveThemePreference(preference, getSystemTheme());

    preferenceRef.current = preference;
    setThemePreferenceState(preference);
    setResolvedTheme(nextResolvedTheme);
    applyThemeToDocument(preference, nextResolvedTheme);
  }, []);

  const setThemePreference = useCallback(
    (preference: ThemePreference) => {
      persistThemePreference(preference);
      syncTheme(preference);
    },
    [syncTheme],
  );

  const toggleTheme = useCallback(() => {
    setThemePreference(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setThemePreference]);

  useEffect(() => {
    const storedPreference = readStoredThemePreference() ?? readThemePreferenceFromDocument();
    syncTheme(storedPreference);

    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      if (preferenceRef.current !== 'system') {
        return;
      }

      const nextResolvedTheme: ResolvedTheme = event.matches ? 'dark' : 'light';
      setResolvedTheme(nextResolvedTheme);
      applyThemeToDocument('system', nextResolvedTheme);
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) {
        return;
      }

      const nextPreference = isThemePreference(event.newValue)
        ? event.newValue
        : DEFAULT_THEME_PREFERENCE;
      syncTheme(nextPreference);
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    window.addEventListener('storage', handleStorage);

    return () => {
      mediaQuery.removeEventListener('change', handleSystemThemeChange);
      window.removeEventListener('storage', handleStorage);
    };
  }, [syncTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      themePreference,
      resolvedTheme,
      setThemePreference,
      toggleTheme,
    }),
    [resolvedTheme, setThemePreference, themePreference, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }

  return context;
}
