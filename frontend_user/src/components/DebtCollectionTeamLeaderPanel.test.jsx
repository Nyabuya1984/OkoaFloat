import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import apiClient from '../services/debtCollectionApi';
import DebtCollectionTeamLeaderPanel from './DebtCollectionTeamLeaderPanel';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('../services/debtCollectionApi', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));

const mountPanel = async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<DebtCollectionTeamLeaderPanel />);
    await Promise.resolve();
  });
  return { container, root };
};

beforeEach(() => {
  apiClient.get.mockReset().mockImplementation((path) => {
    if (path.includes('/loans?')) {
      return Promise.resolve({
        data: {
          data: [{
            id: 21,
            agent_name: 'Mina Wanjiku',
            business_name: 'Mina Shop',
            collector_name: null,
            collector_id: null,
            loan_balance: '750',
            status: 'overdue',
          }],
        },
      });
    }
    if (path === '/api/debt-collection/collectors') {
      return Promise.resolve({ data: { data: [{ id: 8, full_name: 'Juma Kimani', active_accounts: 20 }] } });
    }
    return Promise.resolve({
      data: {
        data: {
          portfolio: { accounts: 1, outstanding: '750' },
          period_recovered: '0',
          period_calls: 0,
          collectors: [],
          interactions: [],
        },
      },
    });
  });
  apiClient.post.mockReset().mockResolvedValue({
    data: { data: { assigned: 1 } },
  });
  apiClient.patch.mockReset().mockResolvedValue({ data: { data: {} } });
  apiClient.delete.mockReset().mockResolvedValue({ data: { data: {} } });
});

test('team leader can assign an unassigned account to a direct report', async () => {
  const { container, root } = await mountPanel();

  expect(container.textContent).toContain('Mina Wanjiku');
  expect(container.textContent).toContain('Juma Kimani');
  const checkbox = container.querySelector('input[aria-label="Select Mina Wanjiku"]');
  const collectorSelect = container.querySelector('.debt-assignment-bar select');
  const form = container.querySelector('form.debt-assignment-bar');

  await act(async () => {
    Simulate.change(checkbox, { target: { checked: true } });
  });
  await act(async () => {
    Simulate.change(collectorSelect, { target: { value: '8' } });
  });
  await act(async () => {
    Simulate.submit(form, { preventDefault() {} });
    await Promise.resolve();
  });

  expect(apiClient.post).toHaveBeenCalledWith(
    '/api/debt-collection/assignments/bulk',
    { collector_id: 8, loan_ids: [21], reason: undefined },
  );
  expect(container.textContent).toContain('1 account allocated to Juma Kimani.');
  await act(async () => root.unmount());
  container.remove();
});

test('team leader can track Excel upload progress and see partial-import results', async () => {
  const { container, root } = await mountPanel();
  const input = container.querySelector('input[type="file"]');
  const chooseFileButton = Array.from(container.querySelectorAll('.debt-import-form button'))
    .find((button) => button.textContent === 'Choose file to import');
  const primaryInputClick = jest.spyOn(input, 'click').mockImplementation(() => {});
  await act(async () => chooseFileButton.click());
  expect(primaryInputClick).toHaveBeenCalledTimes(1);
  primaryInputClick.mockRestore();
  const reportsToolbar = container.querySelector('.collector-report-toolbar-actions');
  const toolbarImportButton = Array.from(reportsToolbar.querySelectorAll('button'))
    .find((button) => button.textContent.includes('Choose CSV / Excel'));
  expect(toolbarImportButton).toBeTruthy();
  const inputClick = jest.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {});
  await act(async () => toolbarImportButton.click());
  expect(inputClick).toHaveBeenCalled();
  inputClick.mockRestore();
  const hideButton = Array.from(reportsToolbar.querySelectorAll('button'))
    .find((button) => button.textContent === 'Hide reports');
  expect(hideButton).toBeTruthy();
  await act(async () => hideButton.click());
  expect(container.querySelector('.collector-outcome-picker')).toBeNull();
  const showButton = Array.from(reportsToolbar.querySelectorAll('button'))
    .find((button) => button.textContent === 'Show reports');
  expect(showButton).toBeTruthy();
  await act(async () => showButton.click());
  expect(container.querySelector('.collector-outcome-picker')).toBeTruthy();
  expect(input.accept).toContain('.xlsx');
  const file = new File(['excel data'], 'debt-list.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });

  await act(async () => {
    Simulate.change(input, { target: { files: [file] } });
  });
  expect(apiClient.post).not.toHaveBeenCalled();
  expect(container.textContent).toContain('debt-list.xlsx');

  let resolveUpload;
  apiClient.post.mockImplementationOnce((path, formData, config) => new Promise((resolve) => {
    expect(path).toBe('/api/debt-collection/import');
    expect(formData).toBeInstanceOf(FormData);
    config.onUploadProgress({ loaded: 50, total: 100 });
    resolveUpload = resolve;
  }));
  const importButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Import portfolio');
  expect(importButton).toBeTruthy();
  await act(async () => importButton.click());
  expect(container.textContent).toContain('Uploading file…');
  expect(container.textContent).toContain('50%');
  await act(async () => resolveUpload({
    data: {
      data: {
        accepted_rows: 1,
        rejected_rows: 1,
        issues: [{ row_number: 3, message: 'loan_amount must be a valid amount' }],
      },
    },
  }));

  expect(apiClient.post).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Import partially complete: 1 accepted, 1 rejected.');
  expect(container.textContent).toContain('Row 3: loan_amount must be a valid amount');
  await act(async () => root.unmount());
  container.remove();
});

test('team leader gets a visible failure status when upload fails', async () => {
  const { container, root } = await mountPanel();
  const input = container.querySelector('input[type="file"]');
  const file = new File(['bad file'], 'debt-list.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  await act(async () => Simulate.change(input, { target: { files: [file] } }));
  apiClient.post.mockRejectedValueOnce(new Error('The Excel file could not be read'));
  const importButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Import portfolio');
  await act(async () => importButton.click());
  expect(container.querySelector('[role="alert"]').textContent).toContain('The Excel file could not be read');
  await act(async () => root.unmount());
  container.remove();
});

test('team leader can identify and permanently delete duplicate entries only', async () => {
  apiClient.get.mockImplementation((path) => {
    if (path.includes('/loans?')) {
      return Promise.resolve({
        data: {
          data: [{
            id: 21,
            agent_name: 'Mina Wanjiku',
            business_name: 'Mina Shop',
            collector_name: null,
            collector_id: null,
            loan_balance: '750',
            status: 'overdue',
            is_duplicate: true,
          }],
        },
      });
    }
    if (path === '/api/debt-collection/collectors') {
      return Promise.resolve({ data: { data: [] } });
    }
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
  });
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  const { container, root } = await mountPanel();
  const row = container.querySelector('input[aria-label="Select Mina Wanjiku"]').closest('tr');
  expect(row.className).toContain('debt-duplicate-row');
  expect(row.textContent).toContain('Duplicate');
  const deleteDuplicate = Array.from(row.querySelectorAll('button'))
    .find((button) => button.textContent === 'Delete duplicate permanently');
  await act(async () => deleteDuplicate.click());
  expect(apiClient.delete).toHaveBeenCalledWith('/api/debt-collection/loans/21/permanent');
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('This cannot be undone'));
  expect(container.textContent).toContain('permanently deleted');
  confirm.mockRestore();
  await act(async () => root.unmount());
  container.remove();
});

test('team leader can edit and soft-delete an account from the actions column', async () => {
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  const { container, root } = await mountPanel();

  const portfolioTable = container.querySelector('input[aria-label="Select Mina Wanjiku"]').closest('table');
  expect(portfolioTable.querySelector('th:last-child').textContent).toBe('Actions');
  const editButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Edit');
  await act(async () => editButton.click());
  const firstNameLabel = Array.from(container.querySelectorAll('label'))
    .find((label) => label.textContent.startsWith('First name'));
  await act(async () => {
    Simulate.change(firstNameLabel.querySelector('input'), { target: { value: 'Mina Updated' } });
  });
  const editForm = container.querySelector('[role="dialog"] form');
  await act(async () => {
    Simulate.submit(editForm, { preventDefault() {} });
    await Promise.resolve();
  });
  expect(apiClient.patch).toHaveBeenCalledWith(
    '/api/debt-collection/loans/21',
    expect.objectContaining({ first_name: 'Mina Updated' }),
  );
  expect(container.textContent).toContain('Debtor and loan details updated.');

  const deleteButton = Array.from(container.querySelectorAll('button'))
    .find((button) => button.textContent === 'Delete');
  await act(async () => {
    deleteButton.click();
    await Promise.resolve();
  });
  expect(confirm).toHaveBeenCalled();
  expect(apiClient.delete).toHaveBeenCalledWith('/api/debt-collection/loans/21');
  expect(container.textContent).toContain('Loan record for Mina Wanjiku deleted.');
  confirm.mockRestore();
  await act(async () => root.unmount());
  container.remove();
});
