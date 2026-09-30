import { AuthUser } from '../types';

/**
 * Token / 用户会话的底层存储（localStorage 优先，兼容迁移旧 sessionStorage 数据）。
 * 独立成模块以避免 authService ↔ apiClient 循环依赖。
 */

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';
const ROLE_KEY = 'role';

function readStorageValue(key: string): string | null {
  // token/user 持久化到 localStorage，支持新标签页共享登录态
  const localValue = localStorage.getItem(key);
  if (localValue) return localValue;

  // 迁移旧的 sessionStorage 数据
  const legacyValue = sessionStorage.getItem(key);
  if (!legacyValue) return null;
  localStorage.setItem(key, legacyValue);
  sessionStorage.removeItem(key);
  return legacyValue;
}

function writeStorageValue(key: string, value: string): void {
  localStorage.setItem(key, value);
  sessionStorage.removeItem(key);
}

function removeStorageValue(key: string): void {
  localStorage.removeItem(key);
  sessionStorage.removeItem(key);
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
    localStorage.removeItem(`chat_sessions_${user.id}`);
  }
  localStorage.removeItem('chat_sessions_guest');
  localStorage.removeItem('chat_sessions'); // 清理旧的通用 key

  removeStorageValue(TOKEN_KEY);
  removeStorageValue(USER_KEY);
  removeStorageValue(ROLE_KEY);
}
