import React, { useCallback, useEffect, useState } from 'react';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';

const requirements = {
  agent: ['certificate_of_incorporation', 'company_kra_pin', 'six_months_commission', 'owners_directors_national_ids', 'cr12_directors'],
  sub_agent: ['business_permit', 'individual_kra_pin', 'six_months_commission', 'subagent_agent_contract', 'owner_national_id', 'sign_contract'],
};
const labels = {
  business_permit: 'Business permit', individual_kra_pin: 'Individual KRA PIN',
  six_months_commission: 'Six months commission statement',
  subagent_agent_contract: 'Sub-agent/agent contract', owner_national_id: 'Owner national ID',
  sign_contract: 'Signed contract', certificate_of_incorporation: 'Certificate of incorporation',
  company_kra_pin: 'Company KRA PIN', owners_directors_national_ids: 'Owners/directors national IDs',
  cr12_directors: 'CR12 directors', witness_name: 'Witness name',
  witness_id_number: 'Witness ID number', witness_phone: 'Witness phone',
};
const witnessKeys = ['witness_name', 'witness_id_number', 'witness_phone'];

async function request(path, options = {}) {
  const send = () => fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
    },
  });
  let response = await send();
  if (response.status === 401 && await refreshAuthToken()) response = await send();
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || 'Unable to update registration follow-up.');
  return payload.data;
}

export default function SalesRecoveryFollowUps() {
  const [tasks, setTasks] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [documents, setDocuments] = useState({});
  const [witness, setWitness] = useState({});
  const [notes, setNotes] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const rows = await request('/api/sales/reports/recovery-follow-ups');
    setTasks(Array.isArray(rows) ? rows : []);
  }, []);
  useEffect(() => { refresh().catch((requestError) => setError(requestError.message)); }, [refresh]);

  const submit = async (event, task) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await request(`/api/sales/reports/${task.report_id}/recovery-follow-up`, {
        method: 'PATCH',
        body: JSON.stringify({ documents, ...witness, notes }),
      });
      setMessage(result.status === 'COMPLETE'
        ? `${task.client_name} registration is complete.`
        : `${task.client_name} remains open: ${result.missing_requirements.map((key) => labels[key] || key).join(', ')}.`);
      setExpanded(null);
      setDocuments({});
      setWitness({});
      setNotes('');
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return <section className="sales-recovery-follow-ups" aria-label="Incomplete registration recovery">
    <div className="leave-section-heading"><div><p className="leave-kicker">DOCUMENT FOLLOW-UP</p><h3>Incomplete field registrations</h3></div><span>{tasks.length} open</span></div>
    <p className="leave-muted">Use the documented customer-type checklist and witness details to complete a registration. Reports remain open until all applicable items are verified.</p>
    {error && <p role="alert" className="leave-alert error">{error}</p>}
    {message && <p role="status" className="leave-alert success">{message}</p>}
    {!tasks.length && !error && <p>No incomplete field registrations need recovery.</p>}
    {tasks.map((task) => <article className="sales-recovery-task" key={task.report_id}>
      <div><strong>{task.client_name}</strong> · {task.employee_name} · {task.date_visited}
        <p>Due {task.due_date || 'within seven days'} · Missing: {task.missing_requirements.map((key) => labels[key] || key).join(', ')}</p>
      </div>
      <button type="button" className="leave-secondary-button" onClick={() => {
        setExpanded(expanded === task.report_id ? null : task.report_id);
        setDocuments({});
        setWitness({});
      }}>{expanded === task.report_id ? 'Close recovery' : 'Update checklist'}</button>
      {expanded === task.report_id && <form onSubmit={(event) => submit(event, task)}>
        <fieldset><legend>Documents verified</legend>
          {(requirements[task.customer_type] || []).filter((key) => task.missing_requirements.includes(key)).map((key) => <label key={key}>
            <input type="checkbox" checked={Boolean(documents[key])} onChange={(event) => setDocuments((current) => ({ ...current, [key]: event.target.checked }))} />
            {labels[key]}
          </label>)}
        </fieldset>
        {witnessKeys.filter((key) => task.missing_requirements.includes(key)).map((key) => <label key={key}>{labels[key]}<input value={witness[key] || ''} onChange={(event) => setWitness((current) => ({ ...current, [key]: event.target.value }))} /></label>)}
        <label>Recovery notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength="1000" /></label>
        <button type="submit" className="leave-primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save recovery update'}</button>
      </form>}
    </article>)}
  </section>;
}
