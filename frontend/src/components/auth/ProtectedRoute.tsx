import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import {
  fetchCurrentUser,
  getAuthToken,
  getStoredUser,
  isAuthenticated,
} from '../../services/authService';
import { canEnterAdmin } from '../../services/authTokenStore';

type ProtectedRouteProps = {
  children: React.ReactNode;
  requireAdmin?: boolean;
};

/**
 * 角色以服务端为准：进入受保护路由时静默拉一次 `/auth/me`，把 localStorage 里
 * 缓存的 user（含 role）刷新一遍。
 *
 * 为什么需要这一步：`get_current_user` 每次请求都从 DB 读用户，所以后端改角色
 * **立即生效**；但前端 `ProtectedRoute` 读的是登录时写进 localStorage 的
 * `user.role`，不重新登录就永远是旧值 —— 表现就是「管理员把我降级了，我还
 * 能进后台」，或者「升成管理员了但进不去」。这里把两边对齐。
 *
 * 失败不阻断渲染：网络抖动不该把已登录用户踢出去；token 真失效时
 * `apiFetch` 的 401 处理会清会话并跳登录页。
 */
const useFreshRole = () => {
  const location = useLocation();
  const [synced, setSynced] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setSynced(false);
    fetchCurrentUser()
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setSynced(true);
      });
    return () => {
      cancelled = true;
    };
    // 换页面时重新校验：管理员在别处改了角色，用户一导航就生效
  }, [location.pathname]);

  return synced;
};

export const ProtectedRoute = ({ children, requireAdmin = false }: ProtectedRouteProps) => {
  const location = useLocation();
  const token = getAuthToken();
  const user = getStoredUser();
  const synced = useFreshRole();

  // 无有效 token 或用户信息 → 回登录页（token 存 localStorage，与 authService 一致）
  if (!token || !user || !isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  // 需要管理员时，等首次校验完成再判定：否则会拿旧 role 先闪一下错误页面
  // （刚被降级的人会短暂看到后台，刚升级的人会被弹回 /chat）。
  if (requireAdmin && !synced) {
    return null;
  }

  // 校验已把最新 user（含 capabilities）写回 localStorage，canEnterAdmin 读的就是它
  if (requireAdmin && !canEnterAdmin()) {
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
};
