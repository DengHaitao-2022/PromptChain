const APP_LOCALE = 'zh-CN';
const APP_TIME_ZONE = 'Asia/Shanghai';

type DateInput = string | number | Date | null | undefined;

export function parseAppDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatAppDateTime(value: DateInput, fallback = '暂无记录'): string {
  const date = parseAppDate(value);
  if (!date) {
    return fallback;
  }

  return new Intl.DateTimeFormat(APP_LOCALE, {
    timeZone: APP_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatAppDate(value: DateInput, fallback = '暂无记录'): string {
  const date = parseAppDate(value);
  if (!date) {
    return fallback;
  }

  return new Intl.DateTimeFormat(APP_LOCALE, {
    timeZone: APP_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

export function formatCompactAppDateTime(value: DateInput, fallback = '暂无记录'): string {
  const date = parseAppDate(value);
  if (!date) {
    return fallback;
  }

  return new Intl.DateTimeFormat(APP_LOCALE, {
    timeZone: APP_TIME_ZONE,
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatAppTime(value: DateInput, fallback = '暂无记录'): string {
  const date = parseAppDate(value);
  if (!date) {
    return fallback;
  }

  return new Intl.DateTimeFormat(APP_LOCALE, {
    timeZone: APP_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
}

export function toUtcIsoString(value: DateInput): string | undefined {
  const date = parseAppDate(value);
  return date?.toISOString();
}

export function toEpochMilliseconds(value: DateInput): number | undefined {
  const date = parseAppDate(value);
  return date?.getTime();
}

export function appDateTimeInputToUtcIsoString(value: string): string | undefined {
  if (!value) {
    return undefined;
  }

  const normalized = value.length === 16 ? `${value}:00` : value;
  return toUtcIsoString(`${normalized}+08:00`);
}
