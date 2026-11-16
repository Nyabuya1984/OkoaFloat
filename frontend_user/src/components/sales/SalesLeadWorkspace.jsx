import React, { useCallback, useEffect, useState } from 'react';
import { apiUrl } from '../../services/apiConfig';
import { getAuthToken, refreshAuthToken } from '../../services/authStorage';

const RESPONSES = [
  ['new', 'New'],
  ['interested', 'Interested'],
  ['not_interested', 'Not Interested'],
  ['ready_to_register', 'Ready to Register'],
  ['appointment', 'Appointment'],
  ['registered', 'Registered'],
  ['unreachable', 'Unreachable'],
  ['wrong_number', 'Wrong Number'],
];
const REGISTRATION_DOCUMENTS = [
  ['director_id', 'Director ID copy'],
  ['business_permit', 'Business permit'],
  ['tax_certificate', 'Tax certificate'],
  ['till_store_number', 'Till / Store number verified'],
];
const LEAD_EDIT_FIELDS = [
  ['business_name', 'Business name', false, 160],
  ['head_office_location', 'Head office location', false, 240],
  ['business_location', 'Business location', false, 240],
  ['director_name', "Director's name", false, 160],
  ['phone_number', 'Phone number', true, 40],
  ['mpesa_agent_name', 'M-Pesa agent name', false, 160],
  ['mpesa_agent_number', 'M-Pesa agent number', false, 80],
  ['mpesa_store_number', 'M-Pesa store number', false, 80],
];
const EMPTY_DRAFT = {
  response: 'new',
  reason_for_decline: '',
  appointment_datetime: '',
  notes: '',
  registration_documents: {},
  reason_for_incompleteness: '',
};

async function request(path, options = {}) {
  const send = () => fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(getAuthToken() ? { Authorization: ['Bearer', getAuthToken()].join(' ') } : {}),
      ...(options.headers || {}),
    },
  });
  let response = await send();
  if (response.status === 401 && await refreshAuthToken()) response = await send();
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || 'Unable to load telesales records.');
  return payload.data;
}

function downloadCsv(filename, contents) {
  downloadBlob(filename, new Blob([contents], { type: 'text/csv;charset=utf-8;' }));
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function responseLabel(response) {
  if (response === 'new_or_existing') return 'New';
  return RESPONSES.find(([value]) => value === response)?.[1] || response || 'No call logged';
}

function dateToIso(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

export default function SalesLeadWorkspace({ canManage = false }) {
  const [leads, setLeads] = useState([]);
  const [assignees, setAssignees] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [followUps, setFollowUps] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [file, setFile] = useState(null);
  const [distributeOnUpload, setDistributeOnUpload] = useState(false);
  const [selectedLeadIds, setSelectedLeadIds] = useState([]);
  const [assignmentRepId, setAssignmentRepId] = useState('');
  const [assignmentReason, setAssignmentReason] = useState('');
  const [columnFilters, setColumnFilters] = useState({
    business: '',
    location: '',
    phone: '',
    response: '',
    representative: '',
    registration: '',
  });
  const [editingLead, setEditingLead] = useState(null);
  const [editDraft, setEditDraft] = useState(null);
  const [viewingLead, setViewingLead] = useState(null);
  const [queueView, setQueueView] = useState('active');
  const [escalationDrafts, setEscalationDrafts] = useState({});
  const [filters, setFilters] = useState({ from: '', to: '', employee_id: '', status: '' });
  const [periodPreset, setPeriodPreset] = useState('all');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [loadError, setLoadError] = useState('');

  const load = useCallback(async () => {
    try {
      const reportQuery = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      const reportSuffix = reportQuery.toString() ? `?${reportQuery}` : '';
      const queueQuery = new URLSearchParams();
      ['from', 'to', 'status'].forEach((key) => {
        if (filters[key]) queueQuery.set(key, filters[key]);
      });
      if (canManage && filters.employee_id) {
        queueQuery.set('employee_id', filters.employee_id);
      }
      const queueSuffix = queueQuery.toString() ? `?${queueQuery}` : '';
      const [leadRows, staff, summary, tasks] = await Promise.all([
        request(`/api/sales/leads${queueSuffix}`),
        canManage ? request('/api/sales/leads/assignees') : Promise.resolve([]),
        request(`/api/sales/leads/analytics${reportSuffix}`),
        request('/api/sales/leads/follow-ups'),
      ]);
      setLeads(Array.isArray(leadRows) ? leadRows : []);
      setSelectedLeadIds((current) => current.filter(
        (id) => (leadRows || []).some((lead) => lead.id === id),
      ));
      setAssignees(Array.isArray(staff) ? staff : []);
      setAnalytics(summary);
      setFollowUps(Array.isArray(tasks) ? tasks : []);
      setDrafts(Object.fromEntries((leadRows || []).map((lead) => [lead.id, {
        ...EMPTY_DRAFT,
        response: RESPONSES.some(([value]) => value === lead.status) ? lead.status : 'new',
        reason_for_decline: lead.outcome_reason || '',
        notes: '',
        registration_documents: lead.registration?.documents || {},
        reason_for_incompleteness: lead.registration?.reason_for_incompleteness || '',
      }])));
      setLoadError('');
    } catch (error) {
      setLoadError(error.message);
    }
  }, [canManage, filters]);

  useEffect(() => { load(); }, [load]);

  const uploadLeads = async (event) => {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setFeedback('');
    const body = new FormData();
    body.append('file', file);
    body.append('distribute_evenly', String(distributeOnUpload));
    try {
      const result = await request('/api/sales/leads/import', { method: 'POST', body });
      setFile(null);
      event.currentTarget.reset();
      setFeedback(`${result.created} leads uploaded; ${result.assigned || 0} distributed.`);
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const downloadLeadTemplate = () => downloadCsv(
    'okoa-telesales-lead-template.csv',
    'Business Name,Head Office Location,Director\'s Name,Phone Number,M-Pesa Agent Name,M-Pesa Agent Number,M-Pesa Store Number\n',
  );

  const exportCallHistory = async (format = 'csv') => {
    setBusy(true);
    setFeedback('');
    try {
      const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      if (format === 'xlsx') query.set('format', 'xlsx');
      const send = () => fetch(apiUrl(`/api/sales/leads/call-history/export.csv${query.toString() ? `?${query}` : ''}`), {
        headers: getAuthToken() ? { Authorization: ['Bearer', getAuthToken()].join(' ') } : {},
      });
      let response = await send();
      if (response.status === 401 && await refreshAuthToken()) response = await send();
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error?.message || 'Unable to export call history.');
      }
      if (format === 'csv') {
        downloadCsv('okoa-telesales-call-history.csv', await response.text());
      } else {
        downloadBlob(`okoa-telesales-call-history.${format}`, await response.blob());
      }
      setFeedback(`Filtered call history exported as ${format.toUpperCase()} with contact audit stamps.`);
    } catch (error) {
      setFeedback(error.message || 'Unable to export call history.');
    } finally {
      setBusy(false);
    }
  };

  const exportLeadSheet = async (format = 'csv') => {
    setBusy(true);
    setFeedback('');
    try {
      const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      const send = () => fetch(apiUrl(`/api/sales/leads/export.${format}${query.toString() ? `?${query}` : ''}`), {
        headers: getAuthToken() ? { Authorization: ['Bearer', getAuthToken()].join(' ') } : {},
      });
      let response = await send();
      if (response.status === 401 && await refreshAuthToken()) response = await send();
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error?.message || 'Unable to export the lead sheet.');
      }
      if (format === 'csv') {
        downloadCsv('okoa-telesales-lead-sheet.csv', await response.text());
      } else {
        downloadBlob(`okoa-telesales-lead-sheet.${format}`, await response.blob());
      }
      setFeedback('Filtered lead sheet exported with current statuses and notes.');
    } catch (error) {
      setFeedback(error.message || 'Unable to export the lead sheet.');
    } finally {
      setBusy(false);
    }
  };

  const distributeLeads = async () => {
    setBusy(true);
    try {
      const result = await request('/api/sales/leads/distribute', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      setFeedback(`${result.assigned} unassigned leads distributed across ${result.representatives || 0} representatives.`);
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const shareSelectedLeads = async (distributeEvenly = false) => {
    if (!selectedLeadIds.length || (!distributeEvenly && !assignmentRepId)) return;
    setBusy(true);
    setFeedback('');
    try {
      const result = await request(
        distributeEvenly ? '/api/sales/leads/distribute' : '/api/sales/leads/assignments/bulk',
        {
          method: 'POST',
          body: JSON.stringify({
            lead_ids: selectedLeadIds,
            ...(distributeEvenly ? {} : { employee_id: Number(assignmentRepId) }),
            reason: assignmentReason.trim() || undefined,
          }),
        },
      );
      setFeedback(distributeEvenly
        ? `${result.assigned} selected leads split across ${result.representatives || 0} representatives.`
        : `${result.assigned} selected leads assigned to ${assignees.find((person) => person.id === Number(assignmentRepId))?.full_name || 'the representative'}.`);
      setSelectedLeadIds([]);
      setAssignmentRepId('');
      setAssignmentReason('');
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleLeadSelection = (leadId, checked) => setSelectedLeadIds((current) => (
    checked ? [...new Set([...current, leadId])] : current.filter((id) => id !== leadId)
  ));

  const selectedLeadRows = leads.filter((lead) => selectedLeadIds.includes(lead.id));
  const selectedLeadNeedsReason = selectedLeadRows.some((lead) => lead.assigned_to_id);

  const updateDraft = (leadId, field, value) => setDrafts((current) => ({
    ...current,
    [leadId]: { ...current[leadId], [field]: value },
  }));

  const updateDocument = (leadId, document, checked) => setDrafts((current) => ({
    ...current,
    [leadId]: {
      ...current[leadId],
      registration_documents: {
        ...current[leadId].registration_documents,
        [document]: checked,
      },
    },
  }));

  const saveOutcome = async (lead) => {
    setBusy(true);
    setFeedback('');
    try {
      await request(`/api/sales/leads/${lead.id}/calls`, {
        method: 'POST',
        body: JSON.stringify(drafts[lead.id]),
      });
      setFeedback(`Call outcome saved for ${lead.lead_name}.`);
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const completeFollowUp = async (task) => {
    setBusy(true);
    try {
      await request(`/api/sales/leads/follow-ups/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_completed: true }),
      });
      setFeedback('Follow-up marked complete.');
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const escalateLead = async (lead) => {
    const draft = escalationDrafts[lead.id] || { level: 'group_leader', reason: '' };
    setBusy(true);
    setFeedback('');
    try {
      await request(`/api/sales/leads/${lead.id}/escalations`, {
        method: 'POST',
        body: JSON.stringify(draft),
      });
      setEscalationDrafts((current) => ({
        ...current,
        [lead.id]: { ...draft, reason: '' },
      }));
      setFeedback(`Escalation sent for ${lead.lead_name}.`);
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const openLeadEditor = (lead) => {
    setEditingLead(lead);
    setEditDraft(Object.fromEntries(LEAD_EDIT_FIELDS.map(([key]) => [
      key,
      lead[key] || (key === 'business_name' ? lead.company_name : '') || '',
    ])));
  };

  const saveLeadDetails = async (event) => {
    event.preventDefault();
    if (!editingLead || !editDraft) return;
    setBusy(true);
    setFeedback('');
    try {
      await request(`/api/sales/leads/${editingLead.id}/details`, {
        method: 'PATCH',
        body: JSON.stringify(editDraft),
      });
      setEditingLead(null);
      setEditDraft(null);
      setFeedback('Lead details updated.');
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const deleteLead = async (lead) => {
    if (!window.confirm(
      `Remove ${lead.company_name || lead.business_name || lead.lead_name} from active leads? Call history and audit records will be retained.`,
    )) return;
    setBusy(true);
    setFeedback('');
    try {
      await request(`/api/sales/leads/${lead.id}`, { method: 'DELETE' });
      setSelectedLeadIds((current) => current.filter((id) => id !== lead.id));
      setFeedback('Lead removed from the active list. Call history was retained.');
      await load();
    } catch (error) {
      setFeedback(error.message);
    } finally {
      setBusy(false);
    }
  };

  const clearFilters = () => {
    setPeriodPreset('all');
    setFilters({ from: '', to: '', employee_id: '', status: '' });
  };
  const updateFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const selectPeriod = (period) => {
    setPeriodPreset(period);
    if (period === 'custom') return;
    if (period === 'all') {
      setFilters((current) => ({ ...current, from: '', to: '' }));
      return;
    }
    const today = new Date();
    const to = dateToIso(today);
    const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (period === 'weekly') {
      const daysSinceMonday = (start.getDay() + 6) % 7;
      start.setDate(start.getDate() - daysSinceMonday);
    } else if (period === 'monthly') {
      start.setDate(1);
    }
    setFilters((current) => ({ ...current, from: dateToIso(start), to }));
  };
  const updateDateFilter = (key, value) => {
    setPeriodPreset('custom');
    updateFilter(key, value);
  };
  const updateColumnFilter = (key, value) => setColumnFilters((current) => ({
    ...current,
    [key]: value,
  }));
  const matches = (value, filter) => !filter
    || String(value || '').toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase());
  const filteredLeads = leads.filter((lead) => {
    const response = responseLabel(lead.status);
    const registration = lead.registration?.status || 'Not registered';
    return matches(
      `${lead.company_name || lead.business_name || lead.lead_name} ${lead.director_name || ''}`,
      columnFilters.business,
    )
      && matches(
        `${lead.business_location || lead.location || ''} ${lead.head_office_location || ''}`,
        columnFilters.location,
      )
      && matches(lead.phone_number, columnFilters.phone)
      && (!columnFilters.response || response === columnFilters.response)
      && (!columnFilters.representative
        || (columnFilters.representative === 'unassigned'
          ? !lead.assigned_to_id
          : String(lead.assigned_to_id) === columnFilters.representative))
      && (!columnFilters.registration || registration === columnFilters.registration);
  });
  const activeQueue = filteredLeads.filter((lead) => !(lead.call_logs || []).some((call) => call.reached));
  const contactedClients = filteredLeads.filter((lead) => (lead.call_logs || []).some((call) => call.reached));
  const visibleLeads = queueView === 'active' ? activeQueue : contactedClients;
  const clearColumnFilters = () => setColumnFilters({
    business: '',
    location: '',
    phone: '',
    response: '',
    representative: '',
    registration: '',
  });

  return <section className="sales-lead-workspace" aria-label="Sales lead operations">
    <div className="sales-lead-heading">
      <div><p className="leave-kicker">TELESALES CALL SHEET</p><h3>{canManage ? 'Lead upload, distribution &amp; call performance' : 'Your daily calling queue'}</h3></div>
      <button type="button" className="leave-secondary-button" disabled={busy} onClick={load}>Refresh</button>
    </div>
    {feedback && <p className="sales-lead-feedback" role="status">{feedback}</p>}
    {loadError && <p className="sales-lead-error" role="alert">{loadError} <button type="button" onClick={load}>Retry</button></p>}
    {canManage && <div className="sales-lead-manager-tools">
      <form onSubmit={uploadLeads}>
        <label>Upload prospect list (CSV or Excel .xlsx)
          <input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => setFile(event.target.files?.[0] || null)} required />
        </label>
        <small>Use the lead template columns for Business Name, Head Office Location, Director&apos;s Name, Phone Number, M-Pesa Agent Name, M-Pesa Agent Number, and M-Pesa Store Number. A director or business name and phone number are required; maximum 500 rows.</small>
        <label className="sales-lead-checkbox"><input type="checkbox" checked={distributeOnUpload} onChange={(event) => setDistributeOnUpload(event.target.checked)} /> Distribute uploaded leads evenly across my Sales group</label>
        <button type="button" className="leave-secondary-button" onClick={downloadLeadTemplate}>Download lead template</button>
        <button type="submit" className="leave-primary-button" disabled={busy || !file}>Upload leads</button>
      </form>
      <div className="sales-lead-manager-actions">
        <button type="button" className="leave-secondary-button" disabled={busy} onClick={distributeLeads}>Distribute unassigned leads evenly</button>
        <button type="button" className="leave-secondary-button" disabled={busy} onClick={exportLeadSheet}>Export filtered lead sheet CSV</button>
        <button type="button" className="leave-secondary-button" disabled={busy} onClick={() => exportLeadSheet('xlsx')}>Export filtered lead sheet Excel</button>
        <button type="button" className="leave-secondary-button" disabled={busy} onClick={() => exportLeadSheet('pdf')}>Export filtered lead sheet PDF</button>
      </div>
    </div>}
    <div className="sales-lead-manager-actions sales-lead-agent-exports" aria-label="Export telesales reports">
      <button type="button" className="leave-secondary-button" disabled={busy} onClick={() => exportCallHistory('csv')}>Export call history CSV</button>
      <button type="button" className="leave-secondary-button" disabled={busy} onClick={() => exportCallHistory('xlsx')}>Export call history Excel</button>
      <button type="button" className="leave-secondary-button" disabled={busy} onClick={() => exportCallHistory('pdf')}>Export call history PDF</button>
    </div>
    {analytics && <section className="sales-lead-analytics" aria-label="Telesales performance analytics">
      <div className="sales-lead-kpis" aria-label="Telesales metrics">
        <div><strong>{analytics.call_attempts || 0}</strong><span>Calls attempted</span></div>
        <div><strong>{analytics.reached_calls || 0}</strong><span>Contacts reached</span></div>
        <div><strong>{analytics.reachability_rate || 0}%</strong><span>Reachability</span></div>
        <div><strong>{analytics.registration_counts?.COMPLETE || 0}</strong><span>Complete registrations</span></div>
        <div><strong>{analytics.registration_counts?.INCOMPLETE || 0}</strong><span>Incomplete registrations</span></div>
      </div>
      <div className="sales-lead-funnel" aria-label="Telesales conversion funnel">
        <h4>Conversion funnel</h4>
        {Object.entries(analytics.funnel || {}).map(([key, count]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{count}</strong></div>)}
      </div>
      <div className="sales-lead-status-summary" aria-label="Lead response counts">
        {Object.entries(analytics.statuses || {}).map(([status, count]) => <div key={status} className={`sales-lead-status-tag is-${status}`}><strong>{count}</strong><span>{responseLabel(status)}</span></div>)}
      </div>
      {canManage && <div className="sales-lead-rep-comparison" aria-label="Cold-calling representative comparison">
        <h4>Representative performance</h4>
        {(analytics.employees || []).length ? <div className="sales-lead-rep-list">
          {analytics.employees.map((employee) => <div key={employee.employee_id}>
            <strong>{employee.employee_name}</strong>
            <span>{employee.call_attempts} attempts · {employee.reached_calls} reached · {employee.reachability_rate}% reachability</span>
            <small>{employee.complete_registrations || 0} complete · {employee.incomplete_registrations || 0} incomplete registrations</small>
          </div>)}
        </div> : <p className="sales-lead-empty">No calls match the selected reporting period.</p>}
      </div>}
      <div className="sales-lead-bottlenecks">
        <h4>Incomplete registration bottlenecks</h4>
        {(analytics.incomplete_bottlenecks || []).length
          ? analytics.incomplete_bottlenecks.map((item) => <p key={item.reason}><strong>{item.count}</strong> {item.reason}</p>)
          : <p>No open registration document bottlenecks.</p>}
      </div>
    </section>}
    <div className="sales-lead-filters" aria-label="Cold-calling lead filters">
      <label>Reporting period<select value={periodPreset} onChange={(event) => selectPeriod(event.target.value)}>
        <option value="all">All dates</option>
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
        <option value="custom">Custom range</option>
      </select></label>
      {(periodPreset === 'all' || periodPreset === 'custom') && <>
        <label>From<input type="date" value={filters.from} onChange={(event) => updateDateFilter('from', event.target.value)} /></label>
        <label>To<input type="date" value={filters.to} onChange={(event) => updateDateFilter('to', event.target.value)} /></label>
      </>}
      {canManage && <label>Representative<select value={filters.employee_id} onChange={(event) => updateFilter('employee_id', event.target.value)}>
        <option value="">All representatives</option>{assignees.map((staff) => <option key={staff.id} value={staff.id}>{staff.full_name}</option>)}
      </select></label>}
      <label>Response<select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}>
        <option value="">All responses</option>{RESPONSES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </select></label>
      <button type="button" className="leave-text-button" onClick={clearFilters}>Clear filters</button>
    </div>
    {followUps.length > 0 && <section className="sales-lead-follow-ups" aria-label="Follow-up tasks">
      <h4>Priority follow-ups</h4>
      {followUps.map((task) => <article key={task.id}>
        <div><strong>{task.lead_name}</strong><a href={`tel:${task.phone_number}`}>{task.phone_number}</a></div>
        <span>{(task.task_type || 'follow-up').replaceAll('_', ' ')} · Due {task.due_at ? new Date(task.due_at).toLocaleString() : 'date not set'}</span>
        {task.notes && <small>{task.notes}</small>}
        <button type="button" disabled={busy} className="leave-secondary-button" onClick={() => completeFollowUp(task)}>Complete task</button>
      </article>)}
    </section>}
    {canManage && <div className="sales-lead-allocation" aria-label="Share selected leads">
      <div className="sales-lead-allocation-heading">
        <strong>Share selected leads</strong>
        <span>{selectedLeadIds.length} selected</span>
      </div>
      <label>Assign selected leads to
        <select
          value={assignmentRepId}
          disabled={!selectedLeadIds.length}
          onChange={(event) => setAssignmentRepId(event.target.value)}
        >
          <option value="">Select a representative</option>
          {assignees.map((staff) => <option key={staff.id} value={staff.id}>{staff.full_name}</option>)}
        </select>
      </label>
      {selectedLeadNeedsReason
        ? <label>Reason for reassignment (required)
          <input
            required
            maxLength="255"
            value={assignmentReason}
            onChange={(event) => setAssignmentReason(event.target.value)}
          />
        </label>
        : <small>Select leads below, then assign to one representative or split them evenly.</small>}
      <button
        type="button"
        className="leave-primary-button"
        disabled={busy || !selectedLeadIds.length || !assignmentRepId || (selectedLeadNeedsReason && !assignmentReason.trim())}
        onClick={() => shareSelectedLeads(false)}
      >Assign selected</button>
      <button
        type="button"
        className="leave-secondary-button"
        disabled={busy || !selectedLeadIds.length || (selectedLeadNeedsReason && !assignmentReason.trim())}
        onClick={() => shareSelectedLeads(true)}
      >Split selected evenly</button>
      <button
        type="button"
        className="leave-text-button"
        disabled={!selectedLeadIds.length}
        onClick={() => setSelectedLeadIds([])}
      >Clear selection</button>
    </div>}
    {viewingLead && <div className="sales-lead-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setViewingLead(null);
    }}>
      <section className="sales-lead-modal" role="dialog" aria-modal="true" aria-labelledby="sales-lead-view-title">
        <div className="sales-lead-modal-heading">
          <div><p className="leave-kicker">LEAD DETAILS</p><h4 id="sales-lead-view-title">{viewingLead.company_name || viewingLead.business_name || viewingLead.lead_name}</h4></div>
          <button type="button" className="leave-text-button" onClick={() => setViewingLead(null)}>Close</button>
        </div>
        <dl className="sales-lead-detail-grid">
          {LEAD_EDIT_FIELDS.map(([key, label]) => <div key={key}>
            <dt>{label}</dt><dd>{viewingLead[key] || (key === 'business_name' ? viewingLead.company_name : '') || '—'}</dd>
          </div>)}
          <div><dt>Assigned representative</dt><dd>{viewingLead.assignee_name || 'Unassigned'}</dd></div>
          <div><dt>Latest response</dt><dd>{responseLabel(viewingLead.status)}</dd></div>
          <div><dt>Registration</dt><dd>{viewingLead.registration?.status || 'Not registered'}</dd></div>
        </dl>
        <h5>Call history ({viewingLead.call_logs?.length || 0})</h5>
        <div className="sales-lead-modal-history">
          {(viewingLead.call_logs || []).length ? viewingLead.call_logs.map((call) => <article key={call.id}>
            <strong>{responseLabel(call.response)}</strong>
            <span>{call.contact_day}, {call.contact_date} at {call.contact_time} · {call.contacted_by_name || 'Unknown representative'}</span>
            {call.notes && <p>{call.notes}</p>}
            {call.reason_for_decline && <small>Decline reason: {call.reason_for_decline}</small>}
          </article>) : <p>No calls have been logged.</p>}
        </div>
      </section>
    </div>}
    {editingLead && editDraft && <div className="sales-lead-modal-backdrop" role="presentation">
      <form className="sales-lead-modal" role="dialog" aria-modal="true" aria-labelledby="sales-lead-edit-title" onSubmit={saveLeadDetails}>
        <div className="sales-lead-modal-heading">
          <div><p className="leave-kicker">EDIT LEAD</p><h4 id="sales-lead-edit-title">{editingLead.company_name || editingLead.lead_name}</h4></div>
          <button type="button" className="leave-text-button" onClick={() => setEditingLead(null)}>Cancel</button>
        </div>
        <div className="sales-lead-edit-grid">
          {LEAD_EDIT_FIELDS.map(([key, label, required, maxLength]) => <label key={key}>
            {label}
            <input
              aria-label={label}
              required={Boolean(required)}
              maxLength={maxLength}
              value={editDraft[key] || ''}
              onChange={(event) => setEditDraft((current) => ({ ...current, [key]: event.target.value }))}
            />
          </label>)}
        </div>
        <div className="sales-lead-modal-actions">
          <button type="button" className="leave-secondary-button" onClick={() => setEditingLead(null)}>Cancel</button>
          <button type="submit" className="leave-primary-button" disabled={busy}>Save changes</button>
        </div>
      </form>
    </div>}
    <div className="sales-lead-queue-tabs" role="tablist" aria-label="Telesales client queues">
      <button
        type="button"
        role="tab"
        aria-selected={queueView === 'active'}
        className={queueView === 'active' ? 'is-selected' : ''}
        onClick={() => setQueueView('active')}
      >Active call queue <span>{activeQueue.length}</span></button>
      <button
        type="button"
        role="tab"
        aria-selected={queueView === 'contacted'}
        className={queueView === 'contacted' ? 'is-selected' : ''}
        onClick={() => setQueueView('contacted')}
      >Contacted clients <span>{contactedClients.length}</span></button>
    </div>
    <h4 className="sales-lead-queue-title">{queueView === 'active' ? 'Active call queue' : 'Contacted clients · shared history'}</h4>
    <div className="sales-lead-table-wrap">
      <table className={`sales-lead-table${canManage ? ' is-manager' : ''}`}>
        <colgroup>
          {canManage && <col className="sales-lead-col-select" />}
          <col className="sales-lead-col-business" />
          <col className="sales-lead-col-contact" />
          <col className="sales-lead-col-mpesa" />
          <col className="sales-lead-col-rep" />
          <col className="sales-lead-col-response" />
          <col className="sales-lead-col-actions" />
        </colgroup>
        <thead><tr>
          {canManage && <th className="sales-lead-select-header"><input
            className="sales-lead-select-checkbox"
            aria-label="Select all visible leads"
            type="checkbox"
            checked={filteredLeads.length > 0 && filteredLeads.every((lead) => selectedLeadIds.includes(lead.id))}
            onChange={(event) => setSelectedLeadIds((current) => event.target.checked
              ? [...new Set([...current, ...filteredLeads.map((lead) => lead.id)])]
              : current.filter((id) => !filteredLeads.some((lead) => lead.id === id)))}
          /></th>}
          <th>Business / director</th><th>Contact</th><th>Agent / location</th><th>Representative</th><th>Response / registration</th><th>Actions</th>
        </tr>
        <tr className="sales-lead-filter-row">
          {canManage && <th aria-label="Selection filter" />}
          <th><input aria-label="Filter business" placeholder="Business or director" value={columnFilters.business} onChange={(event) => updateColumnFilter('business', event.target.value)} /></th>
          <th><input aria-label="Filter phone" placeholder="Phone" value={columnFilters.phone} onChange={(event) => updateColumnFilter('phone', event.target.value)} /></th>
          <th><input aria-label="Filter location" placeholder="Business / head office" value={columnFilters.location} onChange={(event) => updateColumnFilter('location', event.target.value)} /></th>
          <th><select aria-label="Filter representative" value={columnFilters.representative} onChange={(event) => updateColumnFilter('representative', event.target.value)}>
            <option value="">All representatives</option><option value="unassigned">Unassigned</option>
            {assignees.map((staff) => <option value={staff.id} key={staff.id}>{staff.full_name}</option>)}
          </select></th>
          <th><div className="sales-lead-header-filters">
            <select aria-label="Filter response" value={columnFilters.response} onChange={(event) => updateColumnFilter('response', event.target.value)}>
              <option value="">All responses</option>{RESPONSES.map(([value, label]) => <option value={label} key={value}>{label}</option>)}
            </select>
            <select aria-label="Filter registration" value={columnFilters.registration} onChange={(event) => updateColumnFilter('registration', event.target.value)}>
              <option value="">All registration states</option><option>COMPLETE</option><option>INCOMPLETE</option><option>Not registered</option>
            </select>
          </div></th>
          <th><button type="button" className="leave-text-button" onClick={clearColumnFilters}>Clear</button></th>
        </tr>
        </thead>
        <tbody>{visibleLeads.map((lead) => {
          const draft = drafts[lead.id] || EMPTY_DRAFT;
          const documents = draft.registration_documents || {};
          const completedDocuments = REGISTRATION_DOCUMENTS.filter(([key]) => documents[key]).length;
          const calls = [...(lead.call_logs || [])].sort((a, b) => (b.contact_datetime || '').localeCompare(a.contact_datetime || ''));
          return <tr key={lead.id}>
            {canManage && <td><input
              type="checkbox"
              aria-label={`Select ${lead.lead_name}`}
              checked={selectedLeadIds.includes(lead.id)}
              onChange={(event) => toggleLeadSelection(lead.id, event.target.checked)}
            /></td>}
            <td><strong>{lead.company_name || lead.business_name || lead.lead_name}</strong><small>{lead.director_name || lead.lead_name}</small></td>
            <td><a className="sales-lead-call-link" href={`tel:${lead.phone_number}`}>{lead.phone_number}</a></td>
            <td>
              <strong>{lead.mpesa_agent_name || '—'}</strong>
              <small>{lead.mpesa_agent_number || '—'} · {lead.mpesa_store_number || '—'}</small>
              <small>{lead.business_location || lead.location || lead.head_office_location || '—'}</small>
            </td>
            <td>{lead.assignee_name || 'Unassigned'}</td>
            <td>
              <span className={`sales-lead-response-tag is-${lead.status || 'new'}`}>
                {responseLabel(lead.status)}
              </span>
              {lead.open_escalation_count > 0 && <span className="sales-lead-response-tag is-escalated">Escalated · {lead.open_escalation_count}</span>}
              <label>Primary outcome<select aria-label={`Outcome for ${lead.lead_name}`} value={draft.response} onChange={(event) => updateDraft(lead.id, 'response', event.target.value)}>
                {RESPONSES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select></label>
              {draft.response === 'appointment' && <label>Appointment date and time
                <input type="datetime-local" required value={draft.appointment_datetime} onChange={(event) => updateDraft(lead.id, 'appointment_datetime', event.target.value)} />
              </label>}
              {draft.response === 'not_interested' && <label>Reason for decline
                <input required value={draft.reason_for_decline} onChange={(event) => updateDraft(lead.id, 'reason_for_decline', event.target.value)} />
              </label>}
              {draft.response === 'registered' && <details className="sales-registration-documents">
                <summary>Registration documents ({completedDocuments}/{REGISTRATION_DOCUMENTS.length})</summary>
                {REGISTRATION_DOCUMENTS.map(([key, label]) => <label className="sales-lead-checkbox" key={key}>
                  <input type="checkbox" checked={Boolean(documents[key])} onChange={(event) => updateDocument(lead.id, key, event.target.checked)} /> {label}
                </label>)}
                {REGISTRATION_DOCUMENTS.some(([key]) => !documents[key]) && <label>Reason registration is incomplete
                  <textarea required rows="1" value={draft.reason_for_incompleteness} onChange={(event) => updateDraft(lead.id, 'reason_for_incompleteness', event.target.value)} />
                </label>}
              </details>}
              <label>Call notes<textarea rows="1" value={draft.notes} onChange={(event) => updateDraft(lead.id, 'notes', event.target.value)} /></label>
              {lead.registration && <small className={lead.registration.status === 'COMPLETE' ? 'is-complete' : 'is-incomplete'}>
                Registration {lead.registration.status}{lead.registration.reason_for_incompleteness ? `: ${lead.registration.reason_for_incompleteness}` : ''}
              </small>}
              <details className="sales-lead-call-history">
                <summary>Call history ({calls.length})</summary>
                {calls.length ? calls.map((call) => <div key={call.id}>
                  <strong className={`sales-lead-response-tag is-${call.response}`}>{responseLabel(call.response)}</strong>
                  <small>{call.contact_date} ({call.contact_day}) · {call.contact_time} · {call.contacted_by_name}</small>
                  {call.notes && <small>{call.notes}</small>}
                  {call.reason_for_decline && <small>Decline reason: {call.reason_for_decline}</small>}
                  {call.appointment_datetime && <small>Appointment: {new Date(call.appointment_datetime).toLocaleString()}</small>}
                </div>) : <p>No calls have been logged.</p>}
              </details>
              <details className="sales-lead-escalation">
                <summary>Escalate to management</summary>
                <label>Route to
                  <select
                    aria-label={`Escalation level for ${lead.lead_name}`}
                    value={(escalationDrafts[lead.id] || {}).level || 'group_leader'}
                    onChange={(event) => setEscalationDrafts((current) => ({
                      ...current,
                      [lead.id]: {
                        ...(current[lead.id] || { level: 'group_leader', reason: '' }),
                        level: event.target.value,
                      },
                    }))}
                  >
                    <option value="group_leader">Group Leader</option>
                    <option value="department_manager">Department Manager</option>
                    <option value="general_manager">General Manager</option>
                  </select>
                </label>
                <label>Reason and client context
                  <textarea
                    required
                    maxLength="2000"
                    aria-label={`Escalation reason for ${lead.lead_name}`}
                    value={(escalationDrafts[lead.id] || {}).reason || ''}
                    onChange={(event) => setEscalationDrafts((current) => ({
                      ...current,
                      [lead.id]: {
                        ...(current[lead.id] || { level: 'group_leader', reason: '' }),
                        reason: event.target.value,
                      },
                    }))}
                  />
                </label>
                <button
                  type="button"
                  className="leave-secondary-button sales-lead-escalate-button"
                  disabled={busy || !(escalationDrafts[lead.id] || {}).reason?.trim()}
                  onClick={() => escalateLead(lead)}
                >Send escalation</button>
              </details>
            </td>
            <td>
              <div className="sales-lead-row-actions">
                <button
                  type="button"
                  className="leave-primary-button sales-lead-save-call"
                  aria-label={`Save call for ${lead.lead_name}`}
                  disabled={busy}
                  onClick={() => saveOutcome(lead)}
                >
                  Save call
                </button>
                {canManage && <>
                  <button type="button" className="leave-secondary-button" aria-label={`View ${lead.lead_name}`} onClick={() => setViewingLead(lead)}>View</button>
                  <button type="button" className="leave-secondary-button" aria-label={`Edit ${lead.lead_name}`} onClick={() => openLeadEditor(lead)}>Edit</button>
                  <button type="button" className="sales-lead-delete-button" aria-label={`Delete ${lead.lead_name}`} disabled={busy} onClick={() => deleteLead(lead)}>Delete</button>
                </>}
              </div>
            </td>
          </tr>;
        })}</tbody>
      </table>
      {!visibleLeads.length && !loadError && <p className="sales-lead-empty">{filteredLeads.length
        ? queueView === 'active'
          ? 'All assigned leads have been contacted. Check Contacted clients for their shared history.'
          : 'No contacted clients match the table filters.'
        : leads.length
          ? 'No leads match the table filters.'
          : canManage ? 'No leads uploaded yet. Upload or distribute a lead list to start telesales.' : 'No leads are assigned to your calling queue yet. Contact your manager to get leads assigned.'}</p>}
    </div>
  </section>;
}
