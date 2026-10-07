import {
  BarChart3,
  Briefcase,
  Building2,
  CalendarDays,
  FileBarChart2,
  FileText,
  Hand,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Settings,
  ShieldCheck,
  Users,
} from 'lucide-react';

export const ROLES = {
  EMPLOYEE: 'employee',
  MANAGER: 'manager',
  HR: 'hr_admin',
  SYSTEM_ADMIN: 'system_admin',
  SUPER_ADMIN: 'super_admin',
};

export const normalizeRole = (role) => String(role || 'employee').trim().toLowerCase();

export const isDashboardFeatureEnabled = (features, feature) => features?.[feature] !== false;

export const isSuperAdminUser = (role, isSuperUser = false) => {
  const normalizedRole = normalizeRole(role);
  return normalizedRole === 'super_admin' || normalizedRole === 'system_admin' || isSuperUser === true || (normalizedRole === 'hr_admin' && isSuperUser === true);
};

export const navSections = [
  {
    title: 'MAIN',
    items: [
      { label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Apply for Leave', icon: FileText, path: '/dashboard#apply-leave', section: 'apply-leave', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'My Leave', icon: FileText, path: '/dashboard#my-leave', section: 'my-leave', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'History', icon: FileBarChart2, path: '/dashboard#history', section: 'history', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Handover report', icon: Hand, path: '/dashboard#delegations', section: 'delegations', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Chat', icon: MessageCircle, path: '/dashboard#chat', section: 'chat', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], badge: 'unread' },
    ],
  },
  {
    title: 'TEAM',
    items: [
      { label: 'Approvals', icon: ShieldCheck, path: '/dashboard#approvals', section: 'approvals', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], badge: 'pendingApprovals' },
      { label: 'Team Calendar', icon: CalendarDays, path: '/dashboard#team-calendar', section: 'team-calendar', roles: [ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Sales Reports', icon: BarChart3, path: '/dashboard#sales-reports', section: 'sales-reports', feature: 'sales_reports', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Debt Collection', icon: Briefcase, path: '/dashboard#debt-collection', section: 'debt-collection', feature: 'debt_collection', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'HR',
    items: [
      { label: 'HR Module', icon: Briefcase, path: '/dashboard#hr-module', section: 'hr-module', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'HR Verification', icon: ShieldCheck, path: '/dashboard#approvals', section: 'hr-verification', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Users', icon: Users, path: '/dashboard#managed-users', section: 'users', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Departments', icon: Building2, path: '/dashboard#departments', section: 'departments', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'ACCOUNT',
    items: [
      { label: 'Edit profile', icon: Settings, path: '/dashboard#profile', section: 'profile', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
      { label: 'Sign out', icon: LogOut, path: '/logout', action: 'logout', roles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN] },
    ],
  },
  {
    title: 'ADMINISTRATION',
    items: [
      { label: 'Apply for Leave', icon: FileText, path: '/dashboard#apply-leave', section: 'apply-leave', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Pending Leave Approvals', icon: ShieldCheck, path: '/dashboard#pending-leave-approvals', section: 'approvals', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true, badge: 'pendingApprovals' },
      { label: 'Team Calendar', icon: CalendarDays, path: '/dashboard#team-calendar', section: 'team-calendar', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Sales Reports', icon: BarChart3, path: '/dashboard#sales-reports', section: 'sales-reports', feature: 'sales_reports', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Debt Collection', icon: Briefcase, path: '/dashboard#debt-collection', section: 'debt-collection', feature: 'debt_collection', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Dashboard settings', icon: Settings, path: '/dashboard#dashboard-feature-access', section: 'dashboard-feature-access', roles: [ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Departments', icon: Building2, path: '/dashboard#departments', section: 'departments', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
      { label: 'Employee Directory', icon: Users, path: '/dashboard#managed-users', section: 'users', roles: [ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN], superAdminOnly: true },
    ],
  },
];

export const accessibleNavSections = (role, isSuperAdmin = false, features = {}) => {
  const normalizedRole = normalizeRole(role);
  const canShowAdminOnlyItems = isSuperAdmin || normalizedRole === 'system_admin' || normalizedRole === 'super_admin';

  return navSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => item.roles.includes(normalizedRole) && (canShowAdminOnlyItems ? (item.superAdminOnly || item.label === 'Dashboard' || section.title === 'ACCOUNT') : (!item.superAdminOnly || item.section === 'dashboard-feature-access')) && (!item.feature || isDashboardFeatureEnabled(features, item.feature))),
    }))
    .filter((section) => section.items.length > 0);
};