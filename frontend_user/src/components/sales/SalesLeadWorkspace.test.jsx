import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import SalesLeadWorkspace from './SalesLeadWorkspace';

window.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  document.body.innerHTML = '';
});

test('manager call sheet exposes standardized outcomes, import, distribution and export controls', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('/assignees')
      ? { data: [{ id: 8, full_name: 'Sales Rep' }] }
      : String(url).includes('/analytics')
        ? { data: { statuses: { new_or_existing: 1 }, employees: [], funnel: {} } }
        : String(url).includes('/assignments/bulk')
          ? { data: { assigned: 1 } }
        : String(url).includes('/follow-ups')
          ? { data: [{ id: 33, lead_name: 'Follow-up Lead', phone_number: '+254700000033' }] }
        : { data: [{
          id: 4, lead_name: 'Jane Owner', phone_number: '+254700000077',
          company_name: 'Jane Shop', status: 'new', assigned_to_id: null, call_logs: [],
        }] },
  }));

  await act(async () => root.render(<SalesLeadWorkspace canManage />));
  const filters = container.querySelector('.sales-lead-filters');
  const allocation = container.querySelector('[aria-label="Share selected leads"]');
  const followUps = container.querySelector('[aria-label="Follow-up tasks"]');
  const table = container.querySelector('.sales-lead-table-wrap');
  expect(filters.compareDocumentPosition(followUps) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(followUps.compareDocumentPosition(allocation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(allocation.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(allocation.className).toContain('sales-lead-allocation');
  const outcome = container.querySelector('select[aria-label="Outcome for Jane Owner"]');
  await act(async () => Simulate.change(outcome, { target: { value: 'appointment' } }));
  expect(container.querySelector('input[type="datetime-local"][required]')).not.toBeNull();
  const saveCallButton = container.querySelector('[aria-label="Save call for Jane Owner"]');
  expect(saveCallButton.textContent.trim()).toBe('Save call');
  expect(saveCallButton.className).toContain('sales-lead-save-call');
  await act(async () => Simulate.click(saveCallButton));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/leads/4/calls'),
    expect.objectContaining({ method: 'POST' }),
  );
  expect(container.textContent).toContain('Call outcome saved for Jane Owner.');
  expect(container.querySelector('input[aria-label="Select Jane Owner"]')).not.toBeNull();
  expect(container.textContent).toContain("Director's Name");
  expect(container.textContent).toContain('Download lead template');
  expect(container.textContent).toContain('Upload prospect list (CSV or Excel .xlsx)');
  expect(container.textContent).toContain('Distribute uploaded leads evenly');
  expect(container.textContent).toContain('Split selected evenly');
  expect(container.textContent).toContain('New');
  expect(container.textContent).toContain('Wrong Number');
  expect(container.textContent).toContain('Export filtered lead sheet Excel');
  expect(container.textContent).toContain('Export filtered lead sheet PDF');
  expect(container.textContent).toContain('Export call history CSV');
  expect(container.textContent).toContain('Export call history Excel');
  expect(container.textContent).toContain('Export call history PDF');
  expect(container.querySelector('a[href="tel:+254700000077"]')).not.toBeNull();

  await act(async () => Simulate.change(
    container.querySelector('input[aria-label="Select Jane Owner"]'),
    { target: { checked: true } },
  ));
  await act(async () => Simulate.change(
    container.querySelector('.sales-lead-allocation select'),
    { target: { value: '8' } },
  ));
  const assignButton = [...container.querySelectorAll('button')]
    .find((button) => button.textContent === 'Assign selected');
  await act(async () => Simulate.click(assignButton));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/leads/assignments/bulk'),
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ lead_ids: [4], employee_id: 8 }),
    }),
  );

  await act(async () => root.unmount());
  container.remove();
});

test('agent dashboard separates contacted clients from the active call queue', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  let contacted = false;
  const getLead = () => ({
    id: 41,
    lead_name: 'Queue Prospect',
    phone_number: '+254700000041',
    status: contacted ? 'interested' : 'new',
    assigned_to_id: 7,
    call_logs: contacted ? [{
      id: 93,
      response: 'interested',
      reached: true,
      contacted_by_name: 'Sales Agent',
      contact_date: '2026-10-30',
      contact_day: 'Friday',
      contact_time: '10:00:00',
    }] : [],
  });
  global.fetch = jest.fn((url, options = {}) => {
    if (String(url).includes('/analytics')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: {
        call_attempts: 1,
        reached_calls: 1,
        reachability_rate: 100,
        registration_counts: { COMPLETE: 1, INCOMPLETE: 0 },
        statuses: { interested: 1 },
        funnel: { assigned: 1, attempted: 1, reached: 1 },
        employees: [],
        incomplete_bottlenecks: [],
      } }) });
    }
    if (String(url).includes('/follow-ups')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: [] }) });
    }
    if (String(url).includes('/calls') && options.method === 'POST') {
      contacted = true;
      return Promise.resolve({ ok: true, status: 201, json: async () => ({ data: {} }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: [getLead()] }) });
  });

  await act(async () => root.render(<SalesLeadWorkspace />));
  expect(container.textContent).toContain('Calls attempted');
  expect(container.querySelector('[aria-selected="true"]').textContent).toContain('Active call queue');
  await act(async () => Simulate.click(container.querySelector('[aria-label="Save call for Queue Prospect"]')));
  expect(container.textContent).toContain('All assigned leads have been contacted.');

  await act(async () => Simulate.click(
    [...container.querySelectorAll('[role="tab"]')].find((tab) => tab.textContent.includes('Contacted clients')),
  ));
  expect(container.textContent).toContain('Contacted clients · shared history');
  expect(container.querySelector('.sales-lead-response-tag.is-interested')).not.toBeNull();

  await act(async () => root.unmount());
  container.remove();
});

test('reporting period and response filters are applied to the lead list', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  global.fetch = jest.fn(() => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({ data: [] }),
  }));

  await act(async () => root.render(<SalesLeadWorkspace />));
  const filters = container.querySelector('.sales-lead-filters');
  const dateInput = filters.querySelector('input[type="date"]');
  const responseSelect = filters.querySelectorAll('select')[1];

  await act(async () => Simulate.change(dateInput, { target: { value: '2026-10-01' } }));
  await act(async () => Simulate.change(responseSelect, { target: { value: 'interested' } }));

  const leadListRequest = global.fetch.mock.calls
    .map(([url]) => String(url))
    .find((url) => url.includes('/api/sales/leads?') && url.includes('status=interested'));
  expect(leadListRequest).toContain('from=2026-10-01');
  expect(leadListRequest).toContain('status=interested');

  await act(async () => root.unmount());
  container.remove();
});

test('agent can route a lead escalation to management with a reason', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const lead = {
    id: 51,
    lead_name: 'Escalation Prospect',
    phone_number: '+254700000051',
    status: 'interested',
    assigned_to_id: 7,
    call_logs: [{ id: 101, response: 'interested', reached: true }],
  };
  global.fetch = jest.fn((url, options = {}) => {
    if (String(url).includes('/analytics')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: {
        call_attempts: 0, reached_calls: 0, reachability_rate: 0,
        registration_counts: {}, statuses: {}, funnel: {}, employees: [],
        incomplete_bottlenecks: [],
      } }) });
    }
    if (String(url).includes('/follow-ups')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: [] }) });
    }
    if (String(url).includes('/escalations') && options.method === 'POST') {
      return Promise.resolve({ ok: true, status: 201, json: async () => ({ data: { notified_count: 1 } }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: [lead] }) });
  });

  await act(async () => root.render(<SalesLeadWorkspace />));
  await act(async () => Simulate.click(
    [...container.querySelectorAll('[role="tab"]')].find((tab) => tab.textContent.includes('Contacted clients')),
  ));
  const reason = container.querySelector('[aria-label="Escalation reason for Escalation Prospect"]');
  await act(async () => Simulate.change(reason, { target: { value: 'Compliance dispute requires review.' } }));
  await act(async () => Simulate.click(container.querySelector('.sales-lead-escalate-button')));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/leads/51/escalations'),
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        level: 'group_leader',
        reason: 'Compliance dispute requires review.',
      }),
    }),
  );
  expect(container.textContent).toContain('Escalation sent for Escalation Prospect.');

  await act(async () => root.unmount());
  container.remove();
});

test('manager can split selected assigned leads after entering a reassignment reason', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('/assignees')
      ? { data: [{ id: 8, full_name: 'Sales Rep' }, { id: 9, full_name: 'Second Rep' }] }
      : String(url).includes('/analytics')
        ? { data: { statuses: {}, employees: [], funnel: {} } }
        : String(url).includes('/follow-ups')
          ? { data: [] }
          : String(url).includes('/leads/distribute')
            ? { data: { assigned: 1, representatives: 2 } }
            : { data: [{
              id: 12, lead_name: 'Assigned Owner', phone_number: '+254700000012',
              status: 'interested', assigned_to_id: 8, assignee_name: 'Sales Rep', call_logs: [],
            }] },
  }));
  await act(async () => root.render(<SalesLeadWorkspace canManage />));
  await act(async () => Simulate.change(
    container.querySelector('input[aria-label="Select Assigned Owner"]'),
    { target: { checked: true } },
  ));
  const reassignmentReason = container.querySelector(
    '[aria-label="Share selected leads"] input[required]',
  );
  expect(reassignmentReason).not.toBeNull();
  const splitButton = [...container.querySelectorAll('button')]
    .find((button) => button.textContent === 'Split selected evenly');
  expect(splitButton.disabled).toBe(true);

  await act(async () => Simulate.change(reassignmentReason, {
    target: { value: 'Balance current workloads' },
  }));
  expect(splitButton.disabled).toBe(false);
  await act(async () => Simulate.click(splitButton));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/leads/distribute'),
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        lead_ids: [12],
        reason: 'Balance current workloads',
      }),
    }),
  );

  await act(async () => root.unmount());
  container.remove();
});

test('manager can view, edit, archive, and filter leads from compact table actions', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('/assignees')
      ? { data: [{ id: 8, full_name: 'Sales Rep' }] }
      : String(url).includes('/analytics')
        ? { data: { statuses: {}, employees: [], funnel: {} } }
        : String(url).includes('/follow-ups')
          ? { data: [] }
          : { data: [{
            id: 21,
            lead_name: 'Jane Owner',
            director_name: 'Jane Owner',
            phone_number: '+254700000021',
            business_name: 'Jane Shop',
            company_name: 'Jane Shop',
            business_location: 'Westlands',
            head_office_location: 'Nairobi',
            status: 'interested',
            assigned_to_id: null,
            call_logs: [],
          }] },
  }));
  await act(async () => root.render(<SalesLeadWorkspace canManage />));
  expect(container.querySelector('.sales-lead-table.is-manager')).not.toBeNull();
  expect(container.querySelector('.sales-lead-select-header').textContent.trim()).toBe('');
  expect(container.querySelector('[aria-label="Select all visible leads"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="Edit Jane Owner"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="Delete Jane Owner"]')).not.toBeNull();

  await act(async () => Simulate.change(container.querySelector('[aria-label="Filter location"]'), {
    target: { value: 'Westlands' },
  }));
  expect(container.querySelectorAll('.sales-lead-table tbody tr')).toHaveLength(1);
  await act(async () => Simulate.change(container.querySelector('[aria-label="Filter location"]'), {
    target: { value: 'Mombasa' },
  }));
  expect(container.querySelectorAll('.sales-lead-table tbody tr')).toHaveLength(0);
  await act(async () => Simulate.click(container.querySelector('.sales-lead-filter-row button')));

  await act(async () => Simulate.click(container.querySelector('[aria-label="View Jane Owner"]')));
  expect(container.querySelector('[role="dialog"]')).not.toBeNull();
  expect(container.querySelector('[role="dialog"]').textContent).toContain('Westlands');
  await act(async () => Simulate.click(container.querySelector('[role="dialog"] button')));

  await act(async () => Simulate.click(container.querySelector('[aria-label="Edit Jane Owner"]')));
  const businessInput = container.querySelector('[aria-label="Business name"]');
  await act(async () => Simulate.change(businessInput, { target: { value: 'Updated Shop' } }));
  await act(async () => Simulate.submit(container.querySelector('form[role="dialog"]')));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/leads/21/details'),
    expect.objectContaining({
      method: 'PATCH',
      body: expect.stringContaining('"business_name":"Updated Shop"'),
    }),
  );

  await act(async () => Simulate.click(container.querySelector('[aria-label="Delete Jane Owner"]')));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/sales/leads/21'),
    expect.objectContaining({ method: 'DELETE' }),
  );
  confirm.mockRestore();
  await act(async () => root.unmount());
  container.remove();
});

test('call sheet requires decline reasons and registration incompleteness details', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    json: async () => String(url).includes('/follow-ups') ? { data: [] } : { data: [{
      id: 9, lead_name: 'Amina', phone_number: '+254700000088', status: 'new_or_existing',
      assigned_to_id: 8, call_logs: [],
    }] },
  }));
  await act(async () => root.render(<SalesLeadWorkspace />));
  const outcome = container.querySelector('select[aria-label="Outcome for Amina"]');
  await act(async () => Simulate.change(outcome, { target: { value: 'not_interested' } }));
  expect(container.querySelector('input[required]')).not.toBeNull();
  await act(async () => Simulate.change(outcome, { target: { value: 'registered' } }));
  expect(container.textContent).toContain('Director ID copy');
  expect(container.textContent).toContain('Reason registration is incomplete');
  expect(container.querySelector('.sales-registration-documents').open).toBe(false);
  await act(async () => root.unmount());
  container.remove();
});
