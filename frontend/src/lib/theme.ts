export const THEME_STORAGE_KEY = 'promptchain-theme-preference';

export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

export const DEFAULT_THEME_PREFERENCE: ThemePreference = 'system';
export const DEFAULT_RESOLVED_THEME: ResolvedTheme = 'dark';

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark';
}

export function isResolvedTheme(value: unknown): value is ResolvedTheme {
  return value === 'light' || value === 'dark';
}

export function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return DEFAULT_RESOLVED_THEME;
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function resolveThemePreference(
  preference: ThemePreference,
  systemTheme: ResolvedTheme = getSystemTheme(),
): ResolvedTheme {
  return preference === 'system' ? systemTheme : preference;
}

export function readStoredThemePreference(): ThemePreference | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function persistThemePreference(preference: ThemePreference) {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // 本地持久化失败时静默降级到内存态。
  }
}

export function applyThemeToDocument(
  preference: ThemePreference,
  resolvedTheme: ResolvedTheme,
) {
  if (typeof document === 'undefined') {
    return;
  }

  const root = document.documentElement;
  root.dataset.themePreference = preference;
  root.dataset.theme = resolvedTheme;
  root.style.colorScheme = resolvedTheme;
}

export function readThemePreferenceFromDocument(): ThemePreference {
  if (typeof document === 'undefined') {
    return DEFAULT_THEME_PREFERENCE;
  }

  const value = document.documentElement.dataset.themePreference;
  return isThemePreference(value) ? value : DEFAULT_THEME_PREFERENCE;
}

export function readResolvedThemeFromDocument(): ResolvedTheme {
  if (typeof document === 'undefined') {
    return DEFAULT_RESOLVED_THEME;
  }

  const value = document.documentElement.dataset.theme;
  return isResolvedTheme(value) ? value : DEFAULT_RESOLVED_THEME;
}

export function buildThemeInitScript() {
  return `(() => {
    const storageKey = ${JSON.stringify(THEME_STORAGE_KEY)};
    const defaultPreference = ${JSON.stringify(DEFAULT_THEME_PREFERENCE)};
    const defaultTheme = ${JSON.stringify(DEFAULT_RESOLVED_THEME)};
    const root = document.documentElement;
    const getSystemTheme = () => {
      if (!window.matchMedia) {
        return defaultTheme;
      }
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    };

    try {
      const stored = window.localStorage.getItem(storageKey);
      const preference = stored === 'light' || stored === 'dark' || stored === 'system'
        ? stored
        : defaultPreference;
      const resolvedTheme = preference === 'system' ? getSystemTheme() : preference;

      root.dataset.themePreference = preference;
      root.dataset.theme = resolvedTheme;
      root.style.colorScheme = resolvedTheme;
    } catch (error) {
      const resolvedTheme = getSystemTheme();
      root.dataset.themePreference = defaultPreference;
      root.dataset.theme = resolvedTheme;
      root.style.colorScheme = resolvedTheme;
    }
  })();`;
}
