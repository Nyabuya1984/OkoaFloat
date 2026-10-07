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

export default function SmartDebtorTable({ records, search, onSearch, onLogCall }) {
  const [historyLoanId, setHistoryLoanId] = React.useState(null);
  const filteredRecords = records.filter((record) => (
    `${record.agent_name} ${record.business_name} ${record.agent_number} ${record.business_location}`
      .toLowerCase()
      .includes(search.trim().toLowerCase())
  ));

  return (
    <section className="collector-panel collector-table-panel">
      <div className="collector-panel-heading">
        <div>
          <h3>My accounts</h3>
          <p>Uncontacted clients appear first.</p>
        </div>
        <input
          type="search"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search clients"
          aria-label="Search portfolio"
        />
      </div>
      <div className="collector-table-scroll">
        <table className="collector-table">
          <thead>
            <tr>
              <th>Client / business</th>
              <th>Balance</th>
              <th>Next agreed payment</th>
              <th>Last interaction</th>
              <th>Last contacted</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {filteredRecords.length === 0 ? (
              <tr><td colSpan="6" className="collector-empty-cell">{records.length ? 'No accounts match your search.' : 'No accounts are currently assigned to you.'}</td></tr>
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
                    <button type="button" className="collector-log-button" onClick={() => onLogCall(record)}>Log Call</button>
                    <button type="button" className="collector-history-button" aria-expanded={historyLoanId === record.id} onClick={() => setHistoryLoanId((current) => current === record.id ? null : record.id)}>
                      {historyLoanId === record.id ? 'Hide History' : 'History / details'}
                    </button>
                  </td>
                </tr>
                {historyLoanId === record.id && (
                  <tr className="collector-history-row">
                    <td colSpan="6">
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
      <div className="collector-table-footer">{filteredRecords.length} of {records.length} accounts</div>
    </section>
  );
}
