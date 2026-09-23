import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import LeaveDashboard from './LeaveDashboard';
import AppShell from './AppShell';
import ProtectedRoute from './ProtectedRoute';

const AccessDenied = () => <main className="page-state"><h1>403</h1><p>You do not have permission to view this page.</p></main>;

const ShellRoute = ({ currentUser, onLogout, children }) => (
  <AppShell currentUser={currentUser} onLogout={onLogout}>
    {children}
  </AppShell>
);

const AuthenticatedRoutes = ({ currentUser, onUserUpdated, handleLogout }) => (
  <Routes>
    <Route path="/403" element={<ShellRoute currentUser={currentUser} onLogout={handleLogout}><AccessDenied /></ShellRoute>} />
    <Route element={<ProtectedRoute currentUser={currentUser} />}>
      <Route path="/dashboard" element={<LeaveDashboard currentUser={currentUser} onUserUpdated={onUserUpdated} handleLogout={handleLogout} />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Route>
  </Routes>
);

export default AuthenticatedRoutes;