/**
 * 按钮级权限控制（权限矩阵的前端入口）。
 *
 * 数据来源：/auth/me 与登录响应下发的 `user.permissions`（细粒度权限点数组）。
 * 后端是真正的门禁，前端隐藏只是体验层（主流铁律：前端管显示，后端管安全）。
 *
 * 用法：
 *   const { can, hasAny } = usePermission();
 *   if (!can('user:create')) return null;
 *   <Permission point="kb:delete"><DangerButton/></Permission>
 */
import { useCallback, useSyncExternalStore } from 'react';
import { getStoredUser, subscribeAuth } from '../services/authTokenStore';

export interface PermissionApi {
  /** 是否拥有单个权限点 */
  can: (point: string) => boolean;
  /** 是否拥有其中任意一个 */
  hasAny: (points: string[]) => boolean;
  /** 是否拥有全部 */
  hasAll: (points: string[]) => boolean;
  /** 当前用户全部权限点 */
  permissions: string[];
}

/**
 * 旧缓存兼容：无 permissions 字段时，无法确认细粒度权限。
 * 为安全起见默认拒绝（fail-closed）—— 前端隐藏按钮，后端仍会真正校验；
 * 用户重新登录后 /auth/me 会补齐 permissions。
 */
// 稳定空数组：useSyncExternalStore 要求 getSnapshot 返回**引用稳定**的值，
// 每次 new [] 会让 React 认为快照一直在变 → Maximum update depth exceeded。
const EMPTY_PERMISSIONS: string[] = [];
// 缓存：同一份权限数组引用保持不变（getStoredUser 每次 JSON.parse 返回新对象）
let cachedPermissions: string[] = EMPTY_PERMISSIONS;
let cachedRaw = '';

function readPermissions(): string[] {
  const user = getStoredUser();
  const raw = JSON.stringify(user?.permissions ?? []);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedPermissions = user?.permissions ?? EMPTY_PERMISSIONS;
  }
  return cachedPermissions;
}

export function usePermission(): PermissionApi {
  const permissions = useSyncExternalStore(subscribeAuth, readPermissions, readPermissions);

  const can = useCallback((point: string) => permissions.includes(point), [permissions]);
  const hasAny = useCallback(
    (points: string[]) => points.some((p) => permissions.includes(p)),
    [permissions],
  );
  const hasAll = useCallback(
    (points: string[]) => points.every((p) => permissions.includes(p)),
    [permissions],
  );

  return { can, hasAny, hasAll, permissions };
}

export default usePermission;
