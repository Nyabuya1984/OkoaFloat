import {
  accessibleNavSections,
  canAccessDashboardFeature,
  dashboardRouteItems,
  effectiveOrganizationalRoles,
  getRolePreviewLabel,
  getUserDesignation,
  isDashboardFeatureEnabled,
  isGeneralManagerUser,
  isRolePreviewEnabled,
  resolveActiveAssignment,
  ROLES,
} from './navigation';
import { resolveSalesScope } from './components/sales/SalesV2DashboardWidgets';

test('dashboard features remain visible until explicitly disabled', () => {
  expect(isDashboardFeatureEnabled({}, 'debt_collection')).toBe(true);
  expect(isDashboardFeatureEnabled({ debt_collection: false }, 'debt_collection')).toBe(false);
  expect(isDashboardFeatureEnabled({}, 'customer_care')).toBe(true);
  expect(isDashboardFeatureEnabled({ customer_care: false }, 'customer_care')).toBe(false);
});

test('chat is removed from the navigation surface and route list', () => {
  const items = accessibleNavSections(ROLES.EMPLOYEE).flatMap((section) => section.items);

  expect(items.some((item) => item.page === 'chat')).toBe(false);
  expect(dashboardRouteItems.some((item) => item.page === 'chat')).toBe(false);
});

test('role preview is limited to admin users in non-production environments', () => {
  expect(isRolePreviewEnabled({ role: ROLES.SYSTEM_ADMIN }, 'http://localhost:3000')).toBe(true);
  expect(isRolePreviewEnabled({ role: ROLES.SUPER_ADMIN }, 'https://app.example.com')).toBe(false);
  expect(isRolePreviewEnabled({ role: ROLES.EMPLOYEE }, 'http://localhost:3000')).toBe(false);
  expect(getRolePreviewLabel('manager')).toBe('Manager');
});

test.each(['sales_reports', 'debt_collection'])(
  'super admin can access %s when its feature is disabled',
  (feature) => {
  expect(canAccessDashboardFeature(
    { role: ROLES.SUPER_ADMIN, is_superuser: true },
    feature,
    { [feature]: false },
  )).toBe(true);
  },
);

test.each(['sales_reports', 'debt_collection'])(
  'disabled %s remains unavailable to an unassigned employee',
  (feature) => {
    expect(canAccessDashboardFeature(
      { role: ROLES.EMPLOYEE },
      feature,
      { [feature]: false },
    )).toBe(false);
  },
);

test.each(['sales_reports', 'debt_collection'])(
  'disabled %s remains unavailable to system administrators',
  (feature) => {
    expect(canAccessDashboardFeature(
      { role: ROLES.SYSTEM_ADMIN },
      feature,
      { [feature]: false },
    )).toBe(false);
  },
);

test.each([
  ['sales_reports', { organizational_role: 'department_manager', department_name: 'Sales & Marketing' }],
  ['debt_collection', { department_role: 'debt_collection' }],
])('assigned users retain access to disabled %s', (feature, assignment) => {
  expect(canAccessDashboardFeature(
    { role: ROLES.MANAGER, active_assignment: assignment },
    feature,
    { [feature]: false },
  )).toBe(true);
});

test('assignment refresh preserves the authenticated hierarchy while the request is pending', () => {
  const authenticatedAssignment = {
    organizational_role: 'department_manager',
    department_name: 'Sales & Marketing',
  };

  expect(resolveActiveAssignment({ active_assignment: authenticatedAssignment }, null))
    .toBe(authenticatedAssignment);
  expect(resolveActiveAssignment({ active_assignment: authenticatedAssignment }, undefined))
    .toBe(authenticatedAssignment);
  expect(resolveActiveAssignment(
    { active_assignment: authenticatedAssignment },
    { organizational_role: 'team_leader', department_name: 'Sales & Marketing' },
  )).toEqual({ organizational_role: 'team_leader', department_name: 'Sales & Marketing' });
});

test('employee sees Add Client without the TEAM heading', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE, false, {}, { department_role: 'sales' });
  const teamSection = sections.find((section) => section.title === 'TEAM');

  expect(teamSection).toBeTruthy();
  expect(teamSection.hideTitle).toBe(true);
  expect(teamSection.items.some((item) => item.label === 'Add Client' && item.roles.includes(ROLES.EMPLOYEE))).toBe(true);
  expect(teamSection.items.some((item) => item.label === 'Register Client')).toBe(false);
});

test('field agents have no tracking control, and managers see live tracking by position', () => {
  const agentItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    { department_role: 'sales', organizational_role: 'field_agent' },
  ).flatMap((section) => section.items);
  const managerItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    { organizational_role: 'general_manager' },
  ).flatMap((section) => section.items);

  expect(agentItems.some((item) => item.page === 'organization-location')).toBe(false);
  expect(managerItems.some((item) => item.page === 'organization-live')).toBe(true);
});

test('sales dashboard scope follows the operational assignment for managers and general managers', () => {
  expect(resolveSalesScope({ role: 'employee', active_assignment: { organizational_role: 'department_manager', department_name: 'Sales & Marketing' } })).toBe('team');
  expect(resolveSalesScope({ role: 'employee', active_assignment: { organizational_role: 'general_manager', department_name: 'All' } })).toBe('org');
  expect(resolveSalesScope({ role: 'employee', active_assignment: { organizational_role: 'field_agent', department_name: 'Sales & Marketing' } })).toBe('mine');
});

test('general manager is recognized from either the main department or active assignment metadata', () => {
  expect(isGeneralManagerUser({ department: 'All' })).toBe(true);
  expect(isGeneralManagerUser({ active_assignment: { department_name: 'All', organizational_role: 'general_manager' } })).toBe(true);
  expect(isGeneralManagerUser({ department: 'Sales & Marketing' })).toBe(false);
});

test.each([
  [{ active_assignment: { organizational_role: 'general_manager' } }, 'General Manager'],
  [{ active_assignment: { organizational_role: 'department_manager' } }, 'Departmental Manager'],
  [{ active_assignment: { organizational_role: 'team_leader' } }, 'Group Leader'],
  [{ department_role: 'sales', active_assignment: { organizational_role: 'field_agent' } }, 'Sales & Marketing Representative'],
  [{ role: 'system_admin' }, 'System Administrator'],
  [{ role: 'employee' }, 'Employee'],
])('identifies the user designation for dashboard chrome', (user, designation) => {
  expect(getUserDesignation(user)).toBe(designation);
});

test('hides Sales Reports when the role feature is disabled', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE, false, { sales_reports: false });

  expect(sections.flatMap((section) => section.items).some((item) => item.label === 'Add Client')).toBe(false);
});

test('Sales & Marketing managers see performance navigation instead of Add Client', () => {
  const teamLeaderItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    { sales_reports: false },
    { organizational_role: 'team_leader', department_name: 'Sales & Marketing' },
  ).flatMap((section) => section.items);
  const otherDepartmentItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    { sales_reports: false },
    { organizational_role: 'department_manager', department_name: 'Finance' },
  ).flatMap((section) => section.items);

  expect(teamLeaderItems.some((item) => item.page === 'sales-reports' && item.label === 'Sales Performance')).toBe(true);
  expect(teamLeaderItems.some((item) => item.label === 'Add Client')).toBe(false);
  expect(otherDepartmentItems.some((item) => item.page === 'sales-reports')).toBe(false);
});

test.each(['department_manager', 'team_leader'])(
  '%s assignments can access their scoped leave approvals and calendar',
  (organizationalRole) => {
    const items = accessibleNavSections(
      ROLES.EMPLOYEE,
      false,
      {},
      { organizational_role: organizationalRole },
    ).flatMap((section) => section.items);

    expect(items.some((item) => item.page === 'approvals')).toBe(true);
    expect(items.some((item) => item.page === 'calendar')).toBe(true);
    expect(dashboardRouteItems).toEqual(expect.arrayContaining([
      expect.objectContaining({ page: 'approvals', organizationalRoles: expect.arrayContaining([organizationalRole]) }),
      expect.objectContaining({ page: 'calendar', organizationalRoles: expect.arrayContaining([organizationalRole]) }),
    ]));
  },
);

test('a department manager receives scoped Group Leader dashboard roles only when supplied by the backend', () => {
  const fallbackAssignment = {
    organizational_role: 'department_manager',
    department_name: 'Debt Collection',
    effective_organizational_roles: ['department_manager', 'team_leader'],
    group_leader_substitute: true,
  };
  const activeLeaderAssignment = {
    ...fallbackAssignment,
    effective_organizational_roles: ['department_manager'],
    group_leader_substitute: false,
  };
  expect(effectiveOrganizationalRoles(fallbackAssignment))
    .toEqual(['department_manager', 'team_leader']);
  expect(effectiveOrganizationalRoles(activeLeaderAssignment))
    .toEqual(['department_manager']);

  const fallbackPages = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    fallbackAssignment,
  ).flatMap((section) => section.items);
  const activeLeaderPages = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    activeLeaderAssignment,
  ).flatMap((section) => section.items);

  expect(fallbackPages.some((item) => item.page === 'approvals')).toBe(true);
  expect(fallbackPages.some((item) => item.page === 'calendar')).toBe(true);
  expect(activeLeaderPages.some((item) => item.page === 'approvals')).toBe(true);
  expect(activeLeaderPages.some((item) => item.page === 'calendar')).toBe(true);
});

test('sales manager assignment accepts department field and suppresses Add Client', () => {
  const items = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    { organizational_role: 'department_manager', department: 'Sales & Marketing' },
  ).flatMap((section) => section.items);

  expect(items.some((item) => item.page === 'sales-reports' && item.label === 'Sales Performance')).toBe(true);
  expect(items.some((item) => item.label === 'Add Client')).toBe(false);
});

test('general managers get organization performance navigation without an Add Client label', () => {
  const items = accessibleNavSections(
    ROLES.MANAGER,
    false,
    {},
    { organizational_role: 'general_manager', department_name: 'All' },
  ).flatMap((section) => section.items);

  expect(items.some((item) => item.page === 'sales-reports' && item.label === 'Sales & Marketing Performance')).toBe(true);
  expect(items.some((item) => item.label === 'Add Client')).toBe(false);
});

test('hides the profile action from sidebars while retaining sign-out and the profile route', () => {
  const accountSection = accessibleNavSections(ROLES.EMPLOYEE).find((section) => section.title === 'ACCOUNT');

  expect(accountSection.hideTitle).toBe(true);
  expect(accountSection.items.map((item) => item.label)).toEqual(['Sign out']);
  expect(dashboardRouteItems).toEqual(expect.arrayContaining([
    expect.objectContaining({ label: 'Edit profile', path: '/dashboard/profile/edit', page: 'profile' }),
  ]));
});

test('hides Debt Collection when the role feature is disabled', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE, false, { debt_collection: false });

  expect(sections.flatMap((section) => section.items).some((item) => item.label === 'Debt Collection')).toBe(false);
});

test('Debt Collection is limited to assigned employees and general managers', () => {
  const salesItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    { department_role: 'sales' },
  ).flatMap((section) => section.items);
  const debtItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    { department_role: 'debt_collection', organizational_role: 'field_agent' },
  ).flatMap((section) => section.items);
  const generalManagerItems = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    {},
    { organizational_role: 'general_manager' },
  ).flatMap((section) => section.items);

  expect(salesItems.some((item) => item.page === 'debt-collection')).toBe(false);
  expect(debtItems.some((item) => item.page === 'debt-collection')).toBe(true);
  expect(generalManagerItems.some((item) => item.page === 'debt-collection')).toBe(true);
});

test('assigned Debt Collection representatives retain their module when dashboard feature data is disabled', () => {
  const items = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    { debt_collection: false },
    {
      department_role: 'debt_collection',
      organizational_role: 'field_agent',
      department_name: 'Debt Collection',
    },
  ).flatMap((section) => section.items);

  expect(items.some((item) => item.page === 'debt-collection')).toBe(true);
});

test.each(['team_leader', 'department_manager'])(
  'assigned Debt Collection %s retains its module when dashboard feature data is disabled',
  (organizationalRole) => {
    const items = accessibleNavSections(
      ROLES.MANAGER,
      false,
      { debt_collection: false },
      {
        department_role: 'debt_collection',
        organizational_role: organizationalRole,
        department_name: 'Debt Collection',
      },
    ).flatMap((section) => section.items);

    expect(items.some((item) => item.page === 'debt-collection')).toBe(true);
  },
);

test.each([
  [ROLES.SYSTEM_ADMIN, false],
  [ROLES.SUPER_ADMIN, true],
])('%s can navigate to dashboard feature settings', (role, isSuperAdmin) => {
  const sections = accessibleNavSections(role, isSuperAdmin);

  expect(sections.flatMap((section) => section.items)).toEqual(expect.arrayContaining([
    expect.objectContaining({ label: 'Dashboard settings', page: 'dashboard-settings', path: '/dashboard/settings' }),
  ]));
});

test('Super Admin can turn off own Sales Reports and still open dashboard settings', () => {
  const sections = accessibleNavSections(ROLES.SUPER_ADMIN, true, { sales_reports: false });
  const items = sections.flatMap((section) => section.items);

  expect(items.some((item) => item.label === 'Add Client')).toBe(false);
  expect(items.some((item) => item.label === 'Dashboard settings')).toBe(true);
});

test('every sidebar destination has its own absolute route without a fragment', () => {
  const items = accessibleNavSections(ROLES.SUPER_ADMIN, true)
    .flatMap((section) => section.items)
    .filter((item) => item.action !== 'logout');

  expect(items.length).toBeGreaterThan(0);
  items.forEach((item) => {
    expect(item.path).toMatch(/^\//);
    expect(item.path).not.toContain('#');
    expect(item.page).toBeTruthy();
  });
});

test.each([ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN])('%s can see Debt Collection in the admin dashboard links', (role) => {
  const sections = accessibleNavSections(role, true, { debt_collection: true });
  const items = sections.flatMap((section) => section.items);

  expect(items.some((item) => item.label === 'Debt Collection')).toBe(true);
  expect(items.some((item) => item.label === 'Dashboard settings')).toBe(true);
});

test('system administrators have a dedicated administration dashboard route', () => {
  const items = accessibleNavSections(ROLES.SYSTEM_ADMIN, true)
    .flatMap((section) => section.items);

  expect(items).toEqual(expect.arrayContaining([
    expect.objectContaining({ label: 'Admin Dashboard', page: 'admin', path: '/dashboard/admin' }),
  ]));
});

test.each([ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN])('%s can access every admin leave page from navigation', (role) => {
  const items = accessibleNavSections(role, true).flatMap((section) => section.items);

  expect(items).toEqual(expect.arrayContaining([
    expect.objectContaining({ page: 'leave-policies', path: '/dashboard/leave-policies' }),
    expect.objectContaining({ page: 'leave-balances', path: '/dashboard/leave-balances' }),
    expect.objectContaining({ page: 'leave-management-history', path: '/dashboard/leave-management/history' }),
  ]));
});

test('HR administrators have dedicated leave policy, balance, and history pages', () => {
  const items = accessibleNavSections(ROLES.HR)
    .flatMap((section) => section.items);

  expect(items).toEqual(expect.arrayContaining([
    expect.objectContaining({ label: 'Leave policies', page: 'leave-policies', path: '/dashboard/leave-policies' }),
    expect.objectContaining({ label: 'Employee leave balances', page: 'leave-balances', path: '/dashboard/leave-balances' }),
    expect.objectContaining({ label: 'Employee leave history', page: 'leave-management-history', path: '/dashboard/leave-management/history' }),
  ]));
});

test('employees do not see administrative leave pages', () => {
  const items = accessibleNavSections(ROLES.EMPLOYEE)
    .flatMap((section) => section.items);

  expect(items.some((item) => item.page === 'leave-policies')).toBe(false);
  expect(items.some((item) => item.page === 'leave-balances')).toBe(false);
  expect(items.some((item) => item.page === 'leave-management-history')).toBe(false);
});

test.each([ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN])(
  '%s has dedicated customer care routes',
  (role) => {
    const items = accessibleNavSections(role, role === ROLES.SUPER_ADMIN)
      .flatMap((section) => section.items);

    expect(items).toEqual(expect.arrayContaining([
      expect.objectContaining({ page: 'customer-care-logs', path: '/dashboard/customer-care/logs' }),
      expect.objectContaining({ page: 'customer-care-new', path: '/dashboard/customer-care/new' }),
      expect.objectContaining({ page: 'customer-care-customers', path: '/dashboard/customer-care/customers' }),
      expect.objectContaining({ page: 'customer-care-follow-ups', path: '/dashboard/customer-care/follow-ups' }),
    ]));
  },
);

test.each([ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN])(
  '%s can access Customer Care settings',
  (role) => {
    const items = accessibleNavSections(role, true).flatMap((section) => section.items);

    expect(items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: 'Customer Care settings',
        page: 'customer-care-settings',
        path: '/dashboard/customer-care/settings',
      }),
    ]));
  },
);

test.each([ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR])(
  '%s cannot access Customer Care settings',
  (role) => {
    const items = accessibleNavSections(role).flatMap((section) => section.items);

    expect(items.some((item) => item.page === 'customer-care-settings')).toBe(false);
  },
);

test('disabling Customer Care hides its module pages without hiding its admin settings', () => {
  const adminItems = accessibleNavSections(ROLES.SYSTEM_ADMIN, true, { customer_care: false })
    .flatMap((section) => section.items);
  const employeeItems = accessibleNavSections(ROLES.EMPLOYEE, false, { customer_care: false })
    .flatMap((section) => section.items);

  expect(adminItems.some((item) => item.page === 'customer-care-settings')).toBe(true);
  expect(adminItems.some((item) => item.page === 'customer-care-logs')).toBe(false);
  expect(adminItems.some((item) => item.page?.startsWith('okia-'))).toBe(false);
  expect(employeeItems.some((item) => item.page?.startsWith('customer-care-'))).toBe(false);
});

test.each([ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN])(
  '%s has dedicated Okoa Operations pages inside Customer Care navigation',
  (role) => {
    const sections = accessibleNavSections(role, true);
    const operations = sections.find((section) => section.title === 'CUSTOMER CARE');
    const reports = sections.find((section) => section.title === 'CUSTOMER CARE REPORTS');

    expect(operations).toBeTruthy();
    expect(operations.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ page: 'okia-overview', path: '/okia/dashboard' }),
      expect.objectContaining({ page: 'okia-escalations', path: '/okia/escalations' }),
      expect.objectContaining({ page: 'okia-shifts', path: '/okia/shifts' }),
      expect.objectContaining({ page: 'okia-shift-coverage', path: '/okia/shifts/coverage' }),
      expect.objectContaining({ page: 'okia-concerns', path: '/okia/concerns' }),
    ]));
    expect(reports).toBeTruthy();
    expect(reports.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ page: 'okia-gm-resolution', path: '/okia/reports/gm-resolution' }),
      expect.objectContaining({ page: 'okia-gm-attention', path: '/okia/reports/gm-attention' }),
      expect.objectContaining({ page: 'okia-agent-shift-matrix', path: '/okia/reports/agent-shift-matrix' }),
      expect.objectContaining({ page: 'okia-concern-report', path: '/okia/reports/concerns' }),
      expect.objectContaining({ page: 'okia-escalation-report', path: '/okia/reports/escalations' }),
    ]));
    expect(sections.some((section) => section.title === 'OKOA OPERATIONS')).toBe(false);
    expect(sections.some((section) => section.title === 'TEAM' && section.items.some((item) => item.page?.startsWith('okia-')))).toBe(false);
  },
);

test('general managers have cross-department operations and executive reports even when department features are disabled', () => {
  const items = accessibleNavSections(
    ROLES.EMPLOYEE,
    false,
    { sales_reports: false, debt_collection: false, customer_care: false },
    { organizational_role: 'general_manager' },
  ).flatMap((section) => section.items);

  expect(items).toEqual(expect.arrayContaining([
    expect.objectContaining({ page: 'sales-reports', path: '/dashboard/reports/sales' }),
    expect.objectContaining({ page: 'debt-collection', path: '/dashboard/debt-collection' }),
    expect.objectContaining({ page: 'okia-escalations', path: '/okia/escalations' }),
    expect.objectContaining({ page: 'okia-agent-shift-matrix', path: '/okia/reports/agent-shift-matrix' }),
    expect.objectContaining({ page: 'organization-live', path: '/dashboard/organization/live' }),
  ]));
});

test('the GM is recognized by the All department scope before assignment details load', () => {
  const items = accessibleNavSections(
    ROLES.MANAGER,
    false,
    { sales_reports: false, debt_collection: false, customer_care: false },
    { department: 'All' },
  ).flatMap((section) => section.items);

  expect(items).toEqual(expect.arrayContaining([
    expect.objectContaining({ label: 'Executive Overview', page: 'dashboard', path: '/dashboard' }),
    expect.objectContaining({ page: 'okia-escalations', path: '/okia/escalations' }),
    expect.objectContaining({ page: 'sales-reports', path: '/dashboard/reports/sales' }),
    expect.objectContaining({ page: 'debt-collection', path: '/dashboard/debt-collection' }),
  ]));
});

test('employee Apply for Leave route retains employee access when the admin menu shares its path', () => {
  const route = dashboardRouteItems.find((item) => item.path === '/dashboard/leave/apply');

  expect(route.page).toBe('apply-leave');
  expect(route.roles).toContain(ROLES.EMPLOYEE);
  expect(route.roles).toContain(ROLES.HR);
});
