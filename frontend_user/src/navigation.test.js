import { accessibleNavSections, ROLES } from './navigation';

test('employee can access sales reports in the sidebar menu', () => {
  const sections = accessibleNavSections(ROLES.EMPLOYEE);
  const teamSection = sections.find((section) => section.title === 'TEAM');

  expect(teamSection).toBeTruthy();
  expect(teamSection.items.some((item) => item.label === 'Sales Reports' && item.roles.includes(ROLES.EMPLOYEE))).toBe(true);
});
