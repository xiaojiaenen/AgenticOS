import { AuthUser } from '../types';

/**
 * Token / 用户会话的底层存储（localStorage 优先，兼容迁移旧 sessionStorage 数据）。
 * 独立成模块以避免 authService ↔ apiClient 循环依赖。
 *
 * 所有存储访问都包 try/catch：Safari 隐私模式 / 沙箱 iframe / 存储被禁用时
 * getItem 会抛 SecurityError，不容错会导致 ProtectedRoute、useTheme 等
 * 渲染期直接崩溃白屏。
 */

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';
const ROLE_KEY = 'role';

function safeGetItem(store: Storage, key: string): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(store: Storage, key: string, value: string): void {
  try {
    store.setItem(key, value);
  } catch {
    /* 存储不可写时静默降级：会话仅保留在内存中 */
  }
}

function safeRemoveItem(store: Storage, key: string): void {
  try {
    store.removeItem(key);
  } catch {
    /* ignore */
  }
}

function readStorageValue(key: string): string | null {
  // token/user 持久化到 localStorage，支持新标签页共享登录态
  const localValue = safeGetItem(localStorage, key);
  if (localValue) return localValue;

  // 迁移旧的 sessionStorage 数据
  const legacyValue = safeGetItem(sessionStorage, key);
  if (!legacyValue) return null;
  safeSetItem(localStorage, key, legacyValue);
  safeRemoveItem(sessionStorage, key);
  return legacyValue;
}

function writeStorageValue(key: string, value: string): void {
  safeSetItem(localStorage, key, value);
  safeRemoveItem(sessionStorage, key);
}

function removeStorageValue(key: string): void {
  safeRemoveItem(localStorage, key);
  safeRemoveItem(sessionStorage, key);
}

function readJson<T>(value: string | null): T | null {
  if (!value) return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

export function getAuthToken(): string | null {
  return readStorageValue(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  return readJson<AuthUser>(readStorageValue(USER_KEY));
}

export function isAuthenticated(): boolean {
  return Boolean(getAuthToken() && getStoredUser());
}

/**
 * 是否有「完整平台管理」权限（admin / superadmin）。
 *
 * 以服务端下发的 `capabilities` 为准 —— 角色定义在**后端** `app/core/roles.py`
 * 一张表里，前端不硬编码角色名，新增角色不用改前端。
 *
 * 兼容旧缓存：`/auth/me` 之前存下的 user 没有 capabilities 字段，
 * 这时退回按角色名判断，避免用户升级后瞬间失去后台入口。
 */
export function isAdmin(): boolean {
  return hasCapability('user:manage');
}

/** 是否**能进后台页面**（运营/审计也能进，各自只看自己的面板）。 */
export function canEnterAdmin(): boolean {
  const user = getStoredUser();
  if (!user) return false;
  if (user.capabilities?.length) {
    // 任意一项管理类能力即可（后端 can_enter_admin 的同口径：非 agent:use）
    return user.capabilities.some(
      (cap) => cap !== 'agent:use' && cap !== 'conversation:own',
    );
  }
  return user.role === 'admin' || user.role === 'superadmin';
}

/** 是否拥有某个能力（能力位见后端 app/core/roles.py）。 */
export function hasCapability(capability: string): boolean {
  const user = getStoredUser();
  if (!user) return false;
  if (user.capabilities?.length) return user.capabilities.includes(capability);
  // 旧缓存兜底：那时只有 admin/user 两种角色，把 admin 视作拥有全部能力
  return user.role === 'admin' || user.role === 'superadmin';
}

export function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function setAuthSession(response: { access_token: string; user: AuthUser }): void {
  writeStorageValue(TOKEN_KEY, response.access_token);
  writeStorageValue(USER_KEY, JSON.stringify(response.user));
  writeStorageValue(ROLE_KEY, response.user.role);
}

/** 仅更新本地缓存的用户信息（如 /me 刷新角色后） */
export function updateStoredUser(user: AuthUser): void {
  writeStorageValue(USER_KEY, JSON.stringify(user));
  writeStorageValue(ROLE_KEY, user.role);
}

export function clearAuthSession(): void {
  // 清理当前用户的会话缓存
  const user = getStoredUser();
  if (user) {
    safeRemoveItem(localStorage, `chat_sessions_${user.id}`);
  }
  safeRemoveItem(localStorage, 'chat_sessions_guest');
  safeRemoveItem(localStorage, 'chat_sessions'); // 清理旧的通用 key

  removeStorageValue(TOKEN_KEY);
  removeStorageValue(USER_KEY);
  removeStorageValue(ROLE_KEY);
}
