import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { MemoryRouter } from 'react-router-dom';
import { CallLogsPage, CustomerCarePage } from './CustomerCarePages';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const escalationLog = {
  id: 14,
  reference_number: 'OF-2026-000014',
  customer: { id: 9, name: 'Amina Wanjiku', phone_number: '+254711223344' },
  concern_category: 'RECONCILIATION',
  call_type: 'Incoming',
  priority: 'Urgent',
  status: 'Escalated',
  staff_name: 'Care Agent',
  created_at: '2026-10-23T08:00:00Z',
  requires_escalation: true,
  escalation_resolved: false,
  escalation_id: 21,
};

const response = (data) => ({
  ok: true,
  status: 200,
  headers: { get: () => 'application/json' },
  json: async () => ({ data }),
});

const mount = async (currentUser) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <CallLogsPage currentUser={currentUser} />
      </MemoryRouter>,
    );
  });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  return { container, root };
};

const mountNewCallLog = async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <CustomerCarePage page="customer-care-new" />
      </MemoryRouter>,
    );
  });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  return { container, root };
};

const fill = async (element, value) => {
  await act(async () => Simulate.change(element, { target: { value } }));
};

beforeEach(() => {
  jest.spyOn(global, 'fetch').mockImplementation(async (_url, options = {}) => (
    options.method === 'PATCH'
      ? response({ ...escalationLog, status: 'Resolved', escalation_resolved: true })
      : response([escalationLog])
  ));
  sessionStorage.setItem('okoa_access_token', 'test-token');
});

afterEach(() => {
  global.fetch.mockRestore();
  sessionStorage.clear();
});

test('GM call logs expose call review, escalation brief, and confirmed resolution actions', async () => {
  const { container, root } = await mount({ role: 'manager', department: 'All' });

  expect(container.textContent).toContain('Executive case review');
  expect(container.textContent).toContain('1 open escalation');
  expect(container.querySelector('th:last-child').textContent).toBe('GM actions');
  expect(container.querySelector('tbody tr td:first-child a')).toBeNull();
  expect(container.querySelector('tbody tr td:nth-child(2) a')).toBeNull();
  expect(container.querySelector('a[aria-label="View call OF-2026-000014"]')).not.toBeNull();
  expect(container.querySelector('a[aria-label="View customer profile for Amina Wanjiku"]')).not.toBeNull();
  expect(container.querySelector('a[aria-label="Review escalation OF-2026-000014"]')).not.toBeNull();

  const resolveButton = container.querySelector('button[aria-label="Resolve escalation for OF-2026-000014"]');
  expect(resolveButton).not.toBeNull();
  await act(async () => { resolveButton.click(); });
  expect(container.textContent).toContain('Confirm resolving this escalation?');

  const confirmButton = [...container.querySelectorAll('button')].find(
    (button) => button.textContent.includes('Confirm resolve'),
  );
  await act(async () => {
    confirmButton.click();
    await new Promise((resolve) => setTimeout(resolve, 5));
  });

  expect(global.fetch.mock.calls.some(
    ([url, options]) => url.endsWith('/api/calls/14/resolve-escalation') && options.method === 'PATCH',
  )).toBe(true);
  expect(container.textContent).toContain('was marked resolved.');
  expect(container.textContent).toContain('Resolved');

  await act(async () => root.unmount());
  container.remove();
});

test('non-GM call logs do not show executive resolution actions', async () => {
  const { container, root } = await mount({ role: 'employee', department: 'Customer Care' });

  expect(container.textContent).not.toContain('Executive case review');
  expect(container.textContent).not.toContain('Decision brief');
  expect(container.querySelector('button[aria-label="Resolve escalation for OF-2026-000014"]')).toBeNull();
  expect(container.querySelector('.care-gm-log-actions')).toBeNull();
  expect(container.querySelector('tbody tr td:first-child a')).not.toBeNull();
  expect(container.querySelector('tbody tr td:nth-child(2) a')).not.toBeNull();

  await act(async () => root.unmount());
  container.remove();
});

test('caller ready to register offers the Sales new-client registration workflow', async () => {
  const { container, root } = await mountNewCallLog();
  const concernSelect = [...container.querySelectorAll('select')]
    .find((select) => [...select.options].some((option) => option.value === 'CALLER_READY_TO_REGISTER'));

  expect(concernSelect).not.toBeNull();
  expect([...concernSelect.options].find((option) => option.value === 'CALLER_READY_TO_REGISTER').textContent)
    .toBe('Caller ready to register');
  await act(async () => Simulate.change(concernSelect, { target: { value: 'CALLER_READY_TO_REGISTER' } }));
  await act(async () => Simulate.change(concernSelect, { target: { value: 'CALLER_READY_TO_REGISTER' } }));
  expect(container.querySelector('.sales-report-section h2').textContent).toBe('Register A Client');
  expect(container.textContent).not.toContain('SALES REPORT');
  expect(container.textContent).not.toContain('Add one client record at a time.');
  expect(container.textContent).toContain('Status: ready to register');
  expect(container.textContent).not.toContain('This caller is ready to register.');
  expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Add new client')).toBe(false);
  expect(container.querySelector('textarea[placeholder="What did the customer call about? What was discussed or agreed?"]')).toBeNull();
  expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Save call log')).toBe(false);
  const clientCategory = [...container.querySelectorAll('select')]
    .find((select) => [...select.options].some((option) => option.value === 'mpesa_sub_agent'));
  await act(async () => Simulate.change(clientCategory, { target: { value: 'mpesa_sub_agent' } }));
  expect(container.querySelector('[name="registration_date"]')).not.toBeNull();
  expect(container.querySelectorAll('.sales-documents button')).toHaveLength(6);

  await act(async () => root.unmount());
  container.remove();
});

test('removed registration and repayment concerns are not selectable', async () => {
  const { container, root } = await mountNewCallLog();
  const concernSelect = [...container.querySelectorAll('select')]
    .find((select) => [...select.options].some((option) => option.value === 'INFORMATION_INQUIRY'));
  const options = [...concernSelect.options];

  expect(options.map((option) => option.value)).not.toEqual(
    expect.arrayContaining(['REGISTRATION_HOW', 'REPAYMENT_HOW']),
  );
  expect(options.map((option) => option.textContent)).not.toEqual(
    expect.arrayContaining(['How do I register?', 'How do I repay Okoa Float?']),
  );

  await act(async () => root.unmount());
  container.remove();
});

test('call summary and save controls appear only after client registration completes', async () => {
  global.fetch.mockImplementation(async (_url, options = {}) => (
    options.method === 'POST'
      ? response({ id: 42, outcome: 'ready_to_register', registration_status: 'INCOMPLETE' })
      : response([escalationLog])
  ));
  const { container, root } = await mountNewCallLog();
  const concernSelect = [...container.querySelectorAll('select')]
    .find((select) => [...select.options].some((option) => option.value === 'CALLER_READY_TO_REGISTER'));

  await act(async () => Simulate.change(concernSelect, { target: { value: 'CALLER_READY_TO_REGISTER' } }));
  const categorySelect = [...container.querySelectorAll('select')]
    .find((select) => [...select.options].some((option) => option.value === 'mpesa_agent_dealer'));
  await fill(categorySelect, 'mpesa_agent_dealer');
  await fill(container.querySelector('[name="agent_name"]'), 'Agent One');
  await fill(container.querySelector('[name="agent_number"]'), 'AG-1');
  await fill(container.querySelector('[name="store_number"]'), 'STORE-1');
  await fill(container.querySelector('[name="business_location"]'), 'Nairobi');
  await fill(container.querySelector('[name="registration_date"]'), '2026-10-26');
  await fill(container.querySelector('.sales-witness label:nth-of-type(1) input'), 'Witness');
  await fill(container.querySelector('.sales-witness label:nth-of-type(2) input'), 'ID-1');
  await fill(container.querySelector('.sales-witness label:nth-of-type(3) input'), '0712345678');

  await act(async () => Simulate.submit(container.querySelector('.sales-report-form')));
  await act(async () => {
    [...container.querySelectorAll('.sales-review-summary button')]
      .find((button) => button.textContent === 'Submit').click();
  });

  expect(container.querySelector('.sales-report-section')).toBeNull();
  expect(container.querySelector('textarea[placeholder="What did the customer call about? What was discussed or agreed?"]')).not.toBeNull();
  expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Save call log')).toBe(true);
  expect(container.textContent).toContain('Client registration submitted. Complete and save the Customer Care call log below.');
  await act(async () => root.unmount());
  container.remove();
});
