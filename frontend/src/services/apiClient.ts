import { authHeaders, clearAuthSession } from './authTokenStore';
import { localizeError } from '../lib/errors';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

/** 统一 API 错误：status（0 = 网络/超时）、detail（原始错误负载）、message（面向用户的信息） */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export const DEFAULT_TIMEOUT_MS = 30_000;

export type ApiFetchOptions = RequestInit & {
  /** 超时毫秒数（AbortSignal 实现），默认 30s；传 0 或 Infinity 可禁用 */
  timeoutMs?: number;
  /** 响应解析方式，默认 json */
  responseType?: 'json' | 'text' | 'blob';
  /** 为 true 时不触发 401 全局处理（清 token + 跳 /login），供登录/注册等端点使用 */
  skip401?: boolean;
};

function parseErrorPayload(raw: string): string | null {
  if (!raw) return null;
  try {
    const payload = JSON.parse(raw);
    if (typeof payload?.detail === 'string') return payload.detail;
    if (typeof payload?.detail?.message === 'string') return payload.detail.message;
  } catch {
    if (raw) return raw;
  }
  return null;
}

let redirectingToLogin = false;

function handleUnauthorized(): void {
  clearAuthSession();
  const { pathname } = window.location;
  if (!redirectingToLogin && pathname !== '/login' && pathname !== '/signup') {
    redirectingToLogin = true;
    window.location.assign('/login');
  }
}

function combineSignals(
  external: AbortSignal | null | undefined,
  controller: AbortController,
): void {
  if (!external) return;
  if (external.aborted) {
    controller.abort();
    return;
  }
  external.addEventListener('abort', () => controller.abort(), { once: true });
}

/**
 * 统一 fetch 实例：
 *  - 自动注入 Authorization header（读 authService 的 token 存储）
 *  - 统一超时（AbortSignal，默认 30s，可传 timeoutMs 覆盖）
 *  - 401 统一处理（清 token + 跳 /login；可用 skip401 关闭）
 *  - 错误归一化为 ApiError{status, detail, message}
 */
export async function apiFetch<T>(
  url: string,
  options: ApiFetchOptions = {},
  errorMessage?: string,
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, responseType = 'json', skip401, ...init } = options;

  const controller = new AbortController();
  combineSignals(init.signal, controller);

  let timedOut = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  if (timeoutMs !== 0 && timeoutMs !== Infinity) {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
  }

  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: {
        ...authHeaders(),
        ...(init.headers || {}),
      },
    });

    if (response.status === 401 && !skip401) {
      const raw = await response.text().catch(() => '');
      const detail = parseErrorPayload(raw);
      if (!skip401) handleUnauthorized();
      throw new ApiError(
        401,
        detail ?? (raw || null),
        localizeError(detail, errorMessage || '登录已过期，请重新登录'),
      );
    }

    if (!response.ok) {
      const raw = await response.text().catch(() => '');
      const detail = parseErrorPayload(raw);
      throw new ApiError(
        response.status,
        detail ?? (raw || null),
        localizeError(detail, errorMessage || '操作失败，请稍后重试'),
      );
    }

    if (responseType === 'text') return (await response.text()) as unknown as T;
    if (responseType === 'blob') return (await response.blob()) as unknown as T;
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      if (timedOut) {
        throw new ApiError(0, null, `请求超时（${Math.round(timeoutMs / 1000)} 秒），请稍后重试`);
      }
      throw err; // 调用方主动取消，保持 AbortError 语义
    }
    // 网络层错误（断网 / DNS / CORS）
    throw new ApiError(0, err, err instanceof Error ? err.message : '网络请求失败');
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/** 向后兼容导出：旧调用方继续使用 apiFetch 签名 */
export { apiFetch as default };
