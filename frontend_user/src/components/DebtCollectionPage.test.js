import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import apiClient from '../services/debtCollectionApi';
import { apiUrl } from '../services/apiConfig';
import DebtCollectionPage from './DebtCollectionPage';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('../services/debtCollectionApi', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    request: jest.fn(),
  },
}));

const mountPage = async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<DebtCollectionPage />);
    await Promise.resolve();
  });
  return { container, root };
};

beforeEach(() => {
  apiClient.get.mockReset().mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: { can_manage: true, can_view_all: true },
            records: [],
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [] } });
    }
    if (path === '/api/debt-collection/collectors') {
      return Promise.resolve({ data: { data: [] } });
    }
    if (path === '/api/debt-collection/analytics') {
      return Promise.resolve({
        data: {
          data: {
            portfolio: { accounts: 0, outstanding: '0' },
            period_recovered: '0',
            period_calls: 0,
            collectors: [],
            interactions: [],
            recovery_trends: [],
          },
        },
      });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  apiClient.post.mockReset();
  apiClient.delete.mockReset();
  apiClient.request.mockReset();
});

test('manager upload posts the selected spreadsheet and reports success', async () => {
  const { container, root } = await mountPage();
  expect(apiClient.get).toHaveBeenCalledWith(
    '/api/debt-collection/summary?include_records=false',
    expect.objectContaining({ headers: expect.any(Object) }),
  );
  const input = container.querySelector('input[type="file"]');
  const importButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Choose file to import');
  const inputClick = jest.spyOn(input, 'click').mockImplementation(() => {});
  await act(async () => importButton.click());
  expect(inputClick).toHaveBeenCalledTimes(1);
  inputClick.mockRestore();
  const file = new File(['spreadsheet'], 'debt-list.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });

  await act(async () => {
    Simulate.change(input, { target: { files: [file] } });
  });
  expect(container.textContent).toContain('debt-list.xlsx');

  let resolveUpload;
  apiClient.post.mockImplementationOnce((path, formData, config) => new Promise((resolve) => {
    expect(path).toBe(apiUrl('/api/debt-collection/import'));
    expect(formData).toBeInstanceOf(FormData);
    expect(formData.get('file')).toBe(file);
    config.onUploadProgress({ loaded: 50, total: 100 });
    resolveUpload = resolve;
  }));
  const submitButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Import portfolio');

  await act(async () => submitButton.click());
  expect(container.textContent).toContain('50%');
  await act(async () => resolveUpload({
    data: {
      data: {
        total_rows: 1,
        accepted_rows: 1,
        rejected_rows: 0,
        issues: [],
      },
    },
  }));

  expect(apiClient.post).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Import successful: 1 row imported.');
  await act(async () => root.unmount());
  container.remove();
});

test('shows debt access before the full loan list finishes loading', async () => {
  let resolveLoans;
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: { can_manage: false, can_view_all: true },
            records: [],
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return new Promise((resolve) => {
        resolveLoans = resolve;
      });
    }
    return Promise.resolve({ data: { data: [] } });
  });

  const { container, root } = await mountPage();
  expect(container.textContent).not.toContain('Loading debt collection access…');
  expect(container.textContent).toContain('Debt Collection');
  expect(container.textContent).toContain('Total outstanding');
  expect(container.textContent).toContain('Loading debt collection accounts…');
  expect(apiClient.get).toHaveBeenCalledWith(
    '/api/debt-collection/analytics',
    expect.objectContaining({ headers: expect.any(Object) }),
  );

  await act(async () => resolveLoans({ data: { data: [] } }));
  await act(async () => root.unmount());
  container.remove();
});

test('super admin can permanently delete a loan and client record', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: {
              can_manage: false,
              can_view_all: true,
              can_permanently_delete: true,
            },
            records: [],
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [{
        id: 21,
        debtor_id: 7,
        agent_name: 'Mina Wanjiku',
        business_name: 'Mina Shop',
        loan_balance: '750',
        status: 'active',
      }] } });
    }
    if (path === '/api/debt-collection/collectors') {
      return Promise.resolve({ data: { data: [] } });
    }
    if (path === '/api/debt-collection/analytics') {
      return Promise.resolve({
        data: {
          data: {
            portfolio: { accounts: 1, outstanding: '750' },
            period_recovered: '0',
            period_calls: 0,
            collectors: [],
            interactions: [],
            recovery_trends: [],
          },
        },
      });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  apiClient.request.mockResolvedValue({ data: { data: { permanently_deleted: true } } });
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  const { container, root } = await mountPage();
  const actions = container.querySelector('[data-loan-id="21"]');
  const deleteLoanButton = Array.from(actions.querySelectorAll('button'))
    .find((button) => button.textContent === 'Delete permanently');

  await act(async () => deleteLoanButton.click());
  expect(apiClient.request).toHaveBeenCalledWith(
    expect.objectContaining({ url: apiUrl('/api/debt-collection/loans/21/permanent'), method: 'DELETE' }),
  );
  const deleteClientButton = Array.from(container.querySelectorAll('[data-loan-id="21"] button'))
    .find((button) => button.textContent === 'Delete client');
  await act(async () => deleteClientButton.click());
  expect(apiClient.request).toHaveBeenCalledWith(
    expect.objectContaining({ url: apiUrl('/api/debt-collection/debtors/7/permanent'), method: 'DELETE' }),
  );
  expect(confirm).toHaveBeenCalledTimes(2);
  confirm.mockRestore();
  await act(async () => root.unmount());
  container.remove();
});

test('super admin can select and permanently delete multiple loan entries', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: {
              can_manage: false,
              can_view_all: true,
              can_permanently_delete: true,
            },
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [
        { id: 41, debtor_id: 7, agent_name: 'Mina Wanjiku', business_name: 'Mina Shop', status: 'active' },
        { id: 42, debtor_id: 8, agent_name: 'Amina Otieno', business_name: 'Amina Shop', status: 'overdue' },
      ] } });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  apiClient.request.mockResolvedValue({ data: { data: { permanently_deleted: 2 } } });
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  const { container, root } = await mountPage();

  await act(async () => {
    Simulate.change(container.querySelector('[aria-label="Select Mina Wanjiku"]'), { target: { checked: true } });
    Simulate.change(container.querySelector('[aria-label="Select Amina Otieno"]'), { target: { checked: true } });
  });
  const deleteSelected = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Delete selected permanently');
  expect(deleteSelected).toBeTruthy();

  await act(async () => deleteSelected.click());
  expect(confirm).toHaveBeenCalledWith(
    'Permanently delete 2 selected loan entries? This cannot be undone.',
  );
  expect(apiClient.request).toHaveBeenCalledWith(expect.objectContaining({
    url: apiUrl('/api/debt-collection/loans/permanent/bulk'),
    method: 'DELETE',
    data: { loan_ids: [41, 42] },
  }));
  expect(container.textContent).toContain('2 loan entries permanently deleted.');
  confirm.mockRestore();
  await act(async () => root.unmount());
  container.remove();
});

test('account activity shows full entry details when there are no calls', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: { data: { permissions: { can_manage: false, can_view_all: true } } },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [{
        id: 51,
        debtor_id: 9,
        first_name: 'Amina',
        other_names: 'Otieno',
        agent_name: 'Amina Otieno',
        agent_number: '254700000009',
        owner_msisdn: '254700000010',
        operator_msisdn: '254700000011',
        agent_no: 'AG-009',
        store_number: 'ST-009',
        business_name: 'Amina Shop',
        business_location: 'Nairobi',
        loan_amount: '1000',
        loan_balance: '800',
        amount_paid: '200',
        status: 'overdue',
        loan_date: '2026-01-02',
        created_at: '2026-01-03T10:00:00',
        last_interest_calc_date: '2026-01-10',
        no_of_days: 8,
      }] } });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  apiClient.request.mockResolvedValue({ data: { data: [] } });
  const { container, root } = await mountPage();
  const viewButton = Array.from(container.querySelectorAll('.debt-view-activity-button'))
    .find((button) => button.textContent === 'View');
  await act(async () => viewButton.click());

  const dialog = document.body.querySelector('[aria-label="Debtor and loan details"]');
  expect(dialog).toBeTruthy();
  expect(dialog.textContent).toContain('254700000009');
  expect(dialog.textContent).toContain('AG-009');
  expect(dialog.textContent).toContain('Amina Shop');
  expect(dialog.textContent).toContain('1,000');
  expect(dialog.textContent).toContain('800');
  expect(document.body.textContent).not.toContain('No calls recorded for this loan.');
  await act(async () => root.unmount());
  container.remove();
});

test('users with portfolio view access can select and view multiple entries', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: { data: { permissions: { can_manage: false, can_view_all: true, can_permanently_delete: false } } },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [
        { id: 71, agent_name: 'Nia Kamau', business_name: 'Nia Shop', loan_amount: '1000', loan_balance: '800', amount_paid: '200', status: 'active' },
        { id: 72, agent_name: 'Omar Ali', business_name: 'Omar Shop', loan_amount: '2000', loan_balance: '1500', amount_paid: '500', status: 'overdue' },
      ] } });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  const { container, root } = await mountPage();
  await act(async () => {
    container.querySelector('[aria-label="Select Nia Kamau"]').closest('label').click();
    container.querySelector('[aria-label="Select Omar Ali"]').closest('label').click();
  });

  expect(container.querySelector('[aria-label="Select Nia Kamau"]').checked).toBe(true);
  expect(container.querySelector('[aria-label="Select Omar Ali"]').checked).toBe(true);
  const viewSelected = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'View selected');
  expect(viewSelected).toBeTruthy();
  expect(viewSelected.disabled).toBe(false);
  await act(async () => viewSelected.click());

  const dialog = document.body.querySelector('[aria-labelledby="debt-multi-view-title"]');
  expect(dialog).toBeTruthy();
  expect(dialog.querySelector('.debt-multi-record-list')).toBeTruthy();
  expect(dialog.textContent).toContain('Nia Shop');
  expect(dialog.textContent).toContain('Omar Shop');
  await act(async () => root.unmount());
  container.remove();
});

test('group leader can select and view multiple entries in the all-debtors list', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: {
              can_manage: false,
              can_view_all: false,
              can_view_all_debtors: true,
              can_view_team: true,
              can_permanently_delete: false,
            },
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [
        { id: 81, agent_name: 'Nia Kamau', business_name: 'Nia Shop', store_number: 'ST-081', loan_amount: '1000', loan_balance: '800', status: 'active' },
        { id: 82, agent_name: 'Omar Ali', business_name: 'Omar Shop', loan_amount: '2000', loan_balance: '1500', status: 'overdue' },
      ] } });
    }
    if (path === '/api/debt-collection/analytics') {
      return Promise.resolve({ data: { data: {
        portfolio: { accounts: 2, outstanding: '2300' },
        period_recovered: '0',
        period_calls: 0,
        collectors: [],
        interactions: [],
        recovery_trends: [],
      } } });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  const { container, root } = await mountPage();

  expect(container.textContent).toContain('Team outstanding');
  expect(container.textContent).toContain('ALL PORTFOLIO DEBTORS · READ ONLY');
  expect(container.textContent).toContain('All portfolio debtors');
  expect(container.textContent).toContain('2 debtors · 2 loan entries');
  expect(container.querySelector('[aria-label="Select all loans"]')).toBeTruthy();
  await act(async () => {
    Simulate.change(container.querySelector('[aria-label="Select Nia Kamau"]'), { target: { checked: true } });
    Simulate.change(container.querySelector('[aria-label="Select Omar Ali"]'), { target: { checked: true } });
  });
  const viewSelected = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'View selected');
  expect(viewSelected).toBeTruthy();
  await act(async () => viewSelected.click());

  const dialog = document.body.querySelector('[aria-labelledby="debt-multi-view-title"]');
  expect(dialog).toBeTruthy();
  expect(dialog.textContent).toContain('Nia Shop');
  expect(dialog.textContent).toContain('Store number');
  expect(dialog.textContent).not.toContain('Store / branch');
  expect(dialog.textContent).toContain('ST-081');
  expect(dialog.textContent).toContain('Omar Shop');
  expect(dialog.querySelector('button').getAttribute('aria-label')).toBe('Close selected entries');
  expect(Array.from(dialog.querySelectorAll('button')).some((button) => /edit|delete/i.test(button.textContent))).toBe(false);
  expect(Array.from(container.querySelectorAll('button')).some((button) => /edit|delete|archive|distribute/i.test(button.textContent))).toBe(false);
  expect(apiClient.request).not.toHaveBeenCalled();

  await act(async () => root.unmount());
  container.remove();
});

test('department manager can view selected entries, edit one, and use authorized bulk actions', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: { data: { permissions: { can_manage: true, can_view_all: true, can_permanently_delete: false } } },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [
        { id: 61, debtor_id: 11, first_name: 'Mina', other_names: 'Wanjiku', agent_name: 'Mina Wanjiku', agent_number: '254700000061', agent_no: 'AG-061', business_name: 'Mina Shop', loan_amount: '1000', loan_balance: '800', amount_paid: '200', status: 'active', loan_date: '2026-01-02' },
        { id: 62, debtor_id: 12, first_name: 'Amina', other_names: 'Otieno', agent_name: 'Amina Otieno', agent_number: '254700000062', agent_no: 'AG-062', business_name: 'Amina Shop', loan_amount: '2000', loan_balance: '1500', amount_paid: '500', status: 'overdue', loan_date: '2026-02-02' },
      ] } });
    }
    if (path === '/api/debt-collection/analytics') {
      return Promise.resolve({ data: { data: {
        portfolio: { accounts: 2, outstanding: '2300' },
        period_recovered: '0',
        period_calls: 0,
        collectors: [],
        interactions: [],
        recovery_trends: [],
      } } });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  apiClient.request.mockResolvedValue({ data: { data: {} } });
  const { container, root } = await mountPage();
  const portfolioTable = container.querySelector('.debt-portfolio-table');
  const portfolioHeaders = Array.from(portfolioTable.querySelectorAll('thead th'))
    .map((header) => header.textContent.trim());
  expect(portfolioHeaders).toEqual([
    '', 'Debtor / business', 'Store number', 'Original loan', 'Paid',
    'Balance', 'Status', 'Collector', 'Next payment', 'Last contact', 'Actions',
  ]);
  expect(Array.from(portfolioTable.querySelectorAll('tbody tr[data-loan-id]'))
    .map((row) => row.dataset.loanId)).toEqual(['62', '61']);
  const originalLoanHeader = portfolioTable.querySelector('[aria-label="Sort by Original loan"]');
  await act(async () => originalLoanHeader.click());
  expect(Array.from(portfolioTable.querySelectorAll('tbody tr[data-loan-id]'))
    .map((row) => row.dataset.loanId)).toEqual(['61', '62']);
  expect(originalLoanHeader.closest('th').getAttribute('aria-sort')).toBe('ascending');
  await act(async () => originalLoanHeader.click());
  expect(Array.from(portfolioTable.querySelectorAll('tbody tr[data-loan-id]'))
    .map((row) => row.dataset.loanId)).toEqual(['62', '61']);
  expect(originalLoanHeader.closest('th').getAttribute('aria-sort')).toBe('descending');
  const firstEntryRow = portfolioTable.querySelector('tbody tr[data-loan-id="61"]');
  expect(firstEntryRow.cells).toHaveLength(portfolioHeaders.length);
  expect(Array.from(firstEntryRow.cells).every((cell) => (
    cell.textContent.trim() || cell.querySelector('input[type="checkbox"]')
  ))).toBe(true);
  expect(Array.from(firstEntryRow.querySelectorAll('button')).map((button) => button.textContent.trim()))
    .toEqual(expect.arrayContaining(['View', 'Edit', 'Log call', 'Delete']));
  await act(async () => {
    Simulate.change(container.querySelector('[aria-label="Select Mina Wanjiku"]'), { target: { checked: true } });
    Simulate.change(container.querySelector('[aria-label="Select Amina Otieno"]'), { target: { checked: true } });
  });
  const viewSelected = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'View selected');
  expect(viewSelected.disabled).toBe(false);
  expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Archive selected')).toBe(true);
  expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Distribute List')).toBe(true);
  expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Delete selected permanently')).toBe(false);
  await act(async () => viewSelected.click());

  const dialog = document.body.querySelector('[aria-label="dialog"]')
    || document.body.querySelector('[aria-labelledby="debt-multi-view-title"]');
  expect(dialog).toBeTruthy();
  expect(dialog.querySelector('.debt-multi-record-list')).toBeTruthy();
  expect(dialog.textContent).toContain('Mina Shop');
  expect(dialog.textContent).toContain('Amina Shop');
  const editEntry = Array.from(dialog.querySelectorAll('button'))
    .find((button) => button.textContent === 'Edit / update entry');
  await act(async () => editEntry.click());
  expect(document.body.textContent).toContain('Edit selected record');
  expect(document.body.textContent).toContain('Update client details');
  expect(document.body.textContent).toContain('Update loan details');
  const saveLoan = Array.from(document.body.querySelectorAll('button'))
    .find((button) => button.textContent === 'Update loan details');
  await act(async () => saveLoan.click());
  expect(apiClient.request).toHaveBeenCalledWith(expect.objectContaining({
    url: apiUrl('/api/debt-collection/loans/61'),
    method: 'PATCH',
  }));
  await act(async () => root.unmount());
  container.remove();
});

test('department manager can permanently delete a duplicate loan only', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: {
              can_manage: true,
              can_view_all: true,
              can_permanently_delete: false,
            },
            records: [],
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [{
        id: 31,
        debtor_id: 8,
        agent_name: 'Duplicate Client',
        business_name: 'Duplicate Shop',
        loan_balance: '750',
        status: 'active',
        is_duplicate: true,
      }] } });
    }
    if (path === '/api/debt-collection/collectors') {
      return Promise.resolve({ data: { data: [] } });
    }
    if (path === '/api/debt-collection/analytics') {
      return Promise.resolve({
        data: {
          data: {
            portfolio: { accounts: 1, outstanding: '750' },
            period_recovered: '0',
            period_calls: 0,
            collectors: [],
            interactions: [],
            recovery_trends: [],
          },
        },
      });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  apiClient.request.mockResolvedValue({ data: { data: { permanently_deleted: true } } });
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  const { container, root } = await mountPage();
  const duplicateDeleteButton = Array.from(
    container.querySelectorAll('[data-loan-id="31"] button'),
  ).find((button) => button.textContent === 'Delete duplicate permanently');

  expect(duplicateDeleteButton).toBeTruthy();
  await act(async () => duplicateDeleteButton.click());
  expect(apiClient.request).toHaveBeenCalledWith(
    expect.objectContaining({
      url: apiUrl('/api/debt-collection/loans/31/permanent'),
      method: 'DELETE',
    }),
  );
  expect(confirm).toHaveBeenCalledTimes(1);
  confirm.mockRestore();
  await act(async () => root.unmount());
  container.remove();
});

test('group leader cannot permanently delete a duplicate loan', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.startsWith('/api/debt-collection/summary')) {
      return Promise.resolve({
        data: {
          data: {
            permissions: {
              can_manage: false,
              can_view_all: false,
              can_view_team: true,
              can_permanently_delete: false,
            },
            records: [],
          },
        },
      });
    }
    if (path.startsWith('/api/debt-collection/loans')) {
      return Promise.resolve({ data: { data: [{
        id: 32,
        debtor_id: 9,
        agent_name: 'Team Duplicate',
        business_name: 'Team Shop',
        loan_balance: '500',
        status: 'active',
        is_duplicate: true,
      }] } });
    }
    if (path.startsWith('/api/debt-collection/analytics')) {
      return Promise.resolve({
        data: {
          data: {
            portfolio: { accounts: 1, outstanding: '500' },
            period_recovered: '0',
            period_calls: 0,
            collectors: [],
            interactions: [],
            recovery_trends: [],
          },
        },
      });
    }
    return Promise.resolve({ data: { data: [] } });
  });
  const { container, root } = await mountPage();
  const duplicateDeleteButton = Array.from(
    container.querySelectorAll('button'),
  ).find((button) => button.textContent === 'Delete duplicate permanently');

  expect(duplicateDeleteButton).toBeUndefined();
  expect(apiClient.delete).not.toHaveBeenCalled();
  await act(async () => root.unmount());
  container.remove();
});
