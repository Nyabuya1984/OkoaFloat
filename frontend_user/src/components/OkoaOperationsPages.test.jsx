import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import apiClient from '../services/debtCollectionApi';
import {
  AgentShiftMatrixPage,
  EscalationDetailPage,
  EscalationListPage,
  GmAttentionReportPage,
  OkoaOverviewPage,
} from './OkoaOperationsPages';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('../services/debtCollectionApi', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() },
}));

const mountPage = async (page, { entry = '/okia/test', route = '/okia/test' } = {}) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter
        initialEntries={[entry]}
        future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
      >
        <Routes><Route path={route} element={page} /></Routes>
      </MemoryRouter>,
    );
    await Promise.resolve();
  });
  await act(async () => { await Promise.resolve(); });
  return { container, root };
};

const openGmDrilldown = async (container) => {
  const drilldown = container.querySelector('.care-gm-drilldown');
  await act(async () => {
    drilldown.open = true;
    drilldown.dispatchEvent(new Event('toggle'));
    await Promise.resolve();
  });
};

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.patch.mockReset();
  apiClient.get.mockResolvedValue({ data: { data: [] } });
});

test('EscalationList renders and loads the escalation queue', async () => {
  const { container, root } = await mountPage(<EscalationListPage />);
  expect(container.textContent).toContain('Escalation queue');
  expect(container.textContent).toContain('No escalations match these filters.');
  expect(apiClient.get).toHaveBeenCalledWith('/api/escalations?status=open');
  await act(async () => root.unmount());
  container.remove();
});

test('EscalationList shows customer details and resolves open cases from Actions', async () => {
  apiClient.get.mockResolvedValueOnce({
    data: {
      data: [{
        id: 17,
        call_id: 5,
        reference_number: 'OF-2026-000005',
        customer: { name: 'Test Customer', phone_number: '+254700000005' },
        to_dept: 'general_manager',
        reason: 'Test escalation reason',
        status: 'open',
        created_at: '2026-10-23T09:00:00',
      }],
    },
  });
  apiClient.patch.mockResolvedValue({
    data: { data: { id: 17, status: 'resolved', resolved_at: '2026-10-23T09:30:00' } },
  });
  const { container, root } = await mountPage(<EscalationListPage />);

  expect(container.textContent).toContain('Test Customer');
  expect(container.textContent).toContain('+254700000005');
  expect(container.querySelector('th:last-child').textContent).toBe('Actions');
  const resolveButton = container.querySelector(
    'button[aria-label="Resolve escalation OF-2026-000005"]',
  );
  expect(resolveButton).not.toBeNull();

  await act(async () => {
    resolveButton.click();
    await Promise.resolve();
  });

  expect(apiClient.patch).toHaveBeenCalledWith('/api/escalations/17/resolve', {});
  expect(container.textContent).toContain('OF-2026-000005 was resolved.');
  expect(container.textContent).toContain('No escalations match these filters.');
  await act(async () => root.unmount());
  container.remove();
});

test('GM overview shows compact department snapshots from the shift report', async () => {
  apiClient.get.mockImplementation((path) => Promise.resolve({
    data: {
      data: path === '/api/reports/gm/shift-overview'
        ? {
          date: '2026-10-23',
          shift_code: 'A',
          department_snapshots: {
            sales_marketing: { new_registrations: 2, appointments: 3, pending_documents: 1 },
            debt_collection: { calls_made: 8, promises_to_pay: 2, default_escalations: 1 },
            customer_care: {
              calls_handled: 12,
              first_contact_resolution_rate: 0.75,
              open_tickets: 4,
            },
          },
        }
        : [],
    },
  }));
  const { container, root } = await mountPage(<OkoaOverviewPage />);

  expect(container.textContent).toContain('Department performance');
  expect(container.textContent).toContain('General Manager Executive Overview');
  expect(container.textContent).toContain('First recorded call per client in this shift/date; based on logged call status.');
  expect(container.textContent).toContain('Agents are staff with calls recorded in this shift/date. Manager roles come from active organizational assignments; they are not a shift-duty roster.');
  expect(container.querySelector('.care-gm-shift-metrics')).not.toBeNull();
  expect(container.querySelectorAll('.care-gm-shift-metric')).toHaveLength(4);
  expect(container.textContent).not.toContain('Department managers on duty');
  expect(container.textContent).toContain('Sales & Marketing');
  expect(container.textContent).toContain('New registrations2');
  expect(container.textContent).toContain('Debt Collection');
  expect(container.textContent).toContain('Promises to pay2');
  expect(container.textContent).toContain('Customer Care');
  expect(container.textContent).toContain('First-contact resolution75%');
  expect(container.textContent).toContain('Open Debt Collection operations');
  expect(container.textContent).toContain('Open Customer Care activity');
  expect(apiClient.get).not.toHaveBeenCalledWith('/api/escalations?status=open');
  expect(container.querySelector('a[href="/dashboard/reports/sales"]')).not.toBeNull();
  expect(container.querySelector('a[href="/dashboard/debt-collection"]')).not.toBeNull();
  const drilldown = container.querySelector('.care-gm-drilldown');
  expect(drilldown.open).toBe(false);
  await openGmDrilldown(container);
  expect(apiClient.get).toHaveBeenCalledWith('/api/escalations?status=open');
  expect(container.textContent).toContain('Open escalations');

  await act(async () => root.unmount());
  container.remove();
});

test('GM overview stays visible when optional report collections are malformed', async () => {
  apiClient.get.mockImplementation((path) => Promise.resolve({
    data: {
      data: path === '/api/reports/gm/shift-overview'
        ? { manager: {}, team_leader: {}, department_snapshots: {} }
        : path.startsWith('/api/shifts/coverage?')
          ? { shifts: {} }
          : path.startsWith('/api/reports/concerns?')
            ? { categories: {} }
            : path === '/api/escalations?status=open'
              ? { items: {} }
              : [],
    },
  }));
  const { container, root } = await mountPage(<OkoaOverviewPage />);

  expect(container.textContent).toContain('General Manager Executive Overview');
  expect(container.textContent).toContain('Sales & Marketing');
  expect(container.textContent).toContain('Debt Collection');
  expect(container.textContent).toContain('Customer Care');
  expect(apiClient.get).not.toHaveBeenCalledWith('/api/shifts/coverage?from=2026-10-23&to=2026-10-23');

  await openGmDrilldown(container);
  expect(container.textContent).toContain('No calls have been logged today.');

  await act(async () => root.unmount());
  container.remove();
});

test('GM overview renders coverage agents as names instead of raw objects', async () => {
  apiClient.get.mockImplementation((path) => Promise.resolve({
    data: {
      data: path.startsWith('/api/shifts/coverage?')
        ? [{
          shift: 'A',
          total_calls: 2,
          resolved: 1,
          escalated: 1,
          agents_on_duty: [{ id: 7, name: 'Care Agent' }],
        }]
        : [],
    },
  }));
  const { container, root } = await mountPage(<OkoaOverviewPage />);

  expect(container.textContent).toContain('General Manager Executive Overview');
  await openGmDrilldown(container);
  expect(container.textContent).toContain('Care Agent');

  await act(async () => root.unmount());
  container.remove();
});

test('Escalation details render the structured General Manager briefing', async () => {
  const sections = [
    {
      id: 'client',
      title: 'Client overview & call history',
      client: {
        name: 'Test Customer',
        agent_name: 'Agent One',
        agent_number: 'AG-1',
        store_number: 'STORE-1',
        category: 'agent',
        business_location: 'Nairobi',
      },
      call_history: [{
        id: 4,
        reference_number: 'OF-2026-000004',
        date_time: '2026-10-23T08:00:00Z',
        direction: 'Incoming',
        category: 'RECONCILIATION',
        status: 'Escalated',
        remarks: 'Payment is not reflected.',
        handling_agent: 'Care Agent',
        staff_id: 'CC-4',
      }],
    },
    {
      id: 'shift',
      title: 'Shift context & roster',
      shift: { shift_id: 'A', date: '2026-10-23', call_time: '2026-10-23T08:00:00+03:00' },
      on_duty_personnel: { general_manager: [{ name: 'General Manager', staff_id: 'GM-1' }] },
      customer_care_agents: [{ name: 'Care Agent', staff_id: 'CC-4', calls_handled: 1 }],
      roster_note: 'Roster derived from recorded calls.',
    },
    {
      id: 'agent_activity',
      agent: { name: 'Care Agent', staff_id: 'CC-4' },
      shift_activity: { clients_served: 1, resolved_on_spot: 0, escalated_or_pending: 1 },
      call_log: [],
    },
    {
      id: 'escalation',
      reason: 'Payment is not reflected.',
      customer_care_agent_remarks: 'Customer provided transaction reference.',
      recommended_action: 'Confirm payment posting.',
      priority: 'Urgent',
      department: 'Customer Care',
      client: 'Test Customer',
      agent_number: 'AG-1',
      store_number: 'STORE-1',
      handling_agent: 'Care Agent',
      handling_agent_staff_id: 'CC-4',
      team_leader: { name: 'Care TL', staff_id: 'TL-1' },
      shift_manager: { name: 'Care Manager', staff_id: 'DM-1' },
      root_cause: 'Payment is not reflected.',
      impact: 'Open payment dispute.',
      agent_workload: { clients_served: 5, resolved: 3, escalated: 2 },
    },
  ];
  apiClient.get.mockImplementation((path) => {
    if (path === '/api/reports/gm/escalations/17') {
      return Promise.resolve({
        data: {
          data: {
            escalation: { status: 'open' },
            sections,
          },
        },
      });
    }
    return Promise.resolve({
      data: {
        data: {
          id: 17,
          call_id: 4,
          reference_number: 'OF-2026-000004',
          status: 'open',
          reason: 'Payment is not reflected.',
          call: { reference_number: 'OF-2026-000004', customer: { name: 'Test Customer' } },
        },
      },
    });
  });
  const { container, root } = await mountPage(
    <EscalationDetailPage />,
    { entry: '/okia/test/17', route: '/okia/test/:escalationId' },
  );

  expect(container.textContent).toContain('GENERAL MANAGER BRIEFING');
  expect(container.textContent).toContain('Expand Full Client Call & History Log');
  expect(container.textContent).toContain('Ticket #OF-2026-000004');
  expect(container.textContent).toContain('Department Manager');
  expect(container.textContent).toContain('Agent One');
  expect(container.textContent).toContain('Care Agent');
  expect(container.textContent).toContain('Agent workload this shift');
  expect(container.textContent).toContain('Expand Agent Work History for Shift');
  expect(container.textContent).toContain('Expand Submitted Documents Checklist');
  expect(container.textContent).toContain('Recommended decision');
  expect(container.textContent).toContain('Confirm payment posting.');
  expect([...container.querySelectorAll('.care-gm-collapsible')].every((item) => !item.open)).toBe(true);
  expect(apiClient.get).toHaveBeenCalledWith('/api/reports/gm/escalations/17');
  await act(async () => root.unmount());
  container.remove();
});

test('GmAttentionReport renders the report page', async () => {
  const { container, root } = await mountPage(<GmAttentionReportPage />);
  expect(container.textContent).toContain('GM attention report');
  expect(container.textContent).toContain('No report data for this date range.');
  expect(apiClient.get).toHaveBeenCalledWith('/api/reports/gm/attention');
  await act(async () => root.unmount());
  container.remove();
});

test('AgentShiftMatrix renders its report columns', async () => {
  const { container, root } = await mountPage(<AgentShiftMatrixPage />);
  expect(container.textContent).toContain('Agent / shift matrix');
  expect(container.textContent).toContain('No report data for this date range.');
  expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining('/api/reports/gm/agent-shift-matrix?'));
  await act(async () => root.unmount());
  container.remove();
});
