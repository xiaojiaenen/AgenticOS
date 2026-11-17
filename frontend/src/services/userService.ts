import { apiFetch } from './apiClient';

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

export type UserFormPayload = {
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  password?: string;
};

/** 角色元数据（后端 `/users/roles`）：值 + 中文名 + 说明 + 能力位。 */
export type RoleOption = {
  value: string;
  label: string;
  hint: string;
  capabilities: string[];
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const USERS_ENDPOINT = `${API_BASE_URL}/api/v1/users`;

/**
 * 可选角色清单。角色定义在**后端** `app/core/roles.py` 一张表里，
 * 前端只渲染 —— 新增角色不用改前端代码。
 */
export async function listRoles(): Promise<RoleOption[]> {
  const payload = await apiFetch<{ items: RoleOption[] }>(
    `${USERS_ENDPOINT}/roles`,
    {},
    '角色列表加载失败',
  );
  return payload.items;
}

export async function listUsers(params: { search?: string; offset?: number; limit?: number }): Promise<UserListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  query.set('offset', String(params.offset ?? 0));
  query.set('limit', String(params.limit ?? 20));

  return apiFetch<UserListResponse>(`${USERS_ENDPOINT}?${query.toString()}`, {}, '用户列表加载失败');
}

export async function getUser(userId: number): Promise<AdminUser> {
  return apiFetch<AdminUser>(`${USERS_ENDPOINT}/${userId}`, {}, '用户信息加载失败');
}

export async function createUser(payload: UserFormPayload): Promise<AdminUser> {
  return apiFetch<AdminUser>(
    USERS_ENDPOINT,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '创建用户失败',
  );
}

export async function updateUser(userId: number, payload: Partial<UserFormPayload>): Promise<AdminUser> {
  return apiFetch<AdminUser>(
    `${USERS_ENDPOINT}/${userId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '更新用户失败',
  );
}

export async function updateUserStatus(userId: number, isActive: boolean): Promise<AdminUser> {
  return apiFetch<AdminUser>(
    `${USERS_ENDPOINT}/${userId}/status`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: isActive }),
    },
    '更新用户状态失败',
  );
}

export async function deleteUser(userId: number): Promise<void> {
  await apiFetch<void>(`${USERS_ENDPOINT}/${userId}`, { method: 'DELETE' }, '删除用户失败');
}
