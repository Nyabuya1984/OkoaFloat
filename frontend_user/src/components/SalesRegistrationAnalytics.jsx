import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';
import './SalesRegistrationAnalytics.css';

const endpoint = '/api/sales/analytics/registrations';
const detailEndpoint = '/api/sales/analytics/registration-records';
const performanceEndpoint = '/api/sales/analytics/employee-performance';
const categoryLabels = { agent: 'M-Pesa Agent / Dealer', sub_agent: 'M-Pesa Sub-Agent' };
const emptyDetailFilters = {};
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = Array.from({ length: 12 }, (_, index) => ({
  value: String(index + 1),
  label: new Date(Date.UTC(2020, index, 1)).toLocaleString('en', { month: 'long', timeZone: 'UTC' }),
}));
const documentLabels = {
  business_permit: 'Business permit',
  individual_kra_pin: 'Individual KRA PIN',
  six_months_commission: 'Six months commission statement',
  subagent_agent_contract: 'Contract between Sub-Agent and Agent',
  owner_national_id: 'National ID of the owner',
  sign_contract: 'Signed contract',
  certificate_of_incorporation: 'Certificate of incorporation / registration',
  company_kra_pin: 'Company / applicable owner KRA PIN',
  owners_directors_national_ids: 'National IDs of owners / directors',
  cr12_directors: 'CR12 for directors',
};
const statusLabels = { complete: 'Complete', incomplete: 'Incomplete' };
const percentage = (value) => `${Number(value || 0).toFixed(1)}%`;
const selectedCategory = (value) => value === 'sub_agent' ? 'sub_agent' : value === 'agent' ? 'agent' : '';
const categoryLabel = (value) => categoryLabels[value] || value;

function periodRow(date, groupBy) {
  const [year, month, day] = date.split('-').map(Number);
  const utcDate = new Date(Date.UTC(year, month - 1, day));
  if (groupBy === 'weekday') {
    return {
      key: String(utcDate.getUTCDay()),
      label: WEEKDAYS[utcDate.getUTCDay()],
      filters: { day: String(utcDate.getUTCDay()) },
    };
  }
  if (groupBy === 'week') {
    const start = new Date(utcDate);
    start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + 6);
    const iso = (value) => value.toISOString().slice(0, 10);
    return {
      key: iso(start),
      label: `${iso(start)} – ${iso(end)}`,
      filters: { from: iso(start), to: iso(end) },
    };
  }
  if (groupBy === 'month') {
    return {
      key: String(month),
      label: MONTHS[month - 1].label,
      filters: { month: String(month) },
    };
  }
  return { key: date, label: date, filters: { visit_date: date } };
}

function groupVisitRows(rows, groupBy) {
  const grouped = new Map();
  rows.forEach((row) => {
    const period = periodRow(row.date, groupBy);
    const key = `${period.key}:${row.category}`;
    const current = grouped.get(key) || {
      ...period,
      category: row.category,
      category_label: row.category_label,
      date_sort: groupBy === 'weekday' ? Number(period.key)
        : groupBy === 'month' ? String(Number(period.key)).padStart(2, '0')
          : period.key,
      visited: 0,
      complete: 0,
      incomplete: 0,
      outstanding_followups: 0,
    };
    ['visited', 'complete', 'incomplete', 'outstanding_followups'].forEach((metric) => {
      current[metric] += Number(row[metric] || 0);
    });
    if (groupBy === 'weekday') {
      current.date_sort = Number(period.key);
    }
    grouped.set(key, current);
  });
  return [...grouped.values()].map((row) => ({
    ...row,
    total_registrations: row.complete + row.incomplete,
    completion_rate: row.complete + row.incomplete
      ? row.complete * 100 / (row.complete + row.incomplete)
      : 0,
  }));
}

function OutcomeBarList({ rows, onSelect, emptyText }) {
  const maximum = Math.max(1, ...rows.map((row) => row.visited));
  if (!rows.length) return <p className="registration-chart-empty">{emptyText}</p>;
  return <div className="registration-outcome-bars">
    {rows.map((row) => {
      const filters = { ...row.filters, category: row.category };
      const visited = Number(row.visited || 0);
      const completeWidth = visited ? Number(row.complete || 0) * 100 / visited : 0;
      const incompleteWidth = visited ? Number(row.incomplete || 0) * 100 / visited : 0;
      return <button type="button" className="registration-outcome-bar" key={`${row.key}-${row.category}`} onClick={() => onSelect(row, filters)}>
        <span className="registration-outcome-bar-label"><strong>{row.label}</strong><small>{row.category_label}</small></span>
        <span className="registration-outcome-bar-track" aria-label={`${row.visited} visited`}>
          <span className="registration-outcome-bar-total" style={{ width: `${visited * 100 / maximum}%` }}>
            <i className="is-complete" style={{ width: `${completeWidth}%` }} />
            <i className="is-incomplete" style={{ width: `${incompleteWidth}%` }} />
            <i className="is-other" style={{ width: `${Math.max(0, 100 - completeWidth - incompleteWidth)}%` }} />
          </span>
        </span>
        <span className="registration-outcome-bar-values">
          <b>{row.visited}</b><small>{row.complete} complete · {row.incomplete} incomplete</small>
        </span>
      </button>;
    })}
  </div>;
}

function DocumentComplianceList({ rows, onSelect }) {
  const maximum = Math.max(1, ...rows.map((row) => row.applicable));
  if (!rows.length) return <p className="registration-chart-empty">No document records match the selected filters.</p>;
  return <div className="registration-document-bars">
    {rows.slice(0, 10).map((row) => <div className="registration-document-bar" key={`${row.category}-${row.key}`}>
      <span className="registration-document-bar-label">{row.label}<small>{categoryLabel(row.category)}</small></span>
      <div className="registration-document-bar-track" aria-label={`${row.submitted} submitted, ${row.pending} pending`}>
        <button type="button" className="is-submitted" style={{ width: `${row.submitted * 100 / maximum}%` }}
          onClick={() => onSelect(row, 'document_submitted')} aria-label={`View ${row.submitted} submitted ${row.label} records`} />
        <button type="button" className="is-pending" style={{ width: `${row.pending * 100 / maximum}%` }}
          onClick={() => onSelect(row, 'document_pending')} aria-label={`View ${row.pending} pending ${row.label} records`} />
      </div>
      <span className="registration-document-bar-values">{row.submitted} / {row.applicable}</span>
    </div>)}
  </div>;
}

function queryString(values) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  return params.toString();
}

async function request(url) {
  const send = () => fetch(apiUrl(url), {
    headers: getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {},
  });
  let response = await send();
  if (response.status === 401 && await refreshAuthToken()) response = await send();
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || payload.error || 'Unable to load registration analytics.');
  return payload.data;
}

function Table({ children, className = '' }) {
  return <div className={`registration-analytics-table-wrap ${className}`}>
    <table className="registration-analytics-table">{children}</table>
  </div>;
}

function filterRows(rows, filters, columns) {
  return rows.filter((row) => columns.every(({ key, value }) => {
    const filter = filters[key];
    if (!filter) return true;
    return String(value ? value(row) : row[key] ?? '').toLowerCase().includes(filter.toLowerCase());
  }));
}

function MetricButton({ children, onClick, label }) {
  return <button type="button" className="registration-analytics-metric" onClick={onClick} aria-label={label}>
    {children}
  </button>;
}

function Paginator({ page, pages, onChange }) {
  if (pages < 2) return null;
  return <nav className="registration-analytics-pagination" aria-label="Analytics table pages">
    <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
    <span>Page {page} of {pages}</span>
    <button type="button" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button>
  </nav>;
}

function ClientDetailModal({ selection, baseFilters, onClose }) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState({ rows: [], page: 1, per_page: 25, total_rows: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const detailFilters = selection.filters || emptyDetailFilters;
  const mergedFilters = useMemo(() => {
    const defaults = selection.completionDateBasis ? {} : baseFilters;
    const merged = { ...defaults, ...detailFilters };
    if (!selection.completionDateBasis && baseFilters.from && detailFilters.from) {
      merged.from = baseFilters.from > detailFilters.from ? baseFilters.from : detailFilters.from;
    }
    if (!selection.completionDateBasis && baseFilters.to && detailFilters.to) {
      merged.to = baseFilters.to < detailFilters.to ? baseFilters.to : detailFilters.to;
    }
    return merged;
  }, [baseFilters, detailFilters, selection.completionDateBasis]);
  const query = useMemo(() => queryString({
    ...mergedFilters,
    search: search || baseFilters.search,
    page,
    per_page: 25,
  }), [baseFilters.search, mergedFilters, page, search]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    request(`${detailEndpoint}?${query}`)
      .then((data) => active && setResult(data || { rows: [], page: 1, per_page: 25, total_rows: 0 }))
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [query]);

  useEffect(() => {
    const closeOnEscape = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const pages = Math.max(1, Math.ceil(result.total_rows / result.per_page));
  const activeFilters = Object.entries(mergedFilters)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key.replaceAll('_', ' ')}: ${categoryLabels[value] || value}`);

  return <div className="registration-detail-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="registration-detail-modal" role="dialog" aria-modal="true" aria-labelledby="registration-detail-title">
      <header className="registration-detail-header">
        <div><p className="leave-kicker">REGISTRATION RECORDS</p><h2 id="registration-detail-title">{selection.title}</h2><p>{loading ? 'Loading records…' : `${result.total_rows} matching records`}</p></div>
        <button type="button" className="registration-detail-close" onClick={onClose} aria-label="Close client records">Close</button>
      </header>
      {selection.calculation && <div className="registration-detail-calculation">
        <strong>Calculation</strong>
        <span>{selection.calculation}</span>
        {selection.numerator !== undefined && <span>Numerator: {selection.numerator} · Denominator: {selection.denominator}</span>}
      </div>}
      <div className="registration-detail-filters">
        <label>Search matching clients<input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Name, number, location, or officer" /></label>
        {activeFilters.length > 0 && <p><strong>Active filters:</strong> {activeFilters.join(' · ')}</p>}
      </div>
      {error && <div role="alert" className="registration-analytics-error">{error}</div>}
      {loading ? <div className="registration-analytics-state" role="status">Loading client records…</div>
        : result.rows.length === 0 ? <div className="registration-analytics-state">No client records match this selection.</div>
          : <div className="registration-detail-records">
            {result.rows.map((record) => <article className="registration-detail-record" key={record.id}>
              <header><div><h3>{record.client_name || record.agent_name || 'Client'}</h3><span>{record.category_label || categoryLabel(record.customer_type) || record.customer_type}</span></div><span className={`registration-status-chip is-${String(record.registration_status || 'not_started').toLowerCase()}`}>{record.registration_status === 'COMPLETE' ? 'Complete' : record.registration_status === 'INCOMPLETE' ? 'Incomplete' : 'Not started'}</span></header>
              <dl>
                <div><dt>Agent number</dt><dd>{record.agent_number || 'Not recorded'}</dd></div>
                <div><dt>Store number</dt><dd>{record.store_number || 'Not recorded'}</dd></div>
                <div><dt>Business location</dt><dd>{record.business_location || 'Not recorded'}</dd></div>
                <div><dt>Field officer</dt><dd>{record.employee_name || 'Not recorded'}</dd></div>
                <div><dt>Visit date</dt><dd>{record.date_visited || 'Not recorded'}</dd></div>
                <div><dt>Registration date</dt><dd>{record.registration_date || 'Not recorded'}</dd></div>
                <div><dt>Completion date</dt><dd>{record.completion_date || 'Not recorded'}</dd></div>
                {record.witness_name && <div><dt>Contract witness</dt><dd>{record.witness_name}</dd></div>}
                {record.witness_id_number && <div><dt>Witness ID</dt><dd>{record.witness_id_number}</dd></div>}
                {record.witness_phone && <div><dt>Witness phone</dt><dd>{record.witness_phone}</dd></div>}
                {record.notes && <div className="registration-detail-notes"><dt>Remarks</dt><dd>{record.notes}</dd></div>}
              </dl>
              {record.documents?.length > 0 && <div className="registration-detail-documents"><strong>Required documents</strong><ul>
                {record.documents.map((document) => <li key={document.key} className={document.submitted ? 'is-submitted' : 'is-pending'}>
                  <span>{document.label || documentLabels[document.key] || document.key}</span><b>{document.submitted ? 'Submitted' : document.applicable === false ? 'Not applicable' : 'Pending'}</b>
                </li>)}
              </ul></div>}
              {record.missing_requirements?.length > 0 && <p className="registration-detail-missing"><strong>Outstanding requirements:</strong> {record.missing_requirements.map((item) => documentLabels[item] || String(item).replaceAll('_', ' ')).join(', ')}</p>}
            </article>)}
          </div>}
      {!loading && result.total_rows > 0 && <Paginator page={page} pages={pages} onChange={setPage} />}
    </section>
  </div>;
}

export default function SalesRegistrationAnalytics({
  filters = {},
  refreshKey = 0,
  canViewEmployeePerformance = false,
  showRepresentativeFilter = false,
}) {
  const [analytics, setAnalytics] = useState(null);
  const [employeePerformance, setEmployeePerformance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [performanceLoading, setPerformanceLoading] = useState(false);
  const [error, setError] = useState('');
  const [performanceError, setPerformanceError] = useState('');
  const [performanceSearch, setPerformanceSearch] = useState('');
  const [performanceEmployeeFilter, setPerformanceEmployeeFilter] = useState('');
  const [selection, setSelection] = useState(null);
  const [dailyPage, setDailyPage] = useState(1);
  const [dailySort, setDailySort] = useState({ key: 'label', direction: 'asc' });
  const [activityGroup, setActivityGroup] = useState('date');
  const [periodView, setPeriodView] = useState('month');
  const [expandedMonths, setExpandedMonths] = useState({});
  const [columnFilters, setColumnFilters] = useState({});

  const baseFilters = useMemo(() => ({
    from: filters.from,
    to: filters.to,
    category: selectedCategory(filters.category),
    outcome: filters.status,
    registration: filters.registration,
    client_type: filters.clientType,
    referral: filters.referral,
    appointment: filters.appointment,
    search: filters.search,
    day: filters.day,
    month: filters.month,
    year: filters.year,
    location: filters.location,
    employee_id: performanceEmployeeFilter || filters.employee_id,
  }), [filters, performanceEmployeeFilter]);
  const aggregateQuery = useMemo(() => queryString(baseFilters), [baseFilters]);
  const performanceQuery = useMemo(() => queryString({
    from: filters.from,
    to: filters.to,
    category: selectedCategory(filters.category),
  }), [filters.category, filters.from, filters.to]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    request(`${endpoint}?${aggregateQuery}`)
      .then((data) => active && setAnalytics(data))
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [aggregateQuery, refreshKey]);

  useEffect(() => {
    if (!canViewEmployeePerformance) {
      setEmployeePerformance(null);
      setPerformanceError('');
      return undefined;
    }
    let active = true;
    setPerformanceLoading(true);
    setPerformanceError('');
    request(`${performanceEndpoint}?${performanceQuery}`)
      .then((data) => active && setEmployeePerformance(data))
      .catch((requestError) => active && setPerformanceError(requestError.message))
      .finally(() => active && setPerformanceLoading(false));
    return () => { active = false; };
  }, [canViewEmployeePerformance, performanceQuery, refreshKey]);

  useEffect(() => {
    if (!selection) return undefined;
    const prior = document.activeElement;
    document.querySelector('.registration-detail-close')?.focus();
    return () => prior?.focus?.();
  }, [selection]);

  const openDetails = (title, filterValues = {}, calculation = '', numerator, denominator) => setSelection({
    title,
    filters: filterValues,
    calculation,
    numerator,
    denominator,
  });
  const openMetric = (title, metric, filtersForMetric = {}) => openDetails(title, { metric, ...filtersForMetric });

  const dailyRowsAll = (analytics?.daily?.rows || []).map((row) => ({
    ...row,
    category_label: categoryLabel(row.category),
    total_registrations: row.total_registrations ?? row.complete + row.incomplete,
  }));
  const categoryRows = (analytics?.categories?.rows || []).map((row) => ({
    ...row,
    category_label: row.category_label || row.label || categoryLabel(row.category),
  }));
  const documentRows = (analytics?.documents || []).filter((row) => row.category !== 'all');
  const periodSummary = analytics?.daily?.totals || {};
  const statusRows = (analytics?.statuses?.rows || []).map((row) => ({
    ...row,
    label: statusLabels[row.status] || row.status,
    percent_of_registrations: periodSummary.total_registrations
      ? Number(row.count || 0) * 100 / periodSummary.total_registrations
      : 0,
  })).filter((row) => ['complete', 'incomplete'].includes(row.status));
  const periodRows = periodView === 'month' ? analytics?.monthly?.rows || [] : analytics?.yearly?.rows || [];
  const columnFilterRow = (table, columns) => <tr className="registration-analytics-filter-row">
    {columns.map(({ key, label, options }) => <th key={key}>
      {options ? <select
        aria-label={`Filter ${label} in ${table} table`}
        value={columnFilters[table]?.[key] || ''}
        onChange={(event) => setColumnFilters((current) => ({
          ...current,
          [table]: { ...current[table], [key]: event.target.value },
        }))}
      >
        <option value="">All {label.toLowerCase()}</option>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select> : <input
        type={columns.find((column) => column.key === key)?.type || 'search'}
        aria-label={`Filter ${label} in ${table} table`}
        placeholder={`Filter ${label.toLowerCase()}`}
        value={columnFilters[table]?.[key] || ''}
        onChange={(event) => setColumnFilters((current) => ({
          ...current,
          [table]: { ...current[table], [key]: event.target.value },
        }))}
      />}
    </th>)}
  </tr>;
  const dailyColumns = [
    {
      key: 'label',
      label: activityGroup === 'date' ? 'Date' : activityGroup === 'weekday' ? 'Day of week' : activityGroup === 'week' ? 'Week' : 'Month of year',
      type: activityGroup === 'date' ? 'date' : undefined,
      options: activityGroup === 'weekday' ? WEEKDAYS.map((label, index) => ({ value: label, label }))
        : activityGroup === 'month' ? MONTHS.map((month) => ({ value: month.label, label: month.label }))
          : activityGroup === 'week' ? [...new Map(dailyRowsAll.map((row) => {
            const period = periodRow(row.date, 'week');
            return [period.key, { value: period.label, label: period.label }];
          })).values()]
            : undefined,
      value: (row) => row.label,
    },
    { key: 'category', label: 'Agent category', options: [
      { value: 'agent', label: 'Agent / Dealer' }, { value: 'sub_agent', label: 'Sub-Agent' },
    ] },
    { key: 'visited', label: 'Clients visited' }, { key: 'complete', label: 'Complete registrations' },
    { key: 'incomplete', label: 'Incomplete registrations' }, { key: 'completion_rate', label: 'Completion rate' },
    { key: 'outstanding_followups', label: 'Follow-ups' },
  ];
  const activityRows = groupVisitRows(dailyRowsAll, activityGroup);
  const dailyRowsFiltered = filterRows(activityRows, columnFilters.daily || {}, dailyColumns);
  const categoryColumns = [
    { key: 'category', label: 'Registration category', options: [
      { value: 'agent', label: 'Agent / Dealer' }, { value: 'sub_agent', label: 'Sub-Agent' },
    ] },
    { key: 'visited', label: 'Clients visited' }, { key: 'complete', label: 'Completed' },
    { key: 'incomplete', label: 'Incomplete' }, { key: 'completion_rate', label: 'Completion rate' },
    { key: 'outstanding_followups', label: 'Outstanding follow-ups' },
  ];
  const categoryRowsFiltered = filterRows(categoryRows, columnFilters.category || {}, categoryColumns);
  const periodRowsForTable = periodRows.map((row) => ({
    ...row,
    period_label: periodView === 'month' ? row.month_label || row.month : String(row.year),
  }));
  const periodColumns = [
    {
      key: 'period_label',
      label: periodView === 'month' ? 'Month and year' : 'Year',
      options: [...new Set(periodRowsForTable.map((row) => row.period_label))].map((label) => ({ value: label, label })),
    },
    { key: 'visited', label: 'Clients visited' }, { key: 'complete', label: 'Completed' },
    { key: 'incomplete', label: 'Incomplete' }, { key: 'completion_rate', label: 'Completion rate' },
    { key: 'outstanding_followups', label: 'Outstanding follow-ups' },
  ];
  const periodRowsFiltered = filterRows(periodRowsForTable, columnFilters.period || {}, periodColumns);
  const documentColumns = [
    { key: 'label', label: 'Document' },
    { key: 'category', label: 'Registration category', options: [
      { value: 'agent', label: 'Agent / Dealer' }, { value: 'sub_agent', label: 'Sub-Agent' },
    ] },
    { key: 'applicable', label: 'Applicable registrations' }, { key: 'submitted', label: 'Documents submitted' },
    { key: 'pending', label: 'Documents pending' }, { key: 'submission_rate', label: 'Submission rate' },
    { key: 'priority', label: 'Follow-up priority' },
  ];
  const documentRowsFiltered = filterRows(documentRows, columnFilters.documents || {}, documentColumns);
  const statusColumns = [
    { key: 'label', label: 'Registration status', options: [
      { value: 'Complete', label: 'Complete' }, { value: 'Incomplete', label: 'Incomplete' },
    ] },
    { key: 'count', label: 'Number of registrations' },
    { key: 'percent_of_registrations', label: 'Percentage of registrations' },
    { key: 'missing_requirements', label: 'Outstanding requirements', value: (row) => row.missing_requirements.map((item) => typeof item === 'string' ? item : documentLabels[item.key] || item.key).join(', ') },
    { key: 'recommended_action', label: 'Recommended action' },
  ];
  const statusRowsFiltered = filterRows(statusRows, columnFilters.status || {}, statusColumns);
  const employeeRows = (employeePerformance?.rows || []).filter((row) => (
    (!(performanceEmployeeFilter || filters.employee_id)
      || String(row.employee_id) === (performanceEmployeeFilter || String(filters.employee_id)))
    && (!performanceSearch
      || row.employee_name.toLowerCase().includes(performanceSearch.trim().toLowerCase()))
  ));
  const sortedDaily = useMemo(() => {
    const rows = [...dailyRowsFiltered];
    rows.sort((left, right) => {
      const a = dailySort.key === 'label' ? left.date_sort : left[dailySort.key];
      const b = dailySort.key === 'label' ? right.date_sort : right[dailySort.key];
      const compare = typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b));
      return dailySort.direction === 'asc' ? compare : -compare;
    });
    return rows;
  }, [dailyRowsFiltered, dailySort]);
  const dailyPageCount = Math.max(1, Math.ceil(sortedDaily.length / 10));
  const dailyRows = sortedDaily.slice((dailyPage - 1) * 10, dailyPage * 10);
  useEffect(() => setDailyPage(1), [activityGroup, columnFilters.daily]);
  const activityChart = sortedDaily.slice(0, 10);
  const categoryChart = categoryRowsFiltered.map((row) => ({
    ...row,
    key: row.category,
    label: row.category_label,
    filters: {},
  }));
  const documentChart = documentRowsFiltered.slice(0, 10);
  const sortDaily = (key) => setDailySort((current) => ({
    key,
    direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
  }));
  const metricCell = (value, title, metric, rowFilters) => <MetricButton
    label={`View ${value} ${title} records`}
    onClick={() => openMetric(title, metric, rowFilters)}
  >{value}</MetricButton>;
  const rateCell = (value, title, metric, rowFilters, numerator, denominator, formula) => <MetricButton
    label={`View ${title} records. ${formula}`}
    onClick={() => openDetails(title, { metric, ...rowFilters }, formula, numerator, denominator)}
  >{percentage(value)}</MetricButton>;

  if (loading && !analytics) return <div className="registration-analytics-state" role="status">Loading registration analytics…</div>;
  if (error && !analytics) return <div className="registration-analytics-error" role="alert">{error}</div>;
  if (!analytics) return null;

  return <section className="sales-registration-analytics" aria-label="M-Pesa registration analytics">
    {error && <div className="registration-analytics-error" role="alert">{error}</div>}
    <div className="registration-analytics-summary">
      {[
        { label: 'Clients visited', value: periodSummary.visited, metric: 'visited', detail: 'Eligible client visits in this period' },
        { label: 'Complete registrations', value: periodSummary.complete, metric: 'complete', detail: 'All required items submitted' },
        { label: 'Incomplete registrations', value: periodSummary.incomplete, metric: 'incomplete', detail: 'Registration requirements outstanding' },
        { label: 'Registration completion', value: percentage(periodSummary.completion_rate), metric: 'complete', detail: `${periodSummary.total_registrations || 0} complete or incomplete registrations` },
      ].map((item) => <button type="button" className="registration-analytics-summary-card" key={item.label}
        onClick={() => openMetric(item.label, item.metric)}>
        <span>{item.label}</span><strong>{item.value ?? 0}</strong><small>{item.detail}</small>
      </button>)}
    </div>
    <section className="registration-analytics-section registration-funnel" aria-label="Registration funnel">
      <header><div><p className="leave-kicker">REGISTRATION FUNNEL</p><h3>From visit to completed registration</h3></div><span>{analytics.funnel?.visited ?? periodSummary.visited ?? 0} eligible visits</span></header>
      <div className="registration-funnel-stages">
        {[
          ['visited', 'Visited', analytics.funnel?.visited ?? periodSummary.visited],
          ['started', 'Registration started', analytics.funnel?.started ?? periodSummary.started],
          ['complete', 'Completed', analytics.funnel?.complete ?? periodSummary.complete],
        ].map(([metric, label, value]) => <button type="button" className={`registration-funnel-stage is-${metric}`} key={metric} onClick={() => openMetric(label, metric)}>
          <span>{label}</span><strong>{value ?? 0}</strong>
        </button>)}
        <button type="button" className="registration-funnel-stage is-incomplete" onClick={() => openMetric('Incomplete registrations', 'incomplete')}>
          <span>Incomplete</span><strong>{analytics.funnel?.incomplete ?? periodSummary.incomplete ?? 0}</strong>
        </button>
        <button type="button" className="registration-funnel-stage is-not-started" onClick={() => openMetric('Visits not converted to registration', 'unconverted')}>
          <span>Not started</span><strong>{analytics.funnel?.not_started ?? periodSummary.not_started ?? 0}</strong>
        </button>
      </div>
    </section>
    <p className="registration-analytics-intro">Choose a date range and Agent category above. Table header filters narrow each table independently; summary cards show totals for the selected period and category.</p>

    {canViewEmployeePerformance && <section className="registration-analytics-section employee-performance-section">
      <header>
        <div>
          <p className="leave-kicker">TEAM PERFORMANCE</p>
          <h3>Completed registrations by employee</h3>
          <p>Ranked against peers by registrations completed within the selected completion-date period.</p>
        </div>
        <label className="registration-analytics-period">Search employees
          <input aria-label="Search performance employees" value={performanceSearch}
            onChange={(event) => setPerformanceSearch(event.target.value)} placeholder="Employee name" />
        </label>
        {showRepresentativeFilter && <label className="registration-analytics-period">Filter representative
          <select aria-label="Filter performance by representative"
            value={performanceEmployeeFilter}
            onChange={(event) => setPerformanceEmployeeFilter(event.target.value)}>
            <option value="">All representatives</option>
            {(employeePerformance?.rows || []).map((row) => <option key={row.employee_id} value={row.employee_id}>{row.employee_name}</option>)}
          </select>
        </label>}
      </header>
      <div className="employee-performance-summary">
        <span><strong>{employeePerformance?.total_complete ?? 0}</strong> completed</span>
        <span><strong>{employeePerformance?.agent_complete ?? 0}</strong> Agent / Dealer</span>
        <span><strong>{employeePerformance?.sub_agent_complete ?? 0}</strong> Sub-Agent</span>
        <span><strong>{employeePerformance?.team_average ?? 0}</strong> peer average</span>
      </div>
      {performanceError && <div className="registration-analytics-error" role="alert">{performanceError}</div>}
      {performanceLoading ? <div className="registration-analytics-state" role="status">Loading employee performance…</div>
        : employeeRows.length === 0 ? <div className="registration-analytics-state">
          {employeePerformance?.employee_count ? 'No employees match this search.' : 'No Sales & Marketing employees are in this reporting scope.'}
        </div> : <Table className="employee-performance-table">
          <thead><tr><th>Rank</th><th>Employee</th><th>Agent / Dealer</th><th>Sub-Agent</th><th>Complete</th><th>Peer comparison</th><th>Performance</th></tr></thead>
          <tbody>{employeeRows.map((row) => {
            const status = row.performance === 'above_average'
              ? 'Above peer average'
              : row.performance === 'needs_support' ? 'Needs support' : 'At peer average';
            const category = selectedCategory(filters.category);
            return <tr key={row.employee_id} className={`employee-performance-row is-${row.performance}`}>
              <td><span className="employee-performance-rank">#{row.rank}</span></td>
              <th>{row.employee_name}</th>
              <td>{row.agent_complete}</td>
              <td>{row.sub_agent_complete}</td>
              <td><MetricButton
                label={`View ${row.complete} completed registrations for ${row.employee_name}`}
                onClick={() => setSelection({
                  title: `${row.employee_name} · completed registrations`,
                  filters: {
                    metric: 'complete',
                    employee_id: row.employee_id,
                    category,
                    completion_from: filters.from,
                    completion_to: filters.to,
                  },
                  completionDateBasis: true,
                })}
              >{row.complete}</MetricButton></td>
              <td>{row.complete} of {employeePerformance?.team_average ?? 0} average</td>
              <td><span className={`employee-performance-badge is-${row.performance}`}>{status}</span></td>
            </tr>;
          })}</tbody>
        </Table>}
      <p className="registration-analytics-table-hint">Only complete registrations with a recorded completion date are counted. Employees with zero completions remain visible; ties share the same rank.</p>
    </section>}

    <section className="registration-analytics-section">
      <header>
        <div><p className="leave-kicker">VISIT PERIOD BREAKDOWN</p><h3>Visited clients and registration outcomes</h3><p>Use the period selector to compare by date, weekday, week, or month.</p></div>
        <label className="registration-analytics-period">Group by<select aria-label="Group visits by period" value={activityGroup} onChange={(event) => { setActivityGroup(event.target.value); setDailySort({ key: 'label', direction: 'asc' }); setColumnFilters((current) => ({ ...current, daily: {} })); }}>
          <option value="date">Date</option><option value="weekday">Day of week</option><option value="week">Week</option><option value="month">Month of year</option>
        </select></label>
      </header>
      <div className="registration-analytics-table-hint">Filter date with the calendar, or choose a weekday, week, or month from the first column. Select a column title to sort.</div>
      <Table>
        <thead>
          <tr>{[
            ['label', dailyColumns[0].label], ['category_label', 'Agent category'],
            ['visited', 'Clients visited'], ['complete', 'Complete registrations'],
            ['incomplete', 'Incomplete registrations'], ['completion_rate', 'Completion rate'],
            ['outstanding_followups', 'Follow-ups'],
          ].map(([key, label]) => <th key={key}><button type="button" onClick={() => sortDaily(key)}>{label}{dailySort.key === key ? dailySort.direction === 'asc' ? ' ↑' : ' ↓' : ''}</button></th>)}</tr>
          {columnFilterRow('daily', dailyColumns)}
        </thead>
        <tbody>
          {dailyRows.length === 0 ? <tr><td colSpan="7">No visit records match this period and its filters.</td></tr> : dailyRows.map((row) => {
            const rowFilters = { ...row.filters, category: row.category };
            return <tr key={`${row.key}-${row.category}`} onClick={() => openMetric(`${row.label} · ${row.category_label}`, 'visited', rowFilters)} tabIndex="0" onKeyDown={(event) => event.key === 'Enter' && openMetric(`${row.label} · ${row.category_label}`, 'visited', rowFilters)}>
              <td>{row.label}</td><td>{row.category_label}</td>
              <td onClick={(event) => event.stopPropagation()}>{metricCell(row.visited, 'visited clients', 'visited', rowFilters)}</td>
              <td onClick={(event) => event.stopPropagation()}>{metricCell(row.complete, 'completed registrations', 'complete', rowFilters)}</td>
              <td onClick={(event) => event.stopPropagation()}>{metricCell(row.incomplete, 'incomplete registrations', 'incomplete', rowFilters)}</td>
              <td onClick={(event) => event.stopPropagation()}>{rateCell(row.completion_rate, 'Registration completion', 'complete', rowFilters, row.complete, row.total_registrations, `${row.complete} complete ÷ ${row.total_registrations} registrations × 100`)}</td>
              <td onClick={(event) => event.stopPropagation()}>{metricCell(row.outstanding_followups, 'outstanding follow-ups', 'outstanding_followup', rowFilters)}</td>
            </tr>;
          })}
        </tbody>
      </Table>
      <Paginator page={dailyPage} pages={dailyPageCount} onChange={setDailyPage} />
    </section>

    <section className="registration-analytics-section">
      <header><div><p className="leave-kicker">CATEGORY COMPARISON</p><h3>Agent / Dealer and Sub-Agent outcomes</h3></div><span>{categoryRowsFiltered.length} categories shown</span></header>
      <Table>
        <thead>
          <tr><th>Registration category</th><th>Clients visited</th><th>Complete registrations</th><th>Incomplete registrations</th><th>Completion rate</th><th>Outstanding follow-ups</th></tr>
          {columnFilterRow('category', categoryColumns)}
        </thead>
        <tbody>{categoryRowsFiltered.map((row) => {
          const rowFilters = { category: row.category };
          return <tr key={row.category}><th>{row.category_label}</th>
            <td>{metricCell(row.visited, 'visited clients', 'visited', rowFilters)}</td>
            <td>{metricCell(row.complete, 'completed registrations', 'complete', rowFilters)}</td>
            <td>{metricCell(row.incomplete, 'incomplete registrations', 'incomplete', rowFilters)}</td>
            <td>{rateCell(row.completion_rate, `${row.category_label} completion`, 'complete', rowFilters, row.complete, row.complete + row.incomplete, `${row.complete} ÷ ${row.complete + row.incomplete} registrations × 100`)}</td>
            <td>{metricCell(row.outstanding_followups, 'outstanding follow-ups', 'outstanding_followup', rowFilters)}</td>
          </tr>;
        })}{categoryRowsFiltered.length === 0 && <tr><td colSpan="6">No category rows match these filters.</td></tr>}</tbody>
      </Table>
    </section>

    <section className="registration-analytics-section">
      <header><div><p className="leave-kicker">PERIOD COMPARISON</p><h3>{periodView === 'month' ? 'Monthly' : 'Yearly'} registration performance</h3></div>
        <label className="registration-analytics-period">Group by<select value={periodView} onChange={(event) => setPeriodView(event.target.value)}><option value="month">Month</option><option value="year">Year</option></select></label>
      </header>
      <Table>
        <thead>
          <tr><th>{periodView === 'month' ? 'Month and year' : 'Year'}</th><th>Clients visited</th><th>Complete registrations</th><th>Incomplete registrations</th><th>Completion rate</th><th>Outstanding follow-ups</th></tr>
          {columnFilterRow('period', periodColumns)}
        </thead>
        <tbody>{periodRowsFiltered.length === 0 ? <tr><td colSpan="6">No period records match these filters.</td></tr> : periodRowsFiltered.map((row) => {
          const key = periodView === 'month' ? row.month : String(row.year);
          const periodYear = periodView === 'month' ? row.month.slice(0, 4) : String(row.year);
          const periodLabel = periodView === 'month' ? row.month_label : String(row.year);
          const rangeFilters = periodView === 'month' ? { month: Number(row.month.slice(5, 7)), year: periodYear } : { year: periodYear };
          return <React.Fragment key={key}>
            <tr><th><button type="button" className="registration-analytics-expand" onClick={() => setExpandedMonths((current) => ({ ...current, [key]: !current[key] }))} aria-expanded={Boolean(expandedMonths[key])}>{periodView === 'month' ? expandedMonths[key] ? '−' : '+' : ''} {periodLabel}</button></th>
              <td>{metricCell(row.visited, 'visited clients', 'visited', rangeFilters)}
              </td>
              <td>{metricCell(row.complete, 'completed registrations', 'complete', rangeFilters)}</td><td>{metricCell(row.incomplete, 'incomplete registrations', 'incomplete', rangeFilters)}</td>
              <td>{rateCell(row.completion_rate, `${periodLabel} completion`, 'complete', rangeFilters, row.complete, row.complete + row.incomplete, `${row.complete} ÷ ${row.complete + row.incomplete} registrations × 100`)}</td>
              <td>{metricCell(row.outstanding_followups, 'outstanding follow-ups', 'outstanding_followup', rangeFilters)}</td>
            </tr>
            {periodView === 'month' && expandedMonths[key] && dailyRowsAll.filter((daily) => daily.date.startsWith(key)).map((daily) => <tr className="registration-analytics-expanded-row" key={`${key}-${daily.date}-${daily.category}`}>
              <td>{daily.date} · {daily.weekday} · {daily.category_label}</td><td>{metricCell(daily.visited, 'visited clients', 'visited', { visit_date: daily.date, category: daily.category })}</td>
              <td>{metricCell(daily.complete, 'completed registrations', 'complete', { visit_date: daily.date, category: daily.category })}</td>
              <td>{metricCell(daily.incomplete, 'incomplete registrations', 'incomplete', { visit_date: daily.date, category: daily.category })}</td>
              <td>{percentage(daily.completion_rate)}</td><td>Visit and registration dates are shown in client details.</td>
            </tr>)}
          </React.Fragment>;
        })}
        </tbody>
      </Table>
    </section>

    <section className="registration-analytics-section">
      <header><div><p className="leave-kicker">DOCUMENT COMPLIANCE</p><h3>Document submissions and outstanding requirements</h3></div></header>
      <Table>
        <thead>
          <tr><th>Document</th><th>Registration category</th><th>Applicable registrations</th><th>Documents submitted</th><th>Documents pending</th><th>Submission rate</th><th>Follow-up priority</th></tr>
          {columnFilterRow('documents', documentColumns)}
        </thead>
        <tbody>{documentRowsFiltered.map((row) => <tr key={`${row.category}-${row.key}`}>
          <th><MetricButton onClick={() => openDetails(row.label, { metric: 'started', document: row.key, category: row.category })} label={`View applicable registrations for ${row.label}`}>{row.label || documentLabels[row.key] || row.key}</MetricButton></th>
          <td>{categoryLabel(row.category)}</td>
          <td>{metricCell(row.applicable, 'applicable registrations', 'started', { category: row.category })}</td>
          <td>{metricCell(row.submitted, 'registrations with document submitted', 'document_submitted', { category: row.category, document: row.key })}</td>
          <td>{metricCell(row.pending, 'registrations missing document', 'document_pending', { category: row.category, document: row.key })}</td>
          <td>{rateCell(row.submission_rate ?? row.rate, `${row.label} submission rate`, 'document_submitted', { category: row.category, document: row.key }, row.submitted, row.applicable, `${row.submitted} submitted ÷ ${row.applicable} applicable registrations × 100`)}</td>
          <td><span className={`registration-priority is-${row.priority}`}>{row.priority}</span></td>
        </tr>)}
        {documentRowsFiltered.length === 0 && <tr><td colSpan="7">No document requirements match these filters.</td></tr>}
        </tbody>
      </Table>
    </section>

    <section className="registration-analytics-section">
      <header><div><p className="leave-kicker">REGISTRATION FOLLOW-UP</p><h3>Complete and incomplete registrations</h3></div><span>Percentages are of registrations, not visits</span></header>
      <Table>
        <thead>
          <tr><th>Registration status</th><th>Number of registrations</th><th>Percentage of registrations</th><th>Outstanding requirements</th><th>Recommended action</th></tr>
          {columnFilterRow('status', statusColumns)}
        </thead>
        <tbody>{statusRowsFiltered.map((row) => <tr key={row.status}>
          <th><MetricButton onClick={() => openMetric(row.label, row.status)} label={`View ${row.count} ${row.label} clients`}>{row.label}</MetricButton></th>
          <td>{metricCell(row.count, row.label, row.status)}</td>
          <td>{rateCell(row.percent_of_registrations, `${row.label} percentage of registrations`, row.status, {}, row.count, periodSummary.total_registrations, `${row.count} ${row.label} registrations ÷ ${periodSummary.total_registrations} registrations × 100`)}</td>
          <td>{row.missing_requirements?.length ? row.missing_requirements.map((item) => typeof item === 'string' ? item : `${documentLabels[item.key] || String(item.key).replaceAll('_', ' ')} (${item.count})`).join(', ') : 'None'}</td><td>{row.recommended_action}</td>
        </tr>)}{statusRowsFiltered.length === 0 && <tr><td colSpan="5">No registration statuses match these filters.</td></tr>}</tbody>
      </Table>
    </section>

    <section className="registration-analytics-section">
      <header><div><p className="leave-kicker">INTERACTIVE VISUALIZATIONS</p><h3>Visit and registration outcomes</h3><p>Select a bar to open the matching client records.</p></div></header>
      <div className="registration-analytics-charts">
        <article className="registration-analytics-chart-card">
          <h4>{activityGroup === 'date' ? 'Visits by date' : activityGroup === 'weekday' ? 'Visits by day of week' : activityGroup === 'week' ? 'Visits by week' : 'Visits by month'}</h4>
          <div className="registration-chart-legend"><span><i className="is-visited" /> Other visits</span><span><i className="is-complete" /> Complete</span><span><i className="is-incomplete" /> Incomplete</span></div>
          <OutcomeBarList rows={activityChart} onSelect={(row, filtersForRow) => openMetric(`${row.label} · ${row.category_label}`, 'visited', filtersForRow)} emptyText="No visits are available for these filters." />
        </article>
        <article className="registration-analytics-chart-card">
          <h4>Category outcomes</h4>
          <div className="registration-chart-legend"><span><i className="is-complete" /> Complete</span><span><i className="is-incomplete" /> Incomplete</span></div>
          <OutcomeBarList rows={categoryChart} onSelect={(row, filtersForRow) => openMetric(`${row.category_label} clients`, 'visited', filtersForRow)} emptyText="No category results are available." />
        </article>
        <article className="registration-analytics-chart-card">
          <h4>Document compliance</h4>
          <div className="registration-chart-legend"><span><i className="is-submitted" /> Submitted</span><span><i className="is-pending" /> Pending</span></div>
          <DocumentComplianceList rows={documentChart} onSelect={(row, metric) => openDetails(`${row.label} ${metric === 'document_pending' ? 'pending' : 'submitted'}`, { category: row.category, document: row.key, metric })} />
        </article>
      </div>
    </section>
    {selection && <ClientDetailModal key={JSON.stringify([selection.title, selection.filters])} selection={selection} baseFilters={baseFilters} onClose={() => setSelection(null)} />}
  </section>;
}
