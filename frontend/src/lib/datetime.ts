const API_DATE_WITHOUT_TIMEZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

export function parseApiDate(value?: string | null): Date | null {
  if (!value) return null;
  const normalized = API_DATE_WITHOUT_TIMEZONE.test(value) ? `${value}Z` : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatApiDate(value?: string | null): string {
  const date = parseApiDate(value);
  if (!date) return '-';
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

export function formatApiDateTime(value?: string | null): string {
  const date = parseApiDate(value);
  if (!date) return '-';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
