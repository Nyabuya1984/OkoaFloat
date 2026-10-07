import { accessibleNavSections, isDashboardFeatureEnabled, ROLES } from './navigation';

test('dashboard features remain visible until explicitly disabled', () => {
  expect(isDashboardFeatureEnabled({}, 'debt_collection')).toBe(true);
  expect(isDashboardFeatureEnabled({ debt_collection: false }, 'debt_collection')).toBe(false);
});

test('employee can access sales reports in the sidebar menu', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE);
  const teamSection = sections.find((section) => section.title === 'TEAM');

  expect(teamSection).toBeTruthy();
  expect(teamSection.items.some((item) => item.label === 'Sales Reports' && item.roles.includes(ROLES.EMPLOYEE))).toBe(true);
});

test('hides Sales Reports when the role feature is disabled', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE, false, { sales_reports: false });

  expect(sections.flatMap((section) => section.items).some((item) => item.label === 'Sales Reports')).toBe(false);
});

test('hides Debt Collection when the role feature is disabled', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE, false, { debt_collection: false });

  expect(sections.flatMap((section) => section.items).some((item) => item.label === 'Debt Collection')).toBe(false);
});

test.each([
  [ROLES.SYSTEM_ADMIN, false],
  [ROLES.SUPER_ADMIN, true],
])('%s can navigate to dashboard feature settings', (role, isSuperAdmin) => {
  const sections = accessibleNavSections(role, isSuperAdmin);

  expect(sections.flatMap((section) => section.items)).toEqual(expect.arrayContaining([
    expect.objectContaining({ label: 'Dashboard settings', section: 'dashboard-feature-access' }),
  ]));
});

test('Super Admin can turn off own Sales Reports and still open dashboard settings', () => {
  const sections = accessibleNavSections(ROLES.SUPER_ADMIN, true, { sales_reports: false });
  const items = sections.flatMap((section) => section.items);

  expect(items.some((item) => item.label === 'Sales Reports')).toBe(false);
  expect(items.some((item) => item.label === 'Dashboard settings')).toBe(true);
});

test('system admin users can see Debt Collection in the admin dashboard links', () => {
  const sections = accessibleNavSections(ROLES.SYSTEM_ADMIN, true, { debt_collection: true });
  const items = sections.flatMap((section) => section.items);

  expect(items.some((item) => item.label === 'Debt Collection')).toBe(true);
  expect(items.some((item) => item.label === 'Dashboard settings')).toBe(true);
});
