import { authHeaders } from './authService';

export type AdminUser = {
  id: number;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
};

export type UserListResponse = {
  items: AdminUser[];
  total: number;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const USERS_ENDPOINT = `${API_BASE_URL}/api/v1/users`;

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json();
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

export async function listUsers(params: { search?: string; offset?: number; limit?: number }): Promise<UserListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  query.set('offset', String(params.offset ?? 0));
  query.set('limit', String(params.limit ?? 20));

  const response = await fetch(`${USERS_ENDPOINT}?${query.toString()}`, {
    headers: authHeaders(),
  });
  return parseResponse<UserListResponse>(response);
}

export async function updateUserStatus(userId: number, isActive: boolean): Promise<AdminUser> {
  const response = await fetch(`${USERS_ENDPOINT}/${userId}/status`, {
    method: 'PATCH',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ is_active: isActive }),
  });
  return parseResponse<AdminUser>(response);
}
