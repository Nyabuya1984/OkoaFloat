import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

const ProtectedRoute = ({ currentUser, requiredRoles = [] }) => {
  const location = useLocation();

  if (!currentUser) return <Navigate to="/login" replace state={{ from: location }} />;
  if (requiredRoles.length > 0 && !requiredRoles.includes(currentUser.role)) {
    return <Navigate to="/dashboard/employee-home" replace state={{ from: location }} />;
  }

  return <Outlet />;
};

export default ProtectedRoute;