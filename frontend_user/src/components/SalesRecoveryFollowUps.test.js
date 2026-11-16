import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import SalesRecoveryFollowUps from './SalesRecoveryFollowUps';

window.IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  document.body.innerHTML = '';
});

test('submits checklist and witness details to complete an open recovery task', async () => {
  let listRequests = 0;
  global.fetch = jest.fn((url, options = {}) => {
    if (options.method === 'PATCH') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ data: { status: 'COMPLETE', missing_requirements: [] } }),
      });
    }
    listRequests += 1;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ data: listRequests === 1 ? [{
        report_id: 34, employee_name: 'Field Agent', client_name: 'Recovery Store',
        date_visited: '2026-10-20', due_date: '2026-10-27', customer_type: 'agent',
        missing_requirements: [
          'certificate_of_incorporation', 'company_kra_pin', 'six_months_commission',
          'owners_directors_national_ids', 'cr12_directors',
          'witness_name', 'witness_id_number', 'witness_phone',
        ],
      }] : [] }),
    });
  });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<SalesRecoveryFollowUps />));
  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Update checklist')));
  const checkboxes = container.querySelectorAll('input[type="checkbox"]');
  expect(checkboxes).toHaveLength(5);
  for (const checkbox of checkboxes) {
    await act(async () => Simulate.change(checkbox, { target: { checked: true } }));
  }
  const fields = container.querySelectorAll('form input:not([type="checkbox"])');
  expect(fields).toHaveLength(3);
  for (const [index, field] of [...fields].entries()) {
    await act(async () => Simulate.change(field, { target: { value: `Witness ${index}` } }));
  }
  await act(async () => Simulate.submit(container.querySelector('form')));
  const patch = global.fetch.mock.calls.find(([, options]) => options?.method === 'PATCH');
  expect(patch).toBeDefined();
  const submitted = JSON.parse(patch[1].body);
  expect(Object.values(submitted.documents)).toEqual([true, true, true, true, true]);
  expect(submitted.witness_name).toBe('Witness 0');
  expect(container.textContent).toContain('registration is complete');
  await act(async () => root.unmount());
  container.remove();
});
