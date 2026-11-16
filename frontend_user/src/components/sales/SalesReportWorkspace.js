import React, { useEffect, useState } from 'react';
import { getAuthToken, refreshAuthToken } from '../../services/authStorage';
import { apiUrl } from '../../services/apiConfig';
import { AgentPicker } from './AgentPicker';
import { ComplianceBadge } from './ComplianceBadge';
import { DrillDownModal } from './DrillDownModal';
import { ExportMenu } from './ExportMenu';
import { ReportChart } from './ReportChart';
import { ReportFilters } from './ReportFilters';
import { ReportTable } from './ReportTable';
import './sales.css';

export const useSalesQuery = (endpoint, params = {}) => {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== ''));
  const url = `${endpoint}${query.toString() ? `?${query}` : ''}`;
  useEffect(() => {
    let active = true;
    setState({ data: null, loading: true, error: null });
    const request = () => fetch(apiUrl(url), { headers: getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {} });
    request()
      .then(async (response) => {
        if (response.status === 401 && await refreshAuthToken()) return request();
        return response;
      })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (response.status === 403 && String(body.error?.message || body.error || '').includes('Sales Reports are disabled')) {
            window.dispatchEvent(new Event('dashboard-feature-access-denied'));
          }
          throw new Error(body.error?.message || body.error || 'Unable to load sales data.');
        }
        return body.data;
      })
      .then((data) => active && setState({ data, loading: false, error: null }))
      .catch((error) => active && setState({ data: null, loading: false, error }));
    return () => { active = false; };
  }, [url]);
  return state;
};

export const SalesReportWorkspace = ({ scope = 'mine', report = 'summary' }) => {
  const [filters, setFilters] = useState({ from: '', to: '', category: '', status: '', agent: '' });
  const [selectedRows, setSelectedRows] = useState(null);
  const [actionMessage, setActionMessage] = useState('');
  const endpoint = scope === 'mine' ? '/api/sales/v2/summary' : scope === 'team' ? '/api/sales/v2/reports' : '/api/sales/v2/registrations/org';
  const query = useSalesQuery(endpoint, { scope, ...filters });
  const data = query.data || { summary: {}, rows: [], by_agent: [], by_outcome: {} };
  const runAction = async (action) => { const reportId = data.rows?.[0]?.id; if (!reportId) return setActionMessage('Select a visit before using this action.'); try { const response = await fetch(`/api/sales/v2/actions/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}) }, body: JSON.stringify({ report_id: reportId }) }); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.error?.message || 'Action failed.'); setActionMessage(`${action[0].toUpperCase()}${action.slice(1)} completed.`); } catch (error) { setActionMessage(error.message); } };
  return <section className="sales-v2-workspace" aria-label={`${scope} sales reports`}><div className="sales-v2-heading"><div><p className="sales-v2-kicker">SALES REPORTS V2</p><h2>{scope === 'mine' ? 'My sales workspace' : scope === 'team' ? 'Team sales workspace' : 'Organization sales workspace'}</h2></div><ExportMenu exportUrl={data.export_url} /></div><ReportFilters value={filters} onChange={setFilters} /><AgentPicker value={filters.agent} onChange={(agent) => setFilters({ ...filters, agent })} />{actionMessage && <div className="sales-v2-action-message" role="status">{actionMessage}</div>}{scope === 'team' && <button type="button" className="sales-v2-action-button" onClick={() => runAction('chase')}>Chase selected agent</button>}{scope === 'org' && <><button type="button" className="sales-v2-action-button" onClick={() => runAction('flag')}>Flag selected agent</button><button type="button" className="sales-v2-action-button" onClick={() => runAction('verify')}>Verify selected visit</button></>}<div className="sales-v2-grid"><div className="sales-v2-card"><span>Total visits</span><strong>{data.summary?.total ?? '-'}</strong><ComplianceBadge status={data.summary?.rate == null ? 'neutral' : data.summary.rate >= 90 ? 'compliant' : 'at-risk'} /></div><div className="sales-v2-card"><span>Filed today</span><strong>{data.summary?.filed_today ?? data.summary?.filed ?? '-'}</strong><small>Target: {data.summary?.expected_today ?? '-'}</small></div><div className="sales-v2-card"><span>Registrations</span><strong>{data.summary?.complete ?? data.summary?.registrations ?? '-'}</strong><small>Completed pipeline</small></div></div><div className="sales-v2-panels"><div className="sales-v2-card"><h3>Outcomes</h3><ReportChart type="bar" data={Object.entries(data.by_outcome || {}).map(([label, value]) => ({ label, value }))} onSelect={() => setSelectedRows(data.rows || [])} /></div><div className="sales-v2-card"><h3>Visit detail</h3>{query.loading ? <div className="sales-v2-loading">Loading sales data...</div> : query.error ? <div role="alert" className="sales-v2-error">{query.error.message}</div> : <ReportTable rows={data.rows || []} onRowClick={setSelectedRows} />}</div></div>{selectedRows && <DrillDownModal rows={selectedRows} onClose={() => setSelectedRows(null)} />}</section>;
};