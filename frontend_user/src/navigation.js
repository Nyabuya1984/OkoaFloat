import {
  BarChart3,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardList,
  Headset,
  FileBarChart2,
  FileText,
  Hand,
  LayoutDashboard,
  LogOut,
  MapPin,
  History,
  Settings,
  Siren,
  ShieldCheck,
  Users,
  Workflow,
  ChartNoAxesCombined,
} from 'lucide-react';

export const ROLES = {
  EMPLOYEE: 'employee',
  MANAGER: 'manager',
  HR: 'hr_admin',
  SYSTEM_ADMIN: 'system_admin',
  SUPER_ADMIN: 'super_admin',
};

export const ROLE_PREVIEW_OPTIONS = [
  { value: ROLES.EMPLOYEE, label: 'Employee' },
  { value: ROLES.MANAGER, label: 'Manager' },
  { value: ROLES.HR, label: 'HR Administrator' },
  { value: ROLES.SYSTEM_ADMIN, label: 'System Administrator' },
  { value: ROLES.SUPER_ADMIN, label: 'Super Admin' },
];

export const getRolePreviewLabel = (role = '') => {
  const normalizedRole = normalizeRole(role);
  return ROLE_PREVIEW_OPTIONS.find((option) => normalizeRole(option.value) === normalizedRole)?.label
    || normalizedRole.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
};

export const isRolePreviewEnabled = (user = {}, hostname = '') => {
  const normalizedRole = normalizeRole(user?.role);
  const isAdmin = normalizedRole === ROLES.SYSTEM_ADMIN || normalizedRole === ROLES.SUPER_ADMIN || user?.is_superuser === true;
  if (!isAdmin) return false;

  const host = String(hostname || (typeof window !== 'undefined' ? window.location.hostname : '')).toLowerCase();
  const isNonProductionEnvironment = host
    ? /localhost|127\.0\.0\.1|staging|test|preview/.test(host)
    : process.env.NODE_ENV !== 'production';
  return isNonProductionEnvironment;
};

export const normalizeRole = (role) => String(role || 'employee').trim().toLowerCase();

export const resolveActiveAssignment = (user, refreshedAssignment) => (
  refreshedAssignment || user?.active_assignment || user?.assignment || null
);

export const effectiveOrganizationalRoles = (assignment = {}) => (
  Array.isArray(assignment.effective_organizational_roles)
    ? assignment.effective_organizational_roles
    : assignment.organizational_role
      ? [assignment.organizational_role]
      : []
);

export const isDashboardFeatureEnabled = (features, feature) => features?.[feature] !== false;

export const isDebtCollectionAssignment = (assignment = {}) => (
  String(assignment.department_role || assignment.departmentRole || '')
    .trim()
    .replace(/[\s-]+/g, '_')
    .toLowerCase() === 'debt_collection'
);

export const isSuperAdminUser = (role, isSuperUser = false) => {
  const normalizedRole = normalizeRole(role);
  return normalizedRole === 'super_admin' || normalizedRole === 'system_admin' || isSuperUser === true || (normalizedRole === 'hr_admin' && isSuperUser === true);
};

export const isGeneralManagerUser = (user = {}, assignment = null) => {
  const assignmentData = user?.active_assignment || user?.assignment || {};
  const candidate = user?.organizational_role
    || user?.organizationalRole
    || assignmentData?.organizational_role
    || assignment?.organizational_role
    || assignment?.role
    || '';
  if (String(candidate).trim().replace(/[\s-]+/g, '_').toLowerCase() === 'general_manager') {
    return true;
  }

  const department = user?.department
    || user?.department_name
    || user?.department_details?.name
    || assignmentData?.department
    || assignmentData?.department_name
    || assignment?.department
    || assignment?.department_name
    || '';
  return String(department).trim().toLowerCase() === 'all';
};

export const canAccessDashboardFeature = (
  user,
  feature,
  features,
  assignment = resolveActiveAssignment(user) || {},
) => {
  if (
    normalizeRole(user?.role) === ROLES.SUPER_ADMIN
    || user?.is_superuser === true
    || isGeneralManagerUser(user, assignment)
  ) {
    return true;
  }

  const organizationalRole = assignment?.organizational_role || '';
  const department = assignment?.department_name || assignment?.department || '';
  if (
    feature === 'sales_reports'
    && ['team_leader', 'department_manager'].includes(organizationalRole)
    && /sales|marketing/i.test(department)
  ) {
    return true;
  }

  if (feature === 'debt_collection' && isDebtCollectionAssignment(assignment)) {
    return true;
  }

  return isDashboardFeatureEnabled(features, feature);
};

export const getUserDesignation = (user = {}) => {
  const assignment = user?.active_assignment || user?.assignment || {};
  const organizationalRole = String(
    user?.organizational_role || assignment.organizational_role || '',
  ).trim().replace(/[\s-]+/g, '_').toLowerCase();
  const department = String(
    user?.department || user?.department_name || assignment.department_name || assignment.department || '',
  ).trim().toLowerCase();
  const departmentRole = String(
    user?.department_role || assignment.department_role || '',
  ).trim().replace(/[\s-]+/g, '_').toLowerCase();
  const role = normalizeRole(user?.role);

  if (isGeneralManagerUser(user)) return 'General Manager';
  if (organizationalRole === 'department_manager') return 'Departmental Manager';
  if (organizationalRole === 'team_leader') return 'Group Leader';
  if (
    departmentRole === 'sales'
    || departmentRole === 'sales_marketing_executive'
    || organizationalRole === 'sales_marketing_executive'
    || (/sales|marketing/.test(department) && organizationalRole === 'field_agent')
  ) return 'Sales & Marketing Representative';
  if (organizationalRole === 'field_agent' && department) {
    const departmentLabel = department.replace(/\b\w/g, (letter) => letter.toUpperCase());
    return `${departmentLabel} Representative`;
  }

  return {
    super_admin: 'Super Admin',
    system_admin: 'System Administrator',
    hr_admin: 'HR Administrator',
    manager: 'Manager',
    employee: 'Employee',
  }[role] || role.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
};

export const GENERAL_MANAGER_PAGES = new Set([
  'dashboard',
  'approvals',
  'calendar',
  'sales-reports',
  'debt-collection',
  'organization-history',
  'customer-care-logs',
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
  'employees',
  'department-transfers',
  'organization-live',
  'profile',
]);

export const navSections = [
  {
    title: 'MAIN',
    items: [
      { label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard', page: 'dashboard', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Apply for Leave', icon: FileText, path: '/dashboard/leave/apply', page: 'apply-leave', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'My Leave', icon: FileText, path: '/dashboard/leave', page: 'my-leave', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'History', icon: FileBarChart2, path: '/dashboard/history', page: 'history', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Handover report', icon: Hand, path: '/dashboard/handover', page: 'delegations', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'TEAM',
    hideTitle: true,
    items: [
      { label: 'Approvals', icon: ShieldCheck, path: '/dashboard/leave/approvals', page: 'approvals', organizationalRoles: ['department_manager', 'team_leader'], roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], badge: 'pendingApprovals' },
      { label: 'Team Calendar', icon: CalendarDays, path: '/dashboard/calendar', page: 'calendar', organizationalRoles: ['department_manager', 'team_leader'], roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Add Client', icon: BarChart3, path: '/dashboard/reports/sales', page: 'sales-reports', feature: 'sales_reports', organizationalRoles: ['team_leader', 'department_manager'], roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Debt Collection', icon: Briefcase, path: '/dashboard/debt-collection', page: 'debt-collection', feature: 'debt_collection', departmentRoles: ['debt_collection'], roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Previous Department Reports', icon: History, path: '/dashboard/organization/history', page: 'organization-history', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'CUSTOMER CARE',
    items: [
      { label: 'Call Logs', icon: Headset, path: '/dashboard/customer-care/logs', page: 'customer-care-logs', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Log Phone Call', icon: FileText, path: '/dashboard/customer-care/new', page: 'customer-care-new', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Customer Directory', icon: Users, path: '/dashboard/customer-care/customers', page: 'customer-care-customers', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Pending Follow-Ups', icon: CalendarDays, path: '/dashboard/customer-care/follow-ups', page: 'customer-care-follow-ups', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Operations Overview', icon: LayoutDashboard, path: '/okia/dashboard', page: 'okia-overview', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Escalations', icon: Siren, path: '/okia/escalations', page: 'okia-escalations', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Shift Schedule', icon: CalendarDays, path: '/okia/shifts', page: 'okia-shifts', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Shift Coverage', icon: Users, path: '/okia/shifts/coverage', page: 'okia-shift-coverage', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Concern Categories', icon: ClipboardList, path: '/okia/concerns', page: 'okia-concerns', feature: 'customer_care', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Customer Care settings', icon: Settings, path: '/dashboard/customer-care/settings', page: 'customer-care-settings', roles: [ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
    ],
  },
  {
    title: 'CUSTOMER CARE REPORTS',
    items: [
      { label: 'GM Resolution Report', icon: ChartNoAxesCombined, path: '/okia/reports/gm-resolution', page: 'okia-gm-resolution', feature: 'customer_care', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'GM Attention Report', icon: Siren, path: '/okia/reports/gm-attention', page: 'okia-gm-attention', feature: 'customer_care', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Agent / Shift Matrix', icon: Workflow, path: '/okia/reports/agent-shift-matrix', page: 'okia-agent-shift-matrix', feature: 'customer_care', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Concern Volume', icon: ChartNoAxesCombined, path: '/okia/reports/concerns', page: 'okia-concern-report', feature: 'customer_care', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Escalation Report', icon: ChartNoAxesCombined, path: '/okia/reports/escalations', page: 'okia-escalation-report', feature: 'customer_care', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'HR',
    items: [
      { label: 'HR Module', icon: Briefcase, path: '/dashboard/hr', page: 'hr-module', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'HR Verification', icon: ShieldCheck, path: '/dashboard/hr/verification', page: 'hr-verification', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Users', icon: Users, path: '/dashboard/employees', page: 'employees', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Departments', icon: Building2, path: '/dashboard/departments', page: 'departments', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Department transfers', icon: Workflow, path: '/dashboard/organization/transfers', page: 'department-transfers', organizationalRoles: ['general_manager', 'department_manager', 'team_leader'], roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'ACCOUNT',
    hideTitle: true,
    items: [
      { label: 'Edit profile', icon: Settings, path: '/dashboard/profile/edit', page: 'profile', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Sign out', icon: LogOut, path: '/logout', action: 'logout', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'ADMINISTRATION',
    items: [
      { label: 'Admin Dashboard', icon: LayoutDashboard, path: '/dashboard/admin', page: 'admin', roles: [ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Apply for Leave', icon: FileText, path: '/dashboard/leave/apply', page: 'apply-leave', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Pending Leave Approvals', icon: ShieldCheck, path: '/dashboard/leave/approvals', page: 'approvals', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true, badge: 'pendingApprovals' },
      { label: 'Team Calendar', icon: CalendarDays, path: '/dashboard/calendar', page: 'calendar', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Add Client', icon: BarChart3, path: '/dashboard/reports/sales', page: 'sales-reports', feature: 'sales_reports', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Debt Collection', icon: Briefcase, path: '/dashboard/debt-collection', page: 'debt-collection', feature: 'debt_collection', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Dashboard settings', icon: Settings, path: '/dashboard/settings', page: 'dashboard-settings', roles: [ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Leave policies', icon: CalendarDays, path: '/dashboard/leave-policies', page: 'leave-policies', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Employee leave balances', icon: Users, path: '/dashboard/leave-balances', page: 'leave-balances', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Employee leave history', icon: FileBarChart2, path: '/dashboard/leave-management/history', page: 'leave-management-history', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Departments', icon: Building2, path: '/dashboard/departments', page: 'departments', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Employee Directory', icon: Users, path: '/dashboard/employees', page: 'employees', organizationalRoles: ['general_manager', 'department_manager', 'team_leader'], roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Agent Live Tracking', icon: MapPin, path: '/dashboard/organization/live', page: 'organization-live', organizationalRoles: ['general_manager', 'department_manager', 'team_leader'], roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
];

export const dashboardRouteItems = [...navSections
  .flatMap((section) => section.items)
  .filter((item) => item.action !== 'logout')
  .reduce((routes, item) => {
    const existing = routes.get(item.path);
    routes.set(item.path, existing
      ? { ...existing, roles: [...new Set([...existing.roles, ...item.roles])] }
      : { ...item, roles: [...item.roles] });
    return routes;
  }, new Map())
  .values()];

export const accessibleNavSections = (role, isSuperAdmin = false, features = {}, assignment = {}) => {
  const normalizedRole = normalizeRole(role);
  const departmentRole = assignment?.department_role || '';
  const organizationalRoles = effectiveOrganizationalRoles(assignment);
  const assignmentDepartment = assignment?.department_name || assignment?.department || '';
  const isGeneralManager = isGeneralManagerUser({}, assignment);
  const isSalesManager = (
    organizationalRoles.some((position) => ['team_leader', 'department_manager'].includes(position))
    && /sales|marketing/i.test(assignmentDepartment)
  );
  const hasManagementRole = organizationalRoles.some((position) => (
    ['team_leader', 'department_manager', 'general_manager'].includes(position)
  ));
  const canShowAdminOnlyItems = isSuperAdmin || normalizedRole === 'system_admin' || normalizedRole === 'super_admin';

  return navSections
    .map((section) => ({
      ...section,
      items: section.items
        .filter((item) => (
          (
            (isGeneralManager && GENERAL_MANAGER_PAGES.has(item.page))
            || item.roles.includes(normalizedRole)
            || (canShowAdminOnlyItems && item.superAdminOnly)
            || item.organizationalRoles?.some((position) => organizationalRoles.includes(position))
          )
          && (
            item.page !== 'sales-reports'
            || isGeneralManager
            || isSalesManager
            || (!isSalesManager && !hasManagementRole)
          )
          && (canShowAdminOnlyItems || !item.superAdminOnly || item.section === 'dashboard-feature-access')
          && (!item.departmentRoles || isGeneralManager || canShowAdminOnlyItems || item.departmentRoles.includes(departmentRole))
          && (!item.organizationalRoles || item.roles.includes(normalizedRole) || canShowAdminOnlyItems || item.organizationalRoles.some((position) => organizationalRoles.includes(position)))
          && (
            isGeneralManager
            || (item.page === 'debt-collection' && isDebtCollectionAssignment(assignment))
            || (
              item.page === 'sales-reports'
              && isSalesManager
            )
            || !item.feature
            || isDashboardFeatureEnabled(features, item.feature)
          )
          && item.page !== 'profile'
        ))
        .map((item) => isGeneralManager && item.page === 'dashboard'
          ? { ...item, label: 'Executive Overview' }
          : isGeneralManager && item.page === 'sales-reports'
            ? { ...item, label: 'Sales & Marketing Performance' }
            : item.page === 'sales-reports'
              && isSalesManager
              ? { ...item, label: 'Sales Performance' }
              : item),
    }))
    .filter((section) => section.items.length > 0);
};