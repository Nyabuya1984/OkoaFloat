import React, { useEffect, useMemo, useRef, useState } from 'react';
import SalesDailyReportForm from './SalesDailyReportForm';
import SalesRegistrationAnalytics from './SalesRegistrationAnalytics';
import SalesFieldAgentAnalytics from './SalesFieldAgentAnalytics';
import SalesRecoveryFollowUps from './SalesRecoveryFollowUps';
import SalesLeadWorkspace from './sales/SalesLeadWorkspace';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';
import { apiUrl } from '../services/apiConfig';
import './sales/sales.css';

const outcomeLabels = { existing: 'Existing', interested: 'Interested', not_interested: 'Not interested', appointment: 'Appointment', ready_to_register: 'Ready to register', registered: 'Registered', declined: 'Not interested', promised: 'Promised' };
const categoryLabels = { agent: 'M-Pesa Agent / Dealer', sub_agent: 'M-Pesa Sub-Agent', mpesa_agent_dealer: 'M-Pesa Agent / Dealer', mpesa_sub_agent: 'M-Pesa Sub-Agent' };
const emptyFilters = { search: '', from: '', to: '', day: '', month: '', year: '', location: '', employee_id: '', clientType: '', status: '', category: '', registration: '', referral: '', appointment: '' };
const emptyReports = [];

const valueOf = (report, field) => report[field] ?? report.client_record?.[field] ?? '';
const statusOf = (report) => valueOf(report, 'outcome') || report.client_record?.new?.status || (report.client_record?.clientType === 'existing' ? 'existing' : '');
const categoryOf = (report) => valueOf(report, 'customer_type') || report.client_record?.new?.category || report.client_record?.existing?.category || '';
const normalizeCategory = (value) => String(value || '').toLowerCase().includes('sub') ? 'sub_agent' : value ? 'agent' : '';
const registrationOf = (report) => valueOf(report, 'registration_status') || report.client_record?.new?.registrationStatus || (statusOf(report) === 'registered' ? 'COMPLETE' : '');
const referralOf = (report) => valueOf(report, 'referral_agreed') === 'yes' || Boolean(report.client_record?.existing?.referralDetails);
const dateOf = (report) => valueOf(report, 'date_visited') || valueOf(report, 'created_at')?.slice(0, 10) || '';

export default function SalesReportsPage({
  reports: initialReports = emptyReports,
  onSubmitted,
  canEdit = false,
  canViewEmployeePerformance = false,
  canAddClient = false,
  canManageAgentRecords = false,
  isFieldAgent = false,
}) {
  const [showForm, setShowForm] = useState(false);
  const [reports, setReports] = useState(initialReports);
  const [analyticsRefreshKey, setAnalyticsRefreshKey] = useState(0);
  const [tab, setTab] = useState(canViewEmployeePerformance ? 'analytics' : 'records');
  const [filters, setFilters] = useState(emptyFilters);
  const [editingReport, setEditingReport] = useState(null);
  const [editSalesperson, setEditSalesperson] = useState('');
  const [editReportDate, setEditReportDate] = useState('');
  const [editFeedback, setEditFeedback] = useState('');
  const [recordFile, setRecordFile] = useState(null);
  const [recordFeedback, setRecordFeedback] = useState('');
  const [recordBusy, setRecordBusy] = useState(false);
  const formRef = useRef(null);
  const showClientEntry = canAddClient && !canViewEmployeePerformance;
  const showReportCorrections = canEdit && !canViewEmployeePerformance;
  const showLeadWorkspace = canViewEmployeePerformance || canAddClient;

  useEffect(() => {
    setReports(initialReports);
    setAnalyticsRefreshKey((current) => current + 1);
  }, [initialReports]);
  useEffect(() => {
    if (showForm) formRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [showForm]);
  const locations = useMemo(() => [...new Set(reports.map((report) => valueOf(report, 'business_location')).filter(Boolean))].sort(), [reports]);
  const fieldOfficers = useMemo(() => [...new Map(reports.filter((report) => valueOf(report, 'employee_id')).map((report) => [String(valueOf(report, 'employee_id')), valueOf(report, 'employee_name') || `Officer ${valueOf(report, 'employee_id')}`])).entries()], [reports]);
  const reportYears = useMemo(() => [...new Set(reports.map((report) => dateOf(report).slice(0, 4)).filter(Boolean))].sort().reverse(), [reports]);
  const filteredReports = useMemo(() => {
    const search = filters.search.trim().toLowerCase();
    return reports.filter((report) => {
      const date = dateOf(report);
      const day = date ? new Date(`${date}T12:00:00`).getDay() : '';
      const year = date.slice(0, 4);
      const month = date.slice(5, 7);
      const text = [valueOf(report, 'employee_name'), valueOf(report, 'agent_name'), valueOf(report, 'agent_number'), valueOf(report, 'store_number'), valueOf(report, 'business_location'), report.client_record?.new?.witness?.name, report.client_record?.new?.witness?.idNumber, report.client_record?.existing?.referralDetails?.contactNumber].join(' ').toLowerCase();
      const appointmentDate = valueOf(report, 'appointment_date') || report.client_record?.new?.appointmentDate || '';
      const appointmentMatch = !filters.appointment || (filters.appointment === 'upcoming' ? appointmentDate >= new Date().toISOString().slice(0, 10) : appointmentDate < new Date().toISOString().slice(0, 10));
      return (!search || text.includes(search)) && (!filters.from || date >= filters.from) && (!filters.to || date <= filters.to) && (!filters.day || String(day) === filters.day) && (!filters.month || month === filters.month) && (!filters.year || year === filters.year) && (!filters.location || valueOf(report, 'business_location') === filters.location) && (!filters.employee_id || String(valueOf(report, 'employee_id')) === filters.employee_id) && (!filters.clientType || (valueOf(report, 'new_client') === true ? 'new' : valueOf(report, 'new_client') === false ? 'existing' : report.client_record?.clientType) === filters.clientType) && (!filters.status || statusOf(report) === filters.status) && (!filters.category || normalizeCategory(categoryOf(report)) === filters.category) && (!filters.registration || registrationOf(report) === filters.registration) && (!filters.referral || String(referralOf(report)) === filters.referral) && appointmentMatch;
    });
  }, [filters, reports]);

  const updateFilter = (name, value) => setFilters((current) => ({ ...current, [name]: value }));
  const clearFilters = () => setFilters(emptyFilters);
  const authorizedFetch = async (url, options = {}) => {
    const send = () => fetch(apiUrl(url), {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(getAuthToken() ? { Authorization: ['Bearer', getAuthToken()].join(' ') } : {}),
        ...(options.headers || {}),
      },
    });
    let response = await send();
    if (response.status === 401 && await refreshAuthToken()) response = await send();
    return response;
  };
  const downloadAgentRecords = async (template = false, format = 'csv') => {
    setRecordFeedback('');
    try {
      const exportFilters = new URLSearchParams(Object.entries({
        from: filters.from,
        to: filters.to,
        employee_id: filters.employee_id,
      }).filter(([, value]) => value));
      const exportPath = template
        ? `/api/sales/reports/template${format === 'xlsx' ? '.xlsx' : ''}`
        : `/api/sales/reports/export${format === 'xlsx' ? '.xlsx' : ''}${exportFilters.toString() ? `?${exportFilters}` : ''}`;
      const response = await authorizedFetch(exportPath);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error?.message || 'Unable to download M-Pesa agent records.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = template
        ? `sales-agent-records-template.${format}`
        : `mpesa-agent-records.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setRecordFeedback(error.message || 'Unable to download M-Pesa agent records.');
    }
  };
  const importAgentRecords = async (event) => {
    event.preventDefault();
    if (!recordFile) return;
    setRecordBusy(true);
    setRecordFeedback('');
    const body = new FormData();
    body.append('file', recordFile);
    try {
      const response = await authorizedFetch('/api/sales/reports/import', { method: 'POST', body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const rowErrors = payload.data?.errors || [];
        const detail = rowErrors.slice(0, 3).map((item) => `Row ${item.row}: ${item.message}`).join(' · ');
        throw new Error(detail || payload.error?.message || 'Unable to import agent records.');
      }
      setRecordFile(null);
      event.currentTarget.reset();
      setRecordFeedback(`${payload.data?.created || 0} agent records imported.`);
      const refresh = await authorizedFetch('/api/sales/reports');
      const refreshedPayload = await refresh.json().catch(() => ({}));
      if (!refresh.ok) throw new Error(refreshedPayload.error?.message || 'Imported records, but could not refresh the list.');
      setReports(refreshedPayload.data || []);
      setAnalyticsRefreshKey((current) => current + 1);
    } catch (error) {
      setRecordFeedback(error.message || 'Unable to import agent records.');
    } finally {
      setRecordBusy(false);
    }
  };
  const handleSubmitted = (report) => {
    setReports((current) => [report, ...current]);
    setAnalyticsRefreshKey((current) => current + 1);
    onSubmitted?.(report);
  };
  const startEditing = (report) => { setEditingReport(report ? { ...report } : null); setEditSalesperson(report?.employee_name || ''); setEditReportDate(report ? dateOf(report) : ''); setEditFeedback(''); };
  const salespersonNames = [...new Set(reports.map((report) => valueOf(report, 'employee_name')).filter(Boolean))].sort();
  const reportDates = [...new Set(reports.map(dateOf).filter(Boolean))].sort().reverse();
  const searchEditReport = () => {
    const match = reports.find((report) => valueOf(report, 'employee_name') === editSalesperson && dateOf(report) === editReportDate);
    startEditing(match);
    if (!match) setEditFeedback('No report found for that salesperson and date.');
  };
  const updateEditing = (field, value) => setEditingReport((current) => ({ ...current, [field]: value }));
  const saveEditing = async (event) => {
    event.preventDefault();
    try {
      const response = await fetch(apiUrl(`/api/sales/reports/${editingReport.id}`), { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` }, body: JSON.stringify(editingReport) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update sales report.');
      setReports((current) => current.map((report) => report.id === editingReport.id ? payload.data : report));
      setAnalyticsRefreshKey((current) => current + 1);
      setEditingReport(null);
      setEditFeedback('Sales report updated successfully.');
    } catch (error) { setEditFeedback(error.message); }
  };
  return <section className="sales-reports-page" id="sales-reports">
    <div className="sales-page-hero"><div><p className="leave-kicker">{canViewEmployeePerformance ? 'MANAGEMENT REPORTING' : 'FIELD OPERATIONS'}</p><h2>{canViewEmployeePerformance ? 'Sales & Marketing Performance' : 'Sales Reports'}</h2><p className="leave-muted">{canViewEmployeePerformance ? 'Review team performance, registration trends, and follow-up priorities.' : 'Search visits and understand your client pipeline.'}</p></div>{showClientEntry && <button type="button" className="leave-primary-button" aria-expanded={showForm} aria-controls="sales-daily-report" onClick={() => setShowForm((current) => !current)}>{showForm ? 'Close report' : 'Add Client'}</button>}</div>
    {(canManageAgentRecords || canAddClient) && <section className="sales-agent-record-tools" aria-label="M-Pesa agent record import and export">
      <div><p className="leave-kicker">M-PESA AGENT RECORDS</p><h3>Import and export client visit records</h3><p className="leave-muted">Use the CSV or Excel template for field and telesales report data. Managers must supply each field agent's employee ID. Uploads are validated as a complete batch before any records are saved; no example figures are preloaded.</p></div>
      <div className="sales-agent-record-actions">
        <button type="button" className="leave-secondary-button" onClick={() => downloadAgentRecords(true)}>Download CSV template</button>
        <button type="button" className="leave-secondary-button" onClick={() => downloadAgentRecords(true, 'xlsx')}>Download Excel template</button>
        <button type="button" className="leave-secondary-button" onClick={() => downloadAgentRecords(false)}>Export filtered records</button>
        <button type="button" className="leave-secondary-button" onClick={() => downloadAgentRecords(false, 'xlsx')}>Export Excel records</button>
        {canManageAgentRecords && <form onSubmit={importAgentRecords}>
          <label>Import report CSV or Excel<input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required onChange={(event) => setRecordFile(event.target.files?.[0] || null)} /></label>
          <button type="submit" className="leave-primary-button" disabled={!recordFile || recordBusy}>{recordBusy ? 'Importing…' : 'Import records'}</button>
        </form>}
      </div>
      {recordFeedback && <p className="sales-agent-record-feedback" role="status">{recordFeedback}</p>}
    </section>}
    {showClientEntry && showForm && <div ref={formRef}><SalesDailyReportForm onSubmitted={handleSubmitted} isFieldAgent={isFieldAgent} /></div>}
    {showLeadWorkspace && <SalesLeadWorkspace canManage={canViewEmployeePerformance} />}
    {showReportCorrections && <section className="sales-edit-panel" aria-label="Edit sales report"><div className="sales-edit-heading"><div><p className="leave-kicker">REPORT CORRECTIONS</p><h3>Correct an employee report</h3></div>{editFeedback && <span role="status">{editFeedback}</span>}</div><div className="sales-edit-selector-row"><label>Salesperson name<select value={editSalesperson} onChange={(event) => { setEditSalesperson(event.target.value); setEditingReport(null); }}><option value="">Choose salesperson</option>{salespersonNames.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><label>Report date<select value={editReportDate} onChange={(event) => { setEditReportDate(event.target.value); setEditingReport(null); }}><option value="">Choose date</option>{reportDates.map((date) => <option key={date} value={date}>{date}</option>)}</select></label><button type="button" className="leave-primary-button sales-search-button" onClick={searchEditReport} disabled={!editSalesperson || !editReportDate}>Search</button></div>{editingReport && <form className="sales-edit-grid" onSubmit={saveEditing}><label>Agent Name<input value={editingReport.agent_name || ''} onChange={(event) => updateEditing('agent_name', event.target.value)} required /></label><label>Agent Number<input value={editingReport.agent_number || ''} onChange={(event) => updateEditing('agent_number', event.target.value)} /></label><label>Store Number<input value={editingReport.store_number || ''} onChange={(event) => updateEditing('store_number', event.target.value)} /></label><label>Business Location<input value={editingReport.business_location || ''} onChange={(event) => updateEditing('business_location', event.target.value)} /></label><label>Status<select value={editingReport.outcome || ''} onChange={(event) => updateEditing('outcome', event.target.value)}>{Object.entries(outcomeLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="sales-full-field">Notes<textarea value={editingReport.notes || ''} onChange={(event) => updateEditing('notes', event.target.value)} rows="3" /></label><div className="form-actions"><button type="button" className="leave-secondary-button" onClick={() => setEditingReport(null)}>Cancel</button><button type="submit" className="leave-primary-button">Save correction</button></div></form>}</section>}
    <div className="sales-report-toolbar"><label>Search reports<input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} placeholder="Salesperson, client, store, location..." /></label><label>From<input type="date" value={filters.from} onChange={(event) => updateFilter('from', event.target.value)} /></label><label>To<input type="date" value={filters.to} onChange={(event) => updateFilter('to', event.target.value)} /></label><label>Client type<select value={filters.clientType} onChange={(event) => updateFilter('clientType', event.target.value)}><option value="">All</option><option value="new">New</option><option value="existing">Existing</option></select></label><label>Status<select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}><option value="">All statuses</option>{Object.entries(outcomeLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Agent category<select aria-label="Filter analytics by Agent category" value={filters.category} onChange={(event) => updateFilter('category', event.target.value)}><option value="">All (Agent + Sub-Agent)</option><option value="agent">Agent / Dealer</option><option value="sub_agent">Sub-Agent</option></select></label><label>Registration<select value={filters.registration} onChange={(event) => updateFilter('registration', event.target.value)}><option value="">All</option><option value="COMPLETE">Complete</option><option value="INCOMPLETE">Incomplete</option></select></label><label>Referral<select value={filters.referral} onChange={(event) => updateFilter('referral', event.target.value)}><option value="">All</option><option value="true">Yes</option><option value="false">No</option></select></label><label>Appointment<select value={filters.appointment} onChange={(event) => updateFilter('appointment', event.target.value)}><option value="">All</option><option value="upcoming">Upcoming</option><option value="past">Past</option></select></label><button type="button" className="leave-text-button" onClick={clearFilters}>Clear filters</button></div>
    <div className="sales-report-toolbar sales-report-extended-filters">
      <label>Day of week<select value={filters.day} onChange={(event) => updateFilter('day', event.target.value)}><option value="">All days</option>{['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map((day, index) => <option key={day} value={String(index)}>{day}</option>)}</select></label>
      <label>Month<select value={filters.month} onChange={(event) => updateFilter('month', event.target.value)}><option value="">All months</option>{Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, '0')).map((month) => <option key={month} value={month}>{new Date(2020, Number(month) - 1, 1).toLocaleString(undefined, { month: 'long' })}</option>)}</select></label>
      <label>Year<select value={filters.year} onChange={(event) => updateFilter('year', event.target.value)}><option value="">All years</option>{reportYears.map((year) => <option value={year} key={year}>{year}</option>)}</select></label>
      <label>Business location<select value={filters.location} onChange={(event) => updateFilter('location', event.target.value)}><option value="">All locations</option>{locations.map((location) => <option value={location} key={location}>{location}</option>)}</select></label>
      <label>Sales &amp; Marketing agent<select value={filters.employee_id} onChange={(event) => updateFilter('employee_id', event.target.value)}><option value="">All agents</option>{fieldOfficers.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select></label>
    </div>
    <div className="report-view-tabs sales-report-tabs"><button type="button" className={tab === 'records' ? 'is-active' : ''} onClick={() => setTab('records')}>Records ({filteredReports.length})</button><button type="button" className={tab === 'analytics' ? 'is-active' : ''} onClick={() => setTab('analytics')}>Analytics</button></div>
    {tab === 'records' ? <section className="sales-visit-list"><div className="leave-section-heading"><div><p className="leave-kicker">FILTERED RESULTS</p><h3>Client visit records</h3></div><span className="section-meta">{filteredReports.length} of {reports.length}</span></div>{filteredReports.length === 0 ? <div className="sales-empty-state"><strong>No reports match your filters.</strong><button type="button" className="leave-text-button" onClick={clearFilters}>Clear filters</button></div> : <div className="sales-visit-table-wrap"><table className="leave-table"><thead><tr><th>Date</th><th>Sales &amp; Marketing agent</th><th>Client</th><th>Type</th><th>Status</th><th>Category</th><th>Location</th><th>Registration</th><th>Referral</th></tr></thead><tbody>{filteredReports.map((report) => <tr key={report.id || `${valueOf(report, 'agent_name')}-${dateOf(report)}`}><td>{dateOf(report) || '-'}</td><td><strong>{valueOf(report, 'employee_name') || `Employee ${valueOf(report, 'employee_id') || ''}`}</strong></td><td><strong>{valueOf(report, 'agent_name') || '-'}</strong><small>{valueOf(report, 'agent_number') || valueOf(report, 'store_number') || ''}</small></td><td>{valueOf(report, 'new_client') === false || report.client_record?.clientType === 'existing' ? 'Existing' : 'New'}</td><td><span className="sales-outcome">{outcomeLabels[statusOf(report)] || statusOf(report) || '-'}</span></td><td>{categoryLabels[categoryOf(report)] || '-'}</td><td>{valueOf(report, 'business_location') || '-'}</td><td>{registrationOf(report) || '-'}</td><td>{referralOf(report) ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div>}</section> : null}
    {tab === 'analytics' && <SalesRegistrationAnalytics
      filters={filters}
      refreshKey={analyticsRefreshKey}
      canViewEmployeePerformance={canViewEmployeePerformance}
    />}
    {tab === 'analytics' && (canAddClient || canViewEmployeePerformance) && <SalesFieldAgentAnalytics />}
    {(canAddClient || canViewEmployeePerformance) && <SalesRecoveryFollowUps />}
  </section>;
}
