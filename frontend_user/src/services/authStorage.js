const storage = () => window.sessionStorage;
const ADMIN_USER_ACCESS_KEY = 'okoa_admin_user_access_original';

export const getAuthToken = () => storage().getItem('okoa_access_token') || '';
export const getRefreshToken = () => storage().getItem('okoa_refresh_token') || '';
export const hasAdminUserAccessSession = () => Boolean(storage().getItem(ADMIN_USER_ACCESS_KEY));
export const saveDashboardRole = (role) => {
  if (role) storage().setItem('okoa_dashboard_role', String(role).trim().toLowerCase());
  else storage().removeItem('okoa_dashboard_role');
};

export const beginAdminUserAccess = (data) => {
  if (!hasAdminUserAccessSession()) {
    storage().setItem(ADMIN_USER_ACCESS_KEY, JSON.stringify({
      accessToken: getAuthToken(),
      refreshToken: getRefreshToken(),
      dashboardRole: storage().getItem('okoa_dashboard_role') || '',
    }));
  }
  storage().setItem('okoa_access_token', data.access_token);
  storage().removeItem('okoa_refresh_token');
  saveDashboardRole(data.user?.role);
};

export const endAdminUserAccess = () => {
  const savedSession = storage().getItem(ADMIN_USER_ACCESS_KEY);
  if (!savedSession) return false;

  let originalSession;
  try {
    originalSession = JSON.parse(savedSession);
  } catch (error) {
    storage().removeItem(ADMIN_USER_ACCESS_KEY);
    return false;
  }
  if (!originalSession.accessToken) return false;

  storage().setItem('okoa_access_token', originalSession.accessToken);
  if (originalSession.refreshToken) storage().setItem('okoa_refresh_token', originalSession.refreshToken);
  else storage().removeItem('okoa_refresh_token');
  storage().removeItem(ADMIN_USER_ACCESS_KEY);
  saveDashboardRole(originalSession.dashboardRole);
  return true;
};

export const saveAuthSession = (data) => {
  storage().setItem('okoa_access_token', data.access_token);
  if (data.refresh_token) storage().setItem('okoa_refresh_token', data.refresh_token);
  if (data.session_id) storage().setItem('okoa_session_id', data.session_id);
  saveDashboardRole(data.user?.role);
};

export const clearAuthSession = () => {
  storage().removeItem(ADMIN_USER_ACCESS_KEY);
  storage().removeItem('okoa_access_token');
  storage().removeItem('okoa_refresh_token');
  storage().removeItem('okoa_session_id');
  storage().removeItem('okoa_dashboard_role');
  storage().removeItem('okoa_location_tracking');
  storage().removeItem('okoa_location_last_ping');
  window.dispatchEvent(new CustomEvent('okoa-location-tracking', { detail: { enabled: false } }));
};

export const refreshAuthToken = async () => {
  if (hasAdminUserAccessSession()) return false;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/api/auth/refresh`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${refreshToken}` },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.access_token) {
    clearAuthSession();
    return false;
  }
  storage().setItem('okoa_access_token', payload.access_token);
  return true;
};
