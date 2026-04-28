import { AuthUser } from '../types';

type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const AUTH_ENDPOINT = `${API_BASE_URL}/api/v1/auth`;
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

function readJson<T>(value: string | null): T | null {
  if (!value) return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.json();
  }
  let message = 'Request failed';
  try {
    const payload = await response.json();
    if (typeof payload.detail === 'string') message = payload.detail;
  } catch {
    const text = await response.text();
    if (text) message = text;
  }
  throw new Error(message);
}

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  return readJson<AuthUser>(localStorage.getItem(USER_KEY));
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

export function setAuthSession(response: AuthResponse): void {
  localStorage.setItem(TOKEN_KEY, response.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(response.user));
  localStorage.setItem('role', response.user.role);
}

export function clearAuthSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem('role');
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const response = await fetch(`${AUTH_ENDPOINT}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const payload = await parseResponse<AuthResponse>(response);
  setAuthSession(payload);
  return payload.user;
}

export async function register(name: string, email: string, password: string): Promise<AuthUser> {
  const response = await fetch(`${AUTH_ENDPOINT}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  });
  const payload = await parseResponse<AuthResponse>(response);
  setAuthSession(payload);
  return payload.user;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await fetch(`${AUTH_ENDPOINT}/me`, {
    headers: authHeaders(),
  });
  const user = await parseResponse<AuthUser>(response);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  localStorage.setItem('role', user.role);
  return user;
}

export async function logout(): Promise<void> {
  const token = getAuthToken();
  clearAuthSession();
  if (!token) return;
  try {
    await fetch(`${AUTH_ENDPOINT}/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Local logout is authoritative for the current stateless token flow.
  }
}
