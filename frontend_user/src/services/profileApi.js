import { getAuthToken } from './authStorage';

const API_BASE = `${process.env.REACT_APP_API_URL || ''}/api/auth`;

const authHeaders = () => ({ Authorization: `Bearer ${getAuthToken()}` });

const parseResponse = async (response, fallback) => {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error?.message || data.error || fallback);
  return data.user;
};

export const updateProfile = async (payload) => {
  const response = await fetch(`${API_BASE}/me`, {
    method: 'PATCH',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse(response, 'Unable to update profile.');
};

export const uploadProfilePhoto = async (file) => {
  const body = new FormData();
  body.append('photo', file);
  const response = await fetch(`${API_BASE}/me/photo`, {
    method: 'POST',
    headers: authHeaders(),
    body,
  });
  return parseResponse(response, 'Unable to upload profile photo.');
};

export const deleteProfilePhoto = async () => {
  const response = await fetch(`${API_BASE}/me/photo`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return parseResponse(response, 'Unable to remove profile photo.');
};
