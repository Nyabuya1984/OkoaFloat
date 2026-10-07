import axios from 'axios';
import { getAuthToken, refreshAuthToken } from './authStorage';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL || '',
});

let refreshPromise = null;

apiClient.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const request = error.config;
    if (error.response?.status === 401 && request && !request._retry) {
      request._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = refreshAuthToken().finally(() => {
            refreshPromise = null;
          });
        }
        if (await refreshPromise) return apiClient(request);
        return Promise.reject(new Error('Your session has expired. Please sign in again.'));
      } catch (refreshError) {
        return Promise.reject(new Error(refreshError.message || 'Unable to refresh your session.'));
      }
    }
    return Promise.reject(new Error(error.response?.data?.error?.message || error.message));
  },
);

export default apiClient;
