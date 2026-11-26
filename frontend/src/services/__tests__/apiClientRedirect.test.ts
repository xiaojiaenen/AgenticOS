/**
 * apiClient 回归：401 硬跳转必须携带原始目标（issue 7）。
 *
 * 历史故障：`window.location.assign('/login')` 不带 state / query，Login.tsx
 * 只认 ProtectedRoute 写入的 state.from —— 401 来源是硬跳转，没有 state，
 * 用户登录后丢失原本要访问的页面。
 */
import { describe, expect, it } from 'vitest';
import { buildLoginRedirectUrl } from '../apiClient';

describe('buildLoginRedirectUrl', () => {
  it('带上 pathname，编码为 from 查询参数', () => {
    expect(buildLoginRedirectUrl('/admin/users')).toBe('/login?from=%2Fadmin%2Fusers');
  });

  it('保留 search / hash 等原始路径信息', () => {
    expect(buildLoginRedirectUrl('/gallery?page=2')).toBe('/login?from=%2Fgallery%3Fpage%3D2');
  });

  it('非斜杠开头的路径自动补斜杠', () => {
    expect(buildLoginRedirectUrl('chat')).toBe('/login?from=%2Fchat');
  });

  it('根路径也能安全编码', () => {
    expect(buildLoginRedirectUrl('/')).toBe('/login?from=%2F');
  });
});
