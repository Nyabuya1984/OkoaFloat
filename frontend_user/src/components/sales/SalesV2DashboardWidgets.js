import React from 'react';
import { SalesReportCard } from './SalesReportCard';
import { SalesReportWorkspace } from './SalesReportWorkspace';
import TeamPerformancePanel from './TeamPerformancePanel';

const scopeFor = (user) => {
  const role = String(user?.role || 'employee').toLowerCase();
  return user?.is_superuser || role === 'super_admin' || role === 'system_admin' || role === 'hr_admin' ? 'org' : role === 'manager' ? 'team' : 'mine';
};

export default function SalesV2DashboardWidgets({ currentUser, onFileNow, onViewReport, onOpenWorkspace, onViewDetail }) {
  const scope = scopeFor(currentUser);
  const handleViewReport = onViewReport || onFileNow;
  const handleOpenWorkspace = onOpenWorkspace || onFileNow;
  const handleViewDetail = onViewDetail || onFileNow;

  return <section id="sales-report-workspace" className={`sales-v2-dashboard sales-v2-dashboard-${scope}`} aria-label="Sales and marketing reports"><div className="sales-v2-widget-grid"><SalesReportCard title={scope === 'mine' ? "Today's report" : scope === 'team' ? 'Team submissions today' : 'Organization compliance'} value="View report" onAction={handleViewReport} /><SalesReportCard title={scope === 'mine' ? 'Visits today' : 'Registrations this month'} value="Open workspace" onAction={handleOpenWorkspace} /><SalesReportCard title={scope === 'mine' ? 'Open appointments' : 'Top performers'} value="View detail" onAction={handleViewDetail} /></div><SalesReportWorkspace scope={scope} />{scope === 'team' && <TeamPerformancePanel filters={{ from: '', to: '' }} />}</section>;
}
