import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getAuthToken, getStoredUser, isAuthenticated } from '../../services/authService';


type ProtectedRouteProps = {
  children: React.ReactNode;
  requireAdmin?: boolean;
};

export const ProtectedRoute = ({ children, requireAdmin = false }: ProtectedRouteProps) => {
  const location = useLocation();
  const token = getAuthToken();
  const user = getStoredUser();

  // 无有效 token 或用户信息 → 回登录页（token 存 localStorage，与 authService 一致）
  if (!token || !user || !isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (requireAdmin && user.role !== 'admin') {
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
};
