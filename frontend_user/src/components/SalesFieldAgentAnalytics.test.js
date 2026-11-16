import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SalesFieldAgentAnalytics from './SalesFieldAgentAnalytics';

window.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  document.body.innerHTML = '';
});

test('shows scoped agent metrics, category split, and incomplete recovery feedback', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ data: {
      scope: 'team',
      totals: { visits: 3, registrations_started: 2, complete: 1, incomplete: 1 },
      agents: [{
        employee_id: 7, employee_name: 'Agent Seven', visits: 3,
        registrations_started: 2, complete: 1, incomplete: 1,
        conversion_rate: 66.67, completion_rate: 50,
        feedback: 'Recover 1 incomplete registration.',
        by_category: {
          agent: { visits: 2, registrations_started: 1, complete: 0, incomplete: 1 },
          sub_agent: { visits: 1, registrations_started: 1, complete: 1, incomplete: 0 },
        },
      }],
      incomplete_visits: [{
        report_id: 90, employee_name: 'Agent Seven', client_name: 'Shop Nine',
        date_visited: '2026-10-25', missing_requirements: ['business_permit'],
        action: 'Complete the recovery checklist.',
      }],
    } }),
  });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<SalesFieldAgentAnalytics />));
  expect(container.textContent).toContain('Agent Seven');
  expect(container.textContent).toContain('Export analytics CSV');
  expect(container.textContent).toContain('Export analytics Excel');
  expect(container.textContent).toContain('Agent / dealer: 2 visits');
  expect(container.textContent).toContain('Sub-agent: 1 visits');
  expect(container.textContent).toContain('Shop Nine');
  expect(container.textContent).toContain('business_permit');
  expect(global.fetch.mock.calls[0][0]).toContain('/api/sales/analytics/field-agents');
  await act(async () => root.unmount());
  container.remove();
});
