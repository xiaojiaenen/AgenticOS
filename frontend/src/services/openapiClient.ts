/**
 * OpenAPI 类型化客户端试点（战线 B/D 7.1 / 优化方案 2.2）。
 *
 * 用 openapi-fetch + 生成的 `api-schema.ts` 做端到端类型对齐：URL 拼写错、
 * 参数类型错在编译期就报，而不是运行时 404/422。试点挂在**新模块**
 * （tasks 运维台）—— 老的 27 个手写 service 按既有约定渐进迁移，不一次性全换。
 *
 * 鉴权沿用全局 fetch 包装之外的方式：openapi-fetch 接受自定义 fetch，
 * 这里包一层注入 authHeaders（与 apiClient 的鉴权源一致）。
 */
import createClient, { type Middleware } from 'openapi-fetch';
import type { paths } from '../types/api-schema';
import { authHeaders } from './authService';

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const headers = authHeaders();
    for (const [k, v] of Object.entries(headers)) {
      request.headers.set(k, v);
    }
    return request;
  },
};

export const apiV1 = createClient<paths>({
  baseUrl: '',
  fetch: globalThis.fetch.bind(globalThis),
});

apiV1.use(authMiddleware);

/** 统一解包：openapi-fetch 返回 {data, error}，业务层只要 data（出错抛 Error）。 */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown }>,
  label: string,
): Promise<T> {
  const { data, error } = await promise;
  if (error !== undefined && error !== null) {
    const detail =
      typeof error === 'string'
        ? error
        : ((error as { detail?: string }).detail ?? JSON.stringify(error).slice(0, 200));
    throw new Error(`${label}: ${detail}`);
  }
  if (data === undefined) throw new Error(`${label}: 空响应`);
  return data;
}
