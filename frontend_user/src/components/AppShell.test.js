import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { MemoryRouter } from 'react-router-dom';
import AppShell from './AppShell';
import {
  beginAdminUserAccess,
  endAdminUserAccess,
  getAuthToken,
  getRefreshToken,
  hasAdminUserAccessSession,
} from '../services/authStorage';

jest.mock('./Sidebar', () => () => null);
jest.mock('./Topbar', () => () => null);

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const activeUser = {
  id: 2,
  full_name: 'Amina Employee',
  employee_id: 'EMP-002',
  role: 'employee',
  is_active: true,
  account_status: 'approved',
};

beforeEach(() => {
  window.scrollTo = jest.fn();
});

const mountShell = async (props) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter><AppShell {...props} /></MemoryRouter>);
    await Promise.resolve();
  });
  return { container, root };
};

afterEach(() => {
  global.fetch = undefined;
  document.body.innerHTML = '';
});

test('account access restores the original admin token pair', () => {
  window.sessionStorage.clear();
  window.sessionStorage.setItem('okoa_access_token', 'admin-access');
  window.sessionStorage.setItem('okoa_refresh_token', 'admin-refresh');

  beginAdminUserAccess({
    access_token: 'user-access',
    user: { role: 'employee' },
  });

  expect(getAuthToken()).toBe('user-access');
  expect(getRefreshToken()).toBe('');
  expect(hasAdminUserAccessSession()).toBe(true);
  expect(endAdminUserAccess()).toBe(true);
  expect(getAuthToken()).toBe('admin-access');
  expect(getRefreshToken()).toBe('admin-refresh');
  expect(hasAdminUserAccessSession()).toBe(false);
});

test('super admin can select an active approved user account', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    text: async () => JSON.stringify({
      data: [
        activeUser,
        { ...activeUser, id: 3, full_name: 'Pending Employee', account_status: 'pending' },
        { ...activeUser, id: 4, full_name: 'Inactive Employee', is_active: false },
      ],
    }),
  });
  const onStartUserAccess = jest.fn();
  const { container, root } = await mountShell({
    currentUser: { id: 1, name: 'Super Admin', role: 'super_admin', is_superuser: true },
    rolePreview: 'super_admin',
    canPreviewRole: true,
    canAccessUserAccounts: true,
    onStartUserAccess,
  });

  expect(container.querySelector('[aria-label="Super-admin account access"]')?.parentElement.className)
    .toContain('app-shell-content');
  await act(async () => Promise.resolve());
  const selector = container.querySelector('[aria-label="Access a user account"]');
  expect(Array.from(selector.options).map((option) => option.textContent)).toEqual([
    'Choose a user…',
    'Amina Employee (EMP-002)',
  ]);

  await act(async () => {
    Simulate.change(selector, { target: { value: '2' } });
    await Promise.resolve();
  });
  expect(onStartUserAccess).toHaveBeenCalledWith('2');
  await act(async () => root.unmount());
});

test('an accessed account shows a return-to-admin action', async () => {
  const onStopUserAccess = jest.fn();
  const { container, root } = await mountShell({
    currentUser: {
      ...activeUser,
      name: activeUser.full_name,
      acting_as: { id: 1, name: 'Super Admin' },
    },
    onStopUserAccess,
  });

  const button = Array.from(container.querySelectorAll('button'))
    .find((item) => item.textContent === 'Return to super admin');
  expect(button).toBeTruthy();
  await act(async () => {
    Simulate.click(button);
    await Promise.resolve();
  });
  expect(onStopUserAccess).toHaveBeenCalledTimes(1);
  await act(async () => root.unmount());
});
