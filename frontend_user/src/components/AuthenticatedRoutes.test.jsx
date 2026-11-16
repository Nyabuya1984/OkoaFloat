import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { RolePageRoute } from './AuthenticatedRoutes';

jest.mock('./OkoaOperationsPages', () => ({
  EscalationDetailPage: () => null,
  ConcernCategoryDetailPage: () => null,
  OkoaOperationsPage: () => <div>Executive operations overview</div>,
}));
jest.mock('./OrganizationPages', () => ({
  ActiveAssignmentGuard: ({ children }) => children,
  ClientRegistrationPage: () => null,
  DepartmentTransferPage: () => null,
  HistoricalReportsPage: () => null,
  LiveLocationDashboard: () => null,
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  document.body.innerHTML = '';
});

test('General Manager dashboard route includes the organization telesales manager workspace', async () => {
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => {
      const requestUrl = String(url);
      if (requestUrl.includes('/api/sales/leads/assignees')) return { data: [] };
      if (requestUrl.includes('/api/sales/leads/analytics')) return { data: { statuses: {}, employees: [] } };
      if (requestUrl.includes('/api/sales/leads')) return { data: [] };
      return { data: {} };
    },
  }));
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => root.render(
    <RolePageRoute
      page="dashboard"
      currentUser={{ role: 'manager', active_assignment: { organizational_role: 'general_manager', department_name: 'All' } }}
      roles={['manager']}
    />,
  ));

  expect(container.textContent).toContain('Executive operations overview');
  expect(container.querySelector('[aria-label="Telesales lead operations"]')).not.toBeNull();
  expect(container.textContent).toContain('Upload prospect list (CSV or Excel .xlsx)');
  expect(container.textContent).toContain('Export filtered call history CSV');

  await act(async () => root.unmount());
});
