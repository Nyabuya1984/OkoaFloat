import React, { useEffect, useMemo, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  accessibleNavSections,
  dashboardRouteItems,
  isGeneralManagerUser,
  isSuperAdminUser,
} from '../navigation';
import { organizationApi } from '../services/organizationApi';

const leavePages = [
  'apply-leave',
  'my-leave',
  'history',
  'delegations',
  'chat',
  'approvals',
  'calendar',
  'leave-policies',
  'leave-balances',
  'leave-management-history',
];

const getDepartmentPages = (name) => {
  const department = String(name || '').toLowerCase();
  if (/sales|marketing/.test(department)) return ['sales-reports', 'organization-live'];
  if (/debt|collection/.test(department)) return ['debt-collection'];
  if (/customer|care/.test(department)) {
    return [
      'customer-care-logs',
      'customer-care-new',
      'customer-care-customers',
      'customer-care-follow-ups',
      'okia-overview',
      'okia-escalations',
      'okia-shifts',
      'okia-shift-coverage',
      'okia-concerns',
      'okia-gm-resolution',
      'okia-gm-attention',
      'okia-agent-shift-matrix',
      'okia-concern-report',
      'okia-escalation-report',
    ];
  }
  if (/human resources|\bhr\b/.test(department)) return ['hr-module', 'hr-verification'];
  return [];
};

const Sidebar = ({ isOpen, isCollapsed, onClose, onToggleCollapse, currentUser, onLogout }) => {
  const location = useLocation();
  const isSuperAdmin = isSuperAdminUser(currentUser?.role, currentUser?.is_superuser === true);
  const canConfigureDepartmentPages = String(currentUser?.role || '').toLowerCase() === 'super_admin'
    || currentUser?.is_superuser === true;
  const isGeneralManager = isGeneralManagerUser(currentUser);
  const assignment = currentUser?.active_assignment || {};
  const organizationalRole = assignment.organizational_role || '';
  const isDepartmentManager = organizationalRole === 'department_manager';
  const isTeamLeader = organizationalRole === 'team_leader';
  const departmentRole = String(assignment.department_role || currentUser?.department_role || '').toLowerCase();
  const departmentName = String(
    assignment.department_name
    || assignment.department
    || currentUser?.department_name
    || currentUser?.department
    || '',
  ).toLowerCase();
  const sections = accessibleNavSections(
    currentUser?.role || 'employee',
    isSuperAdmin,
    currentUser?.dashboard_features || {},
    {
      ...currentUser?.active_assignment,
      department: currentUser?.active_assignment?.department || currentUser?.department,
      department_name: currentUser?.active_assignment?.department_name || currentUser?.department_name,
    },
  );
  const allItems = useMemo(
    () => sections.flatMap((section) => section.items).filter((item) => item.action !== 'logout'),
    [sections],
  );
  const pageItem = (page) => (
    isSuperAdmin
      ? dashboardRouteItems.find((item) => item.page === page)
      : allItems.find((item) => item.page === page)
  );
  const [expandedGroup, setExpandedGroup] = useState('');
  const [departments, setDepartments] = useState([]);
  const [departmentsLoading, setDepartmentsLoading] = useState(false);
  const [departmentsError, setDepartmentsError] = useState('');
  const logoutItem = sections.flatMap((section) => section.items).find((item) => item.action === 'logout');
  const LogoutIcon = logoutItem?.icon;

  useEffect(() => {
    if (!isSuperAdmin && !isGeneralManager) {
      setDepartments([]);
      setDepartmentsLoading(false);
      setDepartmentsError('');
      return undefined;
    }

    let active = true;
    const refreshDepartments = () => {
      setDepartmentsLoading(true);
      setDepartments([]);
      setDepartmentsError('');
      const request = canConfigureDepartmentPages
        ? organizationApi.getDepartmentPageConfigurations()
        : organizationApi.getDepartments();
      request
        .then((rows) => {
          if (!Array.isArray(rows)) throw new Error('Department data returned an invalid response.');
          if (active) setDepartments(rows.filter((department) => department && typeof department.name === 'string'));
        })
        .catch((error) => {
          if (active) setDepartmentsError(error.message || 'Unable to load departments.');
        })
        .finally(() => {
          if (active) setDepartmentsLoading(false);
        });
    };
    refreshDepartments();
    window.addEventListener('departments-updated', refreshDepartments);

    return () => {
      active = false;
      window.removeEventListener('departments-updated', refreshDepartments);
    };
  }, [canConfigureDepartmentPages, currentUser?.id, isGeneralManager, isSuperAdmin]);

  const getBadge = (badgeType) => {
    if (badgeType === 'unread') return currentUser?.unread_chat_count;
    if (badgeType === 'pendingApprovals') return currentUser?.pending_approval_count;
    return null;
  };

  const departmentPage = departmentRole.includes('sales') || /sales|marketing/.test(departmentName)
    ? 'sales-reports'
    : departmentRole.includes('debt') || /debt|collection/.test(departmentName)
      ? 'debt-collection'
      : departmentRole.includes('customer') || /customer|care/.test(departmentName)
        ? 'customer-care-logs'
        : null;
  const isSalesDepartment = departmentRole.includes('sales') || /sales|marketing/.test(departmentName);

  let menuGroups;
  if (isSuperAdmin || isGeneralManager || isDepartmentManager || isTeamLeader) {
    const leaveItems = [
      ...leavePages.filter((page) => page !== 'chat' || (!isSuperAdmin && !isGeneralManager)),
    ].map(pageItem).filter(Boolean);
    const departmentGroups = (isSuperAdmin || isGeneralManager)
      ? departments.map((department) => {
        const configuredPages = canConfigureDepartmentPages
          && Array.isArray(department.pages)
          ? department.pages
          : getDepartmentPages(department.name);
        const pages = Array.from(new Set([
          ...getDepartmentPages(department.name),
          ...configuredPages,
        ]));
        const items = pages.map(pageItem).filter(Boolean).map((item) => (
          isSuperAdmin && item.page === 'sales-reports'
            ? { ...item, label: 'Sales & Marketing Performance' }
            : item
        ));
        return {
          key: `department-${department.id}`,
          title: department.name,
          items,
          emptyMessage: 'No department pages are configured.',
        };
      })
      : [{
        title: assignment.department_name || assignment.department || currentUser?.department_name || currentUser?.department || 'My Department',
        items: [departmentPage, ...(isSalesDepartment ? ['organization-live'] : []), 'employees'].map(pageItem).filter(Boolean),
      }];

    menuGroups = [
      { title: 'Leave', items: leaveItems },
      ...departmentGroups,
      {
        title: 'Users',
        items: isSuperAdmin
          ? ['dashboard', 'admin', 'employees', 'hr-module', 'hr-verification', 'organization-history', 'department-transfers', 'chat'].map(pageItem).filter(Boolean)
          : isGeneralManager
            ? ['dashboard', 'employees', 'organization-history', 'department-transfers', 'chat'].map(pageItem).filter(Boolean)
            : [],
      },
      ...(isSuperAdmin ? [{
        title: 'Settings',
        items: ['dashboard-settings', 'departments', 'customer-care-settings'].map(pageItem).filter(Boolean),
      }] : []),
    ].filter((group) => group.items.length || group.emptyMessage);
  } else {
    menuGroups = [
      ...sections.map((section) => ({
        title: section.title,
        hideTitle: section.hideTitle,
        items: section.items.filter((item) => item.action !== 'logout'),
      })),
    ].filter((group) => group.items.length);
  }

  const activeGroupTitle = menuGroups.find((group) => group.items?.some((item) => item.path === location.pathname)
    || group.children?.some((child) => child.items.some((item) => item.path === location.pathname)))?.title;

  useEffect(() => {
    if (activeGroupTitle) setExpandedGroup(activeGroupTitle);
  }, [activeGroupTitle]);

  const renderLink = (item) => {
    const { label, icon: Icon, path, badge } = item;
    const count = getBadge(badge);
    return <NavLink
      key={path}
      to={path}
      end={!['/dashboard/customer-care/customers', '/dashboard/customer-care/logs', '/dashboard/customer-care/settings'].includes(path)}
      className={({ isActive }) => `sidebar-link ${isActive || (item.page === 'dashboard' && location.pathname === '/dashboard/employee-home') ? 'active' : ''}`}
      onClick={onClose}
      aria-label={label}
      title={isCollapsed ? label : undefined}
    >
      <Icon size={16} aria-hidden="true" />
      <span>{label}</span>
      {count ? <span className="sidebar-badge" aria-label={`${count} pending`}>{count}</span> : null}
    </NavLink>;
  };

  return (
    <>
      <button className={`shell-backdrop ${isOpen ? 'visible' : ''}`} aria-label="Close navigation" onClick={onClose} type="button" />
      <aside className={`app-sidebar ${isOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <button className="sidebar-collapse-toggle" type="button" onClick={onToggleCollapse} aria-label="Toggle sidebar">
            <span aria-hidden="true">◀</span>
          </button>
          <div className="brand-mark"><img src="/Okoafloat.png" alt="Okoa Float" className="brand-logo" /></div>
        </div>
        <nav className="sidebar-nav" aria-label="Sidebar navigation">
          {(departmentsLoading || departmentsError || ((isSuperAdmin || isGeneralManager) && departments.length === 0)) && (
            <div className={departmentsError ? 'sidebar-nav-alert' : 'sidebar-nav-status'} role={departmentsError ? 'alert' : 'status'}>
              {departmentsError || (departmentsLoading ? 'Loading departments…' : 'No departments have been created.')}
            </div>
          )}
          {menuGroups.map((group) => (
            <section className="sidebar-menu-group" key={group.key || group.title}>
              {!isCollapsed && !group.hideTitle && <button
                type="button"
                className={`sidebar-group-toggle ${expandedGroup === group.title ? 'is-expanded' : ''}`}
                aria-expanded={expandedGroup === group.title}
                onClick={() => setExpandedGroup((current) => current === group.title ? '' : group.title)}
              >
                <span>{group.title}</span><span aria-hidden="true">{expandedGroup === group.title ? '−' : '+'}</span>
              </button>}
              {(isCollapsed || group.hideTitle || expandedGroup === group.title) && <div className="sidebar-group-items">
                {group.items?.map(renderLink)}
                {group.emptyMessage && !group.items.length && <span className="sidebar-group-note">{group.emptyMessage}</span>}
                {group.children?.map((child) => (
                  <details className="sidebar-subgroup" key={child.title}
                    open={child.items.some((item) => item.path === location.pathname)}>
                    <summary>{child.title}</summary>
                    <div>{child.items.map(renderLink)}</div>
                  </details>
                ))}
              </div>}
            </section>
          ))}
        </nav>
        {logoutItem && (
          <div className="sidebar-footer">
            <button type="button" className="sidebar-link sidebar-button sidebar-logout" onClick={onLogout} aria-label={logoutItem.label}><LogoutIcon size={16} aria-hidden="true" /><span>{logoutItem.label}</span></button>
          </div>
        )}
      </aside>
    </>
  );
};

export default Sidebar;