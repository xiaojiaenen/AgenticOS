/**
 * <Permission> — 声明式按钮级权限包裹组件。
 *
 * 无权限时默认不渲染 children（也可传 fallback 显示占位/禁用态）。
 * 与 usePermission hook 同源，都是读 /auth/me 下发的 permissions。
 *
 * 用法：
 *   <Permission point="user:create">
 *     <Button>新建用户</Button>
 *   </Permission>
 *   <Permission points={['user:edit','user:delete']} mode="any">
 *     ...
 *   </Permission>
 */
import type { ReactNode } from 'react';
import { usePermission } from '../../hooks/usePermission';

interface PermissionProps {
  /** 单个权限点（与 points 二选一，point 优先） */
  point?: string;
  /** 多个权限点 */
  points?: string[];
  /** 多权限点时的判定模式：any=任一 / all=全部，默认 any */
  mode?: 'any' | 'all';
  children: ReactNode;
  /** 无权限时的替代内容（默认 null = 不渲染） */
  fallback?: ReactNode;
}

export function Permission({
  point, points, mode = 'any', children, fallback = null,
}: PermissionProps) {
  const { can, hasAny, hasAll } = usePermission();
  let allowed: boolean;
  if (point) {
    allowed = can(point);
  } else if (points && points.length > 0) {
    allowed = mode === 'all' ? hasAll(points) : hasAny(points);
  } else {
    allowed = false;
  }
  return <>{allowed ? children : fallback}</>;
}

export default Permission;
