const DEFAULT_API_ORIGIN = 'http://localhost:8000';
const API_PREFIX = '/api';

export const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_ORIGIN)
  .replace(/\/+$/, '')
  .replace(/\/api$/, '');

const WS_ORIGIN = (
  process.env.NEXT_PUBLIC_WS_URL || API_ORIGIN.replace(/^http/, 'ws')
).replace(/\/+$/, '');

function normalizePath(path: string): string {
  return path.startsWith('/') ? path : `/${path}`;
}

export function apiUrl(path: string): string {
  const normalizedPath = normalizePath(path);
  const apiPath =
    normalizedPath === API_PREFIX || normalizedPath.startsWith(`${API_PREFIX}/`)
      ? normalizedPath
      : `${API_PREFIX}${normalizedPath}`;

  return `${API_ORIGIN}${apiPath}`;
}

export function serviceUrl(path: string): string {
  return `${API_ORIGIN}${normalizePath(path)}`;
}

export function webSocketUrl(path: string): string {
  return `${WS_ORIGIN}${normalizePath(path)}`;
}
