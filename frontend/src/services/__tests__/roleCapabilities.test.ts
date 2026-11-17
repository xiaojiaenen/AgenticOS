/**
 * 前端能力判断（角色不再硬编码）。
 *
 * 角色定义在**后端** `app/core/roles.py` 一张表里，前端只按 `/auth/me` 下发的
 * `capabilities` 判断。这样加角色（如审计员/运营/超级管理员）不用改前端。
 *
 * 这里锁住三件事：
 * 1. 能力位驱动：有 `user:manage` 才进得了后台管理
 * 2. 运营/审计能进后台（他们有内容/审计类能力）
 * 3. 老缓存兜底：`capabilities` 缺失时按角色名判断，不让升级把人挡在门外
 */
import { describe, expect, it, beforeEach } from 'vitest';

import {
  canEnterAdmin,
  clearAuthSession,
  hasCapability,
  isAdmin,
  setAuthSession,
} from '@/services/authTokenStore';

const makeUser = (role: string, capabilities?: string[]) => ({
  id: 1,
  email: 'a@b.com',
  name: 'T',
  role,
  is_active: true,
  ...(capabilities ? { capabilities } : {}),
});

const loginAs = (role: string, capabilities?: string[]) =>
  setAuthSession({ access_token: 'tok', user: makeUser(role, capabilities) as never });

describe('前端角色能力判断', () => {
  beforeEach(() => {
    clearAuthSession();
    localStorage.clear();
  });

  it('admin 能进后台且是 admin', () => {
    loginAs('admin', ['agent:use', 'agent:manage', 'user:manage', 'system:settings']);
    expect(isAdmin()).toBe(true);
    expect(canEnterAdmin()).toBe(true);
    expect(hasCapability('user:manage')).toBe(true);
  });

  it('运营能进后台但不是 admin（用户管理进不去）', () => {
    loginAs('operator', ['agent:use', 'agent:manage', 'announcement:manage']);
    expect(canEnterAdmin()).toBe(true);
    expect(isAdmin()).toBe(false);
    expect(hasCapability('user:manage')).toBe(false);
  });

  it('审计员只看统计：能进后台，不能管任何东西', () => {
    loginAs('auditor', ['agent:use', 'audit:view']);
    expect(canEnterAdmin()).toBe(true);
    expect(hasCapability('audit:view')).toBe(true);
    expect(hasCapability('agent:manage')).toBe(false);
  });

  it('普通用户进不了后台', () => {
    loginAs('user', ['agent:use', 'conversation:own']);
    expect(canEnterAdmin()).toBe(false);
    expect(isAdmin()).toBe(false);
  });

  it('超级管理员拥有代查对话能力，admin 没有', () => {
    loginAs('superadmin', ['agent:use', 'user:manage', 'conversation:read_any']);
    expect(hasCapability('conversation:read_any')).toBe(true);

    loginAs('admin', ['agent:use', 'user:manage']);
    expect(hasCapability('conversation:read_any')).toBe(false);
  });

  it('老缓存（没有 capabilities）按角色名兜底，不会把人挡在门外', () => {
    loginAs('admin'); // 不传 capabilities
    expect(isAdmin()).toBe(true);
    expect(canEnterAdmin()).toBe(true);

    loginAs('user');
    expect(canEnterAdmin()).toBe(false);
  });

  it('未登录时一切为 false', () => {
    expect(isAdmin()).toBe(false);
    expect(canEnterAdmin()).toBe(false);
    expect(hasCapability('agent:use')).toBe(false);
  });
});
