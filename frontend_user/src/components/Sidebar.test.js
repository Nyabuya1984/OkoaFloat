import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from './Sidebar';
import { organizationApi } from '../services/organizationApi';

jest.mock('../services/organizationApi', () => ({
  organizationApi: {
    getDepartments: jest.fn(),
    getDepartmentPageConfigurations: jest.fn(),
  },
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const mountSidebar = async (currentUser) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Sidebar
        currentUser={currentUser}
        isOpen
        isCollapsed={false}
        onClose={jest.fn()}
        onToggleCollapse={jest.fn()}
        onLogout={jest.fn()}
      />
    </MemoryRouter>,
  ));
  await act(async () => { await Promise.resolve(); });
  return { container, root };
};

beforeEach(() => {
  organizationApi.getDepartments.mockResolvedValue([
    { id: 1, name: 'Sales & Marketing', pages: ['sales-reports', 'organization-live'] },
    { id: 2, name: 'Debt Collection', pages: ['debt-collection'] },
    { id: 3, name: 'Customer Care', pages: ['customer-care-logs'] },
    { id: 4, name: 'People & Culture', pages: [] },
  ]);
  organizationApi.getDepartmentPageConfigurations.mockResolvedValue([
    { id: 1, name: 'Sales & Marketing', pages: ['sales-reports', 'organization-live'] },
    { id: 2, name: 'Debt Collection', pages: ['debt-collection'] },
    { id: 3, name: 'Customer Care', pages: ['customer-care-logs'] },
    { id: 4, name: 'People & Culture', pages: ['hr-module', 'hr-verification'] },
  ]);
});

afterEach(() => {
  jest.clearAllMocks();
  document.body.innerHTML = '';
});

test('General Manager sidebar lists live departments before Users and omits Settings', async () => {
  const { container, root } = await mountSidebar({
    role: 'manager',
    active_assignment: { organizational_role: 'general_manager', department_name: 'All' },
    dashboard_features: { sales_reports: true, debt_collection: true, customer_care: true },
  });

  const groupButtons = Array.from(container.querySelectorAll('button.sidebar-group-toggle'));
  expect(groupButtons.map((button) => button.textContent.trim())).toEqual([
    'Leave+',
    'Sales & Marketing+',
    'Debt Collection+',
    'Customer Care+',
    'People & Culture+',
    'Users−',
  ]);
  expect(container.textContent).not.toContain('Settings');

  await act(async () => groupButtons[1].click());
  expect(container.querySelector('a[href="/dashboard/reports/sales"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/organization/live"]')).not.toBeNull();
  expect(container.textContent).toContain('Sales & Marketing Performance');
  expect(container.textContent).not.toContain('Add Client');

  await act(async () => groupButtons[2].click());
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).not.toBeNull();

  await act(async () => groupButtons[4].click());
  expect(container.textContent).toContain('No department pages are configured.');
  await act(async () => groupButtons[5].click());
  expect(container.querySelector('a[href="/dashboard/employees"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/organization/live"]')).toBeNull();
  expect(container.textContent).toContain('Executive Overview');
  await act(async () => root.unmount());
});

test('Super Admin sidebar shows its department, users, and settings', async () => {
  const { container, root } = await mountSidebar({
    role: 'super_admin',
    is_superuser: true,
    department: 'Sales & Marketing',
    active_assignment: { department_name: 'Sales & Marketing', department_role: 'sales' },
  });

  const groupButtons = Array.from(container.querySelectorAll('button.sidebar-group-toggle'));
  expect(groupButtons.map((button) => button.textContent.trim())).toEqual([
    'Leave+',
    'Sales & Marketing+',
    'Users−',
    'Settings+',
  ]);
  expect(container.querySelector('a[href="/dashboard/employees"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).toBeNull();

  await act(async () => groupButtons[1].click());
  expect(container.querySelector('a[href="/dashboard/reports/sales"]')).not.toBeNull();

  await act(async () => groupButtons[0].click());
  expect(container.querySelector('a[href="/dashboard/leave/apply"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/leave-policies"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/leave-balances"]')).not.toBeNull();

  await act(async () => groupButtons[3].click());
  expect(container.querySelector('a[href="/dashboard/departments"]')).not.toBeNull();
  expect(container.querySelector('.sidebar-footer .sidebar-logout')).not.toBeNull();

  await act(async () => root.unmount());
});

test('department loading failures are surfaced in the sidebar', async () => {
  organizationApi.getDepartmentPageConfigurations.mockRejectedValue(new Error('Department service unavailable'));
  const { container, root } = await mountSidebar({ role: 'super_admin', is_superuser: true });

  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Department service unavailable');

  await act(async () => root.unmount());
});

test('department list refreshes after department settings change', async () => {
  const { container, root } = await mountSidebar({
    role: 'super_admin',
    is_superuser: true,
    department: 'Legal',
    active_assignment: { department_name: 'Legal' },
  });
  organizationApi.getDepartmentPageConfigurations.mockResolvedValueOnce([
    { id: 5, name: 'Legal', pages: ['hr-module'] },
  ]);

  await act(async () => {
    window.dispatchEvent(new Event('departments-updated'));
    await Promise.resolve();
  });

  expect(Array.from(container.querySelectorAll('.sidebar-group-toggle'))
    .map((button) => button.textContent.trim())).toContain('Legal+');

  await act(async () => root.unmount());
});

test('super admin department navigation uses the configured page selection', async () => {
  organizationApi.getDepartmentPageConfigurations.mockResolvedValueOnce([
    { id: 7, name: 'Legal', pages: ['hr-module'] },
  ]);
  const { container, root } = await mountSidebar({
    role: 'super_admin',
    is_superuser: true,
    department: 'Legal',
    active_assignment: { department_name: 'Legal' },
  });
  const group = Array.from(container.querySelectorAll('button.sidebar-group-toggle'))
    .find((button) => button.textContent.includes('Legal'));

  await act(async () => group.click());
  expect(container.querySelector('a[href="/dashboard/hr"]')).not.toBeNull();

  await act(async () => root.unmount());
});

test('super admin department navigation falls back when a saved selection is empty', async () => {
  organizationApi.getDepartmentPageConfigurations.mockResolvedValueOnce([
    { id: 2, name: 'Debt Collection', pages: [] },
  ]);
  const { container, root } = await mountSidebar({
    role: 'super_admin',
    is_superuser: true,
    department: 'Debt Collection',
    active_assignment: { department_name: 'Debt Collection' },
  });
  const group = Array.from(container.querySelectorAll('button.sidebar-group-toggle'))
    .find((button) => button.textContent.includes('Debt Collection'));

  await act(async () => group.click());
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).not.toBeNull();
  expect(container.textContent).not.toContain('No department pages are configured.');

  await act(async () => root.unmount());
});

test('super admin department pages are not hidden by role feature flags', async () => {
  const { container, root } = await mountSidebar({
    role: 'super_admin',
    is_superuser: true,
    department: 'Customer Care',
    active_assignment: { department_name: 'Customer Care' },
    dashboard_features: { customer_care: false },
  });
  const group = Array.from(container.querySelectorAll('button.sidebar-group-toggle'))
    .find((button) => button.textContent.includes('Customer Care'));

  await act(async () => group.click());
  expect(container.querySelector('a[href="/dashboard/customer-care/logs"]')).not.toBeNull();
  expect(container.textContent).not.toContain('No department pages are configured.');

  await act(async () => root.unmount());
});

test('system administrator sees only its department pages when role features are disabled', async () => {
  organizationApi.getDepartmentPageConfigurations.mockResolvedValue([
    { id: 2, name: 'Debt Collection', pages: [] },
    { id: 3, name: 'Customer Care', pages: [] },
    { id: 1, name: 'Sales & Marketing', pages: ['organization-live'] },
  ]);
  const { container, root } = await mountSidebar({
    role: 'system_admin',
    is_superuser: true,
    department: 'Customer Care',
    active_assignment: { department_name: 'Customer Care' },
    dashboard_features: {
      customer_care: false,
      debt_collection: false,
      sales_reports: false,
    },
  });
  const groups = Array.from(container.querySelectorAll('button.sidebar-group-toggle'));

  await act(async () => groups.find((button) => button.textContent.includes('Customer Care')).click());
  [
    '/dashboard/customer-care/logs',
    '/dashboard/customer-care/new',
    '/dashboard/customer-care/customers',
    '/dashboard/customer-care/follow-ups',
    '/okia/dashboard',
    '/okia/escalations',
    '/okia/shifts',
    '/okia/shifts/coverage',
    '/okia/concerns',
    '/okia/reports/gm-resolution',
    '/okia/reports/gm-attention',
    '/okia/reports/agent-shift-matrix',
    '/okia/reports/concerns',
    '/okia/reports/escalations',
  ].forEach((path) => {
    expect(container.querySelector(`a[href="${path}"]`)).not.toBeNull();
  });
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/reports/sales"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/organization/live"]')).toBeNull();
  expect(container.textContent).not.toContain('No department pages are configured.');

  await act(async () => root.unmount());
});

test('super admin does not see other departments outside its assignment', async () => {
  organizationApi.getDepartmentPageConfigurations.mockResolvedValue([
    { id: 1, name: 'Sales & Marketing', pages: ['organization-live'] },
    { id: 2, name: 'Debt Collection', pages: [] },
    { id: 3, name: 'Customer Care', pages: [] },
  ]);
  const { container, root } = await mountSidebar({
    role: 'super_admin',
    is_superuser: true,
    department: 'Sales & Marketing',
    active_assignment: { department_name: 'Sales & Marketing' },
    dashboard_features: {
      customer_care: false,
      debt_collection: false,
      sales_reports: false,
    },
  });
  const groups = Array.from(container.querySelectorAll('button.sidebar-group-toggle'));
  const expectPages = async (groupName, paths) => {
    await act(async () => groups.find((button) => button.textContent.includes(groupName)).click());
    paths.forEach((path) => {
      expect(container.querySelector(`a[href="${path}"]`)).not.toBeNull();
    });
  };

  await expectPages('Sales & Marketing', [
    '/dashboard/organization/live',
  ]);

  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/customer-care/logs"]')).toBeNull();
  expect(container.textContent).not.toContain('No department pages are configured.');
  await act(async () => root.unmount());
});

test('department manager only sees leave and department-specific navigation', async () => {
  const { container, root } = await mountSidebar({
    role: 'manager',
    active_assignment: {
      organizational_role: 'department_manager',
      department_name: 'Sales & Marketing',
      department_role: 'sales',
    },
    dashboard_features: { sales_reports: true },
  });

  const groupButtons = Array.from(container.querySelectorAll('.sidebar-group-toggle'));
  const departmentGroup = groupButtons.find((button) => button.textContent.includes('Sales & Marketing'));
  expect(departmentGroup).not.toBeNull();
  expect(groupButtons.map((button) => button.textContent.trim())).toEqual(['Leave+', 'Sales & Marketing+']);

  await act(async () => groupButtons[0].click());
  expect(container.querySelector('a[href="/dashboard/leave/approvals"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/calendar"]')).not.toBeNull();

  await act(async () => departmentGroup.click());
  expect(container.querySelector('a[href="/dashboard/reports/sales"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/organization/live"]')).not.toBeNull();
  expect(container.textContent).toContain('Sales Performance');
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/employees"]')).not.toBeNull();

  await act(async () => root.unmount());
});

test('employee sidebar shows only the assigned department and no admin settings', async () => {
  const { container, root } = await mountSidebar({
    role: 'employee',
    department: 'Sales & Marketing',
    active_assignment: {
      organizational_role: 'field_agent',
      department_name: 'Sales & Marketing',
      department_role: 'sales',
    },
    dashboard_features: { sales_reports: true, debt_collection: true, customer_care: true },
  });

  const groups = Array.from(container.querySelectorAll('.sidebar-group-toggle'))
    .map((button) => button.textContent.trim());
  expect(groups).toEqual(['Leave+', 'Sales & Marketing+']);
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/customer-care/logs"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/settings"]')).toBeNull();

  await act(async () => root.unmount());
});

test('employee sidebar follows only the configured pages for its department', async () => {
  const { container, root } = await mountSidebar({
    role: 'employee',
    department: 'Customer Care',
    department_pages: ['customer-care-logs', 'okia-overview'],
    active_assignment: {
      organizational_role: 'field_agent',
      department_name: 'Customer Care',
      department_role: 'customer_care',
      department_pages: ['customer-care-logs', 'okia-overview'],
    },
    dashboard_features: { customer_care: false },
  });

  const group = Array.from(container.querySelectorAll('.sidebar-group-toggle'))
    .find((button) => button.textContent.includes('Customer Care'));
  await act(async () => group.click());
  expect(container.querySelector('a[href="/dashboard/customer-care/logs"]')).not.toBeNull();
  expect(container.querySelector('a[href="/okia/dashboard"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/customer-care/new"]')).toBeNull();
  expect(container.querySelector('a[href="/dashboard/departments"]')).toBeNull();

  await act(async () => root.unmount());
});

test('system admin sees only its assigned department and retains Settings', async () => {
  const { container, root } = await mountSidebar({
    role: 'system_admin',
    is_superuser: true,
    department: 'Sales & Marketing',
    active_assignment: {
      organizational_role: 'field_agent',
      department_name: 'Sales & Marketing',
      department_role: 'sales',
    },
  });

  const groups = Array.from(container.querySelectorAll('.sidebar-group-toggle'))
    .map((button) => button.textContent.trim());
  expect(groups).toEqual(['Leave+', 'Sales & Marketing+', 'Users−', 'Settings+']);
  await act(async () => container.querySelectorAll('.sidebar-group-toggle')[3].click());
  expect(container.querySelector('a[href="/dashboard/settings"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/departments"]')).not.toBeNull();

  await act(async () => root.unmount());
});

test('Debt Collection Representative sees its department module when feature data is unavailable', async () => {
  const { container, root } = await mountSidebar({
    role: 'employee',
    department: 'Debt Collection',
    department_role: 'debt_collection',
    active_assignment: {
      organizational_role: 'field_agent',
      department_name: 'Debt Collection',
      department_role: 'debt_collection',
    },
    dashboard_features: { debt_collection: false },
  });

  const departmentGroup = Array.from(container.querySelectorAll('.sidebar-group-toggle'))
    .find((button) => button.textContent.includes('Debt Collection'));
  await act(async () => departmentGroup.click());
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).not.toBeNull();
  expect(container.querySelector('a[href="/logout"]')).toBeNull();
  expect(container.querySelector('.sidebar-footer .sidebar-logout')).not.toBeNull();

  await act(async () => root.unmount());
});
