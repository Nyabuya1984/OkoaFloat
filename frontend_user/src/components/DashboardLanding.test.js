import React from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import DashboardLanding from './DashboardLanding';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

const mount = async (props) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<DashboardLanding {...props} />));
  return { container, root };
};

afterEach(() => {
  global.fetch = originalFetch;
  document.body.innerHTML = '';
});

test('employee workspace prioritizes personal leave and self-service actions', async () => {
  const onNavigate = jest.fn();
  const { container, root } = await mount({
    currentUser: { full_name: 'Taylor Employee' },
    tier: 'employee',
    overview: { requests: [{ id: 1 }], balances: [] },
    pendingRequests: [],
    availableDays: 12,
    pendingCount: 1,
    usedDays: 4,
    loading: false,
    message: null,
    canAccessSalesReports: false,
    canAccessDebtCollection: false,
    onNavigate,
  });

  expect(container.textContent).toContain('Good day, Taylor Employee');
  expect(container.textContent).toContain('Leave available');
  expect(container.textContent).toContain('My leave');
  expect(container.textContent).not.toContain('Approvals needing attention');
  expect(container.textContent).not.toContain('Department directory');
  await act(async () => container.querySelector('button').click());
  expect(onNavigate).toHaveBeenCalledWith('apply-leave');
  await act(async () => root.unmount());
});

test('group leader workspace shows approval priorities without embedding the approval workflow', async () => {
  const { container, root } = await mount({
    currentUser: { full_name: 'Jordan Leader' },
    tier: 'team_leader',
    departmentName: 'Sales & Marketing',
    overview: { requests: [], balances: [] },
    pendingRequests: [{ id: 1 }, { id: 2 }],
    availableDays: 0,
    pendingCount: 0,
    usedDays: 0,
    loading: false,
    message: null,
    canAccessSalesReports: true,
    canViewEmployeePerformance: true,
    canAccessDebtCollection: false,
    onNavigate: jest.fn(),
  });

  expect(container.textContent).toContain('Group Leader Workspace');
  expect(container.querySelector('.role-dashboard-kpi strong').textContent).toBe('2');
  expect(container.querySelector('.role-dashboard-kpi small').textContent).toBe('requests awaiting review');
  expect(container.textContent).toContain('Group members');
  expect(container.textContent).toContain('Sales team performance');
  expect(container.textContent).toContain('Employee performance and sales outcomes');
  expect(container.textContent).not.toContain('Add Client');
  expect(container.querySelector('[aria-label="Performance period from"]')).not.toBeNull();
  expect(container.querySelector('.approval-card-list')).toBeNull();
  await act(async () => root.unmount());
});

test.each(['employee', 'team_leader', 'department_manager'])(
  '%s dashboard links to its assigned Debt Collection workspace',
  async (tier) => {
    const onNavigate = jest.fn();
    const { container, root } = await mount({
      currentUser: { full_name: 'Debt Collection User' },
      tier,
      departmentName: 'Debt Collection',
      overview: { requests: [], balances: [] },
      pendingRequests: [],
      availableDays: 0,
      pendingCount: 0,
      usedDays: 0,
      loading: false,
      message: null,
      canAccessSalesReports: false,
      canAccessDebtCollection: true,
      onNavigate,
    });

    const actionLabel = tier === 'employee' ? 'Debt Collection' : 'Debt Collection operations';
    const debtCollectionAction = Array.from(container.querySelectorAll('button'))
      .find((button) => button.textContent.includes(actionLabel));
    expect(debtCollectionAction).toBeTruthy();
    await act(async () => debtCollectionAction.click());
    expect(onNavigate).toHaveBeenCalledWith('debt-collection');

    await act(async () => root.unmount());
  },
);

test('general manager workspace shows organization-wide priorities and team reporting', async () => {
  const { container, root } = await mount({
    currentUser: { full_name: 'Morgan Manager' },
    tier: 'general_manager',
    departmentName: 'All',
    overview: { requests: [], balances: [] },
    pendingRequests: [{ id: 1 }],
    availableDays: 0,
    pendingCount: 0,
    usedDays: 0,
    loading: false,
    message: null,
    canAccessSalesReports: true,
    canViewEmployeePerformance: true,
    canAccessDebtCollection: true,
    onNavigate: jest.fn(),
  });

  expect(container.textContent).toContain('Organization Overview');
  expect(container.textContent).toContain('Organization approvals');
  expect(container.textContent).toContain('All departments');
  expect(container.textContent).toContain('Sales & Marketing reports');
  expect(container.textContent).toContain('Employee performance and sales outcomes');
  expect(container.textContent).toContain('Debt Collection operations');
  expect(container.textContent).not.toContain('Add Client');
  expect(container.textContent).not.toContain('Good day, Morgan Manager');
  await act(async () => root.unmount());
});

test('performance access suppresses employee client-entry action even when user tier is stale', async () => {
  const { container, root } = await mount({
    currentUser: { full_name: 'Sales Manager' },
    tier: 'employee',
    overview: { requests: [], balances: [] },
    pendingRequests: [],
    availableDays: 0,
    pendingCount: 0,
    usedDays: 0,
    loading: false,
    message: null,
    canAccessSalesReports: true,
    canViewEmployeePerformance: true,
    canAccessDebtCollection: false,
    onNavigate: jest.fn(),
  });

  expect(container.textContent).not.toContain('Add Client');
  await act(async () => root.unmount());
});

test('Sales representative dashboard exposes registration results and cold-calling navigation', async () => {
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('/api/sales/leads/follow-ups')
      ? { data: [] }
      : String(url).includes('/api/sales/leads')
        ? { data: [{ id: 21, lead_name: 'Agent Queue Lead', phone_number: '+254700000077', status: 'new', call_logs: [] }] }
        : { data: { daily: { rows: [], totals: {} }, funnel: {} } },
  }));
  const onNavigate = jest.fn();
  const { container, root } = await mount({
    currentUser: { full_name: 'Sales Rep' },
    tier: 'employee',
    overview: { requests: [], balances: [] },
    pendingRequests: [],
    availableDays: 0,
    pendingCount: 0,
    usedDays: 0,
    loading: false,
    message: null,
    canAccessSalesReports: true,
    isSalesRepresentative: true,
    canAccessDebtCollection: false,
    onNavigate,
  });

  expect(container.textContent).toContain('Your registration results');
  expect(container.textContent).toContain('REGISTRATION FUNNEL');
  const salesLink = [...container.querySelectorAll('button')]
    .find((button) => button.textContent.includes('Open visits and cold-calling leads'));
  expect(salesLink).toBeTruthy();
  expect(container.querySelector('[aria-label="Telesales calling queue"]')).not.toBeNull();
  expect(container.querySelector('select[aria-label="Outcome for Agent Queue Lead"]')).not.toBeNull();
  expect(container.textContent).not.toContain('Upload prospect list (CSV or Excel .xlsx)');
  expect(container.textContent).not.toContain('Export filtered call history CSV');
  await act(async () => salesLink.click());
  expect(onNavigate).toHaveBeenCalledWith('sales-reports');
  await act(async () => root.unmount());
});

test('Sales department manager dashboard exposes lead allocation and reporting, not an agent-only queue', async () => {
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => {
      const requestUrl = String(url);
      if (requestUrl.includes('/api/sales/leads/follow-ups')) return { data: [] };
      if (requestUrl.includes('/api/sales/leads/assignees')) return { data: [{ id: 8, full_name: 'Sales Rep' }] };
      if (requestUrl.includes('/api/sales/leads/analytics')) return { data: { statuses: { new: 1 }, employees: [] } };
      if (requestUrl.includes('/api/sales/leads')) return { data: [{ id: 22, lead_name: 'Manager Queue Lead', phone_number: '+254700000078', status: 'new' }] };
      return { data: { daily: { rows: [], totals: {} }, funnel: {}, employees: [] } };
    },
  }));
  const onNavigate = jest.fn();
  const { container, root } = await mount({
    currentUser: { full_name: 'Sales Manager' },
    tier: 'department_manager',
    departmentName: 'Sales & Marketing',
    overview: { requests: [], balances: [] },
    pendingRequests: [],
    availableDays: 0,
    pendingCount: 0,
    usedDays: 0,
    loading: false,
    message: null,
    canAccessSalesReports: true,
    canViewEmployeePerformance: true,
    canAccessDebtCollection: false,
    onNavigate,
  });

  expect(container.querySelector('[aria-label="Telesales lead operations"]')).not.toBeNull();
  expect(container.querySelector('input[aria-label="Select Manager Queue Lead"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="Share selected leads"]')).not.toBeNull();
  expect(container.textContent).toContain('Upload prospect list (CSV or Excel .xlsx)');
  expect(container.textContent).toContain('Export filtered call history CSV');
  expect(container.textContent).not.toContain('Your calling queue');
  const salesLink = [...container.querySelectorAll('button')]
    .find((button) => button.textContent.includes('Sales team performance'));
  expect(salesLink).toBeTruthy();
  await act(async () => salesLink.click());
  expect(onNavigate).toHaveBeenCalledWith('sales-reports');

  await act(async () => root.unmount());
});
