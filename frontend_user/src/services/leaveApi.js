import { getAuthToken } from './authStorage';

const API_BASE = `${process.env.REACT_APP_API_URL || ''}/api/leave`;

const request = async (path, options = {}) => {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.error?.message || payload.error || payload.message || 'Unable to complete the request.';
    throw new Error(message);
  }
  return payload;
};

export const getLeaveOverview = async () => {
  const [types, balances, requests] = await Promise.allSettled([
    request('/types'),
    request('/balances'),
    request('/requests'),
  ]);
  if (types.status === 'rejected') throw types.reason;
  return {
    types: types.value.data || [],
    balances: balances.status === 'fulfilled' ? balances.value.data || [] : [],
    requests: requests.status === 'fulfilled' ? requests.value.data || [] : [],
  };
};

export const createLeaveRequest = (payload) => request('/requests', {
  method: 'POST',
  body: JSON.stringify(payload),
});

export const acknowledgeHandover = (requestId, name, statement) => request(`/requests/${requestId}/handover-ack`, {
  method: 'POST',
  body: JSON.stringify({ name, statement }),
});

export const getHandoverRequest = (requestId) => request(`/requests/${requestId}/handover`);

export const acceptHandover = (requestId, statement, signature, signatureDate) => request(`/requests/${requestId}/handover/accept`, {
  method: 'POST',
  body: JSON.stringify({ statement, signature, signature_date: signatureDate }),
});

export const declineHandover = (requestId, reason) => request(`/requests/${requestId}/handover/decline`, {
  method: 'POST',
  body: JSON.stringify({ reason }),
});
export const remindHandoverDelegate = (requestId) => request(`/requests/${requestId}/handover/remind`, {
  method: 'POST',
});

export const submitHandoverReport = (requestId, report) => request(`/requests/${requestId}/handover/report`, {
  method: 'POST',
  body: JSON.stringify({ report }),
});

export const cancelLeaveRequest = (requestId) => request(`/requests/${requestId}/cancel`, {
  method: 'POST',
});

export const getPendingLeaveRequests = () => request('/requests/pending');
export const getTeamCalendar = () => request('/team-calendar');
export const getLeaveHistory = () => request('/requests/history');
export const getDelegations = () => request('/requests/delegations');

export const decideLeaveRequest = (requestId, decision, decisionComment) => request(
  `/requests/${requestId}/${decision}`,
  {
    method: 'POST',
    body: JSON.stringify({ decision_comment: decisionComment }),
  },
);
