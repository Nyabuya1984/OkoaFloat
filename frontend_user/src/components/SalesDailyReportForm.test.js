import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import SalesDailyReportForm from './SalesDailyReportForm';

window.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

const mountForm = async (props = {}) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<SalesDailyReportForm {...props} />);
  });
  return { container, root };
};

const choose = (element, value) => Simulate.change(element, { target: { value } });
const fill = async (element, value) => {
  await act(async () => Simulate.change(element, { target: { value } }));
};

const startNewClient = async (container) => {
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'New Client')));
};

afterEach(() => {
  global.fetch = originalFetch;
  window.sessionStorage.clear();
  document.body.innerHTML = '';
});

test('new client outcomes expose appointment fields only for appointments', async () => {
  const { container, root } = await mountForm();
  await startNewClient(container);
  await act(async () => {
    choose(container.querySelector('select'), 'appointment');
  });

  expect(container.querySelector('input[type="date"]')).not.toBeNull();
  expect(container.querySelector('input[type="time"]')).not.toBeNull();
  expect(container.querySelectorAll('select')).toHaveLength(2);
  expect(container.textContent).toContain('Telesales');
  expect(container.textContent).toContain('Remarks');
  expect(container.textContent).toContain('Review report');

  await act(async () => root.unmount());
});

test('review does not show an unselected category for a new interested client', async () => {
  const { container, root } = await mountForm();
  await startNewClient(container);
  await fill(container.querySelector('select'), 'interested');
  await fill(container.querySelector('[name="agent_name"]'), 'Agent One');
  await fill(container.querySelector('[name="agent_number"]'), 'AG-1');
  await fill(container.querySelector('[name="store_number"]'), 'STORE-1');
  await fill(container.querySelector('[name="business_location"]'), 'Nairobi');
  await fill(container.querySelector('textarea'), 'Interested in the service');

  await act(async () => Simulate.submit(container.querySelector('form')));

  expect(container.querySelector('[name="business_owner_name"]')).toBeNull();
  expect([...container.querySelectorAll('.sales-review-summary dt')].map((item) => item.textContent)).not.toContain('Category');
  await act(async () => root.unmount());
});

test('registration checklist and status are selected by category and all required documents', async () => {
  const { container, root } = await mountForm();
  await startNewClient(container);
  await act(async () => {
    choose(container.querySelector('select'), 'ready_to_register');
  });

  expect(container.querySelector('.registration-status')).toBeNull();
  await act(async () => {
    choose(container.querySelectorAll('select')[1], 'mpesa_sub_agent');
  });
  expect(container.querySelectorAll('.sales-documents button')).toHaveLength(6);
  expect(container.querySelector('.registration-status strong').textContent).toBe('INCOMPLETE');
  expect(container.textContent).toContain('Missing required documents:');
  expect(container.textContent).toContain('Business permit');

  const documentButtons = [...container.querySelectorAll('.sales-documents button')];
  await act(async () => {
    documentButtons.forEach((button) => Simulate.click(button));
  });
  expect(container.querySelector('.registration-status strong').textContent).toBe('INCOMPLETE');
  const witnessFields = container.querySelectorAll('.sales-witness input');
  await fill(witnessFields[0], 'Witness One');
  await fill(witnessFields[1], 'ID-1');
  await fill(witnessFields[2], '0712345678');
  expect(container.querySelector('.registration-status strong').textContent).toBe('COMPLETE');
  expect(container.querySelector('.sales-witness')).not.toBeNull();

  await act(async () => root.unmount());
});

test('looks up and confirms an existing client before submitting an interaction', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 201,
    json: async () => ({ data: { id: 42, outcome: 'existing' } }),
  });
  global.fetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    json: async () => ({
      data: {
        matches: [{
          source: 'Sales report',
          agent_name: 'Agent One',
          agent_number: 'AG-1',
          store_number: 'STORE-1',
          business_location: 'Nairobi',
          category: 'mpesa_agent',
          documents: { certificate_of_incorporation: true },
          owner_name: 'Owner One',
          owner_id_number: 'ID-101',
          owner_phone_number: '0712345678',
        }],
      },
    }),
  });
  const onSubmitted = jest.fn();
  const { container, root } = await mountForm({ onSubmitted });
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Existing Client')));
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Search saved client profile')));
  await fill(container.querySelector('.sales-lookup-controls input'), 'AG-1');
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Search clients')));
  await act(async () => Simulate.click(container.querySelector('.sales-lookup-result')));
  expect(container.querySelector('[name="agent_name"]').value).toBe('Agent One');
  expect(container.querySelector('[name="agent_number"]').value).toBe('AG-1');
  expect(container.textContent).toContain('Previously recorded document checklist');
  expect(container.textContent).toContain('Source: Sales report');
  await fill(container.querySelector('textarea'), 'Visited the outlet');
  await act(async () => Simulate.click([...container.querySelectorAll('.sales-choice-buttons button')].find((button) => button.textContent === 'NO')));

  await act(async () => Simulate.submit(container.querySelector('form')));
  expect(global.fetch).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Review client report');
  expect(container.textContent).toContain('Recorded: Certificate of incorporation / Registration');
  expect(container.textContent).toContain('No report is submitted until you select');
  const addButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Add Client');
  expect(addButton.disabled).toBe(true);
  await act(async () => Simulate.change(container.querySelector('.sales-autofill-confirm input'), { target: { checked: true } }));

  await act(async () => Simulate.click(addButton));
  expect(global.fetch).toHaveBeenCalledTimes(2);
  expect(global.fetch.mock.calls[1][0]).toContain('/api/sales/reports');
  const requestBody = global.fetch.mock.calls[1][1].body;
  expect(requestBody.get('agent_name')).toBe('Agent One');
  expect(requestBody.get('agent_number')).toBe('AG-1');
  expect(requestBody.get('store_number')).toBe('STORE-1');
  expect(requestBody.get('business_location')).toBe('Nairobi');
  expect(requestBody.get('referral_agreed')).toBe('no');
  expect(container.textContent).toContain('Record #42');
  expect(container.textContent).toContain('Step 1 is ready for the next client.');
  expect(onSubmitted).toHaveBeenCalledTimes(1);
  await act(async () => root.unmount());
});

test('existing client can be entered manually and referral details are submitted when agreed', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 201,
    json: async () => ({ data: { id: 44, outcome: 'existing' } }),
  });
  const { container, root } = await mountForm();
  expect(container.textContent).toContain('Choose client type');
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Existing Client')));
  expect(container.querySelector('select').textContent).toContain('M-Pesa Sub-Agent');
  await fill(container.querySelector('select'), 'mpesa_sub_agent');
  await fill(container.querySelector('[name="agent_name"]'), 'Sub-Agent One');
  await fill(container.querySelector('[name="agent_number"]'), 'SUB-1');
  await fill(container.querySelector('[name="store_number"]'), 'STORE-2');
  await fill(container.querySelector('[name="business_location"]'), 'Mombasa');
  await fill(container.querySelector('textarea'), 'Visited and discussed referrals');
  await act(async () => Simulate.click([...container.querySelectorAll('.sales-choice-buttons button')].find((button) => button.textContent === 'YES')));
  await fill(container.querySelector('[name="referral_name"]'), 'Referral One');
  await fill(container.querySelector('[name="referral_contact_number"]'), '0711222333');
  await fill(container.querySelector('[name="referral_details"]'), 'Nearby business owner');

  await act(async () => Simulate.submit(container.querySelector('form')));
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Add Client')));

  const body = global.fetch.mock.calls[0][1].body;
  expect(body.get('customer_type')).toBe('sub_agent');
  expect(body.get('business_location')).toBe('Mombasa');
  expect(body.get('notes')).toBe('Visited and discussed referrals');
  expect(body.get('referral_agreed')).toBe('yes');
  expect(body.get('referral_name')).toBe('Referral One');
  expect(body.get('referral_contact_number')).toBe('0711222333');
  expect(body.get('referral_details')).toBe('Nearby business owner');
  await act(async () => root.unmount());
});

test('ready-to-register review lists missing documents and allows incomplete confirmation', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 201,
    json: async () => ({ data: { id: 43, registration_status: 'INCOMPLETE' } }),
  });
  const { container, root } = await mountForm();
  await startNewClient(container);
  await fill(container.querySelector('select'), 'ready_to_register');
  await fill(container.querySelectorAll('select')[1], 'mpesa_sub_agent');
  expect(container.querySelector('input[type="date"]')).not.toBeNull();
  expect(container.querySelector('input[name="registration_date"]').required).toBe(true);
  expect(container.querySelector('[name="business_owner_name"]')).toBeNull();
  expect(container.querySelector('[name="notes"]')).not.toBeNull();
  await fill(container.querySelector('[name="notes"]'), 'Caller submitted initial registration details.');
  const inputs = container.querySelectorAll('input');
  for (let i = 0; i < inputs.length; i += 1) {
    await fill(inputs[i], inputs[i].type === 'date' ? '2026-10-23' : `Value ${i}`);
  }

  await act(async () => Simulate.submit(container.querySelector('form')));
  expect(global.fetch).not.toHaveBeenCalled();
  expect(container.textContent).toContain('Registration status');
  expect(container.textContent).toContain('Caller submitted initial registration details.');
  expect(container.textContent).toContain('Registration date');
  expect(container.textContent).toContain('INCOMPLETE');
  expect(container.textContent).toContain('Missing: Business permit');
  expect(container.textContent).toContain('Missing: Sign Contract');

  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Add Client')));
  expect(global.fetch).toHaveBeenCalledTimes(1);
  expect(global.fetch.mock.calls[0][1].body.get('registration_date')).toBe('2026-10-23');
  expect(global.fetch.mock.calls[0][1].body.get('notes')).toBe('Caller submitted initial registration details.');
  expect(container.textContent).toContain('Registration status: INCOMPLETE');
  await act(async () => root.unmount());
});

test('agent/dealer registration displays only its five required document toggles', async () => {
  const { container, root } = await mountForm();
  await startNewClient(container);
  await act(async () => {
    choose(container.querySelector('select'), 'ready_to_register');
  });
  await act(async () => {
    choose(container.querySelectorAll('select')[1], 'mpesa_agent_dealer');
  });

  expect([...container.querySelectorAll('select')][1].options[1].textContent).toBe('M-Pesa Agent / M-Pesa Dealer');
  expect([...container.querySelectorAll('select')][1].options[2].textContent).toBe('M-Pesa Sub-Agent');
  const documentLabels = [...container.querySelectorAll('.sales-documents button')].map((button) => button.textContent);
  expect(documentLabels).toHaveLength(5);
  expect(documentLabels).toEqual(expect.arrayContaining([
    'Certificate of incorporation / Registration',
    'Six months Commission Statement',
    'CR12 for directors',
  ]));
  expect(documentLabels).not.toContain('Sign Contract');

  await act(async () => root.unmount());
});
