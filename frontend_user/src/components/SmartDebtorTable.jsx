import React from 'react';
import { Check } from 'lucide-react';

const outcomeLabels = {
  phone_off: 'Phone off / unreachable',
  no_answer: 'No answer',
  negotiation: 'Negotiation',
  wrong_number: 'Wrong number',
  promise_to_pay: 'Promise to pay',
  callback_requested: 'Callback requested',
  full_payment: 'Full payment',
  partial_payment: 'Partial payment',
};

const outcomes = [
  ['phone_off', 'Phone off / unreachable'],
  ['no_answer', 'No answer'],
  ['negotiation', 'Negotiation'],
  ['wrong_number', 'Wrong number'],
  ['promise_to_pay', 'Promised to pay'],
  ['callback_requested', 'Callback requested / pay later'],
  ['full_payment', 'Paid in full'],
  ['partial_payment', 'Partial payment'],
];

const outcomeTone = {
  phone_off: 'red',
  no_answer: 'amber',
  negotiation: 'blue',
  wrong_number: 'gray',
  promise_to_pay: 'green',
  callback_requested: 'violet',
  full_payment: 'green',
  partial_payment: 'teal',
};

const money = (value) => new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

const localDateKey = (value) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
};

export default function SmartDebtorTable({ records, search, onSearch, onLogCall, onRefresh, refreshing = false, teamMode = false }) {
  const [historyLoanId, setHistoryLoanId] = React.useState(null);
  const [outcomeFilter, setOutcomeFilter] = React.useState('');
  const [receivedDate, setReceivedDate] = React.useState('');
  const [contactedFrom, setContactedFrom] = React.useState('');
  const [contactedTo, setContactedTo] = React.useState('');
  const [sortOrder, setSortOrder] = React.useState('balance_desc');
  const filteredRecords = records
    .filter((record) => {
      const matchesSearch = `${record.agent_name} ${record.business_name} ${record.agent_number} ${record.business_location}`
        .toLowerCase()
        .includes(search.trim().toLowerCase());
      const matchesOutcome = !outcomeFilter
        || (outcomeFilter === 'not_contacted'
          ? !record.last_interaction
          : record.last_interaction?.outcome === outcomeFilter);
      const assignmentDate = localDateKey(record.assigned_at);
      const contactDate = record.last_interaction?.contact_date
        || record.last_interaction?.created_at?.slice(0, 10)
        || '';
      return matchesSearch
        && matchesOutcome
        && (!receivedDate || assignmentDate === receivedDate)
        && (!contactedFrom || (contactDate && contactDate >= contactedFrom))
        && (!contactedTo || (contactDate && contactDate <= contactedTo));
    })
    .sort((first, second) => {
      if (sortOrder === 'balance_asc') return Number(first.loan_balance) - Number(second.loan_balance);
      if (sortOrder === 'received_newest') return (second.assigned_at || '').localeCompare(first.assigned_at || '');
      if (sortOrder === 'received_oldest') return (first.assigned_at || '').localeCompare(second.assigned_at || '');
      return Number(second.loan_balance) - Number(first.loan_balance);
    });

  return (
    <section className="collector-panel collector-table-panel">
      <div className="collector-panel-heading">
        <div>
          <h3>{teamMode ? 'Team accounts' : 'My accounts'}</h3>
          <p>{teamMode ? 'Review accounts allocated to your collection agents and follow their contact progress.' : 'Check when each account was assigned and filter by response or contact date.'}</p>
        </div>
        <div className="collector-list-heading-actions">
          {onRefresh && <button type="button" className="collector-refresh-button" onClick={onRefresh} disabled={refreshing}>Refresh list</button>}
          <input
            type="search"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search clients"
            aria-label="Search portfolio"
          />
        </div>
      </div>
      <div className="collector-list-filters" aria-label="Filter assigned accounts">
        <label>Sort by
          <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
            <option value="balance_desc">Highest balance first</option>
            <option value="balance_asc">Lowest balance first</option>
            <option value="received_newest">Most recently received</option>
            <option value="received_oldest">Oldest received</option>
          </select>
        </label>
        <label>Client response
          <select value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value)}>
            <option value="">All responses</option>
            <option value="not_contacted">Not contacted</option>
            {outcomes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Received on
          <input type="date" value={receivedDate} onChange={(event) => setReceivedDate(event.target.value)} />
        </label>
        <label>Last contacted from
          <input type="date" value={contactedFrom} max={contactedTo || undefined} onChange={(event) => setContactedFrom(event.target.value)} />
        </label>
        <label>Last contacted to
          <input type="date" value={contactedTo} min={contactedFrom || undefined} onChange={(event) => setContactedTo(event.target.value)} />
        </label>
      </div>
      <div className="collector-table-scroll">
        <table className="collector-table">
          <thead>
            <tr>
              <th>Client / business</th>
              <th>List received</th>
              <th>Balance</th>
              <th>Next agreed payment</th>
              <th>Last interaction</th>
              <th>Last contacted</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {filteredRecords.length === 0 ? (
              <tr><td colSpan="7" className="collector-empty-cell">{records.length ? 'No accounts match the selected filters.' : 'No accounts are currently assigned to you.'}</td></tr>
            ) : filteredRecords.map((record) => {
              const interaction = record.last_interaction;
              return (
                <React.Fragment key={record.id}>
                <tr className={interaction ? 'collector-row-contacted' : 'collector-row-pending'}>
                  <td>
                    <div className="collector-client-name">
                      {interaction && <Check size={14} aria-label="Contacted" />}
                      <strong>{record.agent_name}</strong>
                    </div>
                    <small>{record.business_name} · {record.business_location || 'Location not set'}</small>
                    <a href={`tel:${record.agent_number}`}>{record.agent_number}</a>
                  </td>
                  <td>{record.assigned_at ? <><strong>{new Date(record.assigned_at).toLocaleDateString()}</strong><small>{new Date(record.assigned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small></> : '—'}</td>
                  <td className="collector-balance">{money(record.loan_balance)}</td>
                  <td>{record.next_payment_date
                    ? <>{record.next_payment_date} {record.next_payment_time || ''}{record.next_payment_amount ? <small>{money(record.next_payment_amount)}</small> : null}</>
                    : '—'}</td>
                  <td>
                    {interaction
                      ? <span className={`collector-outcome collector-outcome-${outcomeTone[interaction.outcome] || 'gray'}`}>{outcomeLabels[interaction.outcome] || interaction.outcome}</span>
                      : <span className="collector-outcome collector-outcome-not-called">Not called</span>}
                  </td>
                  <td>{interaction?.created_at ? new Date(interaction.created_at).toLocaleString() : '—'}</td>
                  <td className="collector-row-actions">
                    <button type="button" className="collector-log-button" onClick={() => onLogCall(record)} disabled={record.is_assigned_to_me === false}>Log Call</button>
                    <button type="button" className="collector-history-button" aria-expanded={historyLoanId === record.id} onClick={() => setHistoryLoanId((current) => current === record.id ? null : record.id)}>
                      {historyLoanId === record.id ? 'Hide History' : 'History / details'}
                    </button>
                  </td>
                </tr>
                {historyLoanId === record.id && (
                  <tr className="collector-history-row">
                    <td colSpan="7">
                      <section className="collector-client-history" aria-label={`Loan and interaction history for ${record.agent_name}`}>
                        <div className="collector-history-identity">
                          <strong>{record.agent_name}</strong>
                          <span>{record.agent_number} · {record.business_name} · {record.business_location || 'Location not set'}</span>
                          <span>Agent ID: {record.agent_no || '—'} · Store: {record.store_number || '—'}</span>
                        </div>
                        <div className="collector-history-loan-details">
                          <span>Original amount <strong>{money(record.loan_amount)}</strong></span>
                          <span>Total paid <strong>{money(record.amount_paid)}</strong></span>
                          <span>Balance <strong>{money(record.loan_balance)}</strong></span>
                          <span>Disbursed <strong>{record.loan_date || '—'}</strong></span>
                          <span>Last interest calc <strong>{record.last_interest_calc_date || '—'}</strong></span>
                          <span>Days <strong>{record.no_of_days ?? 0}</strong></span>
                          <span>Status <strong>{record.status}</strong></span>
                        </div>
                        <div className="collector-history-interactions">
                          <strong>Interaction history</strong>
                          {(record.interactions || []).length === 0
                            ? <p>No interactions have been recorded.</p>
                            : record.interactions.map((call) => (
                              <article key={call.id}>
                                <strong>{outcomeLabels[call.outcome] || call.outcome}</strong>
                                <span>{call.contact_date || new Date(call.created_at).toLocaleDateString()} {call.contact_time || new Date(call.created_at).toLocaleTimeString()} · {call.collector_name}</span>
                                <span>Response: {outcomeLabels[call.outcome] || call.outcome}</span>
                                {call.notes && <p>Remarks: {call.notes}</p>}
                                {call.promised_date && <span>Promised payment: {call.promised_date} {call.promised_time || ''}{call.promised_amount ? ` · ${money(call.promised_amount)}` : ''}</span>}
                                {call.callback_date && <span>Callback: {call.callback_date} {call.callback_time || ''}</span>}
                                {Number(call.amount_paid) > 0 && <span>Payment: {money(call.amount_paid)} · Balance now {money(call.loan_balance)}</span>}
                              </article>
                            ))}
                        </div>
                      </section>
                    </td>
                  </tr>
                )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="collector-table-footer">{filteredRecords.length} of {records.length} accounts · balance: highest to lowest unless changed · assigned date is the list received date</div>
    </section>
  );
}
