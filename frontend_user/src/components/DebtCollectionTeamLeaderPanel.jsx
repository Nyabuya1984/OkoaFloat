import React, { useCallback, useEffect, useRef, useState } from 'react';
import apiClient from '../services/debtCollectionApi';
import { downloadDebtCollectionTemplate } from '../services/debtCollectionFiles';
import CollectorInteractionTable from './CollectorInteractionTable';
import DebtCollectionImportStatus from './DebtCollectionImportStatus';

const money = (value) => new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

const errorMessage = (error) => error.response?.data?.error?.message || error.message;

export default function DebtCollectionTeamLeaderPanel() {
  const [loans, setLoans] = useState([]);
  const [collectors, setCollectors] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [filters, setFilters] = useState({
    q: '',
    status: '',
    collector_id: '',
    from: '',
    to: '',
  });
  const [appliedFilters, setAppliedFilters] = useState({});
  const [selectedLoans, setSelectedLoans] = useState([]);
  const [collectorId, setCollectorId] = useState('');
  const [reason, setReason] = useState('');
  const [importIssues, setImportIssues] = useState([]);
  const [importFile, setImportFile] = useState(null);
  const [importStatus, setImportStatus] = useState('');
  const [importProgress, setImportProgress] = useState(0);
  const [importFeedback, setImportFeedback] = useState('');
  const [editingLoan, setEditingLoan] = useState(null);
  const importInput = useRef(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingLoanId, setDeletingLoanId] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const loadData = useCallback(async (queryFilters = appliedFilters) => {
    setLoading(true);
    try {
      const portfolioParams = new URLSearchParams();
      portfolioParams.set('include_unassigned', 'true');
      Object.entries(queryFilters).forEach(([key, value]) => {
        if (value && key !== 'from' && key !== 'to') portfolioParams.set(key, value);
      });
      const analyticsParams = new URLSearchParams();
      ['from', 'to', 'collector_id'].forEach((key) => {
        if (queryFilters[key]) analyticsParams.set(key, queryFilters[key]);
      });
      const analyticsQuery = analyticsParams.toString();
      const [portfolioResponse, collectorsResponse, analyticsResponse] = await Promise.all([
        apiClient.get(`/api/debt-collection/loans?${portfolioParams}`),
        apiClient.get('/api/debt-collection/collectors'),
        apiClient.get(`/api/debt-collection/analytics${analyticsQuery ? `?${analyticsQuery}` : ''}`),
      ]);
      setLoans(portfolioResponse.data.data || []);
      setCollectors(collectorsResponse.data.data || []);
      setAnalytics(analyticsResponse.data.data || null);
      setSelectedLoans((current) => current.filter(
        (id) => (portfolioResponse.data.data || []).some((loan) => loan.id === id),
      ));
      setError('');
    } catch (loadError) {
      setError(errorMessage(loadError) || 'Unable to load team debt collection data.');
    } finally {
      setLoading(false);
    }
  }, [appliedFilters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const applyFilters = (event) => {
    event.preventDefault();
    setAppliedFilters({ ...filters });
  };

  const assignSelected = async (event) => {
    event.preventDefault();
    if (!collectorId || selectedLoans.length === 0) return;
    const reassigning = loans.some(
      (loan) => selectedLoans.includes(loan.id) && loan.collector_id,
    );
    if (reassigning && !reason.trim()) {
      setError('A reason is required when reassigning an account.');
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await apiClient.post('/api/debt-collection/assignments/bulk', {
        collector_id: Number(collectorId),
        loan_ids: selectedLoans,
        reason: reason.trim() || undefined,
      });
      const collector = collectors.find((item) => item.id === Number(collectorId));
      setMessage(`${response.data.data.assigned} account${response.data.data.assigned === 1 ? '' : 's'} allocated${collector ? ` to ${collector.full_name}` : ''}.`);
      setSelectedLoans([]);
      setCollectorId('');
      setReason('');
      await loadData();
    } catch (saveError) {
      setError(errorMessage(saveError) || 'Unable to allocate these accounts.');
    } finally {
      setSaving(false);
    }
  };

  const downloadReport = async (format) => {
    try {
      const params = new URLSearchParams();
      Object.entries(appliedFilters).forEach(([key, value]) => {
        if (value && key !== 'from' && key !== 'to') params.set(key, value);
      });
      const query = params.toString();
      const response = await apiClient.get(
        `/api/debt-collection/export.${format}${query ? `?${query}` : ''}`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `debt-team-report.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setError(errorMessage(downloadError) || 'Unable to export the debt collection report.');
    }
  };

  const importReport = async () => {
    if (!importFile || saving) return;
    const formData = new FormData();
    formData.append('file', importFile);
    setSaving(true);
    setError('');
    setMessage('');
    setImportIssues([]);
    setImportFeedback('');
    setImportProgress(0);
    setImportStatus('uploading');
    try {
      const response = await apiClient.post('/api/debt-collection/import', formData, {
        onUploadProgress: (event) => {
          if (!event.total) return;
          setImportProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
          if (event.loaded >= event.total) setImportStatus('processing');
        },
      });
      const result = response.data.data;
      setImportIssues(result.issues || []);
      if (result.total_rows === 0) {
        setImportStatus('failed');
        setImportFeedback('Import failed: the selected file contains no data rows.');
      } else if (result.accepted_rows === 0) {
        setImportStatus('failed');
        setImportFeedback(`Import failed: none of the ${result.rejected_rows} rows were accepted.`);
      } else if (result.rejected_rows > 0) {
        setImportStatus('partial');
        setImportFeedback(`Import partially complete: ${result.accepted_rows} accepted, ${result.rejected_rows} rejected.`);
      } else {
        setImportStatus('success');
        setImportFeedback(`Import successful: ${result.accepted_rows} row${result.accepted_rows === 1 ? '' : 's'} imported.`);
      }
      await loadData();
    } catch (importError) {
      setImportStatus('failed');
      setImportFeedback(errorMessage(importError) || 'Unable to import this debt collection report.');
    } finally {
      setSaving(false);
    }
  };

  const chooseImportFile = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportFile(file);
    setImportStatus('');
    setImportFeedback('');
    setImportIssues([]);
    setImportProgress(0);
    event.target.value = '';
  };

  const handleImportAction = () => {
    if (importFile) importReport();
    else importInput.current?.click();
  };

  const saveLoan = async (event) => {
    event.preventDefault();
    if (!editingLoan) return;
    setSaving(true);
    setError('');
    setMessage('');
    try {
      await apiClient.patch(`/api/debt-collection/loans/${editingLoan.id}`, {
        first_name: editingLoan.first_name,
        other_names: editingLoan.other_names,
        agent_msisdn: editingLoan.agent_msisdn,
        owner_msisdn: editingLoan.owner_msisdn,
        operator_msisdn: editingLoan.operator_msisdn,
        agent_no: editingLoan.agent_no,
        store_number: editingLoan.store_number,
        business_name: editingLoan.business_name,
        location: editingLoan.location,
        loan_amount: editingLoan.loan_amount,
        amount_paid: editingLoan.amount_paid,
        loan_date: editingLoan.loan_date,
        last_interest_calc_date: editingLoan.last_interest_calc_date || null,
        no_of_days: editingLoan.no_of_days,
        status: editingLoan.status,
      });
      setMessage('Debtor and loan details updated.');
      setEditingLoan(null);
      await loadData();
    } catch (saveError) {
      setError(errorMessage(saveError) || 'Unable to update this account.');
    } finally {
      setSaving(false);
    }
  };

  const deleteLoan = async (loan) => {
    if (!window.confirm(`Delete the loan record for ${loan.agent_name}? This is a soft delete and can be audited.`)) return;
    setDeletingLoanId(loan.id);
    setError('');
    setMessage('');
    try {
      await apiClient.delete(`/api/debt-collection/loans/${loan.id}`);
      setMessage(`Loan record for ${loan.agent_name} deleted.`);
      setSelectedLoans((current) => current.filter((id) => id !== loan.id));
      await loadData();
    } catch (deleteError) {
      setError(errorMessage(deleteError) || 'Unable to delete this loan record.');
    } finally {
      setDeletingLoanId(null);
    }
  };

  const permanentlyDeleteDuplicate = async (loan) => {
    if (!loan.is_duplicate) return;
    if (!window.confirm(`Permanently delete this duplicate loan entry for ${loan.agent_name}? This cannot be undone.`)) return;
    setDeletingLoanId(loan.id);
    setError('');
    setMessage('');
    try {
      await apiClient.delete(`/api/debt-collection/loans/${loan.id}/permanent`);
      setMessage(`Duplicate loan entry for ${loan.agent_name} permanently deleted.`);
      setSelectedLoans((current) => current.filter((id) => id !== loan.id));
      await loadData();
    } catch (deleteError) {
      setError(errorMessage(deleteError) || 'Unable to permanently delete this duplicate.');
    } finally {
      setDeletingLoanId(null);
    }
  };

  const openLoanForEdit = (loan) => {
    setEditingLoan({
      ...loan,
      agent_msisdn: loan.agent_number || '',
      location: loan.business_location || '',
      loan_amount: loan.loan_amount ?? '',
      amount_paid: loan.amount_paid ?? '0',
      loan_date: loan.loan_date || '',
      last_interest_calc_date: loan.last_interest_calc_date || '',
      no_of_days: loan.no_of_days ?? 0,
    });
  };

  const allVisibleSelected = loans.length > 0 && loans.every(
    (loan) => selectedLoans.includes(loan.id),
  );

  return (
    <section className="sales-reports-page debt-collection-page" id="debt-collection">
      <div className="leave-section-heading">
        <div>
          <p className="leave-kicker">TEAM COLLECTIONS</p>
          <h2>Debt collection team</h2>
          <p className="leave-muted">Review your representatives' results, distribute accounts, and reassign work.</p>
        </div>
      </div>
      {error && <div className="leave-alert error" role="alert">{error}</div>}
      {message && <div className="leave-alert info" role="status">{message}</div>}
      <section className="leave-section debt-manager-tools">
        <div className="leave-section-heading">
          <div><p className="leave-kicker">PORTFOLIO CONTROLS</p><h3>Import and export</h3><p className="leave-muted">Import the supplied .xlsx or .csv file, or download a CSV template.</p></div>
          <div className="debt-dashboard-transfer-actions">
            <input ref={importInput} className="debt-hidden-file-input" type="file" accept=".csv,.xlsx" onChange={chooseImportFile} aria-label="Choose debt collection CSV or Excel file" />
            <div className="debt-import-form">
              <button className="leave-secondary-button" type="button" onClick={() => importInput.current?.click()} disabled={saving}>Choose CSV / Excel</button>
              <button className="leave-primary-button" type="button" onClick={handleImportAction} disabled={saving}>{saving ? 'Importing…' : importFile ? 'Import portfolio' : 'Choose file to import'}</button>
              <button className="leave-secondary-button" type="button" onClick={downloadDebtCollectionTemplate}>Download CSV template</button>
            </div>
            <div className="debt-export-actions">
              <button type="button" className="leave-secondary-button" onClick={() => downloadReport('csv')}>Export CSV</button>
              <button type="button" className="leave-secondary-button" onClick={() => downloadReport('xlsx')}>Export Excel</button>
            </div>
          </div>
        </div>
      </section>
      <DebtCollectionImportStatus fileName={importFile?.name} status={importStatus} progress={importProgress} message={importFeedback} issues={importIssues} />

      <form className="debt-filter-bar" onSubmit={applyFilters}>
        <label>Search<input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} placeholder="Debtor, business, or collector" /></label>
        <label>Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All statuses</option><option value="active">Active</option><option value="overdue">Overdue</option><option value="in_negotiation">In negotiation</option><option value="promise_to_pay">Promise to pay</option><option value="settled">Settled</option><option value="written_off">Written off</option><option value="legal">Legal</option></select></label>
        <label>Representative<select value={filters.collector_id} onChange={(event) => setFilters({ ...filters, collector_id: event.target.value })}><option value="">All representatives</option>{collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name}</option>)}</select></label>
        <label>From<input type="date" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} /></label>
        <label>To<input type="date" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} /></label>
        <button className="leave-secondary-button" type="submit">Apply filters</button>
        <button className="leave-text-button" type="button" onClick={() => { const cleared = { q: '', status: '', collector_id: '', from: '', to: '' }; setFilters(cleared); setAppliedFilters(cleared); }}>Clear</button>
      </form>

      {analytics && (
        <section className="leave-section debt-analytics">
          <div className="leave-section-heading"><div><p className="leave-kicker">PERFORMANCE REPORT</p><h3>Team response and recovery</h3></div></div>
          <div className="report-card-grid">
            <div className="report-card"><span>Accounts</span><strong>{analytics.portfolio.accounts}</strong></div>
            <div className="report-card"><span>Outstanding</span><strong>{money(analytics.portfolio.outstanding)}</strong></div>
            <div className="report-card"><span>Recovered</span><strong>{money(analytics.period_recovered)}</strong></div>
            <div className="report-card"><span>Calls</span><strong>{analytics.period_calls}</strong></div>
          </div>
          <div className="sales-visit-table-wrap">
            <table className="leave-table">
              <thead><tr><th>Representative</th><th>Assigned</th><th>Contacted</th><th>Pending</th><th>Calls</th><th>Payments</th><th>Recovered</th></tr></thead>
              <tbody>
                {analytics.collectors.length ? analytics.collectors.map((item) => (
                  <tr key={item.collector_id}><td>{item.collector_name}</td><td>{item.assigned_accounts}</td><td>{item.contacted_accounts}</td><td>{item.pending_accounts}</td><td>{item.calls}</td><td>{item.payments}</td><td>{money(item.recovered)}</td></tr>
                )) : <tr><td colSpan="7">No representative activity in this report period.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="debt-recovery-trends" aria-label="Team daily recovery trend">
            <strong>Daily recovery</strong>
            {analytics.recovery_trends?.length ? analytics.recovery_trends.map((trend) => {
              const maximum = Math.max(...analytics.recovery_trends.map((item) => Number(item.recovered)));
              const width = maximum ? Math.max(3, (Number(trend.recovered) / maximum) * 100) : 3;
              return (
                <div className="debt-recovery-trend" key={trend.date}>
                  <time>{trend.date}</time>
                  <span><i style={{ width: `${width}%` }} /></span>
                  <strong>{money(trend.recovered)}</strong>
                </div>
              );
            }) : <p className="leave-empty">No recovery payments in this date range.</p>}
          </div>
          <CollectorInteractionTable
            interactions={analytics.interactions || []}
            loading={loading}
            onImportClick={handleImportAction}
            importReady={Boolean(importFile)}
            importing={saving}
          />
        </section>
      )}

      <section className="leave-section">
        <div className="leave-section-heading"><div><p className="leave-kicker">ASSIGNMENT LIST</p><h3>Allocate accounts to representatives</h3></div></div>
        <form className="debt-assignment-bar" onSubmit={assignSelected}>
          <label><input aria-label="Select all visible accounts" type="checkbox" checked={allVisibleSelected} onChange={(event) => setSelectedLoans(event.target.checked ? loans.map((loan) => loan.id) : [])} /> {selectedLoans.length} selected</label>
          <label>Representative<select value={collectorId} onChange={(event) => setCollectorId(event.target.value)} required><option value="">Select a representative</option>{collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name} ({collector.active_accounts} active)</option>)}</select></label>
          <label>Reassignment reason<input value={reason} onChange={(event) => setReason(event.target.value)} maxLength="255" placeholder="Required when reassigned" /></label>
          <button type="submit" className="leave-primary-button" disabled={saving || !selectedLoans.length}>{saving ? 'Saving...' : 'Allocate selected'}</button>
        </form>
        {loading ? <p className="leave-empty" role="status">Loading team accounts...</p> : (
          <div className="sales-visit-table-wrap">
            <table className="leave-table">
              <thead><tr><th>Select</th><th>Debtor</th><th>Business</th><th>Representative</th><th>Loan balance</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {loans.length ? loans.map((loan) => (
                  <tr key={loan.id} className={loan.is_duplicate ? 'debt-duplicate-row' : undefined}>
                    <td><input aria-label={`Select ${loan.agent_name}`} type="checkbox" checked={selectedLoans.includes(loan.id)} onChange={(event) => setSelectedLoans((current) => event.target.checked ? [...current, loan.id] : current.filter((id) => id !== loan.id))} /></td>
                    <td>{loan.agent_name}{loan.is_duplicate && <span className="debt-duplicate-badge">Duplicate</span>}</td><td>{loan.business_name}</td><td>{loan.collector_name || 'Unassigned'}</td><td>{money(loan.loan_balance)}</td><td>{loan.status}</td>
                    <td className="debt-action-cell debt-row-actions">
                      <button type="button" className="leave-secondary-button" onClick={() => openLoanForEdit(loan)}>Edit</button>
                      <button type="button" className="leave-text-button" onClick={() => deleteLoan(loan)} disabled={deletingLoanId === loan.id}>{deletingLoanId === loan.id ? 'Deleting...' : 'Delete'}</button>
                      {loan.is_duplicate && <button type="button" className="leave-text-button debt-permanent-delete-button" onClick={() => permanentlyDeleteDuplicate(loan)} disabled={deletingLoanId === loan.id}>{deletingLoanId === loan.id ? 'Deleting...' : 'Delete duplicate permanently'}</button>}
                    </td>
                  </tr>
                )) : <tr><td colSpan="7">No accounts match the selected filters.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editingLoan && <div className="debt-modal-backdrop" role="presentation" onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) setEditingLoan(null);
      }}>
        <section className="debt-interaction-modal debt-record-modal" role="dialog" aria-modal="true" aria-labelledby="team-debt-edit-title">
          <div className="debt-modal-heading">
            <div><p className="leave-kicker">UPDATE PORTFOLIO RECORD</p><h2 id="team-debt-edit-title">Edit debtor and loan</h2><p className="leave-muted">{editingLoan.agent_name} · {editingLoan.business_name}</p></div>
            <button type="button" className="leave-text-button" onClick={() => setEditingLoan(null)} disabled={saving}>Close</button>
          </div>
          <form className="debt-record-editors debt-record-modal-editors" onSubmit={saveLoan}>
            <strong>Debtor and business details</strong>
            <label>First name<input required value={editingLoan.first_name || ''} onChange={(event) => setEditingLoan({ ...editingLoan, first_name: event.target.value })} /></label>
            <label>Other names<input value={editingLoan.other_names || ''} onChange={(event) => setEditingLoan({ ...editingLoan, other_names: event.target.value })} /></label>
            <label>Agent phone<input required value={editingLoan.agent_msisdn} onChange={(event) => setEditingLoan({ ...editingLoan, agent_msisdn: event.target.value })} /></label>
            <label>Owner phone<input value={editingLoan.owner_msisdn || ''} onChange={(event) => setEditingLoan({ ...editingLoan, owner_msisdn: event.target.value })} /></label>
            <label>Operator phone<input value={editingLoan.operator_msisdn || ''} onChange={(event) => setEditingLoan({ ...editingLoan, operator_msisdn: event.target.value })} /></label>
            <label>Agent number<input required value={editingLoan.agent_no || ''} onChange={(event) => setEditingLoan({ ...editingLoan, agent_no: event.target.value })} /></label>
            <label>Store number<input value={editingLoan.store_number || ''} onChange={(event) => setEditingLoan({ ...editingLoan, store_number: event.target.value })} /></label>
            <label>Business name<input required value={editingLoan.business_name || ''} onChange={(event) => setEditingLoan({ ...editingLoan, business_name: event.target.value })} /></label>
            <label>Location<input value={editingLoan.location} onChange={(event) => setEditingLoan({ ...editingLoan, location: event.target.value })} /></label>
            <strong>Loan details</strong>
            <label>Original loan amount<input required type="number" min="0.01" step="0.01" value={editingLoan.loan_amount} onChange={(event) => setEditingLoan({ ...editingLoan, loan_amount: event.target.value })} /></label>
            <label>Amount paid<input required type="number" min="0" step="0.01" value={editingLoan.amount_paid} onChange={(event) => setEditingLoan({ ...editingLoan, amount_paid: event.target.value })} /></label>
            <label>Disbursed date<input required type="date" value={editingLoan.loan_date} onChange={(event) => setEditingLoan({ ...editingLoan, loan_date: event.target.value })} /></label>
            <label>Last interest calculation<input type="date" value={editingLoan.last_interest_calc_date} onChange={(event) => setEditingLoan({ ...editingLoan, last_interest_calc_date: event.target.value })} /></label>
            <label>Days since issue<input required type="number" min="0" step="1" value={editingLoan.no_of_days} onChange={(event) => setEditingLoan({ ...editingLoan, no_of_days: event.target.value })} /></label>
            <label>Status<select value={editingLoan.status} onChange={(event) => setEditingLoan({ ...editingLoan, status: event.target.value })}><option value="active">Active</option><option value="overdue">Overdue</option><option value="in_negotiation">In negotiation</option><option value="promise_to_pay">Promise to pay</option><option value="settled">Settled</option><option value="legal">Legal</option></select></label>
            <div className="debt-edit-action"><button type="submit" className="leave-primary-button" disabled={saving}>{saving ? 'Saving...' : 'Save changes'}</button></div>
          </form>
        </section>
      </div>}
    </section>
  );
}
