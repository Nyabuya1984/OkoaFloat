import React, { useMemo, useState } from 'react';

const outcomeLabels = { registered: 'Registered', ready_to_register: 'Ready to register', appointment: 'Appointment', undecided: 'Undecided', promised: 'Promised', declined: 'Not interested' };

export default function SalesReportsPanel({ reports = [] }) {
  const [filters, setFilters] = useState({ from: '', to: '', outcome: '', employee: '' });

  const filtered = useMemo(
    () => reports.filter((report) => (!filters.from || report.date_visited >= filters.from)
      && (!filters.to || report.date_visited <= filters.to)
      && (!filters.outcome || report.outcome === filters.outcome)
      && (!filters.employee || (report.employee_name || '').toLowerCase().includes(filters.employee.toLowerCase()) || (report.agent_name || '').toLowerCase().includes(filters.employee.toLowerCase()))),
    [filters, reports],
  );

  const summary = useMemo(() => {
    const totals = { total: filtered.length, registered: 0, appointment: 0, undecided: 0, promised: 0, declined: 0 };
    filtered.forEach((report) => {
      if (report.outcome && totals[report.outcome] !== undefined) totals[report.outcome] += 1;
    });
    return totals;
  }, [filtered]);

  const update = (name, value) => setFilters((current) => ({ ...current, [name]: value }));

  const downloadLegacyCsv = async () => {
    try {
      const token = window.sessionStorage.getItem('okoa_access_token');
      const response = await fetch('/api/sales/reports/export', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload?.error?.message || payload?.msg || 'Unable to export sales reports.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'sales-reports.csv';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      window.alert(error.message || 'Unable to export sales reports.');
    }
  };

  return (
    <section className="leave-section sales-reports-section" id="sales-reports">
      <div className="leave-section-heading">
        <div>
          <p className="leave-kicker">SALES OPERATIONS</p>
          <h2>Daily sales reports</h2>
          <p className="leave-muted">Review client visits, registrations, appointments, and follow-ups.</p>
        </div>
        <div className="report-actions"><span className="section-meta">{filtered.length} reports</span><button type="button" className="leave-secondary-button" onClick={downloadLegacyCsv}>Download CSV</button></div>
      </div>

      <div className="sales-report-filters">
        <label>
          From
          <input type="date" value={filters.from} onChange={(event) => update('from', event.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={filters.to} onChange={(event) => update('to', event.target.value)} />
        </label>
        <label>
          Employee
          <input placeholder="Search employee or client" value={filters.employee} onChange={(event) => update('employee', event.target.value)} />
        </label>
        <label>
          Outcome
          <select value={filters.outcome} onChange={(event) => update('outcome', event.target.value)}>
            <option value="">All outcomes</option>
            {Object.entries(outcomeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
        </label>
      </div>

      <div className="sales-report-summary" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '10px', marginBottom: '14px' }}>
        <div className="leave-mini-card"><strong>{filtered.length}</strong><span>Total</span></div>
        <div className="leave-mini-card"><strong>{summary.registered}</strong><span>Registered</span></div>
        <div className="leave-mini-card"><strong>{summary.appointment}</strong><span>Appointments</span></div>
        <div className="leave-mini-card"><strong>{summary.undecided}</strong><span>Undecided</span></div>
        <div className="leave-mini-card"><strong>{summary.promised}</strong><span>Promised</span></div>
        <div className="leave-mini-card"><strong>{summary.declined}</strong><span>Declined</span></div>
      </div>

      <div className="leave-table-wrap compact-table">
        <table className="leave-table">
          <thead>
            <tr>
              <th>Employee</th>
              <th>Client</th>
              <th>Type</th>
              <th>Location</th>
              <th>Date</th>
              <th>Outcome</th>
              <th>Documents</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan="7">No sales reports match the selected filters.</td></tr>
            ) : filtered.map((report) => {
              const documentCount = Object.values(report.documents || {}).filter(Boolean).length + (report.uploaded_files || []).length;
              const attachmentLinks = report.uploaded_files || [];
              return (
                <tr key={report.id}>
                  <td>{report.employee_name || 'Employee'}</td>
                  <td>{report.business_owner_name || report.agent_name}</td>
                  <td>{report.customer_type === 'sub_agent' ? 'Sub-agent' : 'Agent / dealer'}</td>
                  <td>{report.business_location || '-'}</td>
                  <td>{report.date_visited}</td>
                  <td><span className="sales-outcome">{outcomeLabels[report.outcome] || report.outcome}</span></td>
                  <td>
                    {documentCount > 0 ? (
                      <div style={{ display: 'grid', gap: '4px' }}>
                        {attachmentLinks.map((file) => (
                          <a key={file.filename || file.name} href={`/api/sales/reports/${report.id}/documents/${encodeURIComponent(file.filename || file.name)}`} target="_blank" rel="noreferrer">
                            {file.name || file.filename || 'Attachment'}
                          </a>
                        ))}
                        {documentCount > attachmentLinks.length && <span>{documentCount - attachmentLinks.length} checklist item(s)</span>}
                      </div>
                    ) : (
                      'No docs'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
