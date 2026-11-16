import { apiUrl } from './apiConfig';
import { getAuthToken, refreshAuthToken } from './authStorage';

const responseErrorMessage = (payload, fallback) => (
  payload.error?.message || payload.msg || fallback
);

const request = async (path, options = {}) => {
  const send = () => fetch(apiUrl(path), {
    ...options,
    headers: {
      Authorization: `Bearer ${getAuthToken()}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });
  let response = await send();
  if (response.status === 401 && await refreshAuthToken()) response = await send();
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(responseErrorMessage(
      payload,
      'The organization service could not complete the request.',
    ));
    error.code = payload.error?.code;
    error.status = response.status;
    throw error;
  }
  return payload.data;
};

export const organizationApi = {
  getDepartments: () => request('/api/organization/departments'),
  getDepartmentPageConfigurations: () => request('/api/admin/department-pages'),
  getTransferCandidates: () => request('/api/organization/transfer-candidates'),
  getMyAssignment: () => request('/api/organization/assignment/me'),
  pingLocation: (coordinates, signal, trackingMode = 'scheduled') => request('/api/agent/location', {
    method: 'POST',
    body: JSON.stringify({ ...coordinates, tracking_mode: trackingMode }),
    signal,
  }),
  setActiveFieldVisit: (action, options = {}) => request('/api/organization/agent/active-visit', {
    ...options,
    method: 'POST',
    body: JSON.stringify({ action }),
  }),
  getAgentLocationTrackingStatus: () => request('/api/organization/agent/location-sharing'),
  getLocationTrackingSchedule: () => request('/api/organization/location-tracking/schedule'),
  setLocationTrackingSchedule: (schedule) => request('/api/organization/location-tracking/schedule', {
    method: 'PUT',
    body: JSON.stringify(schedule),
  }),
  getLocationTrackingControl: () => request('/api/organization/location-tracking/control'),
  setLocationTrackingControl: (enabled) => request('/api/organization/location-tracking/control', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  }),
  getLiveLocations: () => request('/api/manager/agents/live-locations'),
  streamLiveLocations: async (onUpdate, signal) => {
    const send = () => fetch(apiUrl('/api/organization/locations/stream'), {
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        Accept: 'text/event-stream',
      },
      signal,
    });
    let response = await send();
    if (response.status === 401 && await refreshAuthToken()) response = await send();
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(responseErrorMessage(
        payload,
        'The live location stream could not be opened.',
      ));
    }
    if (!response.body) throw new Error('This browser does not support live location streaming.');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) return;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const event = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const eventName = event.match(/^event:\s*(.+)$/m)?.[1];
          const data = event
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n');
          if (data) {
            let payload;
            try {
              payload = JSON.parse(data);
            } catch {
              throw new Error('The live location stream returned invalid data.');
            }
            if (eventName === 'error') {
              throw new Error(payload.error?.message || 'The live location stream was rejected.');
            }
            onUpdate(payload);
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } finally {
      reader.releaseLock();
    }
  },
  getAgentLocationTrail: (userId, start, end) => request(
    `/api/organization/manager/agents/${userId}/location-trail?start=${encodeURIComponent(new Date(start).toISOString())}&end=${encodeURIComponent(new Date(end).toISOString())}`,
  ),
  getHistoricalReports: () => request('/api/organization/reports/history'),
  getDepartmentReports: (departmentId) => request(`/api/reports/${departmentId}`),
  registerClient: (client) => request('/api/clients/register', {
    method: 'POST',
    body: JSON.stringify(client),
  }),
  transferEmployee: (userId, assignment) => request('/api/employees/transfer', {
    method: 'POST',
    body: JSON.stringify({ ...assignment, user_id: userId }),
  }),
};
