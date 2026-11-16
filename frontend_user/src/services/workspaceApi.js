import { getAuthToken } from './authStorage';
import { apiUrl } from './apiConfig';

const storeKey = 'okoa_workspace_store';
const seed = {
  leaves: [
    { id: 'L-1001', type: 'Annual Leave', start: '2026-10-12', end: '2026-10-16', days: 5, status: 'Approved', reason: 'Family time' },
    { id: 'L-1002', type: 'Sick Leave', start: '2026-09-08', end: '2026-09-08', days: 1, status: 'Pending', reason: 'Medical appointment' },
    { id: 'L-1003', type: 'Annual Leave', start: '2026-07-20', end: '2026-07-22', days: 3, status: 'Cancelled', reason: 'Travel changed' },
  ],
  leaveTypes: [
    { id: 'LT-1', name: 'Annual Leave', code: 'AL', paid: true, maxDays: 21, approval: true, color: '#e89b57' },
    { id: 'LT-2', name: 'Sick Leave', code: 'SL', paid: true, maxDays: 14, approval: true, color: '#ef974a' },
    { id: 'LT-3', name: 'Unpaid Leave', code: 'UL', paid: false, maxDays: 30, approval: true, color: '#e68b3c' },
  ],
  delegations: [{ id: 'D-1', person: 'Amina Wanjiku', scope: 'Approvals, Calendar', start: '2026-09-01', end: '2026-09-30', status: 'Active' }],
  approvals: [{ id: 'L-2001', person: 'Brian Otieno', type: 'Annual Leave', start: '2026-10-05', end: '2026-10-07', days: 3, status: 'Pending', balance: 14 }],
  users: [{ id: 'U-1', name: 'Brian Otieno', email: 'brian@okoa.co.ke', role: 'employee', department: 'Sales', manager: 'Mary Njeri', balance: 14, status: 'Active' }, { id: 'U-2', name: 'Amina Wanjiku', email: 'amina@okoa.co.ke', role: 'manager', department: 'Operations', manager: 'Mary Njeri', balance: 18, status: 'Active' }],
  departments: [{ id: 'DEP-1', name: 'Sales', head: 'Mary Njeri', members: 12, policy: 'Standard' }, { id: 'DEP-2', name: 'Operations', head: 'Amina Wanjiku', members: 8, policy: 'Standard' }],
  verifications: [{ id: 'V-1', type: 'Medical certificate', person: 'Brian Otieno', submitted: '2026-09-08', status: 'Pending', note: 'Certificate attached' }],
  audit: [{ id: 'A-1', actor: 'Mary Njeri', action: 'Approved leave request', entity: 'LeaveRequest L-0998', when: '2026-09-21 14:20', detail: 'Status changed from Pending to Approved' }],
  rules: { maxConsecutive: 10, noticeDays: 3, blackoutPeriods: '2026-12-20 to 2027-01-05', carryOver: 5 },
  messages: [{ id: 'M-1', from: 'Amina Wanjiku', body: 'Your October handover looks good.', at: '09:42' }],
};

const saveStore = (store) => window.localStorage.setItem(storeKey, JSON.stringify(store));

export const queryWorkspace = async (key, endpoint) => {
  const token = getAuthToken();
  const response = await fetch(apiUrl(endpoint), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || payload.error || 'Unable to load workspace data.');
  return payload.data ?? payload;
};

export const mutateWorkspace = async (key, updater, endpoint, options = {}) => {
  const response = await fetch(apiUrl(endpoint), { method: options.method || 'POST', headers: { 'Content-Type': 'application/json', ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}) }, body: JSON.stringify(options.body || {}) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || payload.error || 'Unable to update workspace data.');
  window.dispatchEvent(new CustomEvent('okoa-data-changed', { detail: key }));
  return payload.data ?? payload;
};

export const resetWorkspaceStore = () => { saveStore(seed); window.dispatchEvent(new CustomEvent('okoa-data-changed')); };