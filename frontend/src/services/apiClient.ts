import { authHeaders } from './authService';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function apiFetch<T>(
  url: string,
  options?: RequestInit,
  errorMessage?: string,
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options?.headers || {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    let msg = errorMessage || `请求失败 (${response.status})`;
    try {
      const err = JSON.parse(detail);
      if (err.detail) msg = typeof err.detail === 'string' ? err.detail : err.detail.message || msg;
    } catch {
      if (detail) msg = detail;
    }
    throw new Error(msg);
  }
  return response.json();
}
