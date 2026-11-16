import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { organizationApi } from '../services/organizationApi';
import ManagedUsersPanel from './ManagedUsersPanel';

window.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('../services/organizationApi', () => ({
  organizationApi: {
    getTransferCandidates: jest.fn(),
  },
}));

const mountPanel = async (users) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const onRefresh = jest.fn();
  const onMessage = jest.fn();
  await act(async () => {
    root.render(
      <ManagedUsersPanel
        users={users}
        departments={[
          { id: 1, name: 'Sales and Marketing' },
          { id: 2, name: 'Customer Care' },
        ]}
        currentUser={{
          id: 100,
          department: 'Sales and Marketing',
          employer: 'Okoa Float Ltd',
          role: 'system_admin',
        }}
        isSuperAdmin
        canCreateEmployee
        onRefresh={onRefresh}
        onMessage={onMessage}
      />,
    );
    await Promise.resolve();
  });
  return { container, root, onMessage, onRefresh };
};

beforeEach(() => {
  organizationApi.getTransferCandidates.mockReset().mockResolvedValue([]);
  global.fetch = jest.fn();
});

test('shows General Manager across all departments and hides duplicate role assignment', async () => {
  organizationApi.getTransferCandidates.mockResolvedValue([
    {
      id: 1,
      name: 'Sifa Muthoni',
      organizational_role: 'general_manager',
      department: 'Sales & Marketing',
      department_id: 1,
    },
  ]);
  const { container, root } = await mountPanel([
    {
      id: 1,
      full_name: 'Sifa Muthoni',
      organizational_role: 'general_manager',
      department: 'Sales and Marketing',
      account_status: 'approved',
      is_active: true,
    },
    {
      id: 2,
      full_name: 'Taji Mwangi',
      organizational_role: 'department_manager',
      department: 'Debt Collection',
      department_role: 'debt_collection',
      manager_id: 1,
      account_status: 'approved',
      is_active: true,
    },
  ]);

  expect(container.querySelector('tbody tr').textContent).toContain('All');

  const editButton = Array.from(container.querySelectorAll('tbody button'))
    .find((button) => button.textContent === 'Edit');
  await act(async () => {
    Simulate.click(editButton);
    await Promise.resolve();
  });
  const editDepartment = Array.from(container.querySelectorAll('.employee-edit-modal label'))
    .find((label) => label.textContent.includes('Department'))
    .querySelector('input');
  expect(editDepartment.value).toBe('All');

  await act(async () => {
    Simulate.click(container.querySelector('.leave-close'));
  });

  const tajiRow = Array.from(container.querySelectorAll('tbody tr'))
    .find((row) => row.textContent.includes('Taji Mwangi'));
  await act(async () => {
    Simulate.click(Array.from(tajiRow.querySelectorAll('button'))
      .find((button) => button.textContent === 'Edit'));
    await Promise.resolve();
  });
  const managerOptions = Array.from(container.querySelectorAll('.employee-edit-modal label'))
    .find((label) => label.textContent.startsWith('Reports to'))
    .querySelector('select');
  expect(Array.from(managerOptions.options).map((option) => option.textContent))
    .toContain('Sifa Muthoni — All');

  await act(async () => {
    Simulate.click(container.querySelector('.leave-close'));
  });

  const createButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Create employee');
  await act(async () => {
    Simulate.click(createButton);
    await Promise.resolve();
  });

  const roleSelect = Array.from(container.querySelectorAll('label'))
    .find((label) => label.textContent.includes('Organizational role'))
    .querySelector('select');
  expect(Array.from(roleSelect.options).map((option) => option.value))
    .not.toContain('general_manager');

  await act(async () => root.unmount());
  container.remove();
});

test('saves the General Manager department as All', async () => {
  const { container, root } = await mountPanel([
    {
      id: 1,
      full_name: 'Sifa Muthoni',
      email: 'sifa@example.test',
      phone_number: '+254700000001',
      organizational_role: 'general_manager',
      department: 'Sales & Marketing',
      department_role: '',
      account_status: 'approved',
      is_active: true,
      state: 'active',
      role: 'manager',
    },
  ]);
  global.fetch.mockResolvedValue({
    ok: true,
    text: async () => JSON.stringify({ data: {}, error: null }),
  });

  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('tbody button'))
      .find((button) => button.textContent === 'Edit'));
    await Promise.resolve();
  });
  await act(async () => {
    Simulate.submit(container.querySelector('.employee-edit-modal form'));
    await Promise.resolve();
  });

  expect(global.fetch).toHaveBeenCalledTimes(2);
  expect(JSON.parse(global.fetch.mock.calls[1][1].body)).toMatchObject({
    department: 'All',
    organizational_role: 'general_manager',
    department_role: null,
    manager_id: null,
  });

  await act(async () => root.unmount());
  container.remove();
});

test('saves profile details without revalidating an unchanged reporting chain', async () => {
  const { container, root } = await mountPanel([
    {
      id: 12,
      full_name: 'Wanjiku Cherono',
      email: 'wanjiku@example.test',
      phone_number: '+254700000012',
      organizational_role: 'team_leader',
      department: 'Customer Care',
      department_role: 'customer_care',
      manager_id: 8,
      account_status: 'approved',
      is_active: true,
      state: 'active',
      role: 'employee',
    },
  ]);
  global.fetch.mockResolvedValue({
    ok: true,
    text: async () => JSON.stringify({ data: {}, error: null }),
  });

  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('tbody button'))
      .find((button) => button.textContent === 'Edit'));
    await Promise.resolve();
  });
  await act(async () => {
    Simulate.change(
      Array.from(container.querySelectorAll('.employee-edit-modal label'))
        .find((label) => label.textContent.startsWith('Full name'))
        .querySelector('input'),
      { target: { value: 'Wanjiku Cherono Updated' } },
    );
  });
  await act(async () => {
    Simulate.submit(container.querySelector('.employee-edit-modal form'));
    await Promise.resolve();
  });

  expect(global.fetch).toHaveBeenCalledTimes(1);
  const savedProfile = JSON.parse(global.fetch.mock.calls[0][1].body);
  expect(savedProfile.full_name).toBe('Wanjiku Cherono Updated');
  expect(savedProfile).not.toHaveProperty('organizational_role');
  expect(savedProfile).not.toHaveProperty('manager_id');

  await act(async () => root.unmount());
  container.remove();
});

test('System Administrator can save profile details without organizational assignment fields', async () => {
  const { container, root } = await mountPanel([
    {
      id: 1,
      full_name: 'System Administrator',
      email: 'admin@okoa.local',
      phone_number: '+254721143189',
      department: 'HR',
      account_status: 'approved',
      is_active: true,
      is_superuser: true,
      role: 'system_admin',
    },
  ]);
  global.fetch.mockResolvedValue({
    ok: true,
    text: async () => JSON.stringify({ data: {}, error: null }),
  });

  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('tbody button'))
      .find((button) => button.textContent === 'Edit'));
    await Promise.resolve();
  });

  const labels = Array.from(container.querySelectorAll('.employee-edit-modal label'))
    .map((label) => label.textContent);
  expect(labels.some((label) => label.startsWith('Reports to'))).toBe(false);
  expect(labels.some((label) => label.startsWith('Department role'))).toBe(false);
  expect(labels.some((label) => label.startsWith('Department'))).toBe(false);

  await act(async () => {
    Simulate.submit(container.querySelector('.employee-edit-modal form'));
    await Promise.resolve();
  });

  expect(global.fetch).toHaveBeenCalledTimes(1);
  expect(global.fetch.mock.calls[0][0]).toContain('/api/auth/admin/users/1');
  expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toMatchObject({
    full_name: 'System Administrator',
    official_email: 'admin@okoa.local',
    phone_number: '+254721143189',
  });

  await act(async () => root.unmount());
  container.remove();
});

test('keeps profile details when an organizational assignment is rejected', async () => {
  organizationApi.getTransferCandidates.mockResolvedValue([
    {
      id: 1,
      name: 'Sifa Muthoni',
      organizational_role: 'general_manager',
      department: 'Sales and Marketing',
      department_id: 1,
    },
  ]);
  const { container, root, onMessage } = await mountPanel([
    {
      id: 12,
      full_name: 'Wanjiku Cherono',
      email: 'wanjiku@example.test',
      phone_number: '+254700000012',
      organizational_role: 'department_manager',
      department: 'Sales and Marketing',
      department_role: 'sales',
      manager_id: 1,
      account_status: 'approved',
      is_active: true,
      state: 'active',
      role: 'employee',
    },
  ]);
  global.fetch
    .mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ data: {}, error: null }),
    })
    .mockResolvedValueOnce({
      ok: false,
      text: async () => JSON.stringify({
        error: { message: 'The reporting chain must include an active Department Manager' },
      }),
    });

  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('tbody button'))
      .find((button) => button.textContent === 'Edit'));
    await Promise.resolve();
  });
  await act(async () => {
    Simulate.change(
      Array.from(container.querySelectorAll('.employee-edit-modal label'))
        .find((label) => label.textContent.startsWith('Full name'))
        .querySelector('input'),
      { target: { value: 'Wanjiku Updated' } },
    );
    Simulate.change(
      Array.from(container.querySelectorAll('.employee-edit-modal label'))
        .find((label) => label.textContent.startsWith('Department'))
        .querySelector('select'),
      { target: { value: 'Customer Care' } },
    );
    await Promise.resolve();
  });
  await act(async () => {
    Simulate.change(
      Array.from(container.querySelectorAll('.employee-edit-modal label'))
        .find((label) => label.textContent.startsWith('Reports to'))
        .querySelector('select'),
      { target: { value: '1' } },
    );
  });
  await act(async () => {
    Simulate.submit(container.querySelector('.employee-edit-modal form'));
    await Promise.resolve();
  });

  expect(global.fetch).toHaveBeenCalledTimes(2);
  expect(JSON.parse(global.fetch.mock.calls[0][1].body).full_name)
    .toBe('Wanjiku Updated');
  expect(JSON.parse(global.fetch.mock.calls[0][1].body))
    .not.toHaveProperty('department');
  expect(JSON.parse(global.fetch.mock.calls[1][1].body).department)
    .toBe('Customer Care');
  expect(onMessage).toHaveBeenCalledWith(
    expect.stringContaining('Profile details saved. Organizational assignment was not changed'),
    'error',
  );

  await act(async () => root.unmount());
  container.remove();
});

test('Super Admin can deactivate an account from the existing user editor', async () => {
  const { container, root } = await mountPanel([
    {
      id: 21,
      full_name: 'Group Leader',
      email: 'group.leader@example.test',
      phone_number: '+254700000021',
      organizational_role: 'team_leader',
      department: 'Sales and Marketing',
      department_role: 'sales',
      account_status: 'approved',
      is_active: true,
      state: 'active',
      role: 'employee',
    },
  ]);
  global.fetch.mockResolvedValue({
    ok: true,
    text: async () => JSON.stringify({
      data: { id: 21, account_status: 'deactivated', is_active: false },
      error: null,
      message: 'User deactivated',
    }),
  });

  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('tbody button'))
      .find((button) => button.textContent === 'Edit'));
    await Promise.resolve();
  });
  const statusSelect = Array.from(container.querySelectorAll('.employee-edit-modal label'))
    .find((label) => label.textContent.includes('Status'))
    .querySelector('select');
  await act(async () => {
    Simulate.change(statusSelect, { target: { value: 'deactivated' } });
  });
  await act(async () => {
    Simulate.click(Array.from(container.querySelectorAll('.employee-edit-modal button'))
      .find((button) => button.textContent === 'Update status'));
    await Promise.resolve();
  });

  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/auth/admin/users/21/status'),
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ status: 'deactivated' }),
    }),
  );

  await act(async () => root.unmount());
  container.remove();
});

  test('select all matching excludes the current user and bulk deactivates only active selections', async () => {
    const { container, root, onRefresh } = await mountPanel([
      {
        id: 21,
        full_name: 'Active Employee',
        account_status: 'approved',
        is_active: true,
        state: 'active',
      },
      {
        id: 22,
        full_name: 'Inactive Employee',
        account_status: 'deactivated',
        is_active: false,
        state: 'deactivated',
      },
      {
        id: 100,
        full_name: 'Current Administrator',
        account_status: 'approved',
        is_active: true,
        state: 'active',
      },
    ]);
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(true);
    global.fetch.mockResolvedValue({
      ok: true,
      text: async () => JSON.stringify({ data: {}, error: null }),
    });

    await act(async () => {
      Simulate.change(container.querySelector('input[aria-label^="Select all"]'), {
        target: { checked: true },
      });
    });
    expect(container.querySelector('.user-bulk-summary').textContent).toContain('2 selected');

    await act(async () => {
      Simulate.click(Array.from(container.querySelectorAll('.user-bulk-actions button'))
        .find((button) => button.textContent === 'Deactivate (1)'));
      await Promise.resolve();
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls[0][0]).toContain('/api/auth/admin/users/21/status');
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({ status: 'deactivated' });
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalled();

    confirmSpy.mockRestore();
    await act(async () => root.unmount());
    container.remove();
  });
