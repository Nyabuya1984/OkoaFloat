import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import ClientProfileLookup from './ClientProfileLookup';

window.IS_REACT_ACT_ENVIRONMENT = true;

test('searches by a client identifier and requires profile confirmation', async () => {
  const match = {
    agent_name: 'Bahari Test Agent',
    agent_number: 'AG-1',
    store_number: 'STORE-1',
    business_location: 'Nairobi',
    category: 'mpesa_sub_agent',
    source: 'Sales report',
    documents: { business_permit: true },
  };
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ data: { matches: [match] } }),
  });
  const onConfirm = jest.fn();
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<ClientProfileLookup onConfirm={onConfirm} />);
  });
  await act(async () => {
    Simulate.change(container.querySelector('input'), { target: { value: 'AG-1' } });
  });
  await act(async () => {
    Simulate.submit(container.querySelector('form'));
    await Promise.resolve();
  });

  expect(global.fetch).toHaveBeenCalledTimes(1);
  const result = container.querySelector('.client-profile-lookup-result');
  await act(async () => {
    Simulate.click(result);
  });
  expect(onConfirm).not.toHaveBeenCalled();

  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('button'))
      .find((button) => button.textContent === 'Confirm profile details'));
  });
  expect(onConfirm).toHaveBeenCalledWith(match);
  expect(container.textContent).toContain('Profile confirmed and copied into the form.');

  await act(async () => root.unmount());
  container.remove();
});
