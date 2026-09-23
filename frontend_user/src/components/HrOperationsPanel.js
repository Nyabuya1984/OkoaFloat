import React from 'react';

export default function HrOperationsPanel({ leaveTypes, departments, audit }) {
  return (
    <section className="super-admin-panel hr-operations-panel" aria-label="HR operations">
      <div className="leave-section-heading"><div><p className="leave-kicker">HR OPERATIONS</p><h2>Organization overview</h2></div></div>
      <div className="admin-grid">
        <div className="admin-card" id="compliance"><h3>Compliance alerts</h3><p className="leave-muted">Review approval prerequisites and handover gates from the Approvals queue.</p><a className="leave-text-button" href="#approvals">Open verification queue</a></div>
        <div className="admin-card" id="leave-types"><h3>Leave types</h3>{leaveTypes.length === 0 ? <p className="leave-empty">No leave types configured.</p> : <ul className="health-list">{leaveTypes.map((item) => <li key={item.id}><span>{item.name} ({item.code})</span><strong>{item.is_paid ? 'Paid' : 'Unpaid'}</strong></li>)}</ul>}</div>
        <div className="admin-card" id="departments"><h3>Departments</h3>{departments.length === 0 ? <p className="leave-empty">No departments configured.</p> : <ul className="health-list">{departments.map((item) => <li key={item.id}><span>{item.name}</span><strong>{item.user_count || 0} users</strong></li>)}</ul>}</div>
        <div className="admin-card" id="audit-log"><h3>Audit log</h3><div className="leave-table-wrap compact-table"><table className="leave-table"><thead><tr><th>Action</th><th>Actor</th><th>Time</th></tr></thead><tbody>{audit.length === 0 ? <tr><td colSpan="3">No audit entries yet.</td></tr> : audit.slice(0, 10).map((entry) => <tr key={entry.id}><td>{entry.action}</td><td>{entry.actor}</td><td>{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '-'}</td></tr>)}</tbody></table></div></div>
      </div>
    </section>
  );
}
