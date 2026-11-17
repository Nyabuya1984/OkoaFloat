import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LeaveApplicationWizard from './LeaveApplicationWizard';

jest.mock('../services/leaveApi', () => ({
  createLeaveRequest: jest.fn(),
}));
jest.mock('../services/authStorage', () => ({
  getAuthToken: () => 'test-token',
}));
jest.mock('./HandoverReportForm', () => ({
  __esModule: true,
  default: () => null,
  emptyReport: () => ({}),
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const renderWizard = async (currentUser) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(
    <LeaveApplicationWizard
      currentUser={currentUser}
      leaveTypes={[{ id: 1, code: 'ANNUAL', name: 'Annual Leave' }]}
      colleagues={[]}
      onClose={jest.fn()}
    />,
  ));
  return { container, root };
};

afterEach(() => {
  window.sessionStorage.clear();
  document.body.innerHTML = '';
});

test('read-only account access explains why leave cannot be submitted', async () => {
  const { container, root } = await renderWizard({
    name: 'Immaculate Favour',
    acting_as: { id: 42, name: 'System Administrator' },
  });

  expect(container.textContent).toContain('Leave application unavailable');
  expect(container.textContent).toContain('Leave requests cannot be submitted during read-only account access.');
  expect(container.querySelector('form')).toBeNull();

  await act(async () => root.unmount());
});

test('regular users continue to receive the leave application form', async () => {
  const { container, root } = await renderWizard({ name: 'Employee' });

  expect(container.querySelector('form')).not.toBeNull();
  expect(container.querySelector('button[type="button"]')?.textContent).not.toContain('Return to super admin');

  await act(async () => root.unmount());
});