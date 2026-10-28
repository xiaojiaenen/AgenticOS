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

export function isAdmin(): boolean {
  return getStoredUser()?.role === 'admin';
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
