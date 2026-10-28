/**
 * 权限体系：角色 / Casbin 策略 / 审计日志。
 * 全部端点仅管理员可用（后端 require_admin）。
 *
 * 部门（departments）已下线，「用户 → 角色 → 策略」是唯一的授权模型。
 */
import { apiFetch } from './apiClient';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const BASE = `${API_BASE_URL}/api/v1`;

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export interface Role {
  id: number;
  name: string;
  slug: string;
  description: string;
  is_builtin: boolean;
  is_active: boolean;
  created_at: string;
}

export async function listRoles(): Promise<Role[]> {
  return apiFetch<Role[]>(`${BASE}/roles`, {}, '加载角色失败');
}

export async function createRole(payload: { name: string; slug: string; description?: string }): Promise<Role> {
  return apiFetch<Role>(
    `${BASE}/roles`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '创建角色失败',
  );
}

export async function deleteRole(roleId: number): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`${BASE}/roles/${roleId}`, { method: 'DELETE' }, '删除角色失败');
}

// ---------------------------------------------------------------------------
// Casbin policies
// ---------------------------------------------------------------------------

export type PolicyType = 'p' | 'g';

export interface Policy {
  ptype: PolicyType;
  /** p: 角色 slug；g: 用户标识（user:<id> / 邮箱） */
  sub: string;
  /** p: 域（* = 全局）；g 列表里表示角色 */
  dom: string;
  /** p: 资源对象，如 kb:12 */
  obj: string;
  /** p: 动作 read / write / admin */
  act: string;
}

export async function listPolicies(ptype: PolicyType = 'p'): Promise<Policy[]> {
  return apiFetch<Policy[]>(`${BASE}/permissions/policies?ptype=${ptype}`, {}, '加载策略失败');
}

export async function createPolicy(policy: Policy): Promise<Policy> {
  return apiFetch<Policy>(
    `${BASE}/permissions/policies`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(policy),
    },
    '新增策略失败',
  );
}

/** DELETE 带 body：与后端契约保持一致，用 fetch 直接调用 */
export async function deletePolicy(policy: Policy): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(
    `${BASE}/permissions/policies`,
    {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(policy),
    },
    '删除策略失败',
  );
}

export interface UserRoleInfo {
  user_id: number;
  subject: string;
  domain: string;
  roles: string[];
  app_role: string;
}

export async function getUserRoles(userId: number): Promise<UserRoleInfo> {
  return apiFetch<UserRoleInfo>(`${BASE}/permissions/roles/${userId}`, {}, '加载用户角色失败');
}

// ---------------------------------------------------------------------------
// 授权目录：把策略里的内部标识翻成人话
// ---------------------------------------------------------------------------

export interface CatalogOption {
  value: string;
  label: string;
}

export interface CatalogSubject {
  sub: string;
  label: string;
  kind: 'role' | 'user' | string;
  description: string;
}

export interface CatalogResource {
  obj: string;
  label: string;
  /** feature = 功能级（推荐）；resource = 实例级（逐条控制） */
  kind: 'feature' | 'resource' | string;
  resource_type: string;
  resource_id: string;
  description: string;
}

export interface PermissionCatalog {
  resource_types: CatalogOption[];
  actions: CatalogOption[];
  subjects: CatalogSubject[];
  resources: CatalogResource[];
  domain: string;
}

/**
 * 策略编辑器可选项。
 *
 * 后端把 Casbin 的内部标识（`kb:12`、`user:3`、角色 slug）连同人类可读的
 * 名字一起返回，前端只做选择 —— 手写这些字符串等于要求管理员记住主键。
 */
export async function getPermissionCatalog(): Promise<PermissionCatalog> {
  return apiFetch<PermissionCatalog>(`${BASE}/permissions/catalog`, {}, '加载授权目录失败');
}

// ---------------------------------------------------------------------------
// Audit logs
// ---------------------------------------------------------------------------

export interface AuditLog {
  id: number;
  actor_id: number | null;
  actor_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  result: 'allow' | 'deny' | 'error' | string;
  ip: string | null;
  user_agent: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogFilters {
  action?: string;
  resourceType?: string;
  result?: string;
  actorId?: number;
  limit?: number;
  offset?: number;
}

export async function listAuditLogs(
  filters: AuditLogFilters = {},
): Promise<{ items: AuditLog[]; total: number }> {
  const params = new URLSearchParams();
  if (filters.action) params.set('action', filters.action);
  if (filters.resourceType) params.set('resource_type', filters.resourceType);
  if (filters.result) params.set('result', filters.result);
  if (filters.actorId != null) params.set('actor_id', String(filters.actorId));
  params.set('limit', String(filters.limit ?? 50));
  params.set('offset', String(filters.offset ?? 0));
  return apiFetch<{ items: AuditLog[]; total: number }>(
    `${BASE}/audit-logs?${params.toString()}`,
    {},
    '加载审计日志失败',
  );
}

export async function purgeAuditLogs(retentionDays?: number): Promise<{ deleted: number; retention_days: number }> {
  const qs = retentionDays != null ? `?retention_days=${retentionDays}` : '';
  return apiFetch<{ deleted: number; retention_days: number }>(
    `${BASE}/audit-logs/purge${qs}`,
    { method: 'POST' },
    '清理审计日志失败',
  );
}
