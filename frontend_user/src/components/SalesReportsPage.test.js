import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import SalesReportsPage from './SalesReportsPage';
import SalesRegistrationAnalytics from './SalesRegistrationAnalytics';

window.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  document.body.innerHTML = '';
});

test('Add Client opens the client form and Close report hides it', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<SalesReportsPage canAddClient />);
  });

  const addButton = [...container.querySelectorAll('button')]
    .find((button) => button.textContent === 'Add Client');
  expect(addButton).toBeDefined();
  expect(addButton.getAttribute('aria-expanded')).toBe('false');

  await act(async () => Simulate.click(addButton));

  expect(container.querySelector('#sales-daily-report')).not.toBeNull();
  expect(addButton.textContent).toBe('Close report');
  expect(addButton.getAttribute('aria-expanded')).toBe('true');

  await act(async () => Simulate.click(addButton));

  expect(container.querySelector('#sales-daily-report')).toBeNull();
  expect(addButton.textContent).toBe('Add Client');
  expect(addButton.getAttribute('aria-expanded')).toBe('false');

  await act(async () => root.unmount());
  container.remove();
});

test('manager reports open on analytics without client entry or report corrections', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  global.fetch = jest.fn(() => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ data: { daily: { rows: [], totals: {} } } }),
  }));

  await act(async () => {
    root.render(<SalesReportsPage canViewEmployeePerformance canAddClient={false} canEdit />);
  });

  expect(container.textContent).toContain('Sales & Marketing Performance');
  expect(container.querySelector('#sales-daily-report')).toBeNull();
  expect(container.querySelector('.sales-edit-panel')).toBeNull();
  expect([...container.querySelectorAll('.report-view-tabs button')]
    .find((button) => button.textContent === 'Analytics').className).toContain('is-active');
  expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Add Client')).toBe(false);

  await act(async () => root.unmount());
  container.remove();
});

test('Add Client is hidden by default unless explicitly enabled for a representative', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<SalesReportsPage />);
  });

  expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Add Client')).toBe(false);
  await act(async () => root.unmount());
  container.remove();
});

test('Sales users can access M-Pesa agent record CSV import and export tools', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => root.render(<SalesReportsPage canAddClient canManageAgentRecords />));

  expect(container.textContent).toContain('M-PESA AGENT RECORDS');
  expect(container.textContent).toContain('Download CSV template');
  expect(container.textContent).toContain('Download Excel template');
  expect(container.textContent).toContain('Export filtered records');
  expect(container.querySelector('input[type="file"][accept*=".xlsx"]')).not.toBeNull();
  expect(container.textContent).toContain('Import records');

  await act(async () => root.unmount());
  container.remove();
});

test('sales reports show and search by Sales & Marketing employee name', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const reports = [
    {
      id: 1, employee_id: 10, employee_name: 'John Sales', agent_name: 'Shop One',
      date_visited: '2026-04-03', customer_type: 'agent', outcome: 'registered',
    },
    {
      id: 2, employee_id: 11, employee_name: 'Mary Marketing', agent_name: 'Shop Two',
      date_visited: '2026-04-04', customer_type: 'sub_agent', outcome: 'appointment',
    },
  ];

  await act(async () => {
    root.render(<SalesReportsPage reports={reports} />);
  });

  expect(container.textContent).toContain('Sales & Marketing agent');
  expect(container.textContent).toContain('John Sales');
  expect(container.textContent).toContain('Mary Marketing');
  const officerFilter = [...container.querySelectorAll('label')]
    .find((label) => label.textContent.includes('Sales & Marketing agent'))
    .querySelector('select');
  expect([...officerFilter.options].map((option) => option.textContent))
    .toContain('Mary Marketing');

  const search = container.querySelector('input[placeholder^="Salesperson"]');
  await act(async () => Simulate.change(search, { target: { value: 'Mary' } }));
  expect(container.textContent).toContain('Records (1)');
  const visibleRows = container.querySelector('.sales-visit-table-wrap tbody').textContent;
  expect(visibleRows).toContain('Mary Marketing');
  expect(visibleRows).not.toContain('John Sales');

  await act(async () => root.unmount());
  container.remove();
});

test('registration analytics use API totals and open matching client details', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const totals = {
    visited: 3, started: 2, complete: 1, incomplete: 1, total_registrations: 2,
    unconverted: 1, outstanding_followups: 1, not_started: 1, conversion_rate: 66.67,
    completion_rate: 50, visit_to_complete_rate: 33.33, incomplete_rate: 50,
  };
  const analyticsPayload = {
    daily: { rows: [{
      date: '2026-04-03', weekday: 'Friday', month_label: 'April 2026', category: 'agent',
      visited: 3, started: 2, complete: 1, incomplete: 1, total_registrations: 2,
      unconverted: 1, conversion_rate: 66.67, completion_rate: 50,
      visit_to_complete_rate: 33.33, incomplete_rate: 50,
    }], totals },
    categories: { rows: [{ category: 'agent', label: 'Agent', ...totals }], totals },
    monthly: { rows: [{ month: '2026-04', month_label: 'April 2026', year: '2026', ...totals }], totals },
    yearly: { rows: [{ year: '2026', ...totals }], totals },
    documents: [{
      key: 'certificate_of_incorporation', label: 'Certificate of incorporation',
      category: 'agent', applicable: 2, submitted: 1, pending: 1, rate: 50, priority: 'required',
    }],
    statuses: { rows: [
      { status: 'complete', count: 1, percent: 33.33, missing_requirements: [], recommended_action: 'Registration is complete.' },
      { status: 'incomplete', count: 1, percent: 33.33, missing_requirements: [{ key: 'company_kra_pin', count: 1 }], recommended_action: 'Collect missing documents.' },
      { status: 'not_started', count: 1, percent: 33.33, missing_requirements: ['registration start'], recommended_action: 'Begin registration.' },
    ], totals },
    funnel: { visited: 3, started: 2, complete: 1 },
  };
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('registration-records')
      ? { data: { rows: [{
        id: 1, agent_name: 'Ready Agent', agent_number: 'AG-1', store_number: 'ST-1',
        business_location: 'Nairobi', employee_name: 'Officer One', date_visited: '2026-04-03',
        registration_date: '2026-04-03', registration_status: 'COMPLETE', customer_type: 'agent',
        documents: [{ key: 'certificate_of_incorporation', label: 'Certificate of incorporation', submitted: true }],
        missing_requirements: [], witness_name: 'Witness One', witness_id_number: 'ID-1',
      }], page: 1, per_page: 25, total_rows: 1 } }
      : { data: analyticsPayload },
  }));

  await act(async () => {
    root.render(<SalesReportsPage />);
  });

  await act(async () => {
    Simulate.click([...container.querySelectorAll('.report-view-tabs button')].find((button) => button.textContent === 'Analytics'));
  });

  expect(container.querySelector('.sales-registration-analytics')).not.toBeNull();
  expect(container.textContent).toContain('50.0%');
  expect(container.textContent).toContain('Clients visited');
  expect(container.textContent).toContain('Complete registrations');
  expect(container.textContent).toContain('Incomplete registrations');
  expect(container.textContent).not.toContain('Registrations started');
  expect(container.querySelector('[aria-label="Filter analytics by Agent category"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="Filter Date in daily table"]').getAttribute('type')).toBe('date');
  expect(container.querySelectorAll('.registration-outcome-bar').length).toBeGreaterThan(0);
  expect(container.querySelectorAll('.registration-document-bar').length).toBeGreaterThan(0);
  const groupBy = container.querySelector('[aria-label="Group visits by period"]');
  await act(async () => Simulate.change(groupBy, { target: { value: 'weekday' } }));
  expect(container.querySelector('[aria-label="Filter Day of week in daily table"]').tagName).toBe('SELECT');
  expect([...container.querySelector('[aria-label="Filter Day of week in daily table"]').options].map((option) => option.textContent)).toContain('Friday');
  await act(async () => Simulate.change(groupBy, { target: { value: 'week' } }));
  expect([...container.querySelector('[aria-label="Filter Week in daily table"]').options].map((option) => option.textContent)).toContain('2026-03-30 – 2026-04-05');
  await act(async () => Simulate.change(groupBy, { target: { value: 'month' } }));
  expect([...container.querySelector('[aria-label="Filter Month of year in daily table"]').options].map((option) => option.textContent)).toContain('April');
  await act(async () => Simulate.change(groupBy, { target: { value: 'date' } }));
  const completeStatus = container.querySelector('[aria-label="View 1 Complete clients"]');
  await act(async () => Simulate.click(completeStatus));
  expect(container.querySelector('[role="dialog"]')).not.toBeNull();
  expect(container.querySelector('[role="dialog"]').textContent).toContain('Ready Agent');
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('metric=complete'), expect.any(Object));

  await act(async () => Simulate.click([...container.querySelectorAll('[role="dialog"] button')].find((button) => button.textContent === 'Close')));
  expect(container.querySelector('[role="dialog"]')).toBeNull();

  await act(async () => root.unmount());
  container.remove();
});

test('manager performance ranks complete registrations by completion date and opens exact employee records', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const analyticsPayload = {
    daily: { rows: [], totals: {} },
    categories: { rows: [], totals: {} },
    monthly: { rows: [], totals: {} },
    yearly: { rows: [], totals: {} },
    documents: [],
    statuses: { rows: [] },
  };
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('employee-performance')
      ? { data: {
        total_complete: 2,
        agent_complete: 2,
        sub_agent_complete: 0,
        team_average: 1,
        employee_count: 2,
        rows: [
          { employee_id: 10, employee_name: 'Alex Agent', complete: 2, agent_complete: 2, sub_agent_complete: 0, rank: 1, performance: 'above_average' },
          { employee_id: 11, employee_name: 'Blair Agent', complete: 0, agent_complete: 0, sub_agent_complete: 0, rank: 2, performance: 'needs_support' },
        ],
      } }
      : String(url).includes('registration-records')
        ? { data: { rows: [], page: 1, per_page: 25, total_rows: 0 } }
        : { data: analyticsPayload },
  }));

  await act(async () => {
    root.render(<SalesRegistrationAnalytics
      filters={{ from: '2026-04-01', to: '2026-04-07' }}
      canViewEmployeePerformance
    />);
  });

  expect(container.querySelector('.employee-performance-table')).not.toBeNull();
  expect(container.querySelector('.employee-performance-table').textContent).toContain('Alex Agent');
  expect(container.textContent).toContain('Above peer average');
  expect(container.textContent).toContain('Needs support');
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/analytics/employee-performance?from=2026-04-01&to=2026-04-07'),
    expect.anything(),
  );

  const zeroCount = container.querySelector('[aria-label="View 0 completed registrations for Blair Agent"]');
  await act(async () => Simulate.click(zeroCount));
  await act(async () => Promise.resolve());
  const detailRequest = global.fetch.mock.calls
    .map(([url]) => String(url))
    .find((url) => url.includes('registration-records'));
  expect(detailRequest).toContain('completion_from=2026-04-01');
  expect(detailRequest).toContain('completion_to=2026-04-07');
  expect(detailRequest).not.toMatch(/[?&]from=2026-04-01/);

  await act(async () => root.unmount());
  container.remove();
});
