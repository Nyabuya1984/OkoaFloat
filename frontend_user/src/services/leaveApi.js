import { getAuthToken, refreshAuthToken } from './authStorage';

const API_BASE = `${process.env.REACT_APP_API_URL || ''}/api/leave`;
let refreshPromise = null;

const request = async (path, options = {}) => {
  const send = () => fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
      ...(options.headers || {}),
    },
  });
  let response = await send();
  if (response.status === 401) {
    try {
      if (!refreshPromise) {
        refreshPromise = refreshAuthToken().finally(() => {
          refreshPromise = null;
        });
      }
      if (await refreshPromise) response = await send();
    } catch {
      refreshPromise = null;
    }
  }

  const isJson = response.headers.get('content-type')?.includes('application/json');
  const payload = isJson ? await response.json().catch(() => null) : null;
  if (!payload) {
    throw new Error(`The leave service returned an unexpected response (HTTP ${response.status}). Check that the backend is running and up to date.`);
  }
  if (!response.ok) {
    const message = payload.error?.message
      || (typeof payload.error === 'string' ? payload.error : '')
      || payload.msg
      || payload.message
      || (response.status === 401 ? 'Your session has expired. Please sign in again.' : '')
      || 'Unable to complete the request.';
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

export const acceptHandover = (requestId, statement, fullName, signature, signatureDate) => request(`/requests/${requestId}/handover/accept`, {
  method: 'POST',
  body: JSON.stringify({ statement, full_name: fullName, signature, signature_date: signatureDate }),
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
export const getHandoverUsers = () => request('/handover-users');

export const decideLeaveRequest = (requestId, decision, decisionComment, signature) => request(
  `/requests/${requestId}/${decision}`,
  {
    method: 'POST',
    body: JSON.stringify({ decision_comment: decisionComment, signature }),
  },
);
