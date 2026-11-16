import React, { useEffect, useState } from 'react';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';

const categoryNames = { agent: 'Agent / dealer', sub_agent: 'Sub-agent' };

async function loadAnalytics(url) {
  const send = () => fetch(apiUrl(url), {
    headers: getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {},
  });
  let response = await send();
  if (response.status === 401 && await refreshAuthToken()) response = await send();
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || 'Unable to load field-agent analytics.');
  return payload.data;
}

export default function SalesFieldAgentAnalytics() {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const download = async (format) => {
    const params = new URLSearchParams();
    if (from) params.set('from', from);
    if (to) params.set('to', to);
    const query = params.toString();
    const url = `/api/sales/analytics/field-agents/export.${format}${query ? `?${query}` : ''}`;
    const send = () => fetch(apiUrl(url), {
      headers: getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {},
    });
    try {
      let response = await send();
      if (response.status === 401 && await refreshAuthToken()) response = await send();
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error?.message || 'Unable to export field-agent analytics.');
      }
      const objectUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `field-agent-analytics.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    if (from) params.set('from', from);
    if (to) params.set('to', to);
    setLoading(true);
    setError('');
    loadAnalytics(`/api/sales/analytics/field-agents${params.size ? `?${params}` : ''}`)
      .then((result) => active && setData(
        result?.totals && Array.isArray(result.agents) ? result : null,
      ))
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [from, to]);

  return <section className="sales-field-agent-analytics" aria-label="Field-agent visit analytics">
    <div className="leave-section-heading">
      <div><p className="leave-kicker">FIELD VISIT ANALYTICS</p><h3>Agent performance</h3></div>
      <span>{data?.scope === 'org' ? 'Organization scope' : data?.scope === 'team' ? 'Team scope' : 'My visits'}</span>
    </div>
    <div className="sales-report-toolbar">
      <label>From<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
      <label>To<input type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label>
      <button type="button" className="leave-secondary-button" onClick={() => download('csv')}>Export analytics CSV</button>
      <button type="button" className="leave-secondary-button" onClick={() => download('xlsx')}>Export analytics Excel</button>
    </div>
    {error && <p role="alert" className="leave-alert error">{error}</p>}
    {loading && <p role="status">Loading field-agent analytics…</p>}
    {data && <>
      <p className="leave-muted">Conversion = registrations started ÷ eligible new-client visits; completion = complete registrations ÷ started registrations. Existing-client interactions count as visits but not conversion opportunities.</p>
      <div className="sales-report-summary">
        <div className="leave-mini-card"><strong>{data.totals.visits}</strong><span>Visits</span></div>
        <div className="leave-mini-card"><strong>{data.totals.eligible_visits}</strong><span>Eligible visits</span></div>
        <div className="leave-mini-card"><strong>{data.totals.registrations_started}</strong><span>Started</span></div>
        <div className="leave-mini-card"><strong>{data.totals.complete}</strong><span>Complete</span></div>
        <div className="leave-mini-card"><strong>{data.totals.incomplete}</strong><span>Incomplete</span></div>
      </div>
      <div className="leave-table-wrap compact-table">
        <table className="leave-table">
          <thead><tr><th>Field agent</th><th>Visits</th><th>Started</th><th>Complete</th><th>Incomplete</th><th>Conversion</th><th>Completion</th><th>Category split</th><th>Feedback</th></tr></thead>
          <tbody>{data.agents.length ? data.agents.map((agent) => <tr key={agent.employee_id}>
            <td>{agent.employee_name}</td><td>{agent.visits}</td><td>{agent.registrations_started}</td>
            <td>{agent.complete}</td><td>{agent.incomplete}</td>
            <td>{agent.conversion_rate}%</td><td>{agent.completion_rate}%</td>
            <td>{Object.entries(agent.by_category).map(([category, metrics]) => (
              <div key={category}>{categoryNames[category]}: {metrics.visits} visits ({metrics.eligible_visits} eligible), {metrics.registrations_started} started, {metrics.complete} complete, {metrics.incomplete} incomplete; {metrics.conversion_rate}% conversion / {metrics.completion_rate}% completion</div>
            ))}</td><td>{agent.feedback}</td>
          </tr>) : <tr><td colSpan="9">No field visits match this period.</td></tr>}</tbody>
        </table>
      </div>
      {data.incomplete_visits.length > 0 && <div className="sales-incomplete-feedback">
        <h4>Registration recovery priorities</h4>
        <ul>{data.incomplete_visits.map((visit) => <li key={visit.report_id}>
          <strong>{visit.employee_name}</strong> · {visit.client_name} ({visit.date_visited}): {visit.missing_requirements.join(', ')}.
          <span> {visit.action}</span>
        </li>)}</ul>
      </div>}
    </>}
  </section>;
}
