import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

const ProtectedRoute = ({ currentUser, requiredRoles = [] }) => {
  const location = useLocation();

  if (!currentUser) return <Navigate to="/" replace state={{ from: location }} />;
  if (requiredRoles.length > 0 && !requiredRoles.includes(currentUser.role)) return <Navigate to="/403" replace />;

  return <Outlet />;
};

export default ProtectedRoute;