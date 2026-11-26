/**
 * apiFetchPaged 超时归一化回归（issue 10）。
 *
 * 历史故障：分页版直接用 controller.abort() 做超时，catch 里没有 timedOut 标记，
 * 超时抛给调用方的是裸 AbortError —— 前端面板当成「用户主动取消」静默吞掉，
 * 用户看不到任何超时提示（apiFetch 早已做了归一化，分页版漏了）。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { ApiError, apiFetchPaged } from '../apiClient';

describe('apiFetchPaged 超时归一化', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    });
    // 超时的 fetch 永不 resolve，直到我们自己的 timer abort signal
    vi.stubGlobal('fetch', vi.fn((_url: string, init: { signal: AbortSignal }) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      }),
    ));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('超时包装成 ApiError(status=0)，而不是裸 AbortError', async () => {
    await expect(
      apiFetchPaged('/api/items', { timeoutMs: 10 }),
    ).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
    } as Partial<ApiError>);
  });

  it('超时错误消息对用户可读（含「超时」）', async () => {
    await expect(
      apiFetchPaged('/api/items', { timeoutMs: 10 }),
    ).rejects.toThrow(/超时/);
  });

  it('调用方主动取消仍保持 AbortError 语义（不误判为超时）', async () => {
    const external = new AbortController();
    const promise = apiFetchPaged('/api/items', { timeoutMs: 10_000, signal: external.signal });
    // 等 fetch 被调用后再取消
    await new Promise((r) => setTimeout(r, 0));
    external.abort();
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
  });
});
