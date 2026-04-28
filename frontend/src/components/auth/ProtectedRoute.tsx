import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getStoredUser, isAuthenticated } from '../../services/authService';

type ProtectedRouteProps = {
  children: React.ReactNode;
  requireAdmin?: boolean;
};

export const ProtectedRoute = ({ children, requireAdmin = false }: ProtectedRouteProps) => {
  const location = useLocation();
  const user = getStoredUser();

  if (!isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (requireAdmin && user?.role !== 'admin') {
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
};
