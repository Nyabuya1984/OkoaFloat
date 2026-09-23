const storage = () => window.sessionStorage;

export const getAuthToken = () => storage().getItem('okoa_access_token') || '';
export const getRefreshToken = () => storage().getItem('okoa_refresh_token') || '';

export const saveAuthSession = (data) => {
  storage().setItem('okoa_access_token', data.access_token);
  if (data.refresh_token) storage().setItem('okoa_refresh_token', data.refresh_token);
  if (data.session_id) storage().setItem('okoa_session_id', data.session_id);
};

export const clearAuthSession = () => {
  storage().removeItem('okoa_access_token');
  storage().removeItem('okoa_refresh_token');
  storage().removeItem('okoa_session_id');
  storage().removeItem('okoa_dashboard_role');
};

export const refreshAuthToken = async () => {
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
