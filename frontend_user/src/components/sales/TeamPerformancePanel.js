import React, { useState } from 'react';
import { useSalesQuery } from './SalesReportWorkspace';
import { ExportMenu } from './ExportMenu';

export default function TeamPerformancePanel({ filters }) {
  const [period, setPeriod] = useState({ from: filters.from || '', to: filters.to || '' });
  const params = { scope: 'team', from: period.from, to: period.to };
  const performance = useSalesQuery('/api/sales/v2/performance/team', params);
  const registrations = useSalesQuery('/api/sales/v2/registrations/team', params);
  const ranking = performance.data?.rows || performance.data?.top_performers || [];
  const registrationSummary = registrations.data?.summary || {};

  return <section className="sales-team-performance" aria-label="Sales and marketing performance">
    <div className="sales-v2-heading"><div><p className="sales-v2-kicker">TEAM PERFORMANCE</p><h3>Sales and marketing performance</h3><p className="sales-v2-muted">Compare salesperson registrations for the selected period.</p></div><ExportMenu exportUrl={performance.data?.export_url || registrations.data?.export_url} /></div><div className="sales-performance-filters"><label>From<input type="date" value={period.from} onChange={(event) => setPeriod({ ...period, from: event.target.value })} /></label><label>To<input type="date" value={period.to} onChange={(event) => setPeriod({ ...period, to: event.target.value })} /></label></div>
    <div className="sales-v2-grid"><div className="sales-v2-card"><span>Complete registrations</span><strong>{registrationSummary.complete ?? '-'}</strong></div><div className="sales-v2-card"><span>Partial registrations</span><strong>{registrationSummary.partial ?? '-'}</strong></div><div className="sales-v2-card"><span>Total visits</span><strong>{registrationSummary.total ?? '-'}</strong></div></div>
    {performance.loading ? <div className="sales-v2-loading">Loading performance...</div> : performance.error ? <div className="sales-v2-error">{performance.error.message}</div> : <div className="sales-performance-table-wrap"><table className="leave-table"><thead><tr><th>Rank</th><th>Salesperson</th><th>Visits</th><th>Registrations</th></tr></thead><tbody>{ranking.length === 0 ? <tr><td colSpan="4">No performance data for this period.</td></tr> : ranking.map((person, index) => <tr key={person.agent_id || person.employee_id || person.name}><td>{index + 1}</td><td>{person.name || person.employee_name || 'Unknown'}</td><td>{person.visits ?? person.submitted ?? 0}</td><td><strong>{person.registrations ?? 0}</strong></td></tr>)}</tbody></table></div>}
  </section>;
}
