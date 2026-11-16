import React, { useState } from 'react';
import SalesRegistrationAnalytics from './SalesRegistrationAnalytics';
import SalesLeadWorkspace from './sales/SalesLeadWorkspace';

export default function DashboardLanding({
  currentUser,
  tier,
  departmentName,
  overview,
  pendingRequests,
  availableDays,
  pendingCount,
  usedDays,
  loading,
  message,
  canAccessSalesReports,
  isSalesRepresentative = false,
  canViewEmployeePerformance,
  canAccessDebtCollection,
  onNavigate,
}) {
  const [performancePeriod, setPerformancePeriod] = useState({ from: '', to: '' });
  const employeeName = currentUser?.name || currentUser?.full_name || 'there';
  const pendingApprovals = pendingRequests.length;
  const personalRequests = overview.requests || [];
  const awaitingUpdates = personalRequests.filter((request) => (
    ['pending', 'handover_pending', 'team_leader_pending', 'department_manager_pending', 'general_manager_pending', 'hr_verification']
      .includes(request.workflow_state || request.status)
  )).length;
  const manager = ['general_manager', 'department_manager', 'team_leader'].includes(tier);
  const pageLabel = tier === 'general_manager'
    ? 'Organization Overview'
    : tier === 'team_leader' ? 'Group Leader Workspace' : 'Department Overview';
  const approvalLabel = tier === 'general_manager'
    ? 'Organization approvals'
    : tier === 'team_leader' ? 'Team approvals' : 'Approvals needing attention';

  return (
    <main className={`leave-main dashboard-page role-dashboard role-dashboard-${tier}`} aria-labelledby="dashboard-page-title">
      <header className="leave-header">
        <div>
          <p className="leave-kicker">{manager
            ? tier === 'general_manager' ? 'ORGANIZATION WORKSPACE' : tier === 'team_leader' ? 'TEAM WORKSPACE' : 'DEPARTMENT WORKSPACE'
            : 'PERSONAL WORKSPACE'}</p>
          <h1 id="dashboard-page-title">{manager ? pageLabel : `Good day, ${employeeName}`}</h1>
          <p className="leave-muted">{manager
            ? tier === 'general_manager'
              ? 'Organization-wide workload, approvals, and operational follow-up.'
              : `${departmentName || 'Your department'} · Focus on team workload, approvals, and operational follow-up.`
            : 'Your leave, requests, and self-service actions in one place.'}</p>
        </div>
        {!manager && <div className="leave-header-actions">
          <button className="leave-primary-button leave-apply-button" type="button" onClick={() => onNavigate('apply-leave')}>Apply for leave</button>
        </div>}
      </header>

      {message && <div className={`leave-alert ${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.text}</div>}
      {loading ? <div className="leave-loading" role="status">Loading your workspace…</div> : manager ? <>
        <section className="role-dashboard-kpis" aria-label="Team overview">
          <article className="role-dashboard-kpi is-highlight">
            <span>{approvalLabel}</span>
            <strong>{pendingApprovals}</strong>
            <small>{pendingApprovals === 1 ? 'request awaiting review' : 'requests awaiting review'}</small>
          </article>
          <article className="role-dashboard-kpi">
            <span>{tier === 'general_manager' ? 'Organization' : 'Department'}</span>
            <strong className="role-dashboard-department">{tier === 'general_manager' ? 'All departments' : departmentName || 'Assigned department'}</strong>
            <small>{tier === 'general_manager' ? 'Organization-wide operations' : tier === 'team_leader' ? 'Group-level operations' : 'Department-level operations'}</small>
          </article>
          <article className="role-dashboard-kpi">
            <span>Leave workflow</span>
            <strong>{pendingApprovals ? 'Action required' : 'On track'}</strong>
            <small>{pendingApprovals ? 'Review assigned requests' : 'No assigned approvals pending'}</small>
          </article>
        </section>
        <section className="role-dashboard-panel">
          <div className="leave-section-heading">
            <div><p className="leave-kicker">{tier === 'team_leader' ? 'GROUP EXECUTION' : 'DEPARTMENT OPERATIONS'}</p><h2>{tier === 'team_leader' ? 'Team priorities' : 'Department priorities'}</h2></div>
          </div>
          <div className="role-dashboard-actions">
            {pendingApprovals > 0 && <button type="button" className="role-dashboard-action is-priority" onClick={() => onNavigate('approvals')}>
              <strong>Review {pendingApprovals} pending {pendingApprovals === 1 ? 'approval' : 'approvals'}</strong><span>Open the assigned leave approval queue</span>
            </button>}
            <button type="button" className="role-dashboard-action" onClick={() => onNavigate('calendar')}>
              <strong>Team calendar</strong><span>Review team schedules and planned leave</span>
            </button>
            <button type="button" className="role-dashboard-action" onClick={() => onNavigate('employees')}>
              <strong>{tier === 'team_leader' ? 'Group members' : 'Department directory'}</strong><span>View people and their current assignments</span>
            </button>
            {canAccessSalesReports && <button type="button" className="role-dashboard-action" onClick={() => onNavigate('sales-reports')}>
              <strong>{tier === 'general_manager' ? 'Sales & Marketing reports' : 'Sales team performance'}</strong><span>Review employee outcomes, registration trends, and follow-up gaps</span>
            </button>}
            {canAccessDebtCollection && <button type="button" className="role-dashboard-action" onClick={() => onNavigate('debt-collection')}>
              <strong>Debt Collection operations</strong><span>Open department follow-up and collection reports</span>
            </button>}
          </div>
        </section>
        {canViewEmployeePerformance && <section className="role-dashboard-panel managerial-performance-panel" aria-label="Sales and marketing decision support">
          <div className="leave-section-heading">
            <div>
              <p className="leave-kicker">{tier === 'general_manager' ? 'ORGANIZATION PERFORMANCE' : 'SALES & MARKETING PERFORMANCE'}</p>
              <h2>Employee performance and sales outcomes</h2>
              <p className="leave-muted">Compare every representative’s completed registrations, peer performance, and outstanding requirements.</p>
            </div>
            <div className="sales-performance-filters" aria-label="Performance reporting period">
              <label>From<input aria-label="Performance period from" type="date" value={performancePeriod.from} onChange={(event) => setPerformancePeriod((period) => ({ ...period, from: event.target.value }))} /></label>
              <label>To<input aria-label="Performance period to" type="date" value={performancePeriod.to} onChange={(event) => setPerformancePeriod((period) => ({ ...period, to: event.target.value }))} /></label>
            </div>
          </div>
          <SalesRegistrationAnalytics
            filters={performancePeriod}
            canViewEmployeePerformance
            showRepresentativeFilter
          />
        </section>}
        {canViewEmployeePerformance && <section className="role-dashboard-panel" aria-label="Telesales lead operations">
          <div className="leave-section-heading">
            <div><p className="leave-kicker">TELESALES</p><h2>Lead assignment and call follow-up</h2></div>
          </div>
          <SalesLeadWorkspace canManage />
        </section>}
        <p className="role-dashboard-note">Detailed approval decisions and operational records are available in their dedicated pages.</p>
      </> : <>
        <section className="role-dashboard-kpis" aria-label="Personal summary">
          <article className="role-dashboard-kpi is-highlight"><span>Leave available</span><strong>{availableDays}</strong><small>days across your leave balances</small></article>
          <article className="role-dashboard-kpi"><span>Days taken</span><strong>{usedDays}</strong><small>across all leave types</small></article>
          <article className="role-dashboard-kpi"><span>Requests awaiting updates</span><strong>{awaitingUpdates}</strong><small>leave requests in progress</small></article>
        </section>
        <section className="role-dashboard-panel">
          <div className="leave-section-heading"><div><p className="leave-kicker">YOUR WORKSPACE</p><h2>Quick actions</h2></div></div>
          <div className="role-dashboard-actions">
            <button type="button" className="role-dashboard-action" onClick={() => onNavigate('apply-leave')}><strong>Apply for leave</strong><span>Start a new leave request</span></button>
            <button type="button" className="role-dashboard-action" onClick={() => onNavigate('my-leave')}><strong>My leave</strong><span>{personalRequests.length} {personalRequests.length === 1 ? 'request' : 'requests'} · {pendingCount} pending</span></button>
            <button type="button" className="role-dashboard-action" onClick={() => onNavigate('history')}><strong>Leave history</strong><span>Review previous requests and decisions</span></button>
            {canAccessSalesReports && !canViewEmployeePerformance && <button type="button" className="role-dashboard-action" onClick={() => onNavigate('sales-reports')}><strong>Add Client</strong><span>Record a Sales &amp; Marketing client visit</span></button>}
            {canAccessDebtCollection && <button type="button" className="role-dashboard-action" onClick={() => onNavigate('debt-collection')}><strong>Debt Collection</strong><span>Open your assigned operations workspace</span></button>}
          </div>
        </section>
        {isSalesRepresentative && canAccessSalesReports && <section className="role-dashboard-panel sales-representative-dashboard" aria-label="Sales and marketing dashboard">
          <div className="leave-section-heading">
            <div><p className="leave-kicker">SALES &amp; MARKETING</p><h2>Your registration results</h2><p className="leave-muted">Review your visit, registration, and follow-up outcomes. Your lead list and cold-calling workflow are available in Sales Reports.</p></div>
            <div className="sales-performance-filters" aria-label="Sales reporting period">
              <label>From<input aria-label="Sales period from" type="date" value={performancePeriod.from} onChange={(event) => setPerformancePeriod((period) => ({ ...period, from: event.target.value }))} /></label>
              <label>To<input aria-label="Sales period to" type="date" value={performancePeriod.to} onChange={(event) => setPerformancePeriod((period) => ({ ...period, to: event.target.value }))} /></label>
            </div>
          </div>
          <SalesRegistrationAnalytics filters={performancePeriod} />
          <button type="button" className="leave-primary-button" onClick={() => onNavigate('sales-reports')}>Open visits and cold-calling leads</button>
        </section>}
        {isSalesRepresentative && canAccessSalesReports && <section className="role-dashboard-panel" aria-label="Telesales calling queue">
          <div className="leave-section-heading">
            <div><p className="leave-kicker">TELESALES</p><h2>Your calling queue</h2><p className="leave-muted">Update each assigned lead with its call outcome and follow-up details.</p></div>
          </div>
          <SalesLeadWorkspace />
        </section>}
      </>}
    </main>
  );
}
