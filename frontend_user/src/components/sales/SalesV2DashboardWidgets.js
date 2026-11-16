import React from 'react';
import { SalesReportCard } from './SalesReportCard';
import { SalesReportWorkspace } from './SalesReportWorkspace';
import TeamPerformancePanel from './TeamPerformancePanel';

export const resolveSalesScope = (user) => {
  const assignment = user?.active_assignment || user?.assignment || {};
  const organizationalRole = String(
    user?.organizational_role
    || assignment?.organizational_role
    || user?.organizationalRole
    || user?.role
    || 'employee',
  )
    .trim()
    .replace(/[\s-]+/g, '_')
    .toLowerCase();
  const department = String(
    user?.department
    || user?.department_name
    || assignment?.department_name
    || assignment?.department
    || '',
  ).trim().toLowerCase();
  const role = String(user?.role || 'employee').trim().toLowerCase();

  if (user?.is_superuser || ['super_admin', 'system_admin', 'hr_admin'].includes(role) || organizationalRole === 'general_manager' || department === 'all') {
    return 'org';
  }
  if (['department_manager', 'team_leader', 'manager'].includes(organizationalRole) || ['manager'].includes(role)) {
    return 'team';
  }
  return 'mine';
};

export default function SalesV2DashboardWidgets({ currentUser, onFileNow, onViewReport, onOpenWorkspace, onViewDetail }) {
  const scope = resolveSalesScope(currentUser);
  const handleViewReport = onViewReport || onFileNow;
  const handleOpenWorkspace = onOpenWorkspace || onFileNow;
  const handleViewDetail = onViewDetail || onFileNow;

  return <section id="sales-report-workspace" className={`sales-v2-dashboard sales-v2-dashboard-${scope}`} aria-label="Sales and marketing reports"><div className="sales-v2-widget-grid"><SalesReportCard title={scope === 'mine' ? "Today's report" : scope === 'team' ? 'Team submissions today' : 'Organization compliance'} value="View report" onAction={handleViewReport} /><SalesReportCard title={scope === 'mine' ? 'Visits today' : 'Registrations this month'} value="Open workspace" onAction={handleOpenWorkspace} /><SalesReportCard title={scope === 'mine' ? 'Open appointments' : 'Top performers'} value="View detail" onAction={handleViewDetail} /></div><SalesReportWorkspace scope={scope} />{scope === 'team' && <TeamPerformancePanel filters={{ from: '', to: '' }} />}</section>;
}
