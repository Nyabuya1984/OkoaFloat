import React, { useEffect, useMemo, useState } from 'react';
import SalesDailyReportForm from './SalesDailyReportForm';
import { getAuthToken } from '../services/authStorage';
import { apiUrl } from '../services/apiConfig';

const outcomeLabels = { existing: 'Existing', interested: 'Interested', not_interested: 'Not interested', appointment: 'Appointment', ready_to_register: 'Ready to register', registered: 'Registered', declined: 'Not interested', promised: 'Promised' };
const categoryLabels = { agent: 'M-Pesa Agent / Dealer', sub_agent: 'M-Pesa Sub-Agent', mpesa_agent_dealer: 'M-Pesa Agent / Dealer', mpesa_sub_agent: 'M-Pesa Sub-Agent' };
const emptyFilters = { search: '', from: '', to: '', clientType: '', status: '', category: '', registration: '', referral: '', appointment: '' };

const valueOf = (report, field) => report[field] ?? report.client_record?.[field] ?? '';
const statusOf = (report) => valueOf(report, 'outcome') || report.client_record?.new?.status || (report.client_record?.clientType === 'existing' ? 'existing' : '');
const categoryOf = (report) => valueOf(report, 'customer_type') || report.client_record?.new?.category || report.client_record?.existing?.category || '';
const registrationOf = (report) => valueOf(report, 'registration_status') || report.client_record?.new?.registrationStatus || (statusOf(report) === 'registered' ? 'COMPLETE' : '');
const referralOf = (report) => valueOf(report, 'referral_agreed') === 'yes' || Boolean(report.client_record?.existing?.referralDetails);
const dateOf = (report) => valueOf(report, 'date_visited') || valueOf(report, 'created_at')?.slice(0, 10) || '';

export default function SalesReportsPage({ reports: initialReports = [], onSubmitted, canEdit = false }) {
  const [showForm, setShowForm] = useState(false);
  const [reports, setReports] = useState(initialReports);
  const [tab, setTab] = useState('records');
  const [filters, setFilters] = useState(emptyFilters);
  const [editingReport, setEditingReport] = useState(null);
  const [editSalesperson, setEditSalesperson] = useState('');
  const [editReportDate, setEditReportDate] = useState('');
  const [editFeedback, setEditFeedback] = useState('');

  useEffect(() => setReports(initialReports), [initialReports]);
  const locations = useMemo(() => [...new Set(reports.map((report) => valueOf(report, 'business_location')).filter(Boolean))].sort(), [reports]);
  const filteredReports = useMemo(() => {
    const search = filters.search.trim().toLowerCase();
    return reports.filter((report) => {
      const date = dateOf(report);
      const text = [valueOf(report, 'agent_name'), valueOf(report, 'agent_number'), valueOf(report, 'store_number'), valueOf(report, 'business_location'), report.client_record?.new?.witness?.name, report.client_record?.new?.witness?.idNumber, report.client_record?.existing?.referralDetails?.contactNumber].join(' ').toLowerCase();
      const appointmentDate = valueOf(report, 'appointment_date') || report.client_record?.new?.appointmentDate || '';
      const appointmentMatch = !filters.appointment || (filters.appointment === 'upcoming' ? appointmentDate >= new Date().toISOString().slice(0, 10) : appointmentDate < new Date().toISOString().slice(0, 10));
      return (!search || text.includes(search)) && (!filters.from || date >= filters.from) && (!filters.to || date <= filters.to) && (!filters.clientType || (valueOf(report, 'new_client') === true ? 'new' : valueOf(report, 'new_client') === false ? 'existing' : report.client_record?.clientType) === filters.clientType) && (!filters.status || statusOf(report) === filters.status) && (!filters.category || categoryOf(report) === filters.category) && (!filters.registration || registrationOf(report) === filters.registration) && (!filters.referral || String(referralOf(report)) === filters.referral) && appointmentMatch;
    });
  }, [filters, reports]);

  const updateFilter = (name, value) => setFilters((current) => ({ ...current, [name]: value }));
  const clearFilters = () => setFilters(emptyFilters);
  const handleSubmitted = (report) => { setReports((current) => [report, ...current]); onSubmitted?.(report); };
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
      setEditingReport(null);
      setEditFeedback('Sales report updated successfully.');
    } catch (error) { setEditFeedback(error.message); }
  };
  const metrics = useMemo(() => {
    const total = filteredReports.length;
    const newCount = filteredReports.filter((report) => valueOf(report, 'new_client') === true || report.client_record?.clientType === 'new').length;
    const ready = filteredReports.filter((report) => statusOf(report) === 'ready_to_register').length;
    const complete = filteredReports.filter((report) => registrationOf(report) === 'COMPLETE').length;
    const referrals = filteredReports.filter(referralOf).length;
    const appointments = filteredReports.filter((report) => statusOf(report) === 'appointment').length;
    return { total, newCount, existing: total - newCount, ready, complete, incomplete: ready - complete, referrals, appointments };
  }, [filteredReports]);
  const byStatus = useMemo(() => ['interested', 'not_interested', 'appointment', 'ready_to_register', 'registered'].map((status) => ({ label: outcomeLabels[status], value: filteredReports.filter((report) => statusOf(report) === status).length })), [filteredReports]);
  const byLocation = useMemo(() => locations.map((location) => ({ location, value: filteredReports.filter((report) => valueOf(report, 'business_location') === location).length })).sort((a, b) => b.value - a.value).slice(0, 8), [filteredReports, locations]);

  return <section className="sales-reports-page" id="sales-reports">
    <div className="sales-page-hero"><div><p className="leave-kicker">FIELD OPERATIONS</p><h2>Sales Reports</h2><p className="leave-muted">Search visits and understand your client pipeline.</p></div><button type="button" className="leave-primary-button" onClick={() => setShowForm((current) => !current)}>{showForm ? 'Close report' : 'Add New'}</button></div>
    {showForm && <SalesDailyReportForm onSubmitted={handleSubmitted} />}
    {canEdit && <section className="sales-edit-panel" aria-label="Edit sales report"><div className="sales-edit-heading"><div><p className="leave-kicker">REPORT CORRECTIONS</p><h3>Correct an employee report</h3></div>{editFeedback && <span role="status">{editFeedback}</span>}</div><div className="sales-edit-selector-row"><label>Salesperson name<select value={editSalesperson} onChange={(event) => { setEditSalesperson(event.target.value); setEditingReport(null); }}><option value="">Choose salesperson</option>{salespersonNames.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><label>Report date<select value={editReportDate} onChange={(event) => { setEditReportDate(event.target.value); setEditingReport(null); }}><option value="">Choose date</option>{reportDates.map((date) => <option key={date} value={date}>{date}</option>)}</select></label><button type="button" className="leave-primary-button sales-search-button" onClick={searchEditReport} disabled={!editSalesperson || !editReportDate}>Search</button></div>{editingReport && <form className="sales-edit-grid" onSubmit={saveEditing}><label>Agent Name<input value={editingReport.agent_name || ''} onChange={(event) => updateEditing('agent_name', event.target.value)} required /></label><label>Agent Number<input value={editingReport.agent_number || ''} onChange={(event) => updateEditing('agent_number', event.target.value)} /></label><label>Store Number<input value={editingReport.store_number || ''} onChange={(event) => updateEditing('store_number', event.target.value)} /></label><label>Business Location<input value={editingReport.business_location || ''} onChange={(event) => updateEditing('business_location', event.target.value)} /></label><label>Status<select value={editingReport.outcome || ''} onChange={(event) => updateEditing('outcome', event.target.value)}>{Object.entries(outcomeLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="sales-full-field">Notes<textarea value={editingReport.notes || ''} onChange={(event) => updateEditing('notes', event.target.value)} rows="3" /></label><div className="form-actions"><button type="button" className="leave-secondary-button" onClick={() => setEditingReport(null)}>Cancel</button><button type="submit" className="leave-primary-button">Save correction</button></div></form>}</section>}
    <div className="sales-report-toolbar"><label>Search reports<input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} placeholder="Agent, store, location, witness..." /></label><label>From<input type="date" value={filters.from} onChange={(event) => updateFilter('from', event.target.value)} /></label><label>To<input type="date" value={filters.to} onChange={(event) => updateFilter('to', event.target.value)} /></label><label>Client type<select value={filters.clientType} onChange={(event) => updateFilter('clientType', event.target.value)}><option value="">All</option><option value="new">New</option><option value="existing">Existing</option></select></label><label>Status<select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}><option value="">All statuses</option>{Object.entries(outcomeLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Category<select value={filters.category} onChange={(event) => updateFilter('category', event.target.value)}><option value="">All categories</option><option value="agent">M-Pesa Agent / Dealer</option><option value="sub_agent">M-Pesa Sub-Agent</option></select></label><label>Registration<select value={filters.registration} onChange={(event) => updateFilter('registration', event.target.value)}><option value="">All</option><option value="COMPLETE">Complete</option><option value="INCOMPLETE">Incomplete</option></select></label><label>Referral<select value={filters.referral} onChange={(event) => updateFilter('referral', event.target.value)}><option value="">All</option><option value="true">Yes</option><option value="false">No</option></select></label><label>Appointment<select value={filters.appointment} onChange={(event) => updateFilter('appointment', event.target.value)}><option value="">All</option><option value="upcoming">Upcoming</option><option value="past">Past</option></select></label><button type="button" className="leave-text-button" onClick={clearFilters}>Clear filters</button></div>
    <div className="report-view-tabs sales-report-tabs"><button type="button" className={tab === 'records' ? 'is-active' : ''} onClick={() => setTab('records')}>Records ({filteredReports.length})</button><button type="button" className={tab === 'analytics' ? 'is-active' : ''} onClick={() => setTab('analytics')}>Analytics</button></div>
    {tab === 'records' ? <section className="sales-visit-list"><div className="leave-section-heading"><div><p className="leave-kicker">FILTERED RESULTS</p><h3>Client visit records</h3></div><span className="section-meta">{filteredReports.length} of {reports.length}</span></div>{filteredReports.length === 0 ? <div className="sales-empty-state"><strong>No reports match your filters.</strong><button type="button" className="leave-text-button" onClick={clearFilters}>Clear filters</button></div> : <div className="sales-visit-table-wrap"><table className="leave-table"><thead><tr><th>Date</th><th>Client</th><th>Type</th><th>Status</th><th>Category</th><th>Location</th><th>Registration</th><th>Referral</th></tr></thead><tbody>{filteredReports.map((report) => <tr key={report.id || `${valueOf(report, 'agent_name')}-${dateOf(report)}`}><td>{dateOf(report) || '-'}</td><td><strong>{valueOf(report, 'agent_name') || '-'}</strong><small>{valueOf(report, 'agent_number') || valueOf(report, 'store_number') || ''}</small></td><td>{valueOf(report, 'new_client') === false || report.client_record?.clientType === 'existing' ? 'Existing' : 'New'}</td><td><span className="sales-outcome">{outcomeLabels[statusOf(report)] || statusOf(report) || '-'}</span></td><td>{categoryLabels[categoryOf(report)] || '-'}</td><td>{valueOf(report, 'business_location') || '-'}</td><td>{registrationOf(report) || '-'}</td><td>{referralOf(report) ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div>}</section> : <section className="sales-analytics"><div className="sales-day-summary"><div><strong>{metrics.total}</strong><span>Total records</span></div><div><strong>{metrics.newCount} / {metrics.existing}</strong><span>New / existing</span></div><div><strong>{metrics.ready}</strong><span>Ready to register</span></div><div><strong>{metrics.complete}</strong><span>Complete ({metrics.ready ? Math.round((metrics.complete / metrics.ready) * 100) : 0}%)</span></div><div><strong>{metrics.referrals}</strong><span>Referrals captured</span></div><div><strong>{metrics.appointments}</strong><span>Appointments</span></div></div>{metrics.total === 0 ? <div className="sales-empty-state"><strong>No reports match your filters.</strong></div> : <div className="sales-analysis-grid"><div className="sales-analysis-card"><h3>Status breakdown</h3>{byStatus.map((item) => <div className="sales-bar-row" key={item.label}><span>{item.label}</span><div><i style={{ width: `${metrics.total ? (item.value / metrics.total) * 100 : 0}%` }} /></div><strong>{item.value}</strong></div>)}</div><div className="sales-analysis-card"><h3>Top locations</h3>{byLocation.length === 0 ? <p className="leave-muted">No locations recorded.</p> : byLocation.map((item) => <div className="sales-bar-row" key={item.location}><span>{item.location}</span><div><i style={{ width: `${byLocation[0].value ? (item.value / byLocation[0].value) * 100 : 0}%` }} /></div><strong>{item.value}</strong></div>)}</div></div>}</section>}
  </section>;
}
