import { getAuthToken } from './authStorage';

const API_BASE = `${process.env.REACT_APP_API_URL || ''}/api/chat`;

const request = async (path, options = {}) => {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error?.message || data.error || 'Unable to complete chat action.');
  return data;
};

export const getChatUsers = () => request('/users');
export const getChatMessages = (peerId) => request(`/messages/${peerId}`);
export const getUnreadChatCount = () => request('/unread-count');
export const markChatMessagesRead = (peerId) => request(`/messages/${peerId}/read`, { method: 'POST' });
export const sendChatMessage = (recipientId, body) => request('/messages', {
  method: 'POST',
  body: JSON.stringify({ recipient_id: recipientId, body }),
});
