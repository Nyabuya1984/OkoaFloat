import React, { useMemo, useRef, useState } from 'react';
import {
  BadgeCheck,
  BriefcaseBusiness,
  CalendarClock,
  CalendarDays,
  Handshake,
  Phone,
  PhoneCall,
  PhoneOff,
  Search,
  WalletCards,
} from 'lucide-react';

const outcomes = [
  { id: 'phone_off', label: 'Phone Off / Client Unreachable', Icon: PhoneOff },
  { id: 'no_answer', label: 'Phone Ringing — No Answer', Icon: Phone },
  { id: 'negotiation', label: 'Negotiation', Icon: Handshake },
  { id: 'wrong_number', label: 'Wrong Number', Icon: PhoneOff },
  { id: 'promise_to_pay', label: 'Client Promises to Pay (PTP)', Icon: CalendarClock },
  { id: 'callback_requested', label: 'Client Requests Callback', Icon: PhoneCall },
  { id: 'full_payment', label: 'Full Payment', Icon: BadgeCheck },
  { id: 'partial_payment', label: 'Partial Payment', Icon: WalletCards },
];

const money = (value) => new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 2,
}).format(Number(value) || 0);

const today = () => {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
};

const localDate = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const formatDateTime = (value) => value
  ? new Date(value).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' })
  : '—';

const formatAgreedDateTime = (date, time) => {
  if (!date) return '—';
  const promised = new Date(`${date}T${time || '00:00'}`);
  const weekday = new Intl.DateTimeFormat('en-KE', { weekday: 'long' }).format(promised);
  return `${weekday}, ${new Intl.DateTimeFormat('en-KE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(promised)}`;
};

const escapeCsv = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;

function InteractionTable({ outcome, interactions, onLogCall, onOpenLoan }) {
  const [expandedRows, setExpandedRows] = useState([]);
  const toggleRow = (callId) => setExpandedRows((current) => (
    current.includes(callId) ? current.filter((id) => id !== callId) : [...current, callId]
  ));
  const OutcomeIcon = outcome.Icon;

  return (
    <section className={`collector-panel collector-outcome-panel collector-outcome-indicator-${outcome.id}`} id={`report-${outcome.id}`}>
      <div className="collector-table-scroll collector-outcome-table-scroll">
        <table className="collector-table collector-outcome-table">
          <thead>
            <tr>
              <th>Contact date / time</th>
              <th>Debtor / business</th>
              <th>Collector</th>
              <th>Remarks</th>
              <th>Agreed payment / callback</th>
              <th>Amount paid</th>
              <th>Paid to date</th>
              <th>Outstanding</th>
              <th>Loan state</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {interactions.map((call) => {
              const agreedDate = call.promised_date || call.callback_date;
              const agreedTime = call.promised_time || call.callback_time;
              const paymentOnCall = Number(call.amount_paid) || 0;
              const isExpanded = expandedRows.includes(call.id);
              return (
                <React.Fragment key={call.id}>
                  <tr>
                    <td>{formatDateTime(call.created_at)}</td>
                    <td>
                      <strong>{call.debtor_name || 'Unknown debtor'}</strong>
                      <small>{call.business_name || '—'} · {call.agent_number || '—'}</small>
                    </td>
                    <td>{call.collector_name || '—'}</td>
                    <td className="collector-interaction-notes">{call.notes || '—'}</td>
                    <td>
                      {formatAgreedDateTime(agreedDate, agreedTime)}
                      {call.promised_amount != null && <small>Agreed amount: {money(call.promised_amount)}</small>}
                      {call.outcome === 'callback_requested' && <small>Requested callback</small>}
                    </td>
                    <td>{paymentOnCall > 0 ? money(paymentOnCall) : '—'}</td>
                    <td>{call.amount_paid_to_date != null ? money(call.amount_paid_to_date) : '—'}</td>
                    <td>{call.loan_balance != null ? money(call.loan_balance) : '—'}</td>
                    <td>{call.loan_status || (call.outcome === 'full_payment' ? 'Settled' : 'Active')}</td>
                    <td className="collector-report-actions">
                      <button type="button" className="collector-report-action" aria-expanded={isExpanded} onClick={() => toggleRow(call.id)}>
                        {isExpanded ? 'Hide details' : 'Details'}
                      </button>
                      {onOpenLoan && <button type="button" className="collector-report-action" onClick={() => onOpenLoan(call.loan_id)}>Open account</button>}
                      {onLogCall && <button type="button" className="collector-report-action collector-report-action-primary" onClick={() => onLogCall(call.loan_id)}>Log call</button>}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="collector-report-detail-row">
                      <td colSpan="10">
                        <div>
                          <span><strong>Outcome:</strong> {outcome.label}</span>
                          <span><strong>Contacted:</strong> {call.collector_name || '—'} at {formatDateTime(call.created_at)}</span>
                          <span><strong>Phone:</strong> {call.agent_number || '—'}</span>
                          {call.promised_amount != null && <span><strong>Promised amount:</strong> {money(call.promised_amount)}</span>}
                          <span><strong>Loan:</strong> {money(call.loan_amount)} original · {money(call.amount_paid_to_date)} paid · {money(call.loan_balance)} outstanding</span>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {interactions.length === 0 && (
        <div className="collector-outcome-empty">
          <span><OutcomeIcon size={19} aria-hidden="true" /></span>
          <div>
            <strong>No clients in this outcome for the selected day.</strong>
            <p>Try another date or check the other call outcomes.</p>
          </div>
        </div>
      )}
    </section>
  );
}

export default function CollectorInteractionTable({
  interactions = [],
  loading = false,
  onLogCall,
  onOpenLoan,
  onRefresh,
}) {
  const [contactDate, setContactDate] = useState('');
  const [search, setSearch] = useState('');
  const [collapsedOutcomes, setCollapsedOutcomes] = useState([]);
  const tableRefs = useRef({});
  const latestInteractionDate = interactions.reduce((latest, call) => {
    const date = call.contact_date || call.created_at?.slice(0, 10);
    return date && (!latest || date > latest) ? date : latest;
  }, '');
  const selectedContactDate = contactDate || latestInteractionDate || today();
  const selectedDay = useMemo(() => new Date(`${selectedContactDate}T00:00:00`), [selectedContactDate]);
  const selectedDayLabel = selectedContactDate
    ? new Intl.DateTimeFormat('en-KE', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(selectedDay)
    : 'Select a contact date';
  const interactionsForDay = useMemo(
    () => interactions.filter(
      (call) => (call.contact_date || call.created_at?.slice(0, 10)) === selectedContactDate,
    ),
    [selectedContactDate, interactions],
  );
  const visibleInteractions = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    if (!term) return interactionsForDay;
    return interactionsForDay.filter((call) => [
      call.debtor_name,
      call.business_name,
      call.agent_number,
      call.collector_name,
      call.notes,
      outcomes.find((outcome) => outcome.id === call.outcome)?.label,
    ].some((value) => String(value || '').toLocaleLowerCase().includes(term)));
  }, [interactionsForDay, search]);
  const groupedInteractions = useMemo(
    () => outcomes.map((outcome) => ({
      outcome,
      interactions: visibleInteractions.filter((call) => call.outcome === outcome.id),
    })),
    [visibleInteractions],
  );
  const collapsedSet = new Set(collapsedOutcomes);

  const changeDate = (offset) => {
    const date = new Date(`${selectedContactDate}T00:00:00`);
    date.setDate(date.getDate() + offset);
    setContactDate(localDate(date));
  };

  const exportCsv = () => {
    const columns = [
      ['Contact date', (call) => call.contact_date || call.created_at?.slice(0, 10)],
      ['Contact time', (call) => call.contact_time || ''],
      ['Debtor', (call) => call.debtor_name],
      ['Business', (call) => call.business_name],
      ['Phone', (call) => call.agent_number],
      ['Collector', (call) => call.collector_name],
      ['Outcome', (call) => outcomes.find((outcome) => outcome.id === call.outcome)?.label || call.outcome],
      ['Remarks', (call) => call.notes],
      ['Agreed date', (call) => call.promised_date || call.callback_date],
      ['Agreed time', (call) => call.promised_time || call.callback_time],
      ['Amount paid', (call) => call.amount_paid],
      ['Paid to date', (call) => call.amount_paid_to_date],
      ['Outstanding', (call) => call.loan_balance],
      ['Loan state', (call) => call.loan_status],
    ];
    const csv = [
      columns.map(([label]) => escapeCsv(label)).join(','),
      ...visibleInteractions.map((call) => columns.map(([, value]) => escapeCsv(value(call))).join(',')),
    ].join('\r\n');
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `call-reports-${selectedContactDate}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const toggleAll = (expand) => {
    setCollapsedOutcomes(expand ? [] : outcomes.map((outcome) => outcome.id));
  };

  const jumpToReport = (outcomeId) => {
    setCollapsedOutcomes((current) => current.filter((id) => id !== outcomeId));
    window.requestAnimationFrame(() => tableRefs.current[outcomeId]?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  return (
    <section className="collector-interaction-analytics" aria-label="Daily call and interaction analytical tables">
      <header className="collector-interaction-analytics-heading">
        <div className="collector-report-heading-group">
          {onRefresh && <span className="collector-report-heading-mark"><BriefcaseBusiness size={21} aria-hidden="true" /></span>}
          <div className="collector-report-heading-copy">
            {onRefresh ? (
              <>
                <p className="leave-kicker">COLLECTOR WORKSPACE</p>
                <h2>My Assigned Portfolio</h2>
                <p className="collector-report-subtitle"><PhoneCall size={14} aria-hidden="true" /> CALL &amp; INTERACTION ANALYTICS</p>
                <p>Daily call reports · {selectedDayLabel} · {visibleInteractions.length} of {interactionsForDay.length} interactions</p>
              </>
            ) : (
              <>
                <p className="leave-kicker">CALL &amp; INTERACTION ANALYTICS</p>
                <h2>Daily call reports</h2>
                <p>{selectedDayLabel} · {visibleInteractions.length} of {interactionsForDay.length} interaction{interactionsForDay.length === 1 ? '' : 's'}</p>
              </>
            )}
          </div>
        </div>
        {onRefresh && <div className="collector-report-hero-art" aria-hidden="true"><PhoneCall size={30} /><span>LISTEN</span><strong>Connect<br />with clients</strong></div>}
        <div className="collector-report-date-controls">
          <div className="collector-report-date-card">
            <span className="collector-report-date-icon"><CalendarDays size={19} aria-hidden="true" /></span>
            <label>
              Contact date
              <input
                aria-label="Select interaction contact date"
                type="date"
                value={selectedContactDate}
                onChange={(event) => setContactDate(event.target.value)}
              />
            </label>
          </div>
          <div className="collector-report-date-actions">
            <button type="button" className="collector-report-control" onClick={() => changeDate(-1)} aria-label="Previous day">‹</button>
            <button type="button" className="collector-report-control" onClick={() => changeDate(1)} disabled={selectedContactDate >= today()} aria-label="Next day">›</button>
            <button type="button" className="collector-report-control collector-report-today" onClick={() => setContactDate(today())}>Today</button>
            {onRefresh && <button type="button" className="collector-report-control collector-report-refresh" onClick={onRefresh} disabled={loading}>Refresh</button>}
          </div>
        </div>
      </header>
      <div className="collector-report-toolbar">
        <label className="collector-report-search">
          <span>Find a client or remark</span>
          <span className="collector-report-search-field">
            <Search size={17} aria-hidden="true" />
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search this day’s reports…" />
          </span>
        </label>
        <div className="collector-report-toolbar-actions">
          <button type="button" className="collector-report-control" onClick={() => toggleAll(true)}>＋ Expand all</button>
          <button type="button" className="collector-report-control" onClick={() => toggleAll(false)}>－ Collapse all</button>
          <button type="button" className="collector-report-control collector-report-export" onClick={exportCsv} disabled={visibleInteractions.length === 0}>↓ Export CSV</button>
        </div>
      </div>
      <nav className="collector-outcome-picker" aria-label="Jump to call outcome report">
        {groupedInteractions.map(({ outcome, interactions: calls }) => (
          <button
            key={outcome.id}
            type="button"
            className={`collector-outcome-choice collector-outcome-indicator-${outcome.id}`}
            onClick={() => jumpToReport(outcome.id)}
          >
            <span className="collector-outcome-icon"><outcome.Icon size={20} strokeWidth={2.3} aria-hidden="true" /></span>
            <span>{outcome.label}</span>
            <span className="collector-outcome-choice-meta">
              <strong>{calls.length}</strong>
              <small>{calls.length === 1 ? 'record' : 'records'}</small>
            </span>
          </button>
        ))}
      </nav>
      {loading ? (
        <p className="collector-reports-empty" role="status">Loading daily call reports…</p>
      ) : visibleInteractions.length === 0 ? (
        <p className="collector-reports-empty">
          No calls match this date and search. Choose another date, clear the search, or log a call to populate these reports.
        </p>
      ) : null}
      <div className="collector-report-tables">
        {groupedInteractions.map(({ outcome, interactions: calls }) => {
          const OutcomeIcon = outcome.Icon;
          return (
            <div
              key={outcome.id}
              ref={(element) => { tableRefs.current[outcome.id] = element; }}
              className={`collector-report-table-section collector-outcome-indicator-${outcome.id}`}
            >
              <button
                type="button"
                className="collector-report-section-toggle"
                aria-expanded={!collapsedSet.has(outcome.id)}
                onClick={() => setCollapsedOutcomes((current) => (
                  current.includes(outcome.id)
                    ? current.filter((id) => id !== outcome.id)
                    : [...current, outcome.id]
                ))}
              >
                <span className="collector-report-outcome-title"><span><OutcomeIcon size={17} aria-hidden="true" /></span>{outcome.label}</span>
                <span>{calls.length} record{calls.length === 1 ? '' : 's'} · {collapsedSet.has(outcome.id) ? 'Show records +' : 'Hide records −'}</span>
              </button>
              {!collapsedSet.has(outcome.id) && (
                <InteractionTable
                  outcome={outcome}
                  interactions={calls}
                  onLogCall={onLogCall}
                  onOpenLoan={onOpenLoan}
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
