import { AuthUser } from '../types';
import { apiFetch } from './apiClient';

type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const AUTH_ENDPOINT = `${API_BASE_URL}/api/v1/auth`;

// 会话存储实现位于 authTokenStore（避免与 apiClient 循环依赖），此处统一再导出
export {
  getAuthToken,
  getStoredUser,
  isAuthenticated,
  isAdmin,
  authHeaders,
  setAuthSession,
  clearAuthSession,
} from './authTokenStore';

import {
  getAuthToken,
  setAuthSession,
  clearAuthSession,
  updateStoredUser,
} from './authTokenStore';

export async function login(email: string, password: string): Promise<AuthUser> {
  const payload = await apiFetch<AuthResponse>(
    `${AUTH_ENDPOINT}/login`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      skip401: true,
    },
    '登录失败',
  );
  setAuthSession(payload);
  return payload.user;
}

export async function register(name: string, email: string, password: string): Promise<AuthUser> {
  const payload = await apiFetch<AuthResponse>(
    `${AUTH_ENDPOINT}/register`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
      skip401: true,
    },
    '注册失败',
  );
  setAuthSession(payload);
  return payload.user;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const user = await apiFetch<AuthUser>(`${AUTH_ENDPOINT}/me`, {}, '获取当前用户失败');
  updateStoredUser(user);
  return user;
}

export async function logout(): Promise<void> {
  const token = getAuthToken();
  clearAuthSession();
  if (!token) return;
  try {
    await apiFetch<void>(
      `${AUTH_ENDPOINT}/logout`,
      { method: 'POST' },
    );
  } catch {
    // Local logout is authoritative for the current stateless token flow.
  }
}

// ---- 验证码相关 ----

export async function sendVerificationCode(email: string, purpose: 'login' | 'register'): Promise<void> {
  await apiFetch<void>(
    `${AUTH_ENDPOINT}/send-code`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, purpose }),
      skip401: true,
    },
    '发送验证码失败',
  );
}

export async function loginWithCode(email: string, code: string): Promise<AuthUser> {
  const payload = await apiFetch<AuthResponse>(
    `${AUTH_ENDPOINT}/login-code`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, code }),
      skip401: true,
    },
    '登录失败',
  );
  setAuthSession(payload);
  return payload.user;
}

export async function registerWithCode(name: string, email: string, password: string, code: string): Promise<AuthUser> {
  const payload = await apiFetch<AuthResponse>(
    `${AUTH_ENDPOINT}/register-code`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, code }),
      skip401: true,
    },
    '注册失败',
  );
  setAuthSession(payload);
  return payload.user;
}
