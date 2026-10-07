import React, { useCallback, useEffect, useState } from 'react';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken } from '../services/authStorage';
import LogInteractionModal from './LogInteractionModal';
import apiClient from '../services/debtCollectionApi';
import CollectorDashboard from './CollectorDashboard';
import CollectorInteractionTable from './CollectorInteractionTable';

const statusLabels = {
  active: 'Active',
  overdue: 'Overdue',
  in_negotiation: 'In Negotiation',
  promise_to_pay: 'Promise to Pay',
  settled: 'Settled',
  written_off: 'Written Off',
  legal: 'Legal',
};

const formatMoney = (value) => {
  const number = Number(value || 0);
  return new Intl.NumberFormat('en-KE', { style: 'currency', currency: 'KES', maximumFractionDigits: 0 }).format(number);
};

const apiErrorMessage = (error, fallback) => error.response?.data?.error?.message || error.message || fallback;

const emptySummary = { total_outstanding: 0, active_accounts: 0, overdue_accounts: 0, recovered_to_date: 0, records: [], permissions: {} };
const emptyDebtor = { first_name: '', other_names: '', agent_msisdn: '', owner_msisdn: '', operator_msisdn: '', agent_no: '', store_number: '', business_name: '', location: '' };
const emptyLoan = { loan_amount: '', loan_date: '', amount_paid: '0', status: 'active', last_interest_calc_date: '', no_of_days: '0' };
const outcomes = [
  ['phone_off', 'Phone off / client unreachable'],
  ['no_answer', 'Ringing, no answer'],
  ['negotiation', 'Negotiation'],
  ['wrong_number', 'Wrong number'],
  ['promise_to_pay', 'Promise to pay'],
  ['callback_requested', 'Call back requested'],
  ['full_payment', 'Full payment'],
  ['partial_payment', 'Partial payment'],
];

export default function DebtCollectionPage({ compact = false }) {
  const [summary, setSummary] = useState(emptySummary);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('success');
  const [collectors, setCollectors] = useState([]);
  const [followUps, setFollowUps] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [analyticsDates, setAnalyticsDates] = useState({ from: '', to: '' });
  const [performance, setPerformance] = useState(null);
  const [filters, setFilters] = useState({ q: '', status: '', location: '', store_number: '', min_balance: '', max_balance: '', overdue_days: '', collector_id: '', collector_capacity: '' });
  const [appliedFilters, setAppliedFilters] = useState('');
  const [selectedLoans, setSelectedLoans] = useState([]);
  const [collectorId, setCollectorId] = useState('');
  const [distributionOpen, setDistributionOpen] = useState(false);
  const [debtor, setDebtor] = useState(emptyDebtor);
  const [loan, setLoan] = useState(emptyLoan);
  const [importFile, setImportFile] = useState(null);
  const [openCalls, setOpenCalls] = useState(null);
  const [logInteractionLoan, setLogInteractionLoan] = useState(null);
  const [callLogs, setCallLogs] = useState({});
  const [loadingCallLogs, setLoadingCallLogs] = useState({});
  const [callDrafts, setCallDrafts] = useState({});
  const [debtorEdits, setDebtorEdits] = useState({});
  const [loanEdits, setLoanEdits] = useState({});
  const [ratingDrafts, setRatingDrafts] = useState({});
  const [writeOffReasons, setWriteOffReasons] = useState({});

  const showMessage = (text, type = 'success') => {
    setMessageType(type);
    setMessage(text);
  };

  const loadData = useCallback(async (query = appliedFilters) => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${getAuthToken()}` };
      const [summaryResponse, loansResponse] = await Promise.all([
        apiClient.get('/api/debt-collection/summary', { headers }),
        apiClient.get(`/api/debt-collection/loans${query ? `?${query}` : ''}`, { headers }),
      ]);
      const summaryPayload = summaryResponse.data;
      const loansPayload = loansResponse.data;
      setSummary({ ...emptySummary, ...(summaryPayload.data || {}), records: loansPayload.data || [] });
      setError('');
      const permissions = summaryPayload.data?.permissions || {};
      if (permissions.can_manage) {
        const [collectorsResponse, analyticsResponse, followUpsResponse] = await Promise.all([
          apiClient.get('/api/debt-collection/collectors', { headers }),
          apiClient.get('/api/debt-collection/analytics', { headers }),
          apiClient.get('/api/debt-collection/follow-ups', { headers }),
        ]);
        setCollectors(collectorsResponse.data.data || []);
        setAnalytics(analyticsResponse.data.data || null);
        setFollowUps(followUpsResponse.data.data || []);
      } else {
        const [performanceResponse, followUpsResponse] = await Promise.all([
          apiClient.get('/api/debt-collection/analytics/performance', { headers }),
          apiClient.get('/api/debt-collection/follow-ups', { headers }),
        ]);
        setPerformance(performanceResponse.data.data || null);
        setFollowUps(followUpsResponse.data.data || []);
      }
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load debt collection data.'));
    } finally {
      setLoading(false);
    }
  }, [appliedFilters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const request = async (path, options = {}) => {
    const response = await apiClient.request({ url: apiUrl(path),
      ...options,
      data: options.body instanceof FormData || typeof options.body !== 'string' ? options.body : JSON.parse(options.body),
      headers: { Authorization: `Bearer ${getAuthToken()}`, ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers },
    });
    const payload = response.data;
    return payload?.data;
  };

  const submitDebtor = async (event) => {
    event.preventDefault();
    showMessage('');
    try {
      const created = await request('/api/debt-collection/debtors', { method: 'POST', body: JSON.stringify(debtor) });
      if (loan.loan_amount) {
        await request('/api/debt-collection/loans', { method: 'POST', body: JSON.stringify({ ...loan, debtor_id: created.id }) });
      }
      setDebtor(emptyDebtor);
      setLoan(emptyLoan);
      showMessage('Debtor and loan saved.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const assignSelected = async (event) => {
    event.preventDefault();
    if (!collectorId || selectedLoans.length === 0) return;
    try {
      const result = await request('/api/debt-collection/assignments/bulk', { method: 'POST', body: JSON.stringify({ collector_id: Number(collectorId), loan_ids: selectedLoans }) });
      const collector = collectors.find((item) => item.id === Number(collectorId));
      showMessage(`${result.assigned} loan${result.assigned === 1 ? '' : 's'} allocated${collector ? ` to ${collector.full_name}` : ''}.`);
      setSelectedLoans([]);
      setCollectorId('');
      setDistributionOpen(false);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const assignLoan = async (loanId, newCollectorId) => {
    if (!newCollectorId) return;
    try {
      await request(`/api/debt-collection/loans/${loanId}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ collector_id: Number(newCollectorId) }),
      });
      const collector = collectors.find((item) => item.id === Number(newCollectorId));
      showMessage(`Account assigned to ${collector?.full_name || 'collector'}.`);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const saveInteraction = async (loanId, payload) => {
    const result = await request(`/api/debt-collection/loans/${loanId}/calls`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (payload.outcome === 'partial_payment') {
      showMessage(`Partial payment recorded. Outstanding balance: ${formatMoney(result.loan.loan_balance)}.`);
    } else if (payload.outcome === 'full_payment') {
      showMessage('Full payment recorded. Outstanding balance: Ksh 0.');
    } else {
      showMessage('Client interaction recorded.');
    }
    if (openCalls === loanId) await loadCalls(loanId);
    await loadData();
  };

  const submitCall = async (event, loanId) => {
    event.preventDefault();
    const draft = callDrafts[loanId] || {};
    try {
      await request(`/api/debt-collection/loans/${loanId}/calls`, { method: 'POST', body: JSON.stringify(draft) });
      showMessage('Client interaction recorded.');
      setCallDrafts((current) => ({ ...current, [loanId]: { outcome: '', notes: '' } }));
      if (openCalls === loanId) await loadCalls(loanId);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const loadCalls = async (loanId) => {
    setLoadingCallLogs((current) => ({ ...current, [loanId]: true }));
    try {
      const rows = await request(`/api/debt-collection/loans/${loanId}/calls`);
      setCallLogs((current) => ({ ...current, [loanId]: rows || [] }));
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setLoadingCallLogs((current) => ({ ...current, [loanId]: false }));
    }
  };

  const toggleCalls = async (loanId) => {
    const next = openCalls === loanId ? null : loanId;
    setOpenCalls(next);
    if (next !== null) await loadCalls(loanId);
  };

  const saveDebtorDetails = async (event, item) => {
    event.preventDefault();
    try {
      const draft = debtorEdits[item.debtor_id] || item;
      await request(`/api/debt-collection/debtors/${item.debtor_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          first_name: draft.first_name,
          other_names: draft.other_names,
          agent_msisdn: draft.agent_number,
          owner_msisdn: draft.owner_msisdn,
          operator_msisdn: draft.operator_msisdn,
          agent_no: draft.agent_no,
          store_number: draft.store_number,
          business_name: draft.business_name,
          location: draft.business_location,
        }),
      });
      showMessage('Debtor details updated.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const updateDebtorEdit = (item, field, value) => setDebtorEdits((current) => ({
    ...current,
    [item.debtor_id]: { ...item, ...current[item.debtor_id], [field]: value },
  }));

  const saveLoanDetails = async (event, item) => {
    event.preventDefault();
    try {
      await request(`/api/debt-collection/loans/${item.id}`, { method: 'PATCH', body: JSON.stringify(loanEdits[item.id] || {}) });
      showMessage('Loan details updated.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const submitRating = async (event, loanId) => {
    event.preventDefault();
    try {
      await request(`/api/debt-collection/loans/${loanId}/ratings`, { method: 'POST', body: JSON.stringify(ratingDrafts[loanId] || {}) });
      showMessage('Credit rating approved and recorded.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const approveWriteOff = async (event, loanId) => {
    event.preventDefault();
    try {
      await request(`/api/debt-collection/loans/${loanId}/write-off`, { method: 'POST', body: JSON.stringify({ reason: writeOffReasons[loanId] }) });
      showMessage('Loan write-off approved.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const importPortfolio = async (event) => {
    event.preventDefault();
    if (!importFile) return;
    const formData = new FormData();
    formData.append('file', importFile);
    try {
      const result = await request('/api/debt-collection/import', { method: 'POST', body: formData });
      showMessage(`Import complete: ${result.accepted_rows} accepted, ${result.rejected_rows} rejected.`);
      setImportFile(null);
      event.currentTarget.reset();
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const downloadPortfolio = async (format) => {
    try {
      if (appliedFilters) {
        const response = await apiClient.get(apiUrl(`/api/debt-collection/export.${format}?${appliedFilters}`), { responseType: 'blob' });
        const filteredUrl = URL.createObjectURL(response.data);
        const filteredLink = document.createElement('a');
        filteredLink.href = filteredUrl;
        filteredLink.download = `debt-portfolio.${format}`;
        filteredLink.click();
        URL.revokeObjectURL(filteredUrl);
        return;
      }
      const response = await fetch(apiUrl(`/api/debt-collection/export.${format}`), { headers: { Authorization: `Bearer ${getAuthToken()}` } });
      if (!response.ok) throw new Error('Unable to export the debt portfolio.');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `debt-portfolio.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const filterAnalytics = async (event) => {
    event.preventDefault();
    const params = new URLSearchParams(Object.entries(analyticsDates).filter(([, value]) => value));
    try {
      setAnalytics(await request(`/api/debt-collection/analytics${params.toString() ? `?${params}` : ''}`));
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const completeFollowUp = async (followUpId) => {
    try {
      await request(`/api/debt-collection/follow-ups/${followUpId}`, { method: 'PATCH', body: JSON.stringify({ status: 'Completed' }) });
      showMessage('Follow-up marked complete.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const applyFilters = (event) => {
    event.preventDefault();
    const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
    setAppliedFilters(params.toString());
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      setAppliedFilters(params.toString());
    }, 350);
    return () => window.clearTimeout(timer);
  }, [filters]);

  const records = summary.records || [];
  const canManage = Boolean(summary.permissions?.can_manage);
  const updateCallDraft = (loanId, field, value) => setCallDrafts((current) => ({ ...current, [loanId]: { ...current[loanId], [field]: value } }));
  const openLoanFromReport = async (loanId) => {
    if (!loanId) return;
    await toggleCalls(loanId);
    window.setTimeout(() => {
      document.querySelector(`[data-loan-id="${loanId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 0);
  };

  if (!canManage) return <CollectorDashboard compact={compact} />;

  if (compact) {
    return (
      <section className="leave-section" id="debt-collection" aria-label="Debt collection summary">
        <div className="leave-section-heading">
          <div>
            <p className="leave-kicker">COLLECTIONS</p>
            <h2>Debt Collection</h2>
          </div>
        </div>
        <div className="report-card-grid">
          <div className="report-card"><span>{canManage ? 'Total outstanding' : 'My total outstanding'}</span><strong>{formatMoney(summary.total_outstanding)}</strong></div>
          {!canManage && <div className="report-card"><span>Promises to pay today</span><strong>{performance?.periods?.daily?.promises_to_pay || 0}</strong></div>}
          {!canManage && <div className="report-card"><span>Recovered today</span><strong>{formatMoney(performance?.periods?.daily?.recovered)}</strong></div>}
          {canManage && <div className="report-card"><span>Active accounts</span><strong>{summary.active_accounts || 0}</strong></div>}
          {canManage && <div className="report-card"><span>Overdue</span><strong>{summary.overdue_accounts || 0}</strong></div>}
          {canManage && <div className="report-card"><span>Recovered</span><strong>{formatMoney(summary.recovered_to_date)}</strong></div>}
        </div>
        {canManage && (
          <CollectorInteractionTable
            interactions={analytics?.interactions || []}
            loading={loading}
            onOpenLoan={openLoanFromReport}
          />
        )}
        <>
            {message && <div className={`leave-alert ${messageType === 'error' ? 'error' : 'info'}`} role={messageType === 'error' ? 'alert' : 'status'}>{message}</div>}
            {loading && <p className="leave-empty" role="status">Loading your assigned clients…</p>}
            {error && <div className="leave-alert error" role="alert">{error}</div>}
            {!loading && !error && (
              <div className="sales-visit-table-wrap debt-compact-table">
                <table className="leave-table">
                  <thead><tr><th>Client / Business</th><th>Actions</th><th>Loan balance</th><th>Status</th></tr></thead>
                  <tbody>
                    {records.length === 0
                      ? <tr><td colSpan="4">{canManage ? 'No debt collection records available.' : 'No accounts are currently assigned to you.'}</td></tr>
                      : records.map((item) => (
                        <React.Fragment key={item.id}>
                          <tr data-loan-id={item.id}>
                            <td><strong>{item.agent_name}</strong><small>{item.business_name} · {item.business_location || 'Location not set'}</small><a className="debt-client-phone" href={`tel:${item.agent_number}`}>{item.agent_number}</a></td>
                            <td className="debt-action-cell">
                              <button type="button" className="leave-primary-button debt-log-call" onClick={() => setLogInteractionLoan(item)}>Log Call</button>
                              <button type="button" className="leave-text-button" aria-expanded={openCalls === item.id} onClick={() => toggleCalls(item.id)}>{openCalls === item.id ? 'Hide history' : 'View history'}</button>
                            </td>
                            <td><strong>{formatMoney(item.loan_balance)}</strong></td>
                            <td><span className="sales-outcome">{statusLabels[item.status] || item.status}</span></td>
                          </tr>
                          {openCalls === item.id && (
                            <tr className="debt-compact-history-row">
                              <td colSpan="4">
                                <section className="debt-call-history debt-compact-history" aria-label={`Interaction history for ${item.agent_name}`}>
                                  <strong>Interaction history · {item.agent_name}</strong>
                                  {loadingCallLogs[item.id]
                                    ? <p className="leave-empty" role="status">Loading interaction history…</p>
                                    : (callLogs[item.id] || []).length === 0
                                      ? <p className="leave-empty">No interactions logged for this client yet.</p>
                                      : (callLogs[item.id] || []).map((call) => (
                                        <article key={call.id}>
                                          <strong>{outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</strong>
                                          <span>Collector: {call.collector_name} · Contacted: {new Date(call.created_at).toLocaleString()}</span>
                                          <span>Debtor: {call.debtor_name || item.agent_name} · {call.business_name || item.business_name}</span>
                                          <span>Response: {outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</span>
                                          {call.notes && <p>Remarks: {call.notes}</p>}
                                          {call.promised_date && <span>Next payment: {new Date(`${call.promised_date}T${call.promised_time || '00:00'}`).toLocaleString()}{call.promised_amount ? ` · Agreed amount: ${formatMoney(call.promised_amount)}` : ''}</span>}
                                          {call.callback_date && <span>Callback: {new Date(`${call.callback_date}T${call.callback_time || '00:00'}`).toLocaleString()}</span>}
                                          <span>Paid to date: {formatMoney(call.amount_paid_to_date)} · Outstanding: {formatMoney(call.loan_balance)}</span>
                                          {Number(call.amount_paid) > 0 && <span>Payment on this call: {formatMoney(call.amount_paid)}</span>}
                                        </article>
                                      ))}
                                </section>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
        </>
        {logInteractionLoan && (
          <LogInteractionModal
            loan={logInteractionLoan}
            onClose={() => setLogInteractionLoan(null)}
            onSave={(payload) => saveInteraction(logInteractionLoan.id, payload)}
          />
        )}
      </section>
    );
  }

  return (
    <section className="sales-reports-page" id="debt-collection">
      <div className="sales-page-hero">
        <div>
          <p className="leave-kicker">{canManage ? 'PORTFOLIO MANAGEMENT' : 'COLLECTOR WORKSPACE'}</p>
          <h2>{canManage ? 'Debt Collection' : 'My Assigned Portfolio'}</h2>
          <p className="leave-muted">{canManage ? 'Allocate accounts, monitor recovery, and manage outstanding balances.' : 'Work your allocated accounts and record every client interaction.'}</p>
        </div>
      </div>

      {loading && <p className="leave-empty">Loading debt collection portfolio…</p>}
      {error && <div className="leave-alert error" role="status">{error}</div>}
      {message && <div className={`leave-alert ${messageType === 'error' ? 'error' : 'info'}`} role={messageType === 'error' ? 'alert' : 'status'}>{message}</div>}

      {!loading && !error && (
        <>
          {canManage ? (
            <div className="report-card-grid">
              <div className="report-card"><span>Total outstanding</span><strong>{formatMoney(summary.total_outstanding)}</strong></div>
              <div className="report-card"><span>Active accounts</span><strong>{summary.active_accounts || 0}</strong></div>
              <div className="report-card"><span>Overdue accounts</span><strong>{summary.overdue_accounts || 0}</strong></div>
              <div className="report-card"><span>Recovered to date</span><strong>{formatMoney(summary.recovered_to_date)}</strong></div>
            </div>
          ) : (
            <div className="report-card-grid">
              <div className="report-card"><span>My total outstanding</span><strong>{formatMoney(summary.total_outstanding)}</strong></div>
              <div className="report-card"><span>Promises to pay today</span><strong>{performance?.periods?.daily?.promises_to_pay || 0}</strong></div>
              <div className="report-card"><span>Recovered today</span><strong>{formatMoney(performance?.periods?.daily?.recovered)}</strong></div>
            </div>
          )}

          {canManage && (
            <CollectorInteractionTable
              interactions={analytics?.interactions || []}
              loading={loading}
              onOpenLoan={openLoanFromReport}
            />
          )}

          {canManage ? (
            <>
              <section className="leave-section debt-manager-tools">
                <div className="leave-section-heading"><div><p className="leave-kicker">PORTFOLIO CONTROLS</p><h3>Debtor management</h3></div></div>
                <form className="debt-form-grid" onSubmit={submitDebtor}>
                  <label>First name<input value={debtor.first_name} onChange={(event) => setDebtor({ ...debtor, first_name: event.target.value })} required /></label>
                  <label>Middle and last names<input value={debtor.other_names} onChange={(event) => setDebtor({ ...debtor, other_names: event.target.value })} /></label>
                  <label>Agent phone<input value={debtor.agent_msisdn} onChange={(event) => setDebtor({ ...debtor, agent_msisdn: event.target.value })} required /></label>
                  <label>Business owner phone<input value={debtor.owner_msisdn} onChange={(event) => setDebtor({ ...debtor, owner_msisdn: event.target.value })} /></label>
                  <label>Business operator phone<input value={debtor.operator_msisdn} onChange={(event) => setDebtor({ ...debtor, operator_msisdn: event.target.value })} /></label>
                  <label>Unique agent ID<input value={debtor.agent_no} onChange={(event) => setDebtor({ ...debtor, agent_no: event.target.value })} required /></label>
                  <label>Store / branch ID<input value={debtor.store_number} onChange={(event) => setDebtor({ ...debtor, store_number: event.target.value })} /></label>
                  <label>Registered business name<input value={debtor.business_name} onChange={(event) => setDebtor({ ...debtor, business_name: event.target.value })} required /></label>
                  <label>Physical location<input value={debtor.location} onChange={(event) => setDebtor({ ...debtor, location: event.target.value })} /></label>
                  <label>Original loan amount<input type="number" min="0.01" step="0.01" value={loan.loan_amount} onChange={(event) => setLoan({ ...loan, loan_amount: event.target.value })} /></label>
                  <label>Disbursement date<input type="date" value={loan.loan_date} onChange={(event) => setLoan({ ...loan, loan_date: event.target.value })} /></label>
                  <label>Amount already paid<input type="number" min="0" step="0.01" value={loan.amount_paid} onChange={(event) => setLoan({ ...loan, amount_paid: event.target.value })} /></label>
                  <label>Last interest calculation<input type="date" value={loan.last_interest_calc_date} onChange={(event) => setLoan({ ...loan, last_interest_calc_date: event.target.value })} /></label>
                  <label>Days since disbursement<input type="number" min="0" step="1" value={loan.no_of_days} onChange={(event) => setLoan({ ...loan, no_of_days: event.target.value })} /></label>
                  <label>Loan status<select value={loan.status} onChange={(event) => setLoan({ ...loan, status: event.target.value })}>{Object.entries(statusLabels).filter(([value]) => value !== 'written_off').map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                  <div className="debt-form-actions"><button className="leave-primary-button" type="submit">Save debtor / loan</button></div>
                </form>
                <div className="debt-transfer-row">
                  <form onSubmit={importPortfolio} className="debt-import-form"><label>Import CSV / Excel<input type="file" accept=".csv,.xlsx" onChange={(event) => setImportFile(event.target.files?.[0] || null)} required /></label><button className="leave-secondary-button" type="submit">Import portfolio</button></form>
                  <div className="debt-export-actions"><button type="button" className="leave-secondary-button" onClick={() => downloadPortfolio('csv')}>Export CSV</button><button type="button" className="leave-secondary-button" onClick={() => downloadPortfolio('xlsx')}>Export Excel</button></div>
                </div>
              </section>

              {analytics && <section className="leave-section debt-analytics">
                <div className="leave-section-heading"><div><p className="leave-kicker">RECOVERY MONITOR</p><h3>Portfolio health and collector performance</h3></div></div>
                <form className="debt-analytics-filter" onSubmit={filterAnalytics}><label>From<input type="date" value={analyticsDates.from} onChange={(event) => setAnalyticsDates({ ...analyticsDates, from: event.target.value })} /></label><label>To<input type="date" value={analyticsDates.to} onChange={(event) => setAnalyticsDates({ ...analyticsDates, to: event.target.value })} /></label><button className="leave-secondary-button" type="submit">Filter reports</button></form>
                <div className="report-card-grid"><div className="report-card"><span>Book accounts</span><strong>{analytics.portfolio.accounts}</strong></div><div className="report-card"><span>Current outstanding</span><strong>{formatMoney(analytics.portfolio.outstanding)}</strong></div><div className="report-card"><span>Period recovered</span><strong>{formatMoney(analytics.period_recovered)}</strong></div><div className="report-card"><span>Period calls</span><strong>{analytics.period_calls}</strong></div></div>
                <div className="debt-recovery-trends" aria-label="Daily recovery trend">
                  <strong>Recovery trends</strong>
                  {analytics.recovery_trends?.length ? analytics.recovery_trends.map((trend) => {
                    const maximum = Math.max(...analytics.recovery_trends.map((item) => Number(item.recovered)));
                    const width = maximum ? Math.max(3, (Number(trend.recovered) / maximum) * 100) : 3;
                    return <div className="debt-recovery-trend" key={trend.date}><time>{trend.date}</time><span><i style={{ width: `${width}%` }} /></span><strong>{formatMoney(trend.recovered)}</strong></div>;
                  }) : <p className="leave-empty">No recovery payments in this date range.</p>}
                </div>
                <div className="sales-visit-table-wrap"><table className="leave-table"><thead><tr><th>Collector</th><th>Calls</th><th>Payments</th><th>Recovered</th></tr></thead><tbody>{analytics.collectors.length ? analytics.collectors.map((item) => <tr key={item.collector_id}><td>{item.collector_name}</td><td>{item.calls}</td><td>{item.payments}</td><td>{formatMoney(item.recovered)}</td></tr>) : <tr><td colSpan="4">No collector activity in this period.</td></tr>}</tbody></table></div>
              </section>}

              {selectedLoans.length > 0 && <div className="debt-assignment-bar"><strong>{selectedLoans.length} selected</strong><button type="button" className="leave-primary-button" onClick={() => setDistributionOpen(true)}>Distribute List</button></div>}
            </>
          ) : (
            null
          )}

          <form className="debt-filter-bar" onSubmit={applyFilters}>
            <label>Search<input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} placeholder="Name, agent ID, business or phone" /></label>
            <label>Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All statuses</option>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            {canManage && <><label>Location<input value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} /></label><label>Store / branch<input value={filters.store_number} onChange={(event) => setFilters({ ...filters, store_number: event.target.value })} /></label><label>Collector<select value={filters.collector_id} onChange={(event) => setFilters({ ...filters, collector_id: event.target.value })}><option value="">All collectors</option>{collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name} ({collector.active_accounts} active)</option>)}</select></label><label>Max collector load<input type="number" min="0" step="1" value={filters.collector_capacity} onChange={(event) => setFilters({ ...filters, collector_capacity: event.target.value })} placeholder="Active accounts" /></label><label>Minimum balance<input type="number" min="0" step="0.01" value={filters.min_balance} onChange={(event) => setFilters({ ...filters, min_balance: event.target.value })} /></label><label>Maximum balance<input type="number" min="0" step="0.01" value={filters.max_balance} onChange={(event) => setFilters({ ...filters, max_balance: event.target.value })} /></label><label>Overdue age (days)<input type="number" min="0" step="1" value={filters.overdue_days} onChange={(event) => setFilters({ ...filters, overdue_days: event.target.value })} /></label></>}
            <button type="submit" className="leave-secondary-button">Apply filters</button>
            <button type="button" className="leave-text-button" onClick={() => { const cleared = { q: '', status: '', location: '', store_number: '', min_balance: '', max_balance: '', overdue_days: '', collector_id: '', collector_capacity: '' }; setFilters(cleared); setAppliedFilters(''); }}>Clear</button>
          </form>

          <div className="sales-visit-table-wrap">
            <table className="leave-table">
              <thead>
                <tr>
                  {canManage && <th><input aria-label="Select all loans" type="checkbox" checked={records.length > 0 && records.every((item) => selectedLoans.includes(item.id))} onChange={(event) => setSelectedLoans((current) => event.target.checked ? Array.from(new Set([...current, ...records.map((item) => item.id)])) : current.filter((id) => !records.some((item) => item.id === id)))} /></th>}
                  {canManage && <th>Agent</th>}
                  <th>{canManage ? 'Business' : 'Client / Business'}</th>
                  <th>Actions</th>
                  <th>Location</th>
                  <th>Record created</th>
                  <th>Disbursed</th>
                  <th>Original loan</th>
                  <th>Paid to date</th>
                  <th>Loan balance</th>
                  <th>Last interest</th>
                  <th>Days since issue</th>
                  <th>Next agreed payment</th>
                  <th>Status</th>
                  <th>Credit rating</th>
                  {canManage && <th>Assign To</th>}
                  <th>Last contact</th>
                  {canManage && <th>Activity</th>}
                </tr>
              </thead>
              <tbody>
                {records.length === 0 ? (
                  <tr><td colSpan={canManage ? 18 : 14}>No debt collection records available.</td></tr>
                ) : records.map((item) => (
                  <React.Fragment key={item.id}>
                    <tr data-loan-id={item.id}>
                      {canManage && <td><input aria-label={`Select ${item.agent_name}`} type="checkbox" checked={selectedLoans.includes(item.id)} onChange={(event) => setSelectedLoans((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /></td>}
                      {canManage && <td><strong>{item.agent_name}</strong><small>Agent: {item.agent_number} · {item.agent_no}</small><small>Owner: {item.owner_msisdn || '-'}</small><small>Operator: {item.operator_msisdn || '-'}</small></td>}
                      <td>{canManage
                        ? <><strong>{item.business_name}</strong><small>{item.store_number || '-'}</small></>
                        : <><strong>{item.agent_name}</strong><small>{item.business_name} · {item.store_number || '-'}</small><a className="debt-client-phone" href={`tel:${item.agent_number}`}>{item.agent_number}</a></>}
                      </td>
                      <td className="debt-action-cell"><button type="button" className="leave-primary-button debt-log-call" onClick={() => setLogInteractionLoan(item)}>Log Call</button><button type="button" className="leave-text-button" onClick={() => toggleCalls(item.id)}>{openCalls === item.id ? 'Hide details' : 'View Details'}</button></td>
                      <td>{item.business_location || '-'}</td>
                      <td>{item.record_created_at ? new Date(item.record_created_at).toLocaleDateString() : '-'}</td>
                      <td>{item.loan_date || '-'}</td>
                      <td>{formatMoney(item.loan_amount)}</td>
                      <td>{formatMoney(item.amount_paid)}</td>
                      <td>{formatMoney(item.loan_balance)}</td>
                      <td>{item.last_interest_calc_date || '-'}</td>
                      <td>{item.no_of_days ?? 0}</td>
                      <td>{item.next_payment_date ? <>{item.next_payment_date} {item.next_payment_time || ''}{item.next_payment_amount ? <small>{formatMoney(item.next_payment_amount)}</small> : null}</> : '-'}</td>
                      <td><span className="sales-outcome">{statusLabels[item.status] || item.status}</span></td>
                      <td>{item.credit_rating ? `${item.credit_rating} · ${item.credit_score}` : '-'}</td>
                      {canManage && <td><select aria-label={`Assign ${item.agent_name} to collector`} value={item.collector_id || ''} onChange={(event) => assignLoan(item.id, event.target.value)}><option value="">Unassigned</option>{collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name}</option>)}</select></td>}
                      <td>{item.last_contact || '-'}</td>
                      {canManage && <td><button type="button" className="leave-text-button" onClick={() => toggleCalls(item.id)}>{openCalls === item.id ? 'Hide details' : 'View Details'}</button></td>}
                    </tr>
                    {openCalls === item.id && <tr><td colSpan={canManage ? 18 : 14}>
                      <div className="debt-activity-panel">
                        {canManage && <div className="debt-record-editors">
                          <form onSubmit={(event) => saveDebtorDetails(event, item)}><strong>Edit debtor</strong><label>First name<input required value={(debtorEdits[item.debtor_id] || item).first_name || ''} onChange={(event) => updateDebtorEdit(item, 'first_name', event.target.value)} /></label><label>Other names<input value={(debtorEdits[item.debtor_id] || item).other_names || ''} onChange={(event) => updateDebtorEdit(item, 'other_names', event.target.value)} /></label><label>Agent phone<input required value={(debtorEdits[item.debtor_id] || item).agent_number || ''} onChange={(event) => updateDebtorEdit(item, 'agent_number', event.target.value)} /></label><label>Owner phone<input value={(debtorEdits[item.debtor_id] || item).owner_msisdn || ''} onChange={(event) => updateDebtorEdit(item, 'owner_msisdn', event.target.value)} /></label><label>Operator phone<input value={(debtorEdits[item.debtor_id] || item).operator_msisdn || ''} onChange={(event) => updateDebtorEdit(item, 'operator_msisdn', event.target.value)} /></label><label>Agent identifier<input required value={(debtorEdits[item.debtor_id] || item).agent_no || ''} onChange={(event) => updateDebtorEdit(item, 'agent_no', event.target.value)} /></label><label>Store / branch<input value={(debtorEdits[item.debtor_id] || item).store_number || ''} onChange={(event) => updateDebtorEdit(item, 'store_number', event.target.value)} /></label><label>Business name<input required value={(debtorEdits[item.debtor_id] || item).business_name || ''} onChange={(event) => updateDebtorEdit(item, 'business_name', event.target.value)} /></label><label>Location<input value={(debtorEdits[item.debtor_id] || item).business_location || ''} onChange={(event) => updateDebtorEdit(item, 'business_location', event.target.value)} /></label><div className="debt-edit-action"><button className="leave-secondary-button" type="submit">Save debtor</button></div></form>
                          <form onSubmit={(event) => saveLoanDetails(event, item)}><strong>Edit loan terms</strong><label>Original loan amount<input type="number" min="0.01" step="0.01" required value={loanEdits[item.id]?.loan_amount ?? item.loan_amount} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], loan_amount: event.target.value } }))} /></label><label>Disbursed date<input type="date" required value={loanEdits[item.id]?.loan_date ?? item.loan_date} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], loan_date: event.target.value } }))} /></label><label>Last interest calculation<input type="date" value={loanEdits[item.id]?.last_interest_calc_date ?? item.last_interest_calc_date ?? ''} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], last_interest_calc_date: event.target.value || null } }))} /></label><label>Loan status<select value={loanEdits[item.id]?.status ?? item.status} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], status: event.target.value } }))}>{Object.entries(statusLabels).filter(([value]) => value !== 'written_off').map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><div className="debt-edit-action"><button className="leave-secondary-button" type="submit">Save loan</button></div></form>
                        </div>}
                        {canManage && <form className="debt-call-form" onSubmit={(event) => submitCall(event, item.id)}>
                          <label>Call outcome<select required value={callDrafts[item.id]?.outcome || ''} onChange={(event) => updateCallDraft(item.id, 'outcome', event.target.value)}><option value="">Select outcome</option>{outcomes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                          {callDrafts[item.id]?.outcome === 'promise_to_pay' && <><label>Promise date<input type="date" required value={callDrafts[item.id]?.promised_date || ''} onChange={(event) => updateCallDraft(item.id, 'promised_date', event.target.value)} /></label><label>Promise time<input type="time" required value={callDrafts[item.id]?.promised_time || ''} onChange={(event) => updateCallDraft(item.id, 'promised_time', event.target.value)} /></label><label>Promised amount<input type="number" min="0" step="0.01" value={callDrafts[item.id]?.promised_amount || ''} onChange={(event) => updateCallDraft(item.id, 'promised_amount', event.target.value)} /></label></>}
                          {callDrafts[item.id]?.outcome === 'callback_requested' && <><label>Callback date<input type="date" required value={callDrafts[item.id]?.callback_date || ''} onChange={(event) => updateCallDraft(item.id, 'callback_date', event.target.value)} /></label><label>Callback time<input type="time" required value={callDrafts[item.id]?.callback_time || ''} onChange={(event) => updateCallDraft(item.id, 'callback_time', event.target.value)} /></label></>}
                          {callDrafts[item.id]?.outcome === 'partial_payment' && <><label>Amount paid<input type="number" min="0.01" step="0.01" required value={callDrafts[item.id]?.amount_paid || ''} onChange={(event) => updateCallDraft(item.id, 'amount_paid', event.target.value)} /></label><label>Next payment date<input type="date" required value={callDrafts[item.id]?.promised_date || ''} onChange={(event) => updateCallDraft(item.id, 'promised_date', event.target.value)} /></label><label>Next payment time<input type="time" required value={callDrafts[item.id]?.promised_time || ''} onChange={(event) => updateCallDraft(item.id, 'promised_time', event.target.value)} /></label><label>Agreed next payment amount<input type="number" min="0.01" step="0.01" value={callDrafts[item.id]?.promised_amount || ''} onChange={(event) => updateCallDraft(item.id, 'promised_amount', event.target.value)} /></label></>}
                          <label className="debt-notes-field">Interaction notes<textarea rows="2" value={callDrafts[item.id]?.notes || ''} onChange={(event) => updateCallDraft(item.id, 'notes', event.target.value)} /></label>
                          <button className="leave-primary-button" type="submit">Save interaction</button>
                        </form>}
                        {canManage && <div className="debt-manager-actions">
                          <form onSubmit={(event) => submitRating(event, item.id)}><strong>Approve credit rating</strong><select aria-label="Credit grade" value={ratingDrafts[item.id]?.grade || 'C'} onChange={(event) => setRatingDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], grade: event.target.value } }))}>{['A', 'B', 'C', 'D', 'E'].map((grade) => <option key={grade}>{grade}</option>)}</select><input aria-label="Credit score" type="number" min="0" max="100" value={ratingDrafts[item.id]?.score || '50'} onChange={(event) => setRatingDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], score: event.target.value } }))} /><input aria-label="Rating reason" placeholder="Reason for rating" required value={ratingDrafts[item.id]?.reason || ''} onChange={(event) => setRatingDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], reason: event.target.value } }))} /><button className="leave-secondary-button" type="submit">Approve rating</button></form>
                          <form onSubmit={(event) => approveWriteOff(event, item.id)}><strong>Approve loan write-off</strong><input required aria-label="Write-off reason" placeholder="Reason required" value={writeOffReasons[item.id] || ''} onChange={(event) => setWriteOffReasons((current) => ({ ...current, [item.id]: event.target.value }))} /><button className="leave-secondary-button" type="submit">Approve write-off</button></form>
                        </div>}
                        <div className="debt-call-history"><strong>Interaction history · {item.agent_name} · {item.business_name}</strong>{loadingCallLogs[item.id] ? <p className="leave-empty">Loading call log…</p> : (callLogs[item.id] || []).length === 0 ? <p className="leave-empty">No calls recorded for this loan.</p> : (callLogs[item.id] || []).map((call) => <article key={call.id}><strong>{outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</strong><span>Collector: {call.collector_name} · Contacted: {new Date(call.created_at).toLocaleString()}</span><span>Debtor: {call.debtor_name || item.agent_name} · {call.business_name || item.business_name}</span><span>Response: {outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</span>{call.notes && <p>Remarks: {call.notes}</p>}{call.promised_date && <span>Promise: {call.promised_date} {call.promised_time || ''}{call.promised_amount ? ` · ${formatMoney(call.promised_amount)}` : ''}</span>}{call.callback_date && <span>Callback: {call.callback_date} {call.callback_time || ''}</span>}{Number(call.amount_paid) > 0 && <span>Payment: {formatMoney(call.amount_paid)} · Paid to date: {formatMoney(call.amount_paid_to_date)} · Balance: {formatMoney(call.loan_balance)}</span>}</article>)}</div>
                      </div>
                    </td></tr>}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {followUps.length > 0 && <section className="leave-section debt-follow-ups"><div className="leave-section-heading"><div><p className="leave-kicker">SCHEDULED ACTIONS</p><h3>{canManage ? 'Upcoming collector follow-ups' : 'My follow-up queue'}</h3></div></div><div className="sales-visit-table-wrap"><table className="leave-table"><thead><tr><th>Due</th><th>Type</th><th>Debtor</th><th>Business</th>{canManage && <th>Collector</th>}<th>Status</th><th>Action</th></tr></thead><tbody>{followUps.map((item) => <tr key={item.id}><td>{new Date(item.due_at).toLocaleString()}</td><td>{item.follow_up_type}</td><td>{item.debtor.agent_name}</td><td>{item.debtor.business_name}</td>{canManage && <td>{item.collector_name}</td>}<td>{item.status}</td><td>{item.status === 'Pending' && <button type="button" className="leave-text-button" onClick={() => completeFollowUp(item.id)}>Mark complete</button>}</td></tr>)}</tbody></table></div></section>}
        </>
      )}
      {logInteractionLoan && (
        <LogInteractionModal
          loan={logInteractionLoan}
          onClose={() => setLogInteractionLoan(null)}
          onSave={(payload) => saveInteraction(logInteractionLoan.id, payload)}
        />
      )}
      {distributionOpen && (
        <div className="debt-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setDistributionOpen(false);
        }}>
          <section className="debt-interaction-modal" role="dialog" aria-modal="true" aria-labelledby="distribution-title">
            <div className="debt-modal-heading">
              <div><p className="leave-kicker">PORTFOLIO MANAGEMENT</p><h2 id="distribution-title">Distribute selected accounts</h2></div>
              <button type="button" className="leave-text-button" onClick={() => setDistributionOpen(false)}>Close</button>
            </div>
            <form className="debt-modal-form" onSubmit={assignSelected}>
              <label>Debt collector
                <select value={collectorId} onChange={(event) => setCollectorId(event.target.value)} required>
                  <option value="">Choose debt collector</option>
                  {collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name} · {collector.active_accounts} active</option>)}
                </select>
              </label>
              <p>{selectedLoans.length} loan{selectedLoans.length === 1 ? '' : 's'} will be assigned.</p>
              <div className="debt-modal-actions">
                <button type="button" className="leave-secondary-button" onClick={() => setDistributionOpen(false)}>Cancel</button>
                <button type="submit" className="leave-primary-button">Assign selected</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
