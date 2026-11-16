import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, CalendarClock, Check, ExternalLink, Eye, RefreshCw, Siren } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import apiClient from '../services/debtCollectionApi';
import './CustomerCare.css';

const concernDefinitions = [
  ['INFORMATION_INQUIRY', 'Okoa Float service overview', 'inbound'],
  ['REPAYMENT_PERIOD', 'Repayment period', 'inbound'],
  ['ELIGIBILITY', 'Eligibility', 'inbound'],
  ['LIMITS_MIN_MAX', 'Minimum and maximum float', 'inbound'],
  ['USAGE_FREQUENCY', 'Usage frequency', 'inbound'],
  ['TRANSFER_CHARGES', 'M-Pesa float transfer charges', 'inbound'],
  ['TRANSACTIONAL_CHARGES', 'Other transactional charges', 'inbound'],
  ['REGISTRATION_DOCS', 'Registration documents', 'inbound'],
  ['LOAN_BALANCE', 'Loan balance inquiry', 'inbound'],
  ['LOAN_LIMIT', 'Loan limit inquiry', 'inbound'],
  ['LOAN_INCREASE_REQUEST', 'Loan limit increase request', 'inbound'],
  ['REGISTRATION_PROCESS', 'Registration process', 'inbound'],
  ['RECONCILIATION', 'Payment reconciliation dispute', 'inbound'],
  ['PAYMENT_METHOD', 'Loan payment method', 'inbound'],
  ['ACCOUNT_STATUS', 'Account or loan status', 'inbound'],
  ['PRODUCT_INFO', 'Product information', 'inbound'],
  ['GENERAL_INQUIRY', 'General inquiry', 'inbound'],
  ['SALES_REG_VERIFICATION', 'Registration verification (sales)', 'inbound'],
  ['VERIFY_DOCS', 'Verify registration documents', 'outbound'],
  ['VERIFY_REGISTRATION', 'Verify new registration', 'outbound'],
  ['POST_LIMIT_SET', 'Post-limit-set call', 'outbound'],
  ['POST_LIMIT_INCREASE', 'Post-limit-increase call', 'outbound'],
  ['LIMIT_STATUS_ACCEPTED', 'Limit accepted follow-up', 'outbound'],
  ['LIMIT_STATUS_REJECTED', 'Limit rejected follow-up', 'outbound'],
];

const asData = (response) => response.data?.data ?? response.data;
const asArray = (value) => Array.isArray(value) ? value : [];
const today = () => new Date().toISOString().slice(0, 10);
const dateRange = () => ({ start_date: `${today().slice(0, 4)}-01-01`, end_date: today() });
const dateQuery = (start, end) => `from=${encodeURIComponent(start)}&to=${encodeURIComponent(end)}`;
const dateLabel = (value) => {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
};
const labelize = (value) => String(value || '—').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const weekdayLabel = (value) => {
  if (Number.isInteger(value)) return ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][value] || '—';
  return labelize(value);
};
const percentLabel = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${Math.round((numeric <= 1 ? numeric * 100 : numeric) * 10) / 10}%` : '—';
};
const apiMessage = (error) => error.response?.data?.error?.message || error.response?.data?.message || error.message || 'Unable to load this page.';

class OkoaDashboardErrorBoundary extends React.Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <section className="care-page" role="alert">
          <OkoaHeading title="Executive dashboard unavailable" detail="The dashboard encountered a display error. Reload the page to try again." />
          <div className="care-notice is-error">{this.state.error.message || 'An unexpected display error occurred.'}</div>
        </section>
      );
    }
    return this.props.children;
  }
}

function useResource(path, dependencies = [], enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError('');
    apiClient.get(path)
      .then((response) => active && setData(asData(response)))
      .catch((requestError) => active && setError(apiMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  // The caller supplies only stable path values or primitive filter state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, enabled]);

  return { data, loading, error, setData, setError };
}

function OkoaHeading({ eyebrow = 'OKOA OPERATIONS', title, detail, action }) {
  return (
    <header className="care-page-heading">
      <div><p className="care-eyebrow">{eyebrow}</p><h1>{title}</h1>{detail && <p className="care-page-description">{detail}</p>}</div>
      {action}
    </header>
  );
}

function OkoaNotice({ error, success }) {
  if (!error && !success) return null;
  return <div className={`care-notice ${error ? 'is-error' : 'is-success'}`} role={error ? 'alert' : 'status'}>{error || success}</div>;
}

function OkoaState({ loading, error, empty, onRetry }) {
  if (loading) return <div className="care-card care-state" role="status">Loading Okoa Operations data…</div>;
  if (error) return <div className="care-card care-state"><strong>Unable to load this page</strong><span>{error}</span>{onRetry && <button className="care-secondary-button" type="button" onClick={onRetry}><RefreshCw size={14} /> Retry</button>}</div>;
  if (empty) return <div className="care-card care-state">{empty}</div>;
  return null;
}

function OkoaTable({ columns, rows, rowKey = 'id', empty = 'No records found.' }) {
  if (!rows?.length) return <div className="care-card care-state">{empty}</div>;
  return (
    <div className="care-card care-table-scroll">
      <table className="care-table">
        <thead><tr>{columns.map((column) => <th key={column.label}>{column.label}</th>)}</tr></thead>
        <tbody>{rows.map((row, index) => (
          <tr key={row[rowKey] ?? index}>
            {columns.map((column) => <td key={column.label}>{column.render ? column.render(row) : column.value ? column.value(row) : row[column.key]}</td>)}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function MetricCard({ label, value, caption, tone = '', className = '' }) {
  return <article className={`care-card care-okia-metric ${tone} ${className}`}><span>{label}</span><strong>{value ?? '—'}</strong>{caption && <small>{caption}</small>}</article>;
}

function DateFilters({ start, end, onStart, onEnd }) {
  return (
    <div className="care-card care-okia-filter">
      <label className="care-filter"><span>From</span><input type="date" value={start} onChange={(event) => onStart(event.target.value)} /></label>
      <label className="care-filter"><span>To</span><input type="date" value={end} onChange={(event) => onEnd(event.target.value)} /></label>
    </div>
  );
}

export function OkoaOverviewPage() {
  const [range] = useState(dateRange);
  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const todayRange = `?${dateQuery(range.end_date, range.end_date)}`;
  const escalation = useResource('/api/escalations/summary');
  const openEscalations = useResource('/api/escalations?status=open', [drilldownOpen], drilldownOpen);
  const currentShift = useResource('/api/shifts/current', [drilldownOpen], drilldownOpen);
  const coverage = useResource(`/api/shifts/coverage${todayRange}`, [todayRange, drilldownOpen], drilldownOpen);
  const concerns = useResource(`/api/reports/concerns${todayRange}`, [todayRange, drilldownOpen], drilldownOpen);
  const resolution = useResource(`/api/reports/gm/resolution${todayRange}`, [todayRange, drilldownOpen], drilldownOpen);
  const gmShift = useResource('/api/reports/gm/shift-overview');
  const escalationData = escalation.data || {};
  const openEscalationRows = asArray(
    Array.isArray(openEscalations.data)
      ? openEscalations.data
      : openEscalations.data?.items || openEscalations.data?.results,
  );
  const shiftData = currentShift.data || {};
  const coverageRows = asArray(
    Array.isArray(coverage.data)
      ? coverage.data
      : coverage.data?.shifts || coverage.data?.by_shift,
  );
  const concernRows = asArray(
    Array.isArray(concerns.data)
      ? concerns.data
      : concerns.data?.categories || concerns.data?.results,
  );
  const topConcern = concernRows[0];
  const departmentManagers = asArray(gmShift.data?.manager);
  const teamLeaders = asArray(gmShift.data?.team_leader);
  const totalToday = Number(resolution.data?.total || 0);
  const resolvedToday = Number(resolution.data?.resolved || 0);
  const departmentSnapshots = gmShift.data?.department_snapshots || {};

  return (
    <section className="care-page">
      <OkoaHeading title="General Manager Executive Overview" detail="A live view of service, escalations, and department performance." />
      <OkoaNotice error={[escalation.error, gmShift.error].filter(Boolean).join(' · ')} />
      <article className="care-card care-gm-shift-overview" aria-label="GM shift overview">
        <header>
          <div><p className="care-eyebrow">TODAY'S EXECUTIVE SNAPSHOT</p><h2>{gmShift.data?.date || today()} · Shift {gmShift.data?.shift_code || shiftData.code || shiftData.shift_code || '—'}</h2></div>
          <small className="care-gm-shift-timezone">{gmShift.data?.timezone || 'Africa/Nairobi time'}</small>
        </header>
        <div className="care-gm-shift-managers">
          <span><small>Department managers</small><strong>{departmentManagers.map((person) => person.name).join(', ') || 'No managers recorded'}</strong></span>
          <span><small>Team leaders</small><strong>{teamLeaders.map((person) => person.name).join(', ') || 'No team leaders recorded'}</strong></span>
        </div>
        <div className="care-gm-shift-metrics">
          <MetricCard className="care-gm-shift-metric" label="Clients served" value={gmShift.data?.clients_served ?? '—'} />
          <MetricCard className="care-gm-shift-metric" label="First-contact resolution" value={percentLabel(gmShift.data?.first_contact_resolution?.rate)} caption="First recorded call per client in this shift/date; based on logged call status." />
          <MetricCard className="care-gm-shift-metric" label="Pending escalations" value={escalationData.open_count ?? escalationData.open ?? escalationData.total_open ?? gmShift.data?.pending_escalations ?? '—'} tone="is-alert" />
          <MetricCard className="care-gm-shift-metric" label="Active agents" value={gmShift.data?.active_agents ?? '—'} />
        </div>
        <p className="care-gm-report-note">Agents are staff with calls recorded in this shift/date. Manager roles come from active organizational assignments; they are not a shift-duty roster.</p>
      </article>
      <section className="care-gm-department-snapshots" aria-label="Department shift snapshots">
        <header className="care-section-heading"><div><p className="care-eyebrow">EXECUTIVE SNAPSHOT · {gmShift.data?.date || today()}</p><h2>Department performance</h2></div></header>
        <div className="care-gm-department-grid">
          <article className="care-card care-gm-department-card">
            <h3>Sales &amp; Marketing</h3>
            <div className="care-gm-department-metrics">
              <MetricCard label="New registrations" value={departmentSnapshots.sales_marketing?.new_registrations ?? '—'} />
              <MetricCard label="Appointments" value={departmentSnapshots.sales_marketing?.appointments ?? '—'} />
              <MetricCard label="Pending documents" value={departmentSnapshots.sales_marketing?.pending_documents ?? '—'} tone={departmentSnapshots.sales_marketing?.pending_documents > 0 ? 'is-alert' : ''} />
            </div>
            <small className="care-gm-report-note">{departmentSnapshots.sales_marketing?.basis || 'No Sales & Marketing snapshot is available.'}</small>
            <Link className="care-secondary-button" to="/dashboard/reports/sales">Open Sales &amp; Marketing reports <ArrowRight size={14} /></Link>
          </article>
          <article className="care-card care-gm-department-card">
            <h3>Debt Collection</h3>
            <div className="care-gm-department-metrics">
              <MetricCard label="Calls made today" value={departmentSnapshots.debt_collection?.calls_made ?? '—'} />
              <MetricCard label="Promises to pay" value={departmentSnapshots.debt_collection?.promises_to_pay ?? '—'} />
              <MetricCard label="Default escalations" value={departmentSnapshots.debt_collection?.default_escalations ?? '—'} tone={departmentSnapshots.debt_collection?.default_escalations > 0 ? 'is-alert' : ''} />
            </div>
            <small className="care-gm-report-note">{departmentSnapshots.debt_collection?.default_escalations_basis || 'No Debt Collection snapshot is available.'}</small>
            <Link className="care-secondary-button" to="/dashboard/debt-collection">Open Debt Collection operations <ArrowRight size={14} /></Link>
          </article>
          <article className="care-card care-gm-department-card">
            <h3>Customer Care</h3>
            <div className="care-gm-department-metrics">
              <MetricCard label="Calls handled" value={departmentSnapshots.customer_care?.calls_handled ?? '—'} />
              <MetricCard label="First-contact resolution" value={percentLabel(departmentSnapshots.customer_care?.first_contact_resolution_rate)} />
              <MetricCard label="Open tickets" value={departmentSnapshots.customer_care?.open_tickets ?? '—'} tone={departmentSnapshots.customer_care?.open_tickets > 0 ? 'is-alert' : ''} />
            </div>
            <small className="care-gm-report-note">{departmentSnapshots.customer_care?.basis || 'No Customer Care snapshot is available.'}</small>
            <Link className="care-secondary-button" to="/dashboard/customer-care/logs">Open Customer Care activity <ArrowRight size={14} /></Link>
          </article>
        </div>
      </section>
      <details className="care-gm-drilldown" onToggle={(event) => setDrilldownOpen(event.currentTarget.open)}>
        <summary>Open executive operational details</summary>
        <div className="care-gm-drilldown-content">
      <div className="care-okia-metrics">
        <MetricCard label="Open escalations" value={escalationData.open_count ?? escalationData.open ?? escalationData.total_open} caption="Require follow-up" tone="is-alert" />
        <MetricCard label="Unresolved today" value={Math.max(0, totalToday - resolvedToday)} caption={`${resolvedToday} of ${totalToday} calls resolved`} tone="is-alert" />
        <MetricCard label="Current shift" value={shiftData.code ? `Shift ${shiftData.code}` : shiftData.shift_code ? `Shift ${shiftData.shift_code}` : shiftData.name || '—'} caption={shiftData.starts_at ? `Started ${dateLabel(shiftData.starts_at)}` : 'Africa/Nairobi time'} tone="is-primary" />
        <MetricCard label="Top concern today" value={topConcern ? labelize(topConcern.label || topConcern.code || topConcern.concern_category) : '—'} caption={topConcern ? `${topConcern.total_calls ?? topConcern.count ?? 0} calls` : 'No concern data'} />
      </div>
      <div className="care-section-heading"><div><p className="care-eyebrow">TODAY</p><h2>Calls by shift</h2></div><Link className="care-inline-link" to="/okia/shifts/coverage">Full coverage report <ArrowRight size={14} /></Link></div>
      <OkoaTable
        columns={[
          { label: 'Shift', render: (row) => `Shift ${row.shift_code || row.code || row.shift || '—'}` },
          { label: 'Total calls', value: (row) => row.total_calls ?? row.calls ?? row.count ?? 0 },
          { label: 'Resolved', value: (row) => row.resolved ?? row.resolved_calls ?? 0 },
          { label: 'Escalated', value: (row) => row.escalated ?? row.escalated_calls ?? 0 },
          {
            label: 'Agents on duty',
            render: (row) => {
              const agents = asArray(row.agents_on_duty);
              return agents.length
                ? agents.map((agent) => agent.name || agent.employee_id || agent.id).join(', ')
                : row.agent_count ?? '—';
            },
          },
        ]}
        rows={coverageRows}
        empty={coverage.loading ? 'Loading shift coverage…' : coverage.error || 'No calls have been logged today.'}
      />
      <div className="care-section-heading"><div><p className="care-eyebrow">DECISIONS REQUIRED</p><h2>Open escalations</h2></div><Link className="care-inline-link" to="/okia/escalations">Review escalation queue <ArrowRight size={14} /></Link></div>
      <OkoaTable
        columns={[
          { label: 'Ticket', render: (row) => <Link className="care-table-link" to={`/okia/escalations/${row.id}`}>{row.reference_number || `Call #${row.call_id}`}</Link> },
          { label: 'Customer', render: (row) => row.customer?.name || row.customer_name || row.call?.customer?.name || 'Customer details unavailable' },
          { label: 'Department', render: (row) => labelize(row.to_dept || row.escalated_to) },
          { label: 'Reason', render: (row) => row.reason || row.call?.escalation_reason || '—' },
          { label: 'Opened', render: (row) => dateLabel(row.created_at) },
          { label: 'Review', render: (row) => <Link className="care-secondary-button" to={`/okia/escalations/${row.id}`}>Open case <ArrowRight size={14} /></Link> },
        ]}
        rows={openEscalationRows.slice(0, 5)}
        empty={openEscalations.loading ? 'Loading open escalations…' : openEscalations.error || 'No open escalations require a decision.'}
      />
      <div className="care-okia-links">
        <Link className="care-secondary-button" to="/okia/escalations"><Siren size={15} /> Escalation queue</Link>
        <Link className="care-secondary-button" to="/okia/reports/gm-resolution"><CalendarClock size={15} /> GM reports</Link>
        <Link className="care-secondary-button" to="/okia/reports/agent-shift-matrix"><CalendarClock size={15} /> Agent activity report</Link>
        <Link className="care-secondary-button" to="/dashboard/organization/history"><CalendarClock size={15} /> Department history</Link>
        <Link className="care-secondary-button" to="/dashboard/organization/live"><ExternalLink size={15} /> Staff activity and locations</Link>
      </div>
        </div>
      </details>
    </section>
  );
}

export function EscalationListPage() {
  const [status, setStatus] = useState('open');
  const [department, setDepartment] = useState('');
  const [reason, setReason] = useState('');
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (department) params.set('to_dept', department);
  if (reason) params.set('reason', reason);
  const resource = useResource(`/api/escalations?${params.toString()}`, [status, department, reason]);
  const rows = Array.isArray(resource.data) ? resource.data : resource.data?.items || resource.data?.results || [];
  const [savingId, setSavingId] = useState(null);
  const [success, setSuccess] = useState('');
  const [actionError, setActionError] = useState('');

  const resolve = async (row) => {
    setSavingId(row.id);
    setActionError('');
    setSuccess('');
    try {
      const response = await apiClient.patch(`/api/escalations/${row.id}/resolve`, {});
      const updated = { ...row, ...asData(response) };
      resource.setData((previous) => {
        const previousRows = Array.isArray(previous)
          ? previous
          : previous?.items || previous?.results || [];
        return status === 'open'
          ? previousRows.filter((item) => item.id !== row.id)
          : previousRows.map((item) => item.id === row.id ? updated : item);
      });
      setSuccess(`${row.reference_number || `Call #${row.call_id}`} was resolved.`);
    } catch (error) {
      setActionError(apiMessage(error));
    } finally {
      setSavingId(null);
    }
  };

  return (
    <section className="care-page">
      <OkoaHeading
        title="Escalation queue"
        detail="Review urgent customer-care issues, open the related call, and resolve cases when follow-up is complete."
        action={<div className="care-escalation-count"><Siren size={17} /><span>Showing</span><strong>{rows.length}</strong><span>{status === 'open' ? 'open cases' : 'cases'}</span></div>}
      />
      <OkoaNotice error={actionError} success={success} />
      <div className="care-card care-okia-filter">
        <label className="care-filter"><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="open">Open</option><option value="resolved">Resolved</option><option value="">All</option></select></label>
        <label className="care-filter"><span>Route to</span><select value={department} onChange={(event) => setDepartment(event.target.value)}><option value="">All destinations</option><option value="general_manager">General Manager</option><option value="it_support">IT Support</option><option value="supervisor">Supervisor</option></select></label>
        <label className="care-filter"><span>Reason</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Filter by reason" /></label>
      </div>
      <OkoaState loading={resource.loading} error={resource.error} />
      {!resource.loading && !resource.error && <OkoaTable columns={[
        { label: 'Ticket / priority', render: (row) => <><Link className="care-table-link" to={`/okia/escalations/${row.id}`}>{row.reference_number || row.call?.reference_number || `Call #${row.call_id}`}</Link><small className="care-gm-subtext">{labelize(row.priority)}</small></> },
        { label: 'Customer', render: (row) => <div className="care-escalation-customer"><strong>{row.customer?.name || row.customer_name || row.call?.customer?.name || row.call_log?.customer?.name || 'Customer details unavailable'}</strong><small>{row.customer?.phone_number || row.call?.customer?.phone_number || row.call_log?.customer?.phone_number || 'Customer contact not provided'}</small></div> },
        { label: 'Handling agent', render: (row) => row.handling_agent || 'Not recorded' },
        { label: 'Shift', render: (row) => row.shift_code ? `Shift ${row.shift_code}` : 'Not recorded' },
        { label: 'Assigned to', render: (row) => <span className="care-badge status-escalated">{labelize(row.to_dept || row.escalated_to)}</span> },
        { label: 'Reason', render: (row) => row.reason || row.call?.escalation_reason || '—' },
        { label: 'Opened', render: (row) => dateLabel(row.created_at) },
        { label: 'Status', render: (row) => <span className={`care-badge ${row.status === 'resolved' ? 'status-resolved' : 'status-escalated'}`}>{labelize(row.status)}</span> },
        { label: 'Actions', render: (row) => <div className="care-escalation-actions"><Link className="care-secondary-button care-escalation-action" to={`/okia/escalations/${row.id}`} aria-label={`View escalation ${row.reference_number || row.id}`}><Eye size={14} />View</Link>{row.status === 'open' && <button className="care-primary-button care-escalation-action" type="button" onClick={() => resolve(row)} disabled={savingId !== null} aria-label={`Resolve escalation ${row.reference_number || row.id}`}><Check size={14} />{savingId === row.id ? 'Saving…' : 'Resolve'}</button>}</div> },
      ]} rows={rows} empty="No escalations match these filters." />}
    </section>
  );
}

export function EscalationDetailPage() {
  const { escalationId } = useParams();
  const resource = useResource(`/api/escalations/${escalationId}`, [escalationId]);
  const reportResource = useResource(
    `/api/reports/gm/escalations/${escalationId}`,
    [escalationId],
  );
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const escalation = resource.data?.escalation || resource.data;
  const call = escalation?.call || escalation?.call_log || {};
  const report = reportResource.data;
  const reportSections = report?.sections || [];
  const clientReport = reportSections.find((section) => section.id === 'client');
  const shiftReport = reportSections.find((section) => section.id === 'shift');
  const agentReport = reportSections.find((section) => section.id === 'agent_activity');
  const escalationReport = reportSections.find((section) => section.id === 'escalation');

  const resolve = async () => {
    setSaving(true);
    resource.setError('');
    setSuccess('');
    try {
      const response = await apiClient.patch(`/api/escalations/${escalationId}/resolve`, {});
      resource.setData({ ...escalation, ...asData(response) });
      setSuccess('Escalation resolved.');
    } catch (error) {
      resource.setError(apiMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="care-page">
      <Link className="care-back-link" to="/okia/escalations"><ArrowLeft size={16} /> Escalation queue</Link>
      <OkoaHeading title="Escalation details" detail={escalation?.reference_number || call.reference_number || `Escalation #${escalationId}`} />
      <OkoaNotice error={resource.error} success={success} />
      <OkoaState loading={resource.loading} error={resource.error} />
      {!resource.loading && escalation && (
        <>
        <div className="care-okia-detail-grid">
          <article className="care-card care-okia-detail">
            <h2><Siren size={18} /> Escalation</h2>
            <dl>
              <dt>Department</dt><dd>{labelize(escalation.to_dept || escalation.escalated_to)}</dd>
              <dt>Status</dt><dd><span className={`care-badge ${escalation.status === 'resolved' ? 'status-resolved' : 'status-escalated'}`}>{labelize(escalation.status)}</span></dd>
              <dt>Reason</dt><dd>{escalation.reason || call.escalation_reason || '—'}</dd>
              <dt>Opened</dt><dd>{dateLabel(escalation.created_at)}</dd>
              <dt>Resolved</dt><dd>{dateLabel(escalation.resolved_at)}</dd>
            </dl>
            {escalation.status !== 'resolved' && <button className="care-primary-button" type="button" onClick={resolve} disabled={saving}><Check size={15} />{saving ? 'Saving…' : 'Resolve escalation'}</button>}
          </article>
          <article className="care-card care-okia-detail">
            <h2>Related call</h2>
            <dl>
              <dt>Reference</dt><dd>{call.reference_number || escalation.reference_number || `Call #${escalation.call_id}`}</dd>
              <dt>Customer</dt><dd>{call.customer?.name || escalation.customer?.name || escalation.customer_name || 'Customer details unavailable'}{(call.customer?.phone_number || escalation.customer?.phone_number) && <><br /><small>{call.customer?.phone_number || escalation.customer?.phone_number}</small></>}</dd>
              <dt>Concern</dt><dd>{labelize(call.concern_category || call.category)}</dd>
              <dt>Shift</dt><dd>{call.shift_code ? `Shift ${call.shift_code}` : '—'}</dd>
              <dt>Summary</dt><dd>{call.summary || '—'}</dd>
            </dl>
            {escalation.call_id && <Link className="care-inline-link" to={`/dashboard/customer-care/logs/${escalation.call_id}`}>Open call log <ExternalLink size={14} /></Link>}
          </article>
        </div>
        <section className="care-gm-report" aria-label="General Manager escalation report">
          <header><div><p className="care-eyebrow">GENERAL MANAGER BRIEFING</p><h2>Escalation report</h2><p>Client history, shift context, handling-agent activity, and the decision requested.</p></div><span>{report?.escalation?.status ? labelize(report.escalation.status) : 'Loading report'}</span></header>
          {reportResource.error && <div className="care-notice is-error" role="alert">Unable to load the complete GM report: {reportResource.error}</div>}
          {reportResource.loading && <div className="care-card care-state" role="status">Preparing client and shift report…</div>}
          {!reportResource.loading && report && <>
            <article className="care-card care-gm-decision">
              <div className="care-gm-decision-heading">
                <div><span className="care-gm-ticket">Ticket #{escalation.reference_number || call.reference_number || escalation.call_id}</span><h3>Root Cause Summary</h3><p>{escalationReport?.root_cause || escalationReport?.issue_summary || call.summary || escalation.reason || 'No root-cause summary recorded.'}</p></div>
                <div className="care-gm-tags">
                  {(report.escalation?.exception_tags || []).map((tag) => <span className={`care-badge ${tag === 'OPEN' || tag.includes('PRIORITY') || tag === 'URGENT' ? 'status-escalated' : ''}`} key={tag}>{labelize(tag)}</span>)}
                  {!report.escalation?.exception_tags?.length && <span className="care-badge status-escalated">{labelize(escalation.status)}</span>}
                </div>
              </div>
              <dl className="care-gm-decision-facts">
                <dt>Priority</dt><dd>{labelize(escalationReport?.priority || call.priority)}</dd>
                <dt>Department</dt><dd>{labelize(escalationReport?.department || report.escalation?.department || escalation.to_dept)}</dd>
                <dt>Client</dt><dd>{escalationReport?.client || clientReport?.client?.name || escalation.customer?.name || 'Not recorded'} (Store #{escalationReport?.store_number || clientReport?.client?.store_number || '—'}, Agent #{escalationReport?.agent_number || clientReport?.client?.agent_number || '—'})</dd>
                <dt>Handling agent</dt><dd>{escalationReport?.handling_agent || agentReport?.agent?.name || 'Not recorded'} · {escalationReport?.handling_agent_staff_id || agentReport?.agent?.staff_id || 'Staff ID not recorded'}</dd>
                <dt>Team leader</dt><dd>{escalationReport?.team_leader?.name || shiftReport?.hierarchy?.team_leader?.[0]?.name || 'No active assignment recorded'}</dd>
                <dt>Department manager</dt><dd>{typeof escalationReport?.shift_manager === 'string' ? escalationReport.shift_manager : escalationReport?.shift_manager?.name || shiftReport?.hierarchy?.department_manager?.[0]?.name || 'No active assignment recorded'}</dd>
                <dt>Shift / date</dt><dd>{shiftReport?.shift?.shift_id ? `Shift ${shiftReport.shift.shift_id}` : 'Shift not recorded'} · {shiftReport?.shift?.date || 'Date not recorded'}</dd>
                <dt>Business risk / impact</dt><dd>{escalationReport?.impact || 'No separate impact assessment was recorded.'}</dd>
                <dt>Recommended decision</dt><dd>{escalationReport?.recommended_action || report.escalation?.recommended_action || 'General Manager review requested; no specific decision was recorded.'}</dd>
              </dl>
              <div className="care-gm-workload">
                <strong>Agent workload this shift</strong>
                <span>{escalationReport?.agent_workload?.clients_served ?? agentReport?.shift_activity?.clients_served ?? '—'} clients served</span>
                <span>{escalationReport?.agent_workload?.resolved ?? agentReport?.shift_activity?.resolved_on_spot ?? '—'} resolved</span>
                <span>{escalationReport?.agent_workload?.escalated ?? agentReport?.shift_activity?.escalated_or_pending ?? '—'} escalated / pending</span>
              </div>
              <p className="care-gm-hierarchy"><strong>Hierarchy:</strong> {agentReport?.agent?.name || 'Agent not recorded'} → {shiftReport?.hierarchy?.team_leader?.[0]?.name || 'Team Leader not assigned'} → {shiftReport?.hierarchy?.department_manager?.[0]?.name || 'Department Manager not assigned'} → {shiftReport?.hierarchy?.general_manager?.[0]?.name || 'GM assignment not recorded'}</p>
            </article>
            <details className="care-gm-collapsible">
              <summary>Expand Full Client Call &amp; History Log ({clientReport?.call_history?.length || 0} calls)</summary>
              <article className="care-card care-gm-report-section">
                <h3>Client overview</h3>
                <dl className="care-gm-client-fields">
                  <dt>Client</dt><dd>{clientReport?.client?.name || 'Not recorded'}</dd>
                  <dt>Agent name</dt><dd>{clientReport?.client?.agent_name || 'Not recorded'}</dd>
                  <dt>Agent number</dt><dd>{clientReport?.client?.agent_number || 'Not recorded'}</dd>
                  <dt>Store number</dt><dd>{clientReport?.client?.store_number || 'Not recorded'}</dd>
                  <dt>Category</dt><dd>{labelize(clientReport?.client?.category)}</dd>
                  <dt>Business location</dt><dd>{clientReport?.client?.business_location || 'Not recorded'}</dd>
                </dl>
                <OkoaTable columns={[
                  { label: 'Date / time', render: (row) => dateLabel(row.date_time) },
                  { label: 'Reference', render: (row) => row.reference_number || `Call #${row.id}` },
                  { label: 'Direction', render: (row) => labelize(row.direction) },
                  { label: 'Handling agent', render: (row) => <>{row.handling_agent}<small className="care-gm-subtext">{row.staff_id || 'Staff ID not recorded'}</small></> },
                  { label: 'Issue / remarks', render: (row) => <>{row.category ? `${labelize(row.category)} · ` : ''}{row.remarks || 'No remarks recorded'}<small className="care-gm-subtext">{labelize(row.status)}{row.outcome ? ` · ${labelize(row.outcome)}` : ''}</small></> },
                ]} rows={clientReport?.call_history || []} empty="No additional client call history is available." />
              </article>
            </details>
            <details className="care-gm-collapsible">
              <summary>Expand Agent Work History for Shift</summary>
              <article className="care-card care-gm-report-section">
                <h3>Shift context &amp; roster</h3>
                <dl className="care-gm-client-fields">
                  <dt>Shift ID / date</dt><dd>{shiftReport?.shift?.shift_id || 'Not recorded'} · {shiftReport?.shift?.date || 'Not recorded'}</dd>
                  <dt>Call time</dt><dd>{shiftReport?.shift?.call_time ? dateLabel(shiftReport.shift.call_time) : 'Not recorded'}</dd>
                  <dt>Configured shift hours</dt><dd>{shiftReport?.shift?.configured_start_time && shiftReport?.shift?.configured_end_time ? `${shiftReport.shift.configured_start_time}–${shiftReport.shift.configured_end_time} (${shiftReport.shift.timezone})` : 'Not configured'}</dd>
                  {['general_manager', 'department_manager', 'team_leader'].map((role) => <React.Fragment key={role}><dt>{labelize(role)}</dt><dd>{(shiftReport?.on_duty_personnel?.[role] || []).map((person) => `${person.name} (${person.staff_id || 'No staff ID'})`).join(', ') || 'No assignment found for call time'}</dd></React.Fragment>)}
                </dl>
                <p className="care-gm-report-note">{shiftReport?.roster_note || 'Roster data is based on recorded assignments and shift activity.'}</p>
                <OkoaTable columns={[
                  { label: 'Customer Care agent', render: (row) => <>{row.name}<small className="care-gm-subtext">{row.staff_id || 'Staff ID not recorded'}</small></> },
                  { label: 'Calls in shift', key: 'calls_handled' },
                ]} rows={shiftReport?.customer_care_agents || []} empty="No other Customer Care agents have calls recorded in this shift." />
                <h3>Primary handling agent</h3>
                <p className="care-gm-agent-name">{agentReport?.agent?.name || 'Unknown staff'} · Staff ID: {agentReport?.agent?.staff_id || 'Not recorded'}{agentReport?.agent?.department ? ` · ${agentReport.agent.department}` : ''}</p>
                <div className="care-gm-activity-metrics">
                  <MetricCard label="Clients served" value={agentReport?.shift_activity?.clients_served ?? 0} />
                  <MetricCard label="Resolved on the spot" value={agentReport?.shift_activity?.resolved_on_spot ?? 0} />
                  <MetricCard label="Escalated or pending" value={agentReport?.shift_activity?.escalated_or_pending ?? 0} tone="is-alert" />
                </div>
                <OkoaTable columns={[
                  { label: 'Date / time', render: (row) => dateLabel(row.date_time) },
                  { label: 'Client', render: (row) => row.customer_name || 'Client' },
                  { label: 'Reference', render: (row) => row.reference_number || `Call #${row.id}` },
                  { label: 'Issue / remarks', render: (row) => `${labelize(row.category)} · ${row.remarks || 'No remarks recorded'}` },
                  { label: 'Outcome', render: (row) => `${labelize(row.status)}${row.outcome ? ` · ${labelize(row.outcome)}` : ''}` },
                ]} rows={agentReport?.call_log || []} empty="No other calls were recorded for this agent in the selected shift." />
              </article>
            </details>
            <details className="care-gm-collapsible">
              <summary>Expand Submitted Documents Checklist</summary>
              <article className="care-card care-gm-report-section">
                {!clientReport?.document_checklist?.available ? <p>No matching Sales &amp; Marketing document checklist is recorded for this client.</p> : <>
                  <p>Category: {labelize(clientReport.document_checklist.category)} · Registration status: <span className={`care-badge ${clientReport.document_checklist.registration_status === 'COMPLETE' ? 'status-resolved' : 'status-escalated'}`}>{labelize(clientReport.document_checklist.registration_status || 'Not recorded')}</span></p>
                  <ul className="care-gm-checklist">
                    {(clientReport.document_checklist.documents || []).map((document) => <li key={document.name}><span className={document.submitted ? '' : 'care-gm-missing-document'}>{document.submitted ? 'YES' : 'MISSING'}</span> · {document.name}</li>)}
                    {clientReport.document_checklist.submitted_files?.map((file) => <li key={file}>Uploaded file: {file}</li>)}
                  </ul>
                </>}
              </article>
            </details>
          </>}
        </section>
        </>
      )}
    </section>
  );
}

export function ShiftSchedulePage() {
  const shiftsResource = useResource('/api/shifts');
  const currentResource = useResource('/api/shifts/current');
  const shifts = Array.isArray(shiftsResource.data) ? shiftsResource.data : shiftsResource.data?.shifts || [];
  const currentCode = currentResource.data?.code || currentResource.data?.shift_code;
  return (
    <section className="care-page">
      <OkoaHeading title="Shift schedule" detail="Rotating customer care coverage in Africa/Nairobi time." />
      <OkoaNotice error={[shiftsResource.error, currentResource.error].filter(Boolean).join(' · ')} />
      <OkoaState loading={shiftsResource.loading || currentResource.loading} error={shiftsResource.error || currentResource.error} />
      {!shiftsResource.loading && !shiftsResource.error && <div className="care-okia-shifts">
        {(shifts.length ? shifts : [
          { code: 'A', start_weekday: 'Monday', start_time: '08:00', end_weekday: 'Wednesday', end_time: '12:00' },
          { code: 'B', start_weekday: 'Wednesday', start_time: '12:00', end_weekday: 'Friday', end_time: '16:00' },
          { code: 'C', start_weekday: 'Friday', start_time: '16:00', end_weekday: 'Monday', end_time: '08:00' },
        ]).map((shift) => (
          <article className={`care-card care-okia-shift ${currentCode === shift.code ? 'is-current' : ''}`} key={shift.code}>
            <span className="care-okia-shift-label">{currentCode === shift.code ? 'CURRENT SHIFT' : `SHIFT ${shift.code}`}</span>
            <h2>Shift {shift.code}</h2>
            <p><CalendarClock size={16} /> {weekdayLabel(shift.start_weekday)} {shift.start_time} – {weekdayLabel(shift.end_weekday)} {shift.end_time}</p>
            <small>Africa/Nairobi time · all calls are attributed using their start time</small>
          </article>
        ))}
      </div>}
      <Link className="care-secondary-button care-fit-content" to="/okia/shifts/coverage">View shift coverage <ArrowRight size={15} /></Link>
    </section>
  );
}

export function ShiftCoveragePage() {
  const initial = useMemo(dateRange, []);
  const [start, setStart] = useState(initial.start_date);
  const [end, setEnd] = useState(initial.end_date);
  const path = `/api/shifts/coverage?${dateQuery(start, end)}`;
  const resource = useResource(path, [start, end]);
  const rows = Array.isArray(resource.data) ? resource.data : resource.data?.shifts || resource.data?.by_shift || [];
  return (
    <section className="care-page">
      <OkoaHeading title="Shift coverage" detail="Compare call volumes, outcomes, and staffing by shift for a selected period." />
      <DateFilters start={start} end={end} onStart={setStart} onEnd={setEnd} />
      <OkoaState loading={resource.loading} error={resource.error} />
      {!resource.loading && !resource.error && <OkoaTable columns={[
        { label: 'Shift', render: (row) => `Shift ${row.shift_code || row.code || row.shift || '—'}` },
        { label: 'Calls', render: (row) => row.total_calls ?? row.calls ?? row.count ?? 0 },
        { label: 'Resolved', render: (row) => row.resolved ?? row.resolved_calls ?? 0 },
        { label: 'Escalated', render: (row) => row.escalated ?? row.escalated_calls ?? 0 },
        { label: 'Resolution rate', render: (row) => percentLabel(row.resolution_rate) },
        { label: 'Agents on duty', render: (row) => (row.agents || row.agents_on_duty || []).map((agent) => typeof agent === 'string' ? agent : agent.name).join(', ') || row.agent_count || '—' },
      ]} rows={rows} empty="No shift coverage is available for this date range." />}
    </section>
  );
}

export function ConcernCategoryListPage() {
  const resource = useResource('/api/concerns');
  const remote = Array.isArray(resource.data) ? resource.data : resource.data?.categories || [];
  const rows = remote.length ? remote : concernDefinitions.map(([code, label, direction]) => ({ code, label, direction, is_escalation_trigger: ['RECONCILIATION', 'LOAN_INCREASE_REQUEST'].includes(code) }));
  return (
    <section className="care-page">
      <OkoaHeading title="Concern categories" detail="Controlled concern and outbound-call reasons used to classify customer interactions." />
      <OkoaState loading={resource.loading} error={resource.error} />
      {!resource.loading && !resource.error && <OkoaTable columns={[
        { label: 'Code', render: (row) => <Link className="care-table-link" to={`/okia/concerns/${encodeURIComponent(row.code)}`}>{row.code}</Link> },
        { label: 'Category', render: (row) => row.label || labelize(row.code) },
        { label: 'Direction', render: (row) => labelize(row.direction) },
        { label: 'Default escalation', render: (row) => row.is_escalation_trigger ? <span className="care-badge status-escalated">Yes</span> : 'No' },
      ]} rows={rows} empty="No concern categories configured." />}
    </section>
  );
}

export function ConcernCategoryDetailPage() {
  const { code } = useParams();
  const decodedCode = decodeURIComponent(code || '');
  const resource = useResource('/api/concerns');
  const items = Array.isArray(resource.data) ? resource.data : resource.data?.categories || [];
  const item = items.find((row) => row.code === decodedCode)
    || (!resource.error && concernDefinitions.map(([key, label, direction]) => ({ code: key, label, direction })).find((row) => row.code === decodedCode));
  return (
    <section className="care-page">
      <Link className="care-back-link" to="/okia/concerns"><ArrowLeft size={16} /> Concern categories</Link>
      <OkoaHeading title={item?.label || labelize(decodedCode)} detail="Concern category reference." />
      <OkoaState loading={resource.loading} error={resource.error} />
      {!resource.loading && !resource.error && item && <article className="care-card care-okia-detail">
        <dl><dt>Code</dt><dd>{item.code}</dd><dt>Direction</dt><dd>{labelize(item.direction)}</dd><dt>Escalation trigger</dt><dd>{item.is_escalation_trigger ? 'Yes' : 'No'}</dd><dt>Description</dt><dd>{item.description || item.label || '—'}</dd></dl>
      </article>}
      {!resource.loading && !resource.error && !item && <div className="care-card care-state">Concern category not found.</div>}
    </section>
  );
}

function ReportPage({ title, detail, endpoint, columns, dateRangeFilter = true, rowsSelector }) {
  const initial = useMemo(dateRange, []);
  const [start, setStart] = useState(initial.start_date);
  const [end, setEnd] = useState(initial.end_date);
  const params = dateRangeFilter ? `?${dateQuery(start, end)}` : '';
  const resource = useResource(`${endpoint}${params}`, dateRangeFilter ? [start, end] : []);
  const rows = rowsSelector
    ? rowsSelector(resource.data)
    : Array.isArray(resource.data)
      ? resource.data
      : resource.data?.items || resource.data?.results || resource.data?.rows || [];
  return (
    <section className="care-page">
      <OkoaHeading eyebrow="OKOA OPERATIONS · REPORTS" title={title} detail={detail} />
      {dateRangeFilter && <DateFilters start={start} end={end} onStart={setStart} onEnd={setEnd} />}
      <OkoaState loading={resource.loading} error={resource.error} />
      {!resource.loading && !resource.error && <OkoaTable columns={columns} rows={rows} empty="No report data for this date range." />}
    </section>
  );
}

export function GmResolutionReportPage() {
  return <ReportPage
    title="GM resolution report"
    detail="Resolution rate for calls by concern category and shift."
    endpoint="/api/reports/gm/resolution"
    rowsSelector={(data) => [
      ...(data?.by_concern || []).map((row) => ({ ...row, breakdown: 'Concern', key: row.concern_category })),
      ...(data?.by_shift || []).map((row) => ({ ...row, breakdown: 'Shift', key: row.shift })),
    ]}
    columns={[
      { label: 'Breakdown', render: (row) => row.breakdown },
      { label: 'Category / shift', render: (row) => row.breakdown === 'Shift' ? `Shift ${row.key || '—'}` : labelize(row.key) },
      { label: 'Total calls', render: (row) => row.total ?? 0 },
      { label: 'Resolved', render: (row) => row.resolved ?? 0 },
      { label: 'Resolution rate', render: (row) => percentLabel(row.total ? row.resolved / row.total : 0) },
    ]}
  />;
}

export function GmAttentionReportPage() {
  return <ReportPage
    title="GM attention report"
    detail="Open escalations prioritized by reason and how long they have been waiting."
    endpoint="/api/reports/gm/attention"
    dateRangeFilter={false}
    rowsSelector={(data) => data?.by_reason || []}
    columns={[
      { label: 'Reason', render: (row) => row.reason || labelize(row.escalation_reason) },
      { label: 'Open issues', render: (row) => row.count ?? 0 },
      { label: 'Oldest age', render: (row) => row.oldest_age_minutes != null ? `${Math.round(row.oldest_age_minutes)} min` : '—' },
    ]}
  />;
}

export function AgentShiftMatrixPage() {
  return <ReportPage title="Agent / shift matrix" detail="See who served which customers, on which shift, and when." endpoint="/api/reports/gm/agent-shift-matrix" columns={[
    { label: 'Agent', render: (row) => row.agent_name || row.staff_name || row.agent || '—' },
    { label: 'Shift', render: (row) => row.shift_code ? `Shift ${row.shift_code}` : row.shift || '—' },
    { label: 'Calls', render: (row) => row.call_count ?? row.total_calls ?? row.count ?? 0 },
    { label: 'First call', render: (row) => dateLabel(row.first_call_at) },
    { label: 'Last call', render: (row) => dateLabel(row.last_call_at) },
    { label: 'Customers served', render: (row) => (row.customers || []).map((customer) => typeof customer === 'string' ? customer : customer.name).join(', ') || '—' },
  ]} />;
}

export function ConcernVolumeReportPage() {
  return <ReportPage title="Concern volume" detail="Call volume grouped by Okoa Float concern category." endpoint="/api/reports/concerns" columns={[
    { label: 'Concern', render: (row) => labelize(row.concern_category || row.code || row.label) },
    { label: 'Direction', render: (row) => labelize(row.direction) },
    { label: 'Calls', render: (row) => row.total_calls ?? row.count ?? 0 },
    { label: 'Resolved', render: (row) => row.resolved ?? row.resolved_calls ?? 0 },
    { label: 'Escalated', render: (row) => row.escalated ?? row.escalated_calls ?? 0 },
  ]} />;
}

export function EscalationReportPage() {
  return <ReportPage title="Escalation report" detail="Escalation volume by reason and average time to resolution." endpoint="/api/reports/escalations" dateRangeFilter={false} columns={[
    { label: 'Reason', render: (row) => row.reason || labelize(row.escalation_reason) },
    { label: 'Department', render: (row) => row.department || row.call?.department || 'Customer Care' },
    { label: 'Assigned to', render: (row) => labelize(row.to_dept || row.escalated_to) },
    { label: 'Escalations', render: (row) => row.total_escalations ?? row.count ?? 0 },
    { label: 'Resolved', render: (row) => row.resolved ?? row.resolved_count ?? 0 },
    { label: 'Avg resolution time', render: (row) => row.average_resolution_seconds != null ? `${Math.round(row.average_resolution_seconds / 60)} min` : '—' },
  ]} />;
}

export function OkoaOperationsPage({ page }) {
  if (page === 'okia-overview') {
    return (
      <OkoaDashboardErrorBoundary>
        <OkoaOverviewPage />
      </OkoaDashboardErrorBoundary>
    );
  }
  if (page === 'okia-escalations') return <EscalationListPage />;
  if (page === 'okia-shifts') return <ShiftSchedulePage />;
  if (page === 'okia-shift-coverage') return <ShiftCoveragePage />;
  if (page === 'okia-concerns') return <ConcernCategoryListPage />;
  if (page === 'okia-gm-resolution') return <GmResolutionReportPage />;
  if (page === 'okia-gm-attention') return <GmAttentionReportPage />;
  if (page === 'okia-agent-shift-matrix') return <AgentShiftMatrixPage />;
  if (page === 'okia-concern-report') return <ConcernVolumeReportPage />;
  if (page === 'okia-escalation-report') return <EscalationReportPage />;
  return null;
}
