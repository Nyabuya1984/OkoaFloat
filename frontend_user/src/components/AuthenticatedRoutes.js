import React, { useEffect, useState } from 'react';
import { Navigate, Outlet, Route, Routes, useOutletContext } from 'react-router-dom';
import {
  CallLogDetailPage,
  CustomerCarePage,
  CustomerCareSettingsPage,
  CustomerProfilePage,
} from './CustomerCarePages';
import LeaveDashboard from './LeaveDashboard';
import { EscalationDetailPage, ConcernCategoryDetailPage, OkoaOperationsPage } from './OkoaOperationsPages';
import { LeaveBalancesAdminPage, LeavePolicyPage, LeaveHistoryAdminPage } from './LeaveAdministrationPages';
import AppShell from './AppShell';
import ProtectedRoute from './ProtectedRoute';
import SalesLeadWorkspace from './sales/SalesLeadWorkspace';
import {
  dashboardRouteItems,
  effectiveOrganizationalRoles,
  GENERAL_MANAGER_PAGES,
  isGeneralManagerUser,
  canAccessDashboardFeature,
  isSuperAdminUser,
  normalizeRole,
  resolveActiveAssignment,
  ROLES,
} from '../navigation';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';
import { apiUrl, readJsonResponse } from '../services/apiConfig';
import { organizationApi } from '../services/organizationApi';
import {
  ActiveAssignmentGuard,
  ClientRegistrationPage,
  DepartmentTransferPage,
  HistoricalReportsPage,
  LiveLocationDashboard,
} from './OrganizationPages';

const ShellRoute = ({ currentUser, onLogout, children }) => {
  const [dashboardFeatures, setDashboardFeatures] = useState(() => ({
    sales_reports: isGeneralManagerUser(currentUser),
    debt_collection: isGeneralManagerUser(currentUser),
    customer_care: isGeneralManagerUser(currentUser),
  }));
  const [featureError, setFeatureError] = useState('');
  const [activeAssignment, setActiveAssignment] = useState(null);
  const [assignmentError, setAssignmentError] = useState('');
  const isGeneralManager = isGeneralManagerUser(currentUser);

  useEffect(() => {
    let active = true;
    const refreshFeatures = async () => {
      try {
        const request = () => fetch(apiUrl('/api/admin/dashboard-features'), {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        });
        let response = await request();
        if (response.status === 401 && await refreshAuthToken()) response = await request();
        const payload = await readJsonResponse(
          response,
          'Unable to load dashboard navigation features. The server returned an invalid response.',
        );
        if (!response.ok) throw new Error(payload.error?.message || 'Unable to load dashboard navigation features.');
        if (active && payload.data?.features) {
          const generalManagerFeatures = isGeneralManager
            ? { sales_reports: true, debt_collection: true, customer_care: true }
            : {};
          setDashboardFeatures({ sales_reports: true, debt_collection: true, customer_care: true, ...payload.data.features, ...generalManagerFeatures });
          setFeatureError('');
        }
      } catch (error) {
        if (active) setFeatureError(error.message || 'Unable to load dashboard navigation features.');
      }
    };
    refreshFeatures();
    window.addEventListener('focus', refreshFeatures);
    window.addEventListener('dashboard-feature-access-denied', refreshFeatures);
    return () => {
      active = false;
      window.removeEventListener('focus', refreshFeatures);
      window.removeEventListener('dashboard-feature-access-denied', refreshFeatures);
    };
  }, [isGeneralManager]);

  useEffect(() => {
    let active = true;
    const refreshAssignment = () => organizationApi.getMyAssignment()
      .then((assignment) => {
        if (active) {
          setActiveAssignment(assignment);
          setAssignmentError('');
        }
      })
      .catch((error) => {
        if (active) setAssignmentError(error.message || 'Unable to load active department access.');
      });
    refreshAssignment();
    window.addEventListener('focus', refreshAssignment);
    return () => {
      active = false;
      window.removeEventListener('focus', refreshAssignment);
    };
  }, []);

  return (
    <AppShell
      currentUser={{ ...currentUser, active_assignment: resolveActiveAssignment(currentUser, activeAssignment) }}
      onLogout={onLogout}
      dashboardFeatures={dashboardFeatures}
      featureError={featureError || assignmentError}
    >
      {children || <Outlet context={{ dashboardFeatures, setDashboardFeatures, activeAssignment }} />}
    </AppShell>
  );
};

export const RolePageRoute = ({ currentUser, onUserUpdated, handleLogout, page, roles, organizationalRoles = [] }) => {
  const { dashboardFeatures = {}, activeAssignment } = useOutletContext() || {};
  const assignment = resolveActiveAssignment(currentUser, activeAssignment);
  const role = normalizeRole(currentUser?.role);
  const elevated = isSuperAdminUser(role, currentUser?.is_superuser === true);
  const isGeneralManager = isGeneralManagerUser(currentUser, assignment);
  const effectiveRoles = effectiveOrganizationalRoles(assignment);
  const requiredFeature = page === 'sales-reports'
    ? 'sales_reports'
    : page === 'client-registration'
      ? 'sales_reports'
    : page === 'debt-collection'
      ? 'debt_collection'
      : page.startsWith('customer-care-') || page.startsWith('okia-')
        ? 'customer_care'
        : null;
  const hasAccess = roles.includes(role)
    || organizationalRoles.some((position) => effectiveRoles.includes(position))
    || (isGeneralManager && GENERAL_MANAGER_PAGES.has(page))
    || (elevated && roles.some((allowedRole) => [ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN, ROLES.HR].includes(allowedRole)))
    || (page === 'dashboard' && roles.includes(ROLES.EMPLOYEE) && roles.includes(ROLES.SUPER_ADMIN));

  if (
    requiredFeature
    && !canAccessDashboardFeature(currentUser, requiredFeature, dashboardFeatures, assignment)
  ) {
    return <Navigate to="/dashboard" replace />;
  }
  if (page === 'client-registration') {
    return (
      <ActiveAssignmentGuard roles={['sales']}>
        <ClientRegistrationPage />
      </ActiveAssignmentGuard>
    );
  }
  if (page === 'organization-history') return <HistoricalReportsPage />;

  if (page === 'dashboard' && isGeneralManager) return <GeneralManagerDashboard />;
  if (!hasAccess) {
    const home = elevated
      ? '/dashboard/admin'
      : isGeneralManager
        ? '/okia/dashboard'
        : role === ROLES.HR
          ? '/dashboard/hr'
          : [ROLES.EMPLOYEE, ROLES.MANAGER].includes(role)
            ? '/dashboard/employee-home'
            : '/dashboard';
    return <Navigate to={home} replace />;
  }
  if (page === 'department-transfers') return <DepartmentTransferPage currentUser={currentUser} />;
  if (page === 'organization-live') return <LiveLocationDashboard />;
  if (page === 'leave-policies') return <LeavePolicyPage />;
  if (page === 'leave-balances') return <LeaveBalancesAdminPage />;
  if (page === 'leave-management-history') return <LeaveHistoryAdminPage />;
  if (page === 'customer-care-customer-profile') return <CustomerProfilePage />;
  if (page === 'customer-care-log-detail') return <CallLogDetailPage />;
  if (page === 'customer-care-settings') return <CustomerCareSettingsPage />;
  if (page.startsWith('okia-')) return <OkoaOperationsPage page={page} />;
  if (page.startsWith('customer-care-')) return <CustomerCarePage page={page} currentUser={currentUser} />;
  return <LeaveDashboard page={page} currentUser={{ ...currentUser, active_assignment: assignment }} onUserUpdated={onUserUpdated} handleLogout={handleLogout} />;
};

export function GeneralManagerDashboard() {
  return <>
    <OkoaOperationsPage page="okia-overview" />
    <section className="role-dashboard-panel" aria-label="Telesales lead operations">
      <div className="leave-section-heading">
        <div><p className="leave-kicker">TELESALES</p><h2>Organization lead assignment and call follow-up</h2></div>
      </div>
      <SalesLeadWorkspace canManage />
    </section>
  </>;
}

const pageRouteComponents = new Map(dashboardRouteItems.map(({ path, page, roles, organizationalRoles }) => {
  const DashboardRoutePage = (props) => (
    <RolePageRoute {...props} page={page} roles={roles} organizationalRoles={organizationalRoles} />
  );
  DashboardRoutePage.displayName = `${page}DashboardRoute`;
  return [path, DashboardRoutePage];
}));

const AuthenticatedRoutes = ({ currentUser, onUserUpdated, handleLogout }) => (
  <Routes>
    <Route path="/403" element={<Navigate to="/dashboard" replace />} />
    <Route element={<ProtectedRoute currentUser={currentUser} />}>
      <Route element={<ShellRoute currentUser={currentUser} onLogout={handleLogout} />}>
        {dashboardRouteItems.map(({ path }) => {
          const PageRoute = pageRouteComponents.get(path);
          return (
            <Route
              key={path}
              path={path}
              element={<PageRoute currentUser={currentUser} onUserUpdated={onUserUpdated} handleLogout={handleLogout} />}
            />
          );
        })}
        <Route path="/okia/escalations/:escalationId" element={<EscalationDetailPage />} />
        <Route path="/okia/concerns/:code" element={<ConcernCategoryDetailPage />} />
        <Route
          path="/dashboard/customer-care/customers/:customerId"
          element={(
            <RolePageRoute
              currentUser={currentUser}
              page="customer-care-customer-profile"
              roles={[ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN]}
            />
          )}
        />
        <Route
          path="/dashboard/customer-care/logs/:logId"
          element={(
            <RolePageRoute
              currentUser={currentUser}
              page="customer-care-log-detail"
              roles={[ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.HR, ROLES.SYSTEM_ADMIN, ROLES.SUPER_ADMIN]}
            />
          )}
        />
        <Route
          path="/dashboard/employee-home"
          element={(
            <RolePageRoute
              currentUser={currentUser}
              onUserUpdated={onUserUpdated}
              handleLogout={handleLogout}
              page="dashboard"
              roles={[ROLES.EMPLOYEE, ROLES.MANAGER]}
            />
          )}
        />
        <Route path="/hr" element={<Navigate to="/dashboard" replace />} />
        <Route path="/manager" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Route>
  </Routes>
);

export default AuthenticatedRoutes;
