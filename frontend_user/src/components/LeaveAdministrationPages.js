import React, { useEffect, useState } from 'react';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken } from '../services/authStorage';
import './LeaveDashboard.css';

const request = async (path, options = {}) => {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      Authorization: `Bearer ${getAuthToken()}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });
  const isJson = response.headers.get('content-type')?.includes('application/json');
  const payload = isJson ? await response.json().catch(() => null) : null;
  if (!payload) {
    throw new Error(`The leave service returned an unexpected response (HTTP ${response.status}). Check that the backend is running and up to date.`);
  }
  if (!response.ok) {
    throw new Error(payload.error?.message || payload.error || payload.message || 'Unable to complete the request.');
  }
  return payload;
};

export function LeavePolicyPage() {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    request('/api/leave/admin/policies')
      .then((payload) => setPolicies(payload.data || []))
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, []);

  const savePolicy = async (policy) => {
    setSavingId(policy.leave_type_id);
    setError('');
    setSuccess('');
    try {
      const payload = await request(`/api/leave/admin/policies/${policy.leave_type_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          annual_entitlement_days: Number(policy.annual_entitlement_days),
          max_carryover: Number(policy.max_carryover),
          notice_days_required: Number(policy.notice_days_required),
          min_service_months: Number(policy.min_service_months),
          gender_restriction: policy.gender_restriction || null,
        }),
      });
      setPolicies((items) => items.map((item) => (
        item.leave_type_id === policy.leave_type_id ? payload.data : item
      )));
      setSuccess(`${policy.name} allocation saved.`);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSavingId(null);
    }
  };

  return (
    <section className="leave-section" aria-labelledby="leave-policy-title">
      <div className="leave-section-heading">
        <div><p className="leave-kicker">ADMINISTRATION</p><h2 id="leave-policy-title">Leave policy</h2></div>
      </div>
      <p>Set the annual allocation for each paid leave type. Existing employee-specific overrides are preserved.</p>
      {error && <div className="leave-alert error" role="alert">{error}</div>}
      {success && <div className="leave-alert success" role="status">{success}</div>}
      {loading ? <p>Loading leave policies…</p> : (
        <div className="leave-table-wrap">
          <table className="leave-table">
            <thead><tr><th>Leave type</th><th>Code</th><th>Annual days</th><th>Carryover</th><th>Notice days</th><th>Service months</th><th>Gender restriction</th><th>Action</th></tr></thead>
            <tbody>
              {policies.map((policy) => (
                <tr key={policy.leave_type_id}>
                  <td>{policy.name}</td>
                  <td>{policy.code}</td>
                  <td>
                    <input
                      aria-label={`${policy.name} annual days`}
                      type="number"
                      min="0"
                      max="366"
                      step="0.5"
                      value={policy.annual_entitlement_days}
                      onChange={(event) => setPolicies((items) => items.map((item) => (
                        item.leave_type_id === policy.leave_type_id
                          ? { ...item, annual_entitlement_days: event.target.value }
                          : item
                      )))}
                    />
                  </td>
                  <td><input aria-label={`${policy.name} maximum carryover days`} type="number" min="0" max="366" step="0.5" value={policy.max_carryover} onChange={(event) => setPolicies((items) => items.map((item) => item.leave_type_id === policy.leave_type_id ? { ...item, max_carryover: event.target.value } : item))} /></td>
                  <td><input aria-label={`${policy.name} notice days`} type="number" min="0" max="365" step="1" value={policy.notice_days_required} onChange={(event) => setPolicies((items) => items.map((item) => item.leave_type_id === policy.leave_type_id ? { ...item, notice_days_required: event.target.value } : item))} /></td>
                  <td><input aria-label={`${policy.name} minimum service months`} type="number" min="0" max="1200" step="1" value={policy.min_service_months} onChange={(event) => setPolicies((items) => items.map((item) => item.leave_type_id === policy.leave_type_id ? { ...item, min_service_months: event.target.value } : item))} /></td>
                  <td><select aria-label={`${policy.name} gender restriction`} value={policy.gender_restriction || ''} onChange={(event) => setPolicies((items) => items.map((item) => item.leave_type_id === policy.leave_type_id ? { ...item, gender_restriction: event.target.value || null } : item))}><option value="">None</option><option value="Female">Female</option><option value="Male">Male</option></select></td>
                  <td>
                    <button type="button" className="leave-primary-button" disabled={savingId === policy.leave_type_id} onClick={() => savePolicy(policy)}>
                      {savingId === policy.leave_type_id ? 'Saving…' : 'Save policy'}
                    </button>
                  </td>
                </tr>
              ))}
              {!policies.length && <tr><td colSpan="8">No paid leave types are configured.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BalanceAdjustmentRow({ balance, onSaved }) {
  const [entitledDays, setEntitledDays] = useState(String(balance.entitled_days));
  const [usedDays, setUsedDays] = useState(String(balance.used_days));
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const save = async (event) => {
    event.preventDefault();
    const adjustment = {};
    if (Number(entitledDays) !== Number(balance.entitled_days)) adjustment.entitled_days = Number(entitledDays);
    if (Number(usedDays) !== Number(balance.used_days)) adjustment.used_days = Number(usedDays);
    if (!Object.keys(adjustment).length) {
      setError('Change the allocation or taken days before saving.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const payload = await request(`/api/leave/admin/balances/${balance.user_id}/${balance.leave_type_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          year: balance.year,
          ...adjustment,
          reason,
        }),
      });
      onSaved(payload.data);
      setReason('');
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr>
      <td>{balance.employee_name}<small>{balance.employee_id || `User ${balance.user_id}`}</small></td>
      <td>{balance.department || '—'}</td>
      <td>{balance.name}</td>
      <td><input aria-label={`${balance.employee_name} ${balance.name} allocated days`} type="number" min="0" max="366" step="0.5" value={entitledDays} onChange={(event) => setEntitledDays(event.target.value)} required /></td>
      <td>{balance.total_allocated_days}</td>
      <td><input aria-label={`${balance.employee_name} ${balance.name} taken days`} type="number" min="0" max="366" step="0.5" value={usedDays} onChange={(event) => setUsedDays(event.target.value)} required /></td>
      <td>{balance.remaining_days}</td>
      <td>
        <form onSubmit={save} className="leave-balance-adjustment">
          <input aria-label={`Reason for ${balance.employee_name} balance adjustment`} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason required" required minLength="3" maxLength="500" />
          <button type="submit" className="leave-primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
          {error && <span role="alert">{error}</span>}
        </form>
      </td>
    </tr>
  );
}

export function LeaveBalancesAdminPage() {
  const [balances, setBalances] = useState([]);
  const [year, setYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    request(`/api/leave/admin/balances?year=${year}`)
      .then((payload) => setBalances(payload.data || []))
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, [year]);

  const updateBalance = (updated) => {
    setBalances((items) => items.map((item) => (
      item.user_id === updated.user_id && item.leave_type_id === updated.leave_type_id
        ? { ...item, ...updated }
        : item
    )));
    setSuccess('Balance saved. The adjustment and reason were added to the audit log.');
  };

  return (
    <section className="leave-section" aria-labelledby="leave-balances-title">
      <div className="leave-section-heading">
        <div><p className="leave-kicker">ADMINISTRATION</p><h2 id="leave-balances-title">Employee leave balances</h2></div>
        <label>Year <input aria-label="Leave balance year" type="number" min="2000" max="9999" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
      </div>
      <p>Review annual allocation, leave taken, and remaining balance. Any manual change requires a reason and is audited.</p>
      {error && <div className="leave-alert error" role="alert">{error}</div>}
      {success && <div className="leave-alert success" role="status">{success}</div>}
      {loading ? <p>Loading employee balances…</p> : (
        <div className="leave-table-wrap">
          <table className="leave-table">
            <thead><tr><th>Employee</th><th>Department</th><th>Leave type</th><th>Annual allocation</th><th>Total allocated</th><th>Taken</th><th>Remaining</th><th>Adjustment (reason required)</th></tr></thead>
            <tbody>
              {balances.map((balance) => (
                <BalanceAdjustmentRow key={`${balance.user_id}-${balance.leave_type_id}`} balance={balance} onSaved={updateBalance} />
              ))}
              {!balances.length && <tr><td colSpan="8">No employee leave balances found for {year}.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function LeaveHistoryAdminPage() {
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [requests, setRequests] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 0, total: 0 });
  const [filters, setFilters] = useState({ employee: '', year: '', leave_type_id: '', status: '' });
  const [appliedFilters, setAppliedFilters] = useState(filters);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    request('/api/leave/types')
      .then((payload) => setLeaveTypes(payload.data || []))
      .catch((loadError) => setError(loadError.message));
  }, []);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ page: String(page), per_page: '50' });
    Object.entries(appliedFilters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    setLoading(true);
    setError('');
    request(`/api/leave/admin/requests?${params.toString()}`)
      .then((payload) => {
        if (!active) return;
        setRequests(payload.data || []);
        setPagination(payload.pagination || { page, pages: 0, total: 0 });
      })
      .catch((loadError) => {
        if (active) setError(loadError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [appliedFilters, page]);

  const applyFilters = (event) => {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({ ...filters });
  };

  return (
    <section className="leave-section" aria-labelledby="admin-leave-history-title">
      <div className="leave-section-heading">
        <div><p className="leave-kicker">ADMINISTRATION</p><h2 id="admin-leave-history-title">Employee leave history</h2></div>
        <span className="section-meta">{pagination.total} requests</span>
      </div>
      <p>Review past and current requests, including status, dates, duration, and decision notes.</p>
      <form className="leave-filter-bar" onSubmit={applyFilters}>
        <label>Employee or employee ID<input value={filters.employee} onChange={(event) => setFilters((current) => ({ ...current, employee: event.target.value }))} placeholder="Search employees" /></label>
        <label>Year<input type="number" min="2000" max="9998" value={filters.year} onChange={(event) => setFilters((current) => ({ ...current, year: event.target.value }))} placeholder="All years" /></label>
        <label>Leave type<select value={filters.leave_type_id} onChange={(event) => setFilters((current) => ({ ...current, leave_type_id: event.target.value }))}><option value="">All leave types</option>{leaveTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label>
        <label>Status<select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">All statuses</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="cancelled">Cancelled</option></select></label>
        <button type="submit" className="leave-primary-button">Search history</button>
      </form>
      {error && <div className="leave-alert error" role="alert">{error}</div>}
      {loading ? <p className="leave-loading" role="status">Loading employee leave history…</p> : (
        <>
          <div className="leave-table-wrap">
            <table className="leave-table">
              <thead><tr><th>Employee</th><th>Department</th><th>Leave type</th><th>Dates</th><th>Days</th><th>Status</th><th>Reason / decision note</th><th>Submitted</th></tr></thead>
              <tbody>
                {requests.map((item) => (
                  <tr key={item.id}>
                    <td>{item.requester_name || `Employee ${item.user_id}`}</td>
                    <td>{item.department_name || '—'}</td>
                    <td>{item.type_name || '—'}</td>
                    <td>{item.start_date} – {item.end_date}</td>
                    <td>{item.days_requested}</td>
                    <td><span className={`leave-status leave-status-${item.workflow_state || item.status}`}>{item.workflow_state || item.status}</span></td>
                    <td className="leave-history-reason">{item.decision_comment || item.reason || '—'}</td>
                    <td>{item.applied_at ? new Date(item.applied_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
                {!requests.length && <tr><td colSpan="8">No employee leave requests match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="leave-history-pagination">
            <button type="button" className="leave-secondary-button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
            <span>Page {pagination.pages ? page : 0} of {pagination.pages}</span>
            <button type="button" className="leave-secondary-button" disabled={page >= pagination.pages} onClick={() => setPage((current) => current + 1)}>Next</button>
          </div>
        </>
      )}
    </section>
  );
}
