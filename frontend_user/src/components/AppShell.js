import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import { getRolePreviewLabel, getUserDesignation, ROLE_PREVIEW_OPTIONS } from '../navigation';
import { getAuthToken } from '../services/authStorage';
import { apiUrl, readJsonResponse } from '../services/apiConfig';

const AppShell = ({
  children,
  currentUser,
  onLogout,
  dashboardFeatures,
  featureError,
  rolePreview,
  canPreviewRole,
  onRolePreviewChange,
  onClearRolePreview,
  canAccessUserAccounts,
  onStartUserAccess,
  onStopUserAccess,
}) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('okoa_theme') === 'dark');
  const [accounts, setAccounts] = useState([]);
  const [accessingAccount, setAccessingAccount] = useState(false);
  const [accessError, setAccessError] = useState('');
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    localStorage.setItem('okoa_theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    setSidebarOpen(false);
  }, [location.pathname]);

  const dashboardLabel = getUserDesignation(currentUser);
  const shellUser = {
    ...currentUser,
    active_assignment: currentUser?.active_assignment,
    dashboard_features: dashboardFeatures || currentUser?.dashboard_features || {},
  };

  useEffect(() => {
    if (!canAccessUserAccounts) {
      setAccounts([]);
      return undefined;
    }
    let active = true;
    fetch(apiUrl('/api/auth/admin/users'), {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    })
      .then((response) => readJsonResponse(response, 'Unable to load user accounts.').then((payload) => {
        if (!response.ok) throw new Error(payload.error?.message || 'Unable to load user accounts.');
        return payload.data || [];
      }))
      .then((users) => {
        if (active) setAccounts(users.filter((user) => (
          user.id !== currentUser?.id
          && user.is_active === true
          && user.account_status === 'approved'
          && !user.is_deleted
          && !user.is_archived
        )));
      })
      .catch((error) => {
        if (active) setAccessError(error.message || 'Unable to load user accounts.');
      });
    return () => { active = false; };
  }, [canAccessUserAccounts, currentUser?.id]);

  const startAccess = async (event) => {
    const userId = event.target.value;
    if (!userId) return;
    setAccessingAccount(true);
    setAccessError('');
    try {
      await onStartUserAccess?.(userId);
    } catch (error) {
      setAccessError(error.message || 'Unable to access this user account.');
    } finally {
      setAccessingAccount(false);
    }
  };

  const stopAccess = async () => {
    setAccessingAccount(true);
    setAccessError('');
    try {
      await onStopUserAccess?.();
    } catch (error) {
      setAccessError(error.message || 'Unable to restore the super-admin account.');
    } finally {
      setAccessingAccount(false);
    }
  };

  return (
    <div className={`app-shell ${darkMode ? 'dark-shell' : ''}`}>
      <Sidebar
        isOpen={sidebarOpen}
        isCollapsed={sidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onLogout={onLogout}
        currentUser={shellUser}
      />
      <div className={`app-shell-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''} ${sidebarOpen ? 'sidebar-open' : ''}`}>
        {currentUser?.acting_as ? (
          <div className="role-preview-banner" role="status" aria-live="polite">
            <div className="role-preview-copy">
              <strong>Accessing account: {currentUser.name || currentUser.full_name}</strong>
              <span>Read-only session started by {currentUser.acting_as.name}.</span>
            </div>
            <div className="role-preview-actions">
              <button type="button" className="role-preview-exit" onClick={stopAccess} disabled={accessingAccount}>
                {accessingAccount ? 'Returning…' : 'Return to super admin'}
              </button>
            </div>
            {accessError && <span role="alert">{accessError}</span>}
          </div>
        ) : canAccessUserAccounts && (
          <div className="role-preview-banner" aria-label="Super-admin account access">
            <div className="role-preview-copy">
              <strong>Administrative account access</strong>
              <span>Select an active user account to inspect its dashboard in read-only mode.</span>
            </div>
            <div className="role-preview-actions">
              <label className="role-preview-select">
                <span>Access user account</span>
                <select aria-label="Access a user account" value="" onChange={startAccess} disabled={accessingAccount}>
                  <option value="">Choose a user…</option>
                  {accounts.map((user) => <option value={user.id} key={user.id}>{user.full_name} ({user.employee_id || user.email})</option>)}
                </select>
              </label>
              {accessingAccount && <span role="status">Opening account…</span>}
            </div>
            {accessError && <span role="alert">{accessError}</span>}
          </div>
        )}
        {canPreviewRole && (
          <div className="role-preview-banner" role="status" aria-live="polite">
            <div className="role-preview-copy">
              <strong>{rolePreview ? `Previewing as ${getRolePreviewLabel(rolePreview)}` : 'Testing access preview'}</strong>
              <span>{rolePreview ? 'This dashboard reflects the selected previewed role.' : 'Select a role to test access without leaving admin.'}</span>
            </div>
            <div className="role-preview-actions">
              <label className="role-preview-select">
                <span>Preview role</span>
                <select
                  value={rolePreview || currentUser?.role || 'employee'}
                  onChange={(event) => onRolePreviewChange?.(event.target.value)}
                  aria-label="Select a role preview"
                >
                  {ROLE_PREVIEW_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              {rolePreview && (
                <button type="button" className="role-preview-exit" onClick={onClearRolePreview}>
                  Exit / Return to Admin
                </button>
              )}
            </div>
          </div>
        )}
        {!canPreviewRole && <div className="role-banner">{dashboardLabel} Dashboard</div>}
        <Topbar
          currentUser={shellUser}
          onOpenProfile={() => navigate('/dashboard/profile/edit')}
          onMenu={() => setSidebarOpen(true)}
          onLogout={onLogout}
          darkMode={darkMode}
          onToggleTheme={() => setDarkMode((value) => !value)}
          onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
          dashboardLabel={dashboardLabel}
        />
        <div className="app-shell-body">
          {featureError && <div className="leave-alert error" role="alert">{featureError}</div>}
          {children}
        </div>
      </div>
    </div>
  );
};

export default AppShell;
