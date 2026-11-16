import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, useOutletContext } from 'react-router-dom';
import {
  cancelLeaveRequest,
  createLeaveRequest,
  decideLeaveRequest,
  getDelegations,
  getLeaveHistory,
  getLeaveOverview,
  getPendingLeaveRequests,
  getTeamCalendar,
  remindHandoverDelegate,
} from '../services/leaveApi';
import { deleteProfilePhoto, updateProfile, uploadProfilePhoto } from '../services/profileApi';
import { getChatMessages, getChatUsers, getUnreadChatCount, markChatMessagesRead, sendChatMessage } from '../services/chatApi';
import { getManagerChatPeers } from '../services/leaveChatUtils';
import './LeaveDashboard.css';
import HandoverAcceptance from './HandoverAcceptance';
import HandoverReportForm from './HandoverReportForm';
import ApprovalRequestCard from './ApprovalRequestCard';
import ManagedUsersPanel from './ManagedUsersPanel';
import HrOperationsPanel from './HrOperationsPanel';
import HrModulePanel from './HrModulePanel';
import SalesDailyReportForm from './SalesDailyReportForm';
import SalesReportsPanel from './SalesReportsPanel';
import SalesReportsPage from './SalesReportsPage';
import LeaveApplicationWizard from './LeaveApplicationWizard';
import TeamCalendarSection from './TeamCalendarSection';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';
import { apiUrl, readJsonResponse } from '../services/apiConfig';
import SalesV2DashboardWidgets from './sales/SalesV2DashboardWidgets';
import DebtCollectionPage from './DebtCollectionPage';
import {
  canAccessDashboardFeature,
  isDebtCollectionAssignment,
  isGeneralManagerUser,
} from '../navigation';
import { LocationSharingAdminPanel, LocationTrackingScheduleSettings } from './OrganizationPages';
import DashboardLanding from './DashboardLanding';

const emptyForm = {
  leave_type_id: '', start_date: '', end_date: '', reason: '', contact_phone: '', contact_email: '',
  handover_user_id: '', handover_report: '',
};
const defaultWorkflowSettings = {
  handover_threshold_days: 2,
  handover_report_threshold_days: 3,
  approval_routing: 'manager_then_hr',
  hr_verification_required: true,
  require_delegate_for_extended_leave: true,
};
const departmentPageOptions = [
  ['sales-reports', 'Sales reports'],
  ['organization-live', 'Live field locations'],
  ['debt-collection', 'Debt Collection'],
  ['customer-care-logs', 'Call Logs'],
  ['customer-care-new', 'Log Phone Call'],
  ['customer-care-customers', 'Customer Directory'],
  ['customer-care-follow-ups', 'Pending Follow-Ups'],
  ['okia-overview', 'Operations Overview'],
  ['okia-escalations', 'Escalations'],
  ['okia-shifts', 'Shift management'],
  ['okia-shift-coverage', 'Shift coverage'],
  ['okia-concerns', 'Customer concerns'],
  ['okia-gm-resolution', 'GM resolutions'],
  ['okia-gm-attention', 'GM attention'],
  ['okia-agent-shift-matrix', 'Agent shift matrix'],
  ['okia-concern-report', 'Concern report'],
  ['okia-escalation-report', 'Escalation report'],
  ['hr-module', 'HR module'],
  ['hr-verification', 'HR verification'],
];
const pagePaths = {
  dashboard: '/dashboard',
  'apply-leave': '/dashboard/leave/apply',
  'my-leave': '/dashboard/leave',
  history: '/dashboard/history',
  delegations: '/dashboard/handover',
  chat: '/dashboard/chat',
  approvals: '/dashboard/leave/approvals',
  'team-calendar': '/dashboard/calendar',
  calendar: '/dashboard/calendar',
  'sales-reports': '/dashboard/reports/sales',
  'debt-collection': '/dashboard/debt-collection',
  'hr-module': '/dashboard/hr',
  'hr-verification': '/dashboard/hr/verification',
  users: '/dashboard/employees',
  employees: '/dashboard/employees',
  departments: '/dashboard/departments',
  profile: '/dashboard/profile/edit',
  'dashboard-feature-access': '/dashboard/settings',
  'dashboard-settings': '/dashboard/settings',
  'leave-policies': '/dashboard/leave-policies',
  'leave-balances': '/dashboard/leave-balances',
  'leave-management-history': '/dashboard/leave-management/history',
};

const formatDate = (value) => {
  if (!value) return '-';
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
  });
};

const statusClass = (status) => `leave-status leave-status-${String(status).toLowerCase()}`;
const organizationRoleLabels = {
  general_manager: 'General Manager',
  department_manager: 'Department Manager',
  team_leader: 'Team Leader',
  field_agent: 'Field Agent / Employee',
};
const managerRoleByPosition = {
  department_manager: 'general_manager',
  team_leader: 'department_manager',
  field_agent: 'team_leader',
};
const departmentRoleFor = (department) => {
  const normalized = String(department || '').toLowerCase();
  if (normalized.includes('sales') || normalized.includes('marketing')) return 'sales';
  if (normalized.includes('debt') || normalized.includes('collection')) return 'debt_collection';
  if (normalized.includes('care')) return 'customer_care';
  return '';
};
const workflowLabel = (request) => ({
  handover_pending: 'Waiting for delegate',
  team_leader_pending: 'Waiting for Team Leader',
  department_manager_pending: 'Waiting for Department Manager',
  general_manager_pending: 'Waiting for General Manager',
  hr_verification: 'Waiting for HR verification',
  approved: 'Approved · awaiting HR',
  completed: 'Completed',
  rejected: 'Rejected',
  deferred: 'Deferred',
}[request.workflow_state] || request.status || 'Submitted');
const workflowStatusClass = (request) => statusClass(request.workflow_state || request.status);

const LeaveDashboard = ({ page = 'dashboard', currentUser, onUserUpdated, handleLogout }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { dashboardFeatures, setDashboardFeatures } = useOutletContext();
  const [overview, setOverview] = useState({ types: [], balances: [], requests: [] });
  const [historyRequests, setHistoryRequests] = useState([]);
  const [delegations, setDelegations] = useState([]);
  const [pendingRequests, setPendingRequests] = useState([]);
  const [calendarRequests, setCalendarRequests] = useState([]);
  const [salesReports, setSalesReports] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);
  const [showLegacyRequestForm, setShowLegacyRequestForm] = useState(false);
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({});
  const [profilePhoto, setProfilePhoto] = useState('');
  const [chatUsers, setChatUsers] = useState([]);
  const [chatPeer, setChatPeer] = useState(() => String(location.state?.chatPeer || ''));
  const [chatTarget, setChatTarget] = useState(() => location.state?.chatTarget || null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatBody, setChatBody] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const [unreadChatCount, setUnreadChatCount] = useState(0);
  const [showChat, setShowChat] = useState(false);
  const activeSection = 'dashboard';
  const [decisionDialog, setDecisionDialog] = useState(null);
  const [decisionComment, setDecisionComment] = useState('');
  const [decisionSignature, setDecisionSignature] = useState('');
  const [openHandoverId, setOpenHandoverId] = useState(null);
  const [requestView, setRequestView] = useState(null);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [selectedCalendarDate, setSelectedCalendarDate] = useState(null);
  const [reportFilters, setReportFilters] = useState({ from: '', to: '', user: '', status: '', leaveType: '', region: '' });
  const [reportMode, setReportMode] = useState('summary');
  const [emailNotifications, setEmailNotifications] = useState(() => window.sessionStorage.getItem('okoa_email_notifications') !== 'false');
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminDepartments, setAdminDepartments] = useState([]);
  const [organizationalCandidates, setOrganizationalCandidates] = useState([]);
  const [adminLeaveTypes, setAdminLeaveTypes] = useState([]);
  const [adminWorkflowSettings, setAdminWorkflowSettings] = useState(defaultWorkflowSettings);
  const [dashboardRoleFeatures, setDashboardRoleFeatures] = useState({ EMPLOYEE: { sales_reports: true, debt_collection: true }, MANAGER: { sales_reports: true, debt_collection: true }, HR_ADMIN: { sales_reports: true, debt_collection: true }, SYSTEM_ADMIN: { sales_reports: true, debt_collection: true }, SUPER_ADMIN: { sales_reports: true, debt_collection: true } });
  const [userDuties, setUserDuties] = useState({});
  const [userDutySearch, setUserDutySearch] = useState('');
  const [securityEvents, setSecurityEvents] = useState([]);
  const [adminAudit, setAdminAudit] = useState([]);
  const [adminHealth, setAdminHealth] = useState({ database: 'unknown', uploads_ready: false, active_users: 0, pending_users: 0 });
  const [systemTestDataBusy, setSystemTestDataBusy] = useState(false);
  const [systemTestDataConfirmation, setSystemTestDataConfirmation] = useState('');
  const [adminDepartmentName, setAdminDepartmentName] = useState('');
  const [editingDepartmentId, setEditingDepartmentId] = useState(null);
  const [departmentPageSettings, setDepartmentPageSettings] = useState({});
  const [savingDepartmentPagesId, setSavingDepartmentPagesId] = useState(null);
  const [leaveTypeForm, setLeaveTypeForm] = useState({ name: '', code: '', is_paid: true, requires_document: false, default_days_per_year: 21 });
  const [editingLeaveTypeId, setEditingLeaveTypeId] = useState(null);
  const [editingAdminUserId, setEditingAdminUserId] = useState(null);
  const [adminUserForm, setAdminUserForm] = useState({ full_name: '', email: '', phone_number: '', department: '', job_position_title: '', employer: '', role: 'employee', is_superuser: false });
  const [adminForm, setAdminForm] = useState({
    full_name: '',
    email: '',
    phone_number: '',
    password: '',
    department: '',
    role: 'employee',
    job_position_title: 'Staff',
    organizational_role: 'field_agent',
    department_role: '',
    manager_id: '',
    employer: 'Okoa Float Ltd',
    is_superuser: false,
  });

  const role = String(currentUser?.role || 'employee').toLowerCase();
  const organizationalRole = currentUser?.active_assignment?.organizational_role || '';
  const isDepartmentManagerTier = organizationalRole === 'department_manager';
  const isTeamLeaderTier = organizationalRole === 'team_leader';
  const dashboardTier = isGeneralManagerUser(currentUser) ? 'general_manager'
    : isDepartmentManagerTier ? 'department_manager'
      : isTeamLeaderTier ? 'team_leader' : 'employee';
  const assignedDepartment = currentUser?.active_assignment?.department_name
    || currentUser?.active_assignment?.department
    || currentUser?.department
    || '';
  const isOrgApprover = ['general_manager', 'department_manager', 'team_leader'].includes(organizationalRole);
  const canAssignEmployeeDuties = role === 'super_admin' || currentUser?.is_superuser === true;
  const isManager = role === 'manager';
  const isHr = ['hr_admin', 'system_admin'].includes(role);
  const isSuperAdmin = role === 'super_admin' || currentUser?.is_superuser === true || role === 'system_admin' || (role === 'hr_admin' && currentUser?.is_superuser === true);
  const canConfigureDepartmentPages = role === 'super_admin' || currentUser?.is_superuser === true;
  const managerRole = managerRoleByPosition[adminForm.organizational_role];
  const managerCandidates = organizationalCandidates.filter((candidate) => (
    candidate.organizational_role === managerRole
    && (
      adminForm.organizational_role === 'department_manager'
      || candidate.department_id === adminDepartments.find(
        (department) => department.name === adminForm.department,
      )?.id
    )
  ));
  const canManageLeaveSettings = ['hr_admin', 'system_admin', 'super_admin'].includes(role)
    || currentUser?.is_superuser === true;
  const canApprove = isHr || isSuperAdmin || isOrgApprover;
  const canEditOperations = isManager || isHr || isSuperAdmin
    || ['department_manager', 'team_leader'].includes(organizationalRole);
  const isSalesEmployee = role === 'employee'
    && organizationalRole === 'field_agent'
    && (
      String(currentUser?.active_assignment?.department_role || currentUser?.department_role || '').toLowerCase() === 'sales'
      || /sales|marketing/i.test(assignedDepartment)
    )
    && !isSuperAdmin;
  const filteredDutyUsers = adminUsers.filter((user) => {
    const query = userDutySearch.trim().toLowerCase();
    return !query || [user.full_name, user.email, user.employee_id].some((value) => String(value || '').toLowerCase().includes(query));
  });
  const canViewEmployeePerformance = isGeneralManagerUser(currentUser)
    || (
      ['team_leader', 'department_manager'].includes(organizationalRole)
      && /sales|marketing/i.test(assignedDepartment)
    );
  const canAccessSalesReports = canViewEmployeePerformance
    || (
      !isDepartmentManagerTier
      && !isTeamLeaderTier
      && canAccessDashboardFeature(currentUser, 'sales_reports', dashboardFeatures)
      && (isSalesEmployee || isManager || isHr || isSuperAdmin)
    );
  const hasDebtCollectionAssignment = isDebtCollectionAssignment({
    ...currentUser?.active_assignment,
    department_role: currentUser?.active_assignment?.department_role || currentUser?.department_role,
  });
  const canAccessDebtCollection = hasDebtCollectionAssignment
    || (canAccessDashboardFeature(currentUser, 'debt_collection', dashboardFeatures)
      && (isGeneralManagerUser(currentUser) || isHr || isSuperAdmin));

  useEffect(() => {
    if (page !== 'legacy' || !isSuperAdmin) return undefined;
    let active = true;
    fetch(apiUrl('/api/organization/transfer-candidates'), {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    })
      .then(async (response) => {
        const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
        if (!response.ok) throw new Error(payload.error?.message || 'Unable to load organizational managers.');
        return payload.data || [];
      })
      .then((candidates) => {
        if (active) setOrganizationalCandidates(candidates);
      })
      .catch((error) => {
        if (active) setMessage({ type: 'error', text: error.message });
      });
    return () => { active = false; };
  }, [page, isSuperAdmin]);

  useEffect(() => {
    if (page === 'sales-reports' && !canAccessSalesReports) {
      navigate('/dashboard', { replace: true });
    }
    if (page === 'debt-collection' && !canAccessDebtCollection) {
      navigate('/dashboard', { replace: true });
    }
  }, [canAccessDebtCollection, canAccessSalesReports, navigate, page]);

  const openSalesReports = () => {
    if (!canAccessSalesReports) {
      navigate('/dashboard', { replace: true });
      return;
    }
    navigate(pagePaths['sales-reports']);
  };

  const navigateToSection = (section) => {
    if (section === 'sales-reports' && !canAccessSalesReports) {
      navigate('/dashboard', { replace: true });
      return;
    }
    if (section === 'debt-collection' && !canAccessDebtCollection) {
      navigate('/dashboard', { replace: true });
      return;
    }
    if (section === 'logout') {
      handleLogout();
      return;
    }
    if (pagePaths[section]) navigate(pagePaths[section]);
  };

  const loadPageData = async () => {
    setLoading(true);
    setMessage(null);
    try {
      if (['dashboard', 'my-leave', 'apply-leave'].includes(page)) {
        setOverview(await getLeaveOverview());
      }
      if (page === 'history') {
        setHistoryRequests((await getLeaveHistory()).data || []);
      }
      if (page === 'delegations') {
        setDelegations((await getDelegations()).data || []);
      }
      if (['apply-leave', 'delegations'].includes(page)) {
        const peers = await getChatUsers();
        setChatUsers(peers.data || []);
        if (!chatPeer && peers.data?.[0]) setChatPeer(String(peers.data[0].id));
      }
      if (['approvals', 'hr-verification'].includes(page)) {
        setPendingRequests((await getPendingLeaveRequests()).data || []);
      }
      if (page === 'dashboard' && (isGeneralManagerUser(currentUser) || isDepartmentManagerTier || isTeamLeaderTier)) {
        setPendingRequests((await getPendingLeaveRequests()).data || []);
      }
      if (page === 'calendar') {
        setCalendarRequests((await getTeamCalendar()).data || []);
      }
      if (page === 'sales-reports') {
        const response = await fetch(apiUrl('/api/sales/reports'), { headers: { Authorization: `Bearer ${getAuthToken()}` } });
        const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
        if (!response.ok) throw new Error(payload.error?.message || 'Unable to load sales reports.');
        setSalesReports(payload.data || []);
      }
      if (page === 'chat') {
        const unread = await getUnreadChatCount();
        setUnreadChatCount(Number(unread.data?.count || 0));
      }
      if (['admin', 'employees', 'departments', 'dashboard-settings', 'hr-module'].includes(page)) {
        await loadRouteAdminData(page);
      }
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Unable to load this page.' });
    } finally {
      setLoading(false);
    }
  };

  const loadData = async () => {
    if (page !== 'legacy') return loadPageData();
    setLoading(true);
    setMessage(null);
    try {
      const [data, chatData, historyData, delegationData] = await Promise.all([
        getLeaveOverview(),
        getChatUsers().catch(() => ({ data: [] })),
        getLeaveHistory(),
        getDelegations(),
      ]);
      setOverview(data);
      setHistoryRequests(historyData.data || []);
      setDelegations(delegationData.data || []);
      setChatUsers(chatData.data || []);
      if (canApprove || isSalesEmployee) {
        fetch(apiUrl('/api/sales/reports'), { headers: { Authorization: `Bearer ${getAuthToken()}` } }).then((response) => readJsonResponse(response, 'The server responded unexpectedly.')).then((payload) => setSalesReports(payload.data || [])).catch(() => {});
      }
      getUnreadChatCount().then((unread) => setUnreadChatCount(Number(unread.data?.count || 0))).catch(() => {});
      if (!chatPeer && (chatData.data || []).length > 0) {
        setChatPeer(String((chatData.data || [])[0].id));
      }
      if (canApprove) {
        try {
          const [pending, calendar] = await Promise.all([getPendingLeaveRequests(), getTeamCalendar()]);
          setPendingRequests(pending.data || []);
          setCalendarRequests(calendar.data || []);
        } catch (error) {
          if (!error.message.toLowerCase().includes('forbidden')) throw error;
        }
      }
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setLoading(false);
    }
  };

  const loadRouteAdminData = async (requestedPage) => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${getAuthToken()}` };
      const requests = [];
      if (['employees', 'admin', 'hr-module'].includes(requestedPage)) {
        requests.push(['users', fetch(apiUrl('/api/auth/admin/users'), { headers })]);
      }
      if (['admin', 'employees', 'departments', 'hr-module'].includes(requestedPage)) {
        requests.push(['departments', fetch(apiUrl('/api/auth/admin/departments'), { headers })]);
      }
      if (requestedPage === 'admin') {
        requests.push(['health', fetch(apiUrl('/api/auth/admin/system-health'), { headers })]);
      }
      if (requestedPage === 'employees' && canAssignEmployeeDuties) {
        requests.push(['duties', fetch(apiUrl('/api/admin/user-duties'), { headers })]);
      }
      if (requestedPage === 'dashboard-settings') {
        requests.push(['features', fetch(apiUrl('/api/admin/dashboard-features'), { headers })]);
      }
      if (requestedPage === 'departments' && canConfigureDepartmentPages) {
        requests.push(['departmentPages', fetch(apiUrl('/api/admin/department-pages'), { headers })]);
      }
      const payloads = Object.fromEntries(await Promise.all(requests.map(async ([key, request]) => {
        const response = await request;
        const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
        if (!response.ok) throw new Error(payload.error?.message || `Unable to load ${key}.`);
        return [key, payload];
      })));
      if (payloads.users) setAdminUsers(payloads.users.data || []);
      if (payloads.departments) setAdminDepartments(payloads.departments.data || []);
      if (payloads.departmentPages?.data) {
        setDepartmentPageSettings(Object.fromEntries(
          payloads.departmentPages.data.map((department) => [department.id, department.pages || []]),
        ));
      }
      if (payloads.health) setAdminHealth(payloads.health.data || { database: 'unknown', uploads_ready: false, active_users: 0, pending_users: 0 });
      if (payloads.duties?.data) setUserDuties(payloads.duties.data);
      if (payloads.features?.data?.features) {
        setDashboardFeatures({ sales_reports: true, debt_collection: true, ...payloads.features.data.features });
        if (payloads.features.data.roles) setDashboardRoleFeatures(payloads.features.data.roles);
      }
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Unable to load this page.' });
    } finally {
      setLoading(false);
    }
  };

  const runSystemTestDataAction = async (action) => {
    const deleting = action === 'delete';
    if (deleting && systemTestDataConfirmation !== 'DELETE SYSTEM TEST DATA') {
      setMessage({ type: 'error', text: 'Enter DELETE SYSTEM TEST DATA to confirm removal.' });
      return;
    }

    setSystemTestDataBusy(true);
    try {
      const response = await fetch(apiUrl('/api/admin/system-test-data'), {
        method: deleting ? 'DELETE' : 'POST',
        headers: {
          Authorization: `Bearer ${getAuthToken()}`,
          ...(deleting ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(deleting ? { body: JSON.stringify({ confirmation: systemTestDataConfirmation }) } : {}),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update system test data.');
      setMessage({ type: 'success', text: payload.data?.message || 'System test data updated.' });
      setSystemTestDataConfirmation('');
      await loadRouteAdminData('admin');
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Unable to update system test data.' });
    } finally {
      setSystemTestDataBusy(false);
    }
  };

  const loadSuperAdminData = async () => {
    if (page !== 'legacy') return loadRouteAdminData(page);
    try {
      const token = getAuthToken();
      const [usersResponse, departmentsResponse, leaveTypesResponse, workflowResponse, securityResponse, auditResponse, healthResponse, featuresResponse, dutiesResponse] = await Promise.all([
        fetch(apiUrl('/api/auth/admin/users'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/auth/admin/departments'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/auth/admin/leave-types'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/auth/admin/workflow-settings'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/auth/admin/security-events'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/auth/admin/audit'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/auth/admin/system-health'), { headers: { Authorization: `Bearer ${token}` } }),
        fetch(apiUrl('/api/admin/dashboard-features'), { headers: { Authorization: `Bearer ${token}` } }),
        canAssignEmployeeDuties
          ? fetch(apiUrl('/api/admin/user-duties'), { headers: { Authorization: `Bearer ${token}` } })
          : Promise.resolve(null),
      ]);
      const [usersPayload, departmentsPayload, leaveTypesPayload, workflowPayload, securityPayload, auditPayload, healthPayload, featuresPayload, dutiesPayload] = await Promise.all([
        usersResponse.json(),
        departmentsResponse.json(),
        leaveTypesResponse.json(),
        workflowResponse.json(),
        securityResponse.json(),
        auditResponse.json(),
        healthResponse.json(),
        featuresResponse.json(),
        dutiesResponse ? dutiesResponse.json() : Promise.resolve(null),
      ]);
      setAdminUsers(usersPayload.data || []);
      setAdminDepartments(departmentsPayload.data || []);
      setAdminLeaveTypes(leaveTypesPayload.data || []);
      setAdminWorkflowSettings(workflowPayload.data || defaultWorkflowSettings);
      setSecurityEvents(securityPayload.data || []);
      setAdminAudit(auditPayload.data || []);
      setAdminHealth(healthPayload.data || { database: 'unknown', uploads_ready: false, active_users: 0, pending_users: 0 });
      if (dutiesPayload?.data) setUserDuties(dutiesPayload.data);
      if (featuresPayload.data) {
        setDashboardFeatures({ sales_reports: true, debt_collection: true, ...(featuresPayload.data.features || {}) });
        setDashboardRoleFeatures(
          featuresPayload.data.roles || {
            EMPLOYEE: { sales_reports: true, debt_collection: true },
            MANAGER: { sales_reports: true, debt_collection: true },
            HR_ADMIN: { sales_reports: true, debt_collection: true },
            SYSTEM_ADMIN: { sales_reports: true, debt_collection: true },
            SUPER_ADMIN: { sales_reports: true, debt_collection: true },
          }
        );
      }
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Unable to load system administration data.' });
    }
  };

  const updateDashboardRoleFeature = async (roleName, feature, enabled) => {
    try {
      const response = await fetch(apiUrl('/api/admin/dashboard-features'), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify({ role: roleName, feature, enabled }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update dashboard feature.');
      const label = feature === 'debt_collection' ? 'Debt Collection' : 'Sales Reports';
      setDashboardRoleFeatures((current) => ({
        ...current,
        [roleName]: { ...current[roleName], [feature]: enabled },
      }));
      if (roleName === role.toUpperCase()) {
        setDashboardFeatures((current) => ({ ...current, [feature]: enabled }));
      }
      setMessage({ type: 'success', text: `${label} ${enabled ? 'enabled' : 'disabled'} for ${roleName.replace('_', ' ').toLowerCase()} users.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  useEffect(() => {
    if (page !== 'legacy') return undefined;
    let active = true;
    const refreshFeatures = () => {
      const request = () => fetch(apiUrl('/api/admin/dashboard-features'), { headers: { Authorization: `Bearer ${getAuthToken()}` } });
      request()
        .then(async (response) => {
          if (response.status === 401 && await refreshAuthToken()) return request();
          return response;
        })
        .then(async (response) => {
          const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
          if (!response.ok) {
            const message = response.status === 401
              ? 'Your session has expired. Please sign in again to load dashboard features.'
              : payload.error?.message || 'Unable to load dashboard features.';
            throw new Error(message);
          }
          return payload;
        })
        .then((payload) => {
          if (!active || !payload.data?.features) return;
          setDashboardFeatures({ sales_reports: true, debt_collection: true, ...payload.data.features });
          if (payload.data.roles) setDashboardRoleFeatures({
            EMPLOYEE: { sales_reports: true, debt_collection: true, ...(payload.data.roles.EMPLOYEE || {}) },
            MANAGER: { sales_reports: true, debt_collection: true, ...(payload.data.roles.MANAGER || {}) },
            HR_ADMIN: { sales_reports: true, debt_collection: true, ...(payload.data.roles.HR_ADMIN || {}) },
            SYSTEM_ADMIN: { sales_reports: true, debt_collection: true, ...(payload.data.roles.SYSTEM_ADMIN || {}) },
            SUPER_ADMIN: { sales_reports: true, debt_collection: true, ...(payload.data.roles.SUPER_ADMIN || {}) },
          });
        })
        .catch((error) => {
          if (active) setMessage({ type: 'error', text: error.message || 'Unable to load dashboard features.' });
        });
    };
    refreshFeatures();
    window.addEventListener('focus', refreshFeatures);
    window.addEventListener('dashboard-feature-access-denied', refreshFeatures);
    return () => {
      active = false;
      window.removeEventListener('focus', refreshFeatures);
      window.removeEventListener('dashboard-feature-access-denied', refreshFeatures);
    };
  }, [page, setDashboardFeatures]);

  const createDepartment = async (event) => {
    event.preventDefault();
    try {
      const token = getAuthToken();
      const isEditing = Boolean(editingDepartmentId);
      const response = await fetch(apiUrl(`/api/auth/admin/departments${isEditing ? `/${editingDepartmentId}` : ''}`), {
        method: isEditing ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: adminDepartmentName }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to save department.');
      setAdminDepartmentName('');
      setEditingDepartmentId(null);
      await loadSuperAdminData();
      window.dispatchEvent(new Event('departments-updated'));
      setMessage({ type: 'success', text: isEditing ? 'Department updated successfully.' : 'Department created successfully.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const deleteDepartment = async (departmentId) => {
    try {
      const token = getAuthToken();
      const response = await fetch(apiUrl(`/api/auth/admin/departments/${departmentId}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to delete department.');
      setEditingDepartmentId(null);
      setAdminDepartmentName('');
      await loadSuperAdminData();
      window.dispatchEvent(new Event('departments-updated'));
      setMessage({ type: 'success', text: payload.message || 'Department deleted.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const saveDepartmentPages = async (departmentId) => {
    setSavingDepartmentPagesId(departmentId);
    try {
      const response = await fetch(apiUrl(`/api/admin/departments/${departmentId}/pages`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: ['Bearer', getAuthToken()].join(' '),
        },
        body: JSON.stringify({ pages: departmentPageSettings[departmentId] || [] }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to save department pages.');
      setDepartmentPageSettings((current) => ({
        ...current,
        [departmentId]: payload.data.pages || [],
      }));
      window.dispatchEvent(new Event('departments-updated'));
      setMessage({ type: 'success', text: `Pages configured for ${payload.data.name}.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Unable to save department pages.' });
    } finally {
      setSavingDepartmentPagesId(null);
    }
  };

  const saveLeaveType = async (event) => {
    event.preventDefault();
    try {
      const token = getAuthToken();
      const method = editingLeaveTypeId ? 'PATCH' : 'POST';
      const url = editingLeaveTypeId ? `/api/auth/admin/leave-types/${editingLeaveTypeId}` : '/api/auth/admin/leave-types';
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          ...leaveTypeForm,
          default_days_per_year: Number(leaveTypeForm.default_days_per_year || 0),
        }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to save leave type.');
      setLeaveTypeForm({ name: '', code: '', is_paid: true, requires_document: false, default_days_per_year: 21 });
      setEditingLeaveTypeId(null);
      await loadSuperAdminData();
      setMessage({ type: 'success', text: editingLeaveTypeId ? 'Leave type updated.' : 'Leave type created.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const deleteLeaveType = async (leaveTypeId) => {
    try {
      const token = getAuthToken();
      const response = await fetch(apiUrl(`/api/auth/admin/leave-types/${leaveTypeId}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to delete leave type.');
      setEditingLeaveTypeId(null);
      setLeaveTypeForm({ name: '', code: '', is_paid: true, requires_document: false, default_days_per_year: 21 });
      await loadSuperAdminData();
      setMessage({ type: 'success', text: payload.message || 'Leave type deleted.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const saveWorkflowSettings = async (event) => {
    event.preventDefault();
    try {
      const token = getAuthToken();
      const response = await fetch(apiUrl('/api/auth/admin/workflow-settings'), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(adminWorkflowSettings),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to update workflow settings.');
      setAdminWorkflowSettings(payload.data || defaultWorkflowSettings);
      setMessage({ type: 'success', text: payload.message || 'Workflow settings updated.' });
      await loadSuperAdminData();
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const sanitizeAdminRoleAssignment = (roleValue, isSuperUserValue = false) => {
    const normalized = String(roleValue || 'employee').trim().toLowerCase();
    const allowedRoles = ['employee', 'manager', 'hr_admin', 'system_admin'];
    const nextRole = normalized === 'super_admin' ? 'system_admin' : allowedRoles.includes(normalized) ? normalized : 'employee';
    return { role: nextRole, is_superuser: false };
  };

  const createAdminUser = async (event) => {
    event.preventDefault();
    if (
      ['field_agent', 'team_leader', 'department_manager'].includes(adminForm.organizational_role)
      && !adminForm.department_role
    ) {
      setMessage({ type: 'error', text: 'Select the operational role matching the chosen department.' });
      return;
    }
    if (adminForm.organizational_role !== 'general_manager' && !adminForm.manager_id) {
      setMessage({ type: 'error', text: 'Select the employee’s manager in the organizational hierarchy.' });
      return;
    }
    try {
      const token = getAuthToken();
      const sanitized = sanitizeAdminRoleAssignment(adminForm.role, adminForm.is_superuser);
      const response = await fetch(apiUrl('/api/auth/admin/users'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ...adminForm,
          official_email: adminForm.email,
          ...sanitized,
          is_superuser: false,
        }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to create user.');
      setAdminForm({
        full_name: '',
        email: '',
        phone_number: '',
        password: '',
        department: '',
        role: 'employee',
        job_position_title: organizationRoleLabels.field_agent,
        organizational_role: 'field_agent',
        department_role: '',
        manager_id: '',
        employer: 'Okoa Float Ltd',
        is_superuser: false,
      });
      setMessage({ type: 'success', text: 'User created successfully.' });
      await loadSuperAdminData();
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const updateAdminUserRole = async (userId, nextRole, isSuperUser) => {
    try {
      const token = getAuthToken();
      const sanitized = sanitizeAdminRoleAssignment(nextRole, isSuperUser);
      const response = await fetch(apiUrl(`/api/auth/admin/users/${userId}/role`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ role: sanitized.role, is_superuser: false }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to update role.');
      setMessage({ type: 'success', text: payload.message || 'Role updated successfully.' });
      await loadSuperAdminData();
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const updateUserDuty = async (userId, duty, enabled) => {
    const duties = new Set(userDuties[userId] || []);
    if (enabled) duties.add(duty);
    else duties.delete(duty);
    try {
      const response = await fetch(apiUrl(`/api/admin/users/${userId}/duties`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify({ duties: [...duties] }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update employee duties.');
      setUserDuties((current) => ({ ...current, [userId]: payload.data.duties }));
      setMessage({ type: 'success', text: `Employee duties updated for ${adminUsers.find((user) => user.id === userId)?.full_name || 'employee'}.` });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const startAdminUserEdit = (user) => {
    const sanitizedRole = sanitizeAdminRoleAssignment(user.role, user.is_superuser).role;
    setEditingAdminUserId(user.id);
    setAdminUserForm({
      full_name: user.full_name || '', email: user.email || '',
      phone_number: user.phone_number || '',
      department: user.department || user.department_details?.name || '', job_position_title: user.job_position_title || '',
      employer: user.employer || '', role: sanitizedRole, is_superuser: false,
      status: user.account_status === 'pending' ? 'pending' : (user.state || (user.is_active ? 'active' : 'deactivated')),
    });
  };

  const saveAdminUser = async (event) => {
    event.preventDefault();
    try {
      const token = getAuthToken();
      const sanitized = sanitizeAdminRoleAssignment(adminUserForm.role, adminUserForm.is_superuser);
      const { status, ...profileFields } = adminUserForm;
      const originalUser = adminUsers.find((user) => user.id === editingAdminUserId);
      const originalStatus = originalUser?.account_status === 'pending'
        ? 'pending'
        : (originalUser?.state || (originalUser?.is_active ? 'active' : 'deactivated'));
      const response = await fetch(apiUrl(`/api/auth/admin/users/${editingAdminUserId}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          ...profileFields,
          ...sanitized,
          is_superuser: false,
        }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to update user.');
      if (editingAdminUserId !== currentUser.id && status !== originalStatus) {
        const statusResponse = await fetch(apiUrl(`/api/auth/admin/users/${editingAdminUserId}/status`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: ['Bearer', token].join(' ') },
          body: JSON.stringify({ status }),
        });
        const statusPayload = await statusResponse.json();
        if (!statusResponse.ok) {
          throw new Error(statusPayload?.error?.message || 'Profile saved, but account status could not be updated.');
        }
      }
      setEditingAdminUserId(null);
      await loadSuperAdminData();
      setMessage({ type: 'success', text: 'User updated successfully.' });
    } catch (error) { setMessage({ type: 'error', text: error.message }); }
  };

  const updateAdminUserStatus = async (userId, status) => {
    try {
      const response = await fetch(apiUrl(`/api/auth/admin/users/${userId}/status`), {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify({ status }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to update user status.');
      setEditingAdminUserId(null);
      await loadSuperAdminData();
      setMessage({ type: 'success', text: payload.message || 'User status updated.' });
    } catch (error) { setMessage({ type: 'error', text: error.message }); }
  };

  const deleteAdminUser = async (userId) => {
    if (!window.confirm('Delete this user account? This action cannot be undone from this screen.')) return;
    try {
      const token = getAuthToken();
      const response = await fetch(apiUrl(`/api/auth/admin/users/${userId}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload?.error?.message || 'Unable to delete user.');
      await loadSuperAdminData();
      setMessage({ type: 'success', text: payload.message || 'User deleted.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  // Load only the resource set required by this route.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadData(); }, [page]);
  useEffect(() => {
    if (page !== 'chat') return undefined;
    const refreshUnreadCount = () => getUnreadChatCount().then((data) => setUnreadChatCount(Number(data.data?.count || 0))).catch(() => {});
    refreshUnreadCount();
    const timer = window.setInterval(refreshUnreadCount, 10000);
    return () => window.clearInterval(timer);
  }, [page]);
  useEffect(() => { setShowChat(page === 'chat'); }, [page]);

  const updateForm = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const workingDays = () => {
    if (!form.start_date || !form.end_date) return 0;
    const start = new Date(`${form.start_date}T00:00:00`);
    const end = new Date(`${form.end_date}T00:00:00`);
    if (end < start) return 0;
    let days = 0;
    for (let current = start; current <= end; current.setDate(current.getDate() + 1)) {
      if (current.getDay() !== 0 && current.getDay() !== 6) days += 1;
    }
    return days;
  };

  const saveProfile = async (event) => {
    event.preventDefault();
    try {
      const user = await updateProfile({ ...profileForm, profile_photo_url: profilePhoto || null });
      onUserUpdated(user);
      setMessage({ type: 'success', text: 'Profile updated.' });
    } catch (error) { setMessage({ type: 'error', text: error.message }); }
  };

  const changeProfilePhoto = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const user = await uploadProfilePhoto(file);
      onUserUpdated(user);
      setProfilePhoto(user.profile_photo_url || '');
      setMessage({ type: 'success', text: 'Profile photo updated.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const removeProfilePhoto = async () => {
    try {
      const user = await deleteProfilePhoto();
      onUserUpdated(user);
      setProfilePhoto('');
      setMessage({ type: 'success', text: 'Profile photo removed.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  useEffect(() => {
    if (page !== 'profile') return;
    setProfileForm({
      employee_name: currentUser.employee_name || currentUser.full_name || '',
      job_position_title: currentUser.job_position_title || '',
      employer: currentUser.employer || '',
      department: currentUser.department || '',
      contact_phone: currentUser.contact?.phone || '',
      contact_email: currentUser.contact?.email || '',
      address_line1: currentUser.contact?.address_line1 || '',
      address_line2: currentUser.contact?.address_line2 || '',
      city: currentUser.contact?.city || '',
      country: currentUser.contact?.country || 'Kenya',
      postal_code: currentUser.contact?.postal_code || '',
    });
    setProfilePhoto(currentUser.profile_photo_url || '');
  }, [page, currentUser]);

  const loadChat = async () => {
    setChatLoading(true);
    setChatError('');
    try {
      const users = await getChatUsers();
      const allUsers = users.data || [];
      const targetUsers = getManagerChatPeers(allUsers, chatTarget);
      setChatUsers(targetUsers);
      if (!chatPeer && targetUsers.length === 1) setChatPeer(String(targetUsers[0].id));
      else if (!chatPeer && !chatTarget && targetUsers[0]) setChatPeer(String(targetUsers[0].id));
      if (chatTarget?.role === 'manager' && targetUsers.length === 0) {
        setChatError('No active manager is assigned to this department. Contact your administrator to assign one.');
      }
    } catch (error) { setChatError(error.message); }
    finally { setChatLoading(false); }
  };

  // Reload peers when the conversation target changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (showChat) loadChat(); }, [showChat, chatTarget]);
  useEffect(() => {
    if (!showChat || !chatPeer) return undefined;
    setChatLoading(true);
    Promise.all([getChatMessages(chatPeer), markChatMessagesRead(Number(chatPeer))]).then(([data]) => {
      setChatMessages(data.data || []);
      getUnreadChatCount().then((unread) => setUnreadChatCount(Number(unread.data?.count || 0))).catch(() => {});
      setChatError('');
    }).catch((error) => setChatError(error.message)).finally(() => setChatLoading(false));
    return undefined;
  }, [showChat, chatPeer, currentUser.id]);

  const submitChat = async (event) => {
    event.preventDefault();
    if (!chatBody.trim() || !chatPeer) return;
    try {
      setChatError('');
      await sendChatMessage(Number(chatPeer), chatBody.trim());
      setChatBody('');
      const data = await getChatMessages(chatPeer);
      setChatMessages(data.data || []);
    } catch (error) { setChatError(error.message); }
  };

  const submitRequest = async (event) => {
    event.preventDefault();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.contact_email.trim())) {
      setMessage({ type: 'error', text: 'Enter a valid leave contact email address.' });
      return;
    }
    if (!/^\+?[0-9 ()-]{7,30}$/.test(form.contact_phone.trim())) {
      setMessage({ type: 'error', text: 'Enter a valid leave contact phone number.' });
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const leavePayload = Object.fromEntries(Object.entries(form).filter(([field]) => !['address_line1', 'address_line2', 'city', 'country', 'postal_code'].includes(field)));
      await createLeaveRequest({ ...leavePayload, leave_type_id: Number(form.leave_type_id), handover_user_id: form.handover_user_id ? Number(form.handover_user_id) : null });
      setForm(emptyForm);
      setShowLegacyRequestForm(false);
      setMessage({ type: 'success', text: 'Leave request submitted for approval.' });
      await loadData();
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setSubmitting(false);
    }
  };

  const cancelRequest = async (requestId) => {
    try {
      await cancelLeaveRequest(requestId);
      setMessage({ type: 'success', text: 'Leave request cancelled.' });
      await loadData();
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const decideRequest = async (requestOrId, decision) => {
    const request = typeof requestOrId === 'object'
      ? requestOrId
      : pendingRequests.find((item) => item.id === requestOrId);
    if (!request) {
      setMessage({ type: 'error', text: 'This leave request is no longer available.' });
      return;
    }
    setDecisionDialog({ request, decision });
    setDecisionComment('');
    setDecisionSignature(currentUser?.full_name || currentUser?.name || '');
  };

  const submitDecision = async () => {
    if (!decisionDialog) return;
    const { request, decision } = decisionDialog;
    const comment = decisionComment.trim();
    if (['reject', 'defer'].includes(decision) && comment.length < 10) {
      setMessage({ type: 'error', text: 'A reason of at least 10 characters is required.' });
      return;
    }
    if (!decisionSignature.trim()) {
      setMessage({ type: 'error', text: 'Enter the immediate supervisor signature.' });
      return;
    }
    try {
      await decideLeaveRequest(request.id, decision, comment, decisionSignature.trim());
      setDecisionDialog(null);
      setDecisionComment('');
      setDecisionSignature('');
      setMessage({ type: 'success', text: `Leave request ${decision}d.` });
      await loadData();
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const verifyRequest = async (requestId) => {
    try {
      const response = await fetch(apiUrl(`/api/leave/requests/${requestId}/verify-complete`), { method: 'POST', headers: { Authorization: `Bearer ${getAuthToken()}` } });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to verify leave request.');
      setMessage({ type: 'success', text: payload.message });
      await loadData();
    } catch (error) { setMessage({ type: 'error', text: error.message }); }
  };

  const openRequestView = (request, view) => setRequestView({ request, view });

  const openRequestChat = (request) => {
    const isEmployeeRequest = currentUser.id === request.user_id;
    let peerId = null;
    if (isEmployeeRequest) {
      peerId = request.handover_user_id || request.manager_id || request.supervisor_id;
    } else {
      peerId = request.user_id;
    }
    if (!peerId) {
      setMessage({ type: 'error', text: 'No chat participant is available for this request.' });
      return;
    }
    navigate('/dashboard/chat', { state: { chatPeer: String(peerId) } });
  };

  const getChatStage = (request) => {
    const state = String(request?.workflow_state || '').trim().toLowerCase();
    if (state === 'handover_pending') return 'delegate';
    if (['team_leader_pending', 'department_manager_pending', 'general_manager_pending'].includes(state)
    ) return 'manager';
    return null;
  };

  const getChatPeerForStatus = (request) => {
    const stage = getChatStage(request);
    if (stage === 'delegate') return request.handover_user_id;
    if (stage === 'manager') return request.pending_approver_id || request.manager_id || request.approver_id;
    return null;
  };

  const openStatusChat = (request) => {
    const stage = getChatStage(request);
    if (stage === 'delegate') {
      const peerId = getChatPeerForStatus(request);
      if (!peerId || Number(peerId) === Number(currentUser?.id)) {
        setMessage({ type: 'error', text: 'No delegate is assigned for this request yet.' });
        return;
      }
      navigate('/dashboard/chat', { state: { chatPeer: String(peerId) } });
      return;
    }

    if (stage !== 'manager') return;
    const peerId = getChatPeerForStatus(request);
    navigate('/dashboard/chat', {
      state: {
        chatTarget: {
          role: 'manager',
          department: request.department_name,
          departmentId: request.department_id,
          peerId: peerId && Number(peerId) !== Number(currentUser?.id) ? Number(peerId) : null,
        },
      },
    });
  };

  const chaseDelegate = async (request) => {
    try {
      const response = await remindHandoverDelegate(request.id);
      setMessage({ type: 'success', text: response.message || 'Delegate reminder sent.' });
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const pendingCount = overview.requests.filter((request) => request.status === 'pending').length;
  const usedDays = overview.balances.reduce((sum, balance) => sum + Number(balance.used_days || 0), 0);
  const availableDays = overview.balances.reduce((sum, balance) => sum + Number(balance.available_days || 0), 0);
  const leaveTypeName = (request) => overview.types.find((type) => type.id === request.leave_type_id)?.name || `Leave #${request.leave_type_id}`;
  const calendarDate = calendarMonth;
  const calendarDays = Array.from({ length: new Date(calendarDate.getFullYear(), calendarDate.getMonth() + 1, 0).getDate() }, (_, index) => index + 1);
  const calendarOffset = calendarDate.getDay();
  const reportRequests = Array.from(new Map([...overview.requests, ...pendingRequests].map((request) => [request.id, request])).values());
  const teamRequests = calendarRequests.length ? calendarRequests : reportRequests;
  const reportFilteredRequests = reportRequests.filter((request) => {
    const requestStart = request.start_date || '';
    const requestEnd = request.end_date || requestStart;
    const name = (request.requester_name || request.user_name || '').toLowerCase();
    const region = `${request.country || ''} ${request.city || ''} ${request.region || ''}`.toLowerCase();
    const status = request.workflow_state || request.status || '';
    return (!reportFilters.from || requestEnd >= reportFilters.from)
      && (!reportFilters.to || requestStart <= reportFilters.to)
      && (!reportFilters.user || name.includes(reportFilters.user.toLowerCase()))
      && (!reportFilters.status || status === reportFilters.status)
      && (!reportFilters.leaveType || String(request.leave_type_id) === String(reportFilters.leaveType))
      && (!reportFilters.region || region.includes(reportFilters.region.toLowerCase()));
  });
  const reportApproved = reportFilteredRequests.filter((request) => ['approved', 'completed'].includes(request.status) || ['approved', 'completed'].includes(request.workflow_state)).length;
  const reportRejected = reportFilteredRequests.filter((request) => ['rejected', 'declined'].includes(request.status) || ['rejected', 'declined'].includes(request.workflow_state)).length;
  const reportHandoverGaps = pendingRequests.filter((request) => request.handover_gate?.required && (!request.handover_gate.assigned || !request.handover_gate.accepted || (request.handover_gate.report_required && !request.handover_gate.report_submitted))).length;
  const calendarRequestsForDay = (day) => teamRequests.filter((request) => {
    const start = new Date(`${request.start_date}T00:00:00`);
    const end = new Date(`${request.end_date || request.start_date}T00:00:00`);
    const date = new Date(calendarDate.getFullYear(), calendarDate.getMonth(), day);
    return date >= start && date <= end;
  });
  const selectedCalendarEvents = selectedCalendarDate ? calendarRequestsForDay(selectedCalendarDate) : [];
  const exportReport = () => {
    const rows = [['Employee', 'Leave type', 'Start date', 'End date', 'Days', 'Status', 'Region'], ...reportFilteredRequests.map((request) => [request.requester_name || request.user_name || 'Employee', leaveTypeName(request), request.start_date, request.end_date, request.days_requested, workflowLabel(request), `${request.city || ''} ${request.country || ''}`.trim()])];
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    link.download = `leave-report-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  if (page === 'dashboard' && !isSuperAdmin) {
    return <DashboardLanding
      currentUser={currentUser}
      tier={dashboardTier}
      departmentName={assignedDepartment}
      overview={overview}
      pendingRequests={pendingRequests}
      availableDays={availableDays}
      pendingCount={pendingCount}
      usedDays={usedDays}
      loading={loading}
      message={message}
      canAccessSalesReports={canAccessSalesReports}
      isSalesRepresentative={isSalesEmployee}
      canViewEmployeePerformance={canViewEmployeePerformance}
      canAccessDebtCollection={canAccessDebtCollection}
      onNavigate={(target) => navigate(pagePaths[target] || '/dashboard')}
    />;
  }

  if (page !== 'legacy') {
    const pageTitles = {
      dashboard: 'Dashboard',
      'apply-leave': 'Apply for leave',
      'my-leave': 'My leave',
      history: 'Leave history',
      delegations: 'Handover reports',
      chat: 'Team chat',
      approvals: 'Leave approvals',
      'hr-verification': 'HR verification',
      calendar: 'Team calendar',
      'sales-reports': 'Sales reports',
      'debt-collection': 'Debt collection',
      'hr-module': 'HR module',
      employees: 'Employee directory',
      departments: 'Departments',
      profile: 'Edit profile',
      'dashboard-settings': 'Dashboard settings',
      'leave-policies': 'Leave policies & settings',
      'leave-balances': 'Employee leave balances',
      'leave-management-history': 'Employee leave history',
      admin: 'System administration',
    };
    const pageTitle = pageTitles[page] || 'Dashboard';
    const openPage = (target) => navigate(pagePaths[target] || '/dashboard');
    const renderLeaveRequests = (requests) => requests.length === 0
      ? <p className="leave-empty">No leave requests to display.</p>
      : <div className="leave-table-wrap"><table className="leave-table"><thead><tr><th>Leave type</th><th>Dates</th><th>Days</th><th>Status</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td>{request.type_name || request.leave_type_name || leaveTypeName(request)}</td><td>{formatDate(request.start_date)} - {formatDate(request.end_date)}</td><td>{request.days_requested}</td><td><span className={workflowStatusClass(request)}>{workflowLabel(request)}</span></td></tr>)}</tbody></table></div>;

    return (
      <main className="leave-main dashboard-page" aria-labelledby="dashboard-page-title">
        <header className="leave-header">
          <div>
            <p className="leave-kicker">{isSuperAdmin ? 'ADMINISTRATION' : canViewEmployeePerformance && page === 'sales-reports' ? 'MANAGEMENT REPORTING' : 'EMPLOYEE PORTAL'}</p>
            <h1 id="dashboard-page-title">{pageTitle}</h1>
            <p className="leave-muted">{page === 'dashboard'
              ? `Good day, ${currentUser?.name || currentUser?.full_name || 'there'}.`
              : canViewEmployeePerformance && page === 'sales-reports'
                ? 'Review performance and registration analytics for every employee in your reporting scope.'
                : `Manage ${pageTitle.toLowerCase()} for your account and team.`}</p>
          </div>
          {page === 'dashboard' && <div className="leave-header-actions"><button className="leave-primary-button leave-apply-button" type="button" onClick={() => openPage('apply-leave')}>Apply for leave</button></div>}
        </header>

        {message && <div className={`leave-alert ${message.type}`} role="status">{message.text}</div>}
        {loading && <div className="leave-loading" role="status">Loading {pageTitle.toLowerCase()}…</div>}

        {['dashboard', 'admin'].includes(page) && canManageLeaveSettings && (
          <section className="leave-section admin-leave-shortcuts" aria-labelledby="dashboard-leave-management-title">
            <div className="leave-section-heading">
              <div>
                <p className="leave-kicker">SYSTEM ADMINISTRATION</p>
                <h2 id="dashboard-leave-management-title">Leave management</h2>
              </div>
            </div>
            <p>Configure leave entitlements, review employee balances, and inspect leave request history.</p>
            <div className="dashboard-page-links">
              <button type="button" className="leave-secondary-button" onClick={() => openPage('leave-policies')}>Leave policies &amp; settings</button>
              <button type="button" className="leave-secondary-button" onClick={() => openPage('leave-balances')}>Employee leave balances</button>
              <button type="button" className="leave-secondary-button" onClick={() => openPage('leave-management-history')}>Employee leave history</button>
            </div>
          </section>
        )}

        {!loading && page === 'dashboard' && (
          <>
            <section className="leave-stat-grid" aria-label="Leave summary">
              <div className="leave-stat-card accent-blue"><span>Available days</span><strong>{availableDays}</strong><small>Across all leave types</small></div>
              <div className="leave-stat-card accent-teal"><span>Days taken</span><strong>{usedDays}</strong><small>This leave year</small></div>
              <div className="leave-stat-card accent-amber"><span>Pending requests</span><strong>{pendingCount}</strong><small>Awaiting a decision</small></div>
            </section>
            <div className="dashboard-page-links">
              <button type="button" className="leave-secondary-button" onClick={() => openPage('my-leave')}>View my leave</button>
              <button type="button" className="leave-secondary-button" onClick={() => openPage('history')}>View leave history</button>
              {canApprove && <button type="button" className="leave-secondary-button" onClick={() => openPage('approvals')}>Review approvals</button>}
              {canApprove && <button type="button" className="leave-secondary-button" onClick={() => openPage('calendar')}>Open team calendar</button>}
            </div>
          </>
        )}

        {!loading && page === 'apply-leave' && <LeaveApplicationWizard currentUser={currentUser} leaveTypes={overview.types} balances={overview.balances} colleagues={chatUsers} onClose={() => openPage('dashboard')} onViewRequests={() => openPage('my-leave')} />}

        {!loading && page === 'my-leave' && (
          <>
            <section className="leave-section"><div className="leave-section-heading"><div><p className="leave-kicker">YOUR ENTITLEMENT</p><h2>Leave balances</h2></div></div><div className="leave-balance-grid">{overview.balances.length === 0 ? <p className="leave-empty">No leave balances have been configured yet.</p> : overview.balances.map((balance) => <article className="leave-balance-card" key={balance.leave_type_id}><div><h3>{balance.name}</h3><span>{balance.code}</span></div><strong>{balance.available_days}</strong><p>available of {balance.entitled_days} days</p><small>{balance.used_days} used · {balance.pending_days} pending</small></article>)}</div></section>
            <section className="leave-section"><div className="leave-section-heading"><div><p className="leave-kicker">TIME AWAY</p><h2>My leave requests</h2></div></div>{renderLeaveRequests(overview.requests)}</section>
          </>
        )}

        {!loading && page === 'history' && <section className="leave-section"><div className="leave-section-heading"><div><p className="leave-kicker">RECORDS</p><h2>Leave history</h2></div></div>{renderLeaveRequests(historyRequests)}</section>}

        {!loading && page === 'delegations' && <section className="leave-section"><div className="leave-section-heading"><div><p className="leave-kicker">HANDOVER</p><h2>Handover reports assigned to you</h2></div></div>{delegations.length === 0 ? <p className="leave-empty">No handover reports have been assigned to you.</p> : delegations.map((request) => <article className="profile-summary delegate-card" key={request.id}><div><strong>{request.requester_name || 'Employee'} · {leaveTypeName(request)} · {formatDate(request.start_date)} - {formatDate(request.end_date)}</strong><p>{request.handover_statement || 'Briefing pending your confirmation.'}</p><div className="delegate-card-actions"><button type="button" className="leave-secondary-button" onClick={() => openRequestView(request, 'request')}>View request</button><button type="button" className="leave-secondary-button" onClick={() => openRequestView(request, 'report')}>View report</button><button type="button" className="leave-secondary-button" onClick={() => openRequestChat(request)}>Chat requester</button></div></div>{request.handover_statement ? <HandoverReportForm requestId={request.id} readOnly /> : <HandoverAcceptance requestId={request.id} onComplete={loadData} />}</article>)}</section>}

        {!loading && ['approvals', 'hr-verification'].includes(page) && <section className="leave-section"><div className="leave-section-heading"><div><p className="leave-kicker">TEAM WORKFLOW</p><h2>{pageTitle}</h2></div><span className="section-meta">{pendingRequests.length} pending</span></div><div className="approval-card-list">{pendingRequests.length === 0 ? <p className="leave-empty">No submitted leave requests are currently assigned to this approval queue.</p> : pendingRequests.map((request) => { const gate = request.handover_gate || {}; const handoverReady = !gate.required || (gate.assigned && gate.accepted && (!gate.report_required || gate.report_submitted)); return <ApprovalRequestCard key={`page-approval-${request.id}`} request={request} leaveType={request.type_name} formatDate={formatDate} workflowLabel={workflowLabel} workflowStatusClass={workflowStatusClass} handoverReady={handoverReady} canVerify={(isHr || isSuperAdmin) && request.workflow_state === 'hr_verification'} waitingForDelegate={false} waitingForManager={false} onView={openRequestView} onChat={openRequestChat} onDecide={decideRequest} onChase={chaseDelegate} onVerify={verifyRequest} />; })}</div></section>}

        {!loading && page === 'calendar' && <TeamCalendarSection calendarDate={calendarDate} calendarDays={calendarDays} calendarOffset={calendarOffset} calendarRequestsForDay={calendarRequestsForDay} selectedCalendarDate={selectedCalendarDate} setSelectedCalendarDate={setSelectedCalendarDate} selectedCalendarEvents={selectedCalendarEvents} setCalendarMonth={setCalendarMonth} openRequestView={openRequestView} leaveTypeName={leaveTypeName} formatDate={formatDate} workflowLabel={workflowLabel} currentUser={currentUser} />}

        {!loading && page === 'sales-reports' && canAccessSalesReports && <SalesReportsPage reports={salesReports} canEdit={canEditOperations && !canViewEmployeePerformance} canAddClient={isSalesEmployee && !canViewEmployeePerformance} canManageAgentRecords={isSalesEmployee || canEditOperations || isSuperAdmin} canViewEmployeePerformance={canViewEmployeePerformance || isSuperAdmin} isFieldAgent={organizationalRole === 'field_agent' && isSalesEmployee} onSubmitted={(report) => setSalesReports((current) => [report, ...current])} />}
        {!loading && page === 'debt-collection' && canAccessDebtCollection && <DebtCollectionPage />}
        {!loading && page === 'hr-module' && <HrModulePanel employees={adminUsers} departments={adminDepartments} isSuperAdmin={isSuperAdmin} onRefresh={loadSuperAdminData} />}
        {!loading && page === 'employees' && <ManagedUsersPanel users={adminUsers} departments={adminDepartments} currentUser={currentUser} isSuperAdmin={isSuperAdmin} canCreateEmployee={isHr || isSuperAdmin || ['general_manager', 'department_manager', 'team_leader'].includes(currentUser.active_assignment?.organizational_role)} onRefresh={loadSuperAdminData} onMessage={(text, type = 'success') => setMessage({ type, text })} />}

        {!loading && page === 'departments' && (
          <section className="leave-section">
            <div className="leave-section-heading">
              <div><p className="leave-kicker">ORGANIZATION</p><h2>Departments</h2></div>
            </div>
            <form className="admin-form" onSubmit={createDepartment}>
              <label>Department name<input value={adminDepartmentName} onChange={(event) => setAdminDepartmentName(event.target.value)} required /></label>
              <div className="leave-modal-actions">
                {editingDepartmentId && <button className="leave-secondary-button" type="button" onClick={() => { setEditingDepartmentId(null); setAdminDepartmentName(''); }}>Cancel edit</button>}
                <button className="leave-primary-button" type="submit">{editingDepartmentId ? 'Save department' : 'Add department'}</button>
              </div>
            </form>
            <div className="department-list">
              {adminDepartments.map((department) => (
                <div className="department-pill" key={department.id}>
                  <span>{department.name}</span>
                  <button className="edit-action" type="button" onClick={() => { setEditingDepartmentId(department.id); setAdminDepartmentName(department.name); }}>Edit</button>
                  <button className="danger-action" type="button" onClick={() => deleteDepartment(department.id)}>Delete</button>
                </div>
              ))}
              {adminDepartments.length === 0 && <p className="leave-empty">No departments configured.</p>}
            </div>
            {canConfigureDepartmentPages && adminDepartments.map((department) => (
              <fieldset className="admin-form leave-fieldset" key={`department-pages-${department.id}`}>
                <legend>{department.name} pages</legend>
                <div className="department-page-options">
                  {departmentPageOptions.map(([pageKey, label]) => (
                    <label key={pageKey}>
                      <input
                        type="checkbox"
                        checked={(departmentPageSettings[department.id] || []).includes(pageKey)}
                        onChange={(event) => setDepartmentPageSettings((current) => {
                          const pages = current[department.id] || [];
                          return {
                            ...current,
                            [department.id]: event.target.checked
                              ? [...pages, pageKey]
                              : pages.filter((page) => page !== pageKey),
                          };
                        })}
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <button
                  type="button"
                  className="leave-primary-button"
                  disabled={savingDepartmentPagesId === department.id}
                  onClick={() => saveDepartmentPages(department.id)}
                >
                  {savingDepartmentPagesId === department.id ? 'Saving pages…' : 'Save department pages'}
                </button>
              </fieldset>
            ))}
          </section>
        )}

        {!loading && page === 'dashboard-settings' && (
          <>
            <section className="admin-card dashboard-feature-settings" aria-label="Dashboard feature settings">
              <div className="leave-section-heading">
                <div><p className="leave-kicker">SYSTEM SETTINGS</p><h2>Dashboard feature access</h2></div>
              </div>
              <div className="dashboard-feature-list">
                {Object.keys(dashboardRoleFeatures).map((roleName) => (
                  <div className="dashboard-feature-row" key={roleName}>
                    <span>{roleName.replace('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())}</span>
                    <div className="dashboard-feature-toggle-group">
                      {['sales_reports', 'debt_collection'].map((feature) => (
                        <label className="dashboard-feature-control" key={feature}>
                          <input
                            type="checkbox"
                            checked={dashboardRoleFeatures[roleName]?.[feature] !== false}
                            onChange={(event) => updateDashboardRoleFeature(roleName, feature, event.target.checked)}
                            aria-label={`${feature.replace('_', ' ')} for ${roleName}`}
                          />
                          <span>{feature === 'sales_reports' ? 'Sales Reports' : 'Debt Collection'}</span>
                          <strong>{dashboardRoleFeatures[roleName]?.[feature] === false ? 'Disabled' : 'Enabled'}</strong>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
            <LocationTrackingScheduleSettings />
          </>
        )}

        {!loading && page === 'admin' && <>
          <section className="admin-stat-grid">
            <div className="leave-stat-card accent-blue"><span>Total users</span><strong>{adminUsers.length}</strong></div>
            <div className="leave-stat-card accent-teal"><span>Active users</span><strong>{adminHealth.active_users || 0}</strong></div>
            <div className="leave-stat-card accent-amber"><span>Pending users</span><strong>{adminHealth.pending_users || 0}</strong></div>
          </section>
          {isSuperAdmin && <section className="admin-card system-test-data-panel" aria-labelledby="system-test-data-title">
            <div className="leave-section-heading">
              <div><p className="leave-kicker">DEVELOPMENT TOOLS</p><h2 id="system-test-data-title">System test data</h2></div>
            </div>
            <p>Load synthetic, clearly marked sample records for Sales &amp; Marketing, Customer Care, and Debt Collection. Actions are restricted to a local development database and use existing assigned staff.</p>
            <div className="dashboard-page-links">
              <button
                className="leave-primary-button"
                type="button"
                onClick={() => runSystemTestDataAction('load')}
                disabled={systemTestDataBusy}
              >{systemTestDataBusy ? 'Working…' : 'Load test data'}</button>
            </div>
            <label className="system-test-data-confirmation">
              To delete only marked synthetic records, enter <strong>DELETE SYSTEM TEST DATA</strong>.
              <input
                value={systemTestDataConfirmation}
                onChange={(event) => setSystemTestDataConfirmation(event.target.value)}
                autoComplete="off"
                disabled={systemTestDataBusy}
                aria-label="Test data deletion confirmation"
              />
            </label>
            <button
              className="leave-secondary-button"
              type="button"
              onClick={() => runSystemTestDataAction('delete')}
              disabled={systemTestDataBusy || systemTestDataConfirmation !== 'DELETE SYSTEM TEST DATA'}
            >Delete test data</button>
          </section>}
          {(isSuperAdmin || isHr) && <LocationSharingAdminPanel />}
          <section className="leave-section">
            <h2>Administration pages</h2>
            <div className="dashboard-page-links">
              <button className="leave-secondary-button" type="button" onClick={() => openPage('employees')}>Employee directory</button>
              <button className="leave-secondary-button" type="button" onClick={() => openPage('departments')}>Departments</button>
              <button className="leave-secondary-button" type="button" onClick={() => openPage('dashboard-settings')}>Dashboard settings</button>
            </div>
          </section>
        </>}

        {!loading && page === 'profile' && <section className="leave-section"><div className="leave-section-heading"><div><p className="leave-kicker">YOUR DETAILS</p><h2>Edit profile</h2></div></div><form onSubmit={saveProfile}><label>Profile photo<input type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={changeProfilePhoto} /><span className="leave-helper">JPG, PNG, GIF, or WEBP up to 5 MB.</span></label>{profilePhoto && <button type="button" className="leave-text-button" onClick={removeProfilePhoto}>Remove photo</button>}<div className="leave-form-row">{[['employee_name', 'Employee name'], ['job_position_title', 'Job position title']].map(([name, label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} required /></label>)}</div><div className="leave-form-row">{[['employer', 'Employer'], ['department', 'Department']].map(([name, label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} required /></label>)}</div><fieldset className="leave-fieldset"><legend>Contact and address</legend><div className="leave-form-row">{[['contact_phone', 'Phone'], ['contact_email', 'Email']].map(([name, label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} /></label>)}</div><div className="leave-form-row">{[['address_line1', 'Address'], ['address_line2', 'Address line 2'], ['city', 'City'], ['country', 'Country'], ['postal_code', 'Postal code']].map(([name, label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} /></label>)}</div></fieldset><div className="leave-modal-actions"><button type="submit" className="leave-primary-button">Save profile</button></div></form></section>}

        {!loading && page === 'chat' && <section className="leave-section chat-page"><div className="leave-section-heading"><div><p className="leave-kicker">TEAM CHAT</p><h2>Messages</h2></div></div>{chatTarget?.role === 'manager' && <p className="leave-muted">Choose a manager for {chatTarget.department || 'your department'}.</p>}<label>{chatTarget?.role === 'manager' ? 'Manager' : 'Chat with'}<select value={chatPeer} onChange={(event) => setChatPeer(event.target.value)}><option value="">{chatTarget?.role === 'manager' ? 'Select a manager' : 'Select a colleague'}</option>{chatUsers.map((peer) => <option value={peer.id} key={peer.id}>{peer.name}</option>)}</select></label>{chatError && <div className="leave-alert error chat-error" role="alert">{chatError}<button type="button" className="leave-text-button" onClick={loadChat}>Try again</button></div>}<div className="chat-messages" aria-live="polite">{chatLoading ? <p className="leave-empty">Loading messages...</p> : chatMessages.length === 0 ? <p className="leave-empty">No messages yet. Start the conversation below.</p> : chatMessages.map((item) => <div className={`chat-message ${item.sender_id === currentUser.id ? 'mine' : ''}`} key={item.id}><span>{item.sender_name} · {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><p>{item.body}</p></div>)}</div><form className="chat-compose" onSubmit={submitChat}><input value={chatBody} onChange={(event) => setChatBody(event.target.value)} placeholder="Write a message" maxLength="2000" disabled={!chatPeer || chatLoading} /><button className="leave-primary-button" type="submit" disabled={!chatPeer || !chatBody.trim() || chatLoading}>Send</button></form></section>}

        {requestView && <section className="leave-section"><h2>Leave request #{requestView.request.id}</h2><p>{requestView.request.requester_name || currentUser.name} · {leaveTypeName(requestView.request)} · {formatDate(requestView.request.start_date)} - {formatDate(requestView.request.end_date)}</p><p>{requestView.request.reason || requestView.request.handover_statement || 'Request details'}</p><button type="button" className="leave-secondary-button" onClick={() => setRequestView(null)}>Close details</button></section>}
        {decisionDialog && <section className="leave-section"><h2>Complete approval</h2><p>Decision: {decisionDialog.decision}</p><label>Comment<textarea value={decisionComment} onChange={(event) => setDecisionComment(event.target.value)} /></label><label>Supervisor signature<input value={decisionSignature} onChange={(event) => setDecisionSignature(event.target.value)} /></label><div className="leave-modal-actions"><button type="button" className="leave-secondary-button" onClick={() => setDecisionDialog(null)}>Cancel</button><button type="button" className="leave-primary-button" onClick={submitDecision}>Confirm</button></div></section>}
      </main>
    );
  }

  return (
    <div className="legacy-dashboard-content">
      <main className="leave-main">
        <header className="leave-header">
          <div>
            <p className="leave-kicker">{isSuperAdmin ? 'SUPER ADMIN' : 'EMPLOYEE PORTAL'}</p>
            <h1>{isSuperAdmin ? 'Okoa Float Portal' : `Good day, ${currentUser?.name || currentUser?.full_name || 'there'}`}</h1>
            {!isSuperAdmin && <p className="leave-muted">Plan your time away and keep your team informed.</p>}
          </div>
          <div className="leave-header-actions"><button className="leave-primary-button leave-apply-button" onClick={() => setShowRequestForm(true)}>Apply for leave</button></div>
        </header>

        {isSuperAdmin && (
          <div className="admin-stat-grid">
            <div className="leave-stat-card accent-blue"><span>Total users</span><strong>{adminUsers.length}</strong><small>people in the system</small></div>
            <div className="leave-stat-card accent-teal"><span>Active users</span><strong>{adminHealth.active_users || 0}</strong><small>currently active</small></div>
            <div className="leave-stat-card accent-amber"><span>Pending users</span><strong>{adminHealth.pending_users || 0}</strong><small>awaiting approval</small></div>
          </div>
        )}

        {message && <div className={`leave-alert ${message.type}`} role="status">{message.text}</div>}
        {canAccessSalesReports && <SalesV2DashboardWidgets currentUser={currentUser} onViewReport={() => openSalesReports('sales-reports')} onOpenWorkspace={() => openSalesReports('sales-reports')} onViewDetail={() => openSalesReports('sales-reports')} />}
        {canAccessDebtCollection && isSuperAdmin && activeSection === 'dashboard' && <DebtCollectionPage compact />}
        {unreadChatCount > 0 && <div className="leave-alert info chat-notification" role="status"><strong>New message{unreadChatCount === 1 ? '' : 's'} waiting.</strong><button type="button" className="leave-text-button" onClick={() => setShowChat(true)}>Open chat ({unreadChatCount})</button></div>}
        {isSuperAdmin && <TeamCalendarSection calendarDate={calendarDate} calendarDays={calendarDays} calendarOffset={calendarOffset} calendarRequestsForDay={calendarRequestsForDay} selectedCalendarDate={selectedCalendarDate} setSelectedCalendarDate={setSelectedCalendarDate} selectedCalendarEvents={selectedCalendarEvents} setCalendarMonth={setCalendarMonth} openRequestView={openRequestView} leaveTypeName={leaveTypeName} formatDate={formatDate} workflowLabel={workflowLabel} currentUser={currentUser} />}

        {isSuperAdmin && (
          <section className="super-admin-panel" id="dashboard" aria-label="System administration">
            <section className="admin-card" id="pending-leave-approvals">
              <div className="leave-section-heading"><div><p className="leave-kicker">LEAVE WORKFLOW</p><h3>Pending Leave Approvals</h3><p className="leave-muted">Review every pending leave request across the organization.</p></div><span className="section-meta">{pendingRequests.length} pending</span></div>
              <div className="approval-card-list">{pendingRequests.length === 0 ? <p className="leave-empty">No pending leave approvals.</p> : pendingRequests.map((request) => { const gate = request.handover_gate || {}; const handoverReady = !gate.required || (gate.assigned && gate.accepted && (!gate.report_required || gate.report_submitted)); return <ApprovalRequestCard key={`super-pending-${request.id}`} request={request} leaveType={request.type_name} formatDate={formatDate} workflowLabel={workflowLabel} workflowStatusClass={workflowStatusClass} handoverReady={handoverReady} canVerify={request.workflow_state === 'hr_verification'} waitingForDelegate={false} waitingForManager={false} onView={openRequestView} onChat={openRequestChat} onDecide={decideRequest} onChase={chaseDelegate} onVerify={verifyRequest} />; })}</div>
            </section>

            <div className="admin-grid">
              <div className="admin-card" id="users">
                <h3>Create user</h3>
                <form onSubmit={createAdminUser} className="admin-form">
                  <div className="leave-form-row">
                    <label>Full name<input value={adminForm.full_name} onChange={(event) => setAdminForm({ ...adminForm, full_name: event.target.value })} required /></label>
                    <label>Role<select value={adminForm.role} onChange={(event) => setAdminForm({ ...adminForm, role: event.target.value })}><option value="employee">Employee</option><option value="manager">Manager</option><option value="hr_admin">HR Admin</option><option value="system_admin">System Admin</option></select></label>
                  </div>
                  <div className="leave-form-row">
                    <label>Official email<input type="email" autoComplete="email" value={adminForm.email} onChange={(event) => setAdminForm({ ...adminForm, email: event.target.value })} required /></label>
                    <label>Phone<input value={adminForm.phone_number} onChange={(event) => setAdminForm({ ...adminForm, phone_number: event.target.value })} required /></label>
                  </div>
                  <div className="leave-form-row">
                    {adminForm.organizational_role === 'general_manager' ? (
                      <label>Department<input value="All" readOnly /></label>
                    ) : (
                      <label>Department<select value={adminForm.department} onChange={(event) => setAdminForm({
                        ...adminForm,
                        department: event.target.value,
                        department_role: departmentRoleFor(event.target.value),
                        manager_id: '',
                      })} required><option value="">Select department</option>{adminDepartments.map((department) => <option value={department.name} key={department.id}>{department.name}</option>)}</select></label>
                    )}
                    <label>Organizational role<select value={adminForm.organizational_role} onChange={(event) => setAdminForm({
                      ...adminForm,
                      organizational_role: event.target.value,
                      job_position_title: organizationRoleLabels[event.target.value],
                      department: event.target.value === 'general_manager'
                        ? 'All'
                        : adminForm.department === 'All' ? '' : adminForm.department,
                      department_role: event.target.value === 'general_manager'
                        ? ''
                        : departmentRoleFor(adminForm.department === 'All' ? '' : adminForm.department),
                      manager_id: '',
                    })}>{Object.entries(organizationRoleLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                  </div>
                  {adminForm.organizational_role !== 'general_manager' && <div className="leave-form-row">
                    <label>Reports to — {organizationRoleLabels[managerRole]}<select value={adminForm.manager_id} onChange={(event) => setAdminForm({ ...adminForm, manager_id: event.target.value })} required>
                      <option value="">Select manager</option>
                      {managerCandidates.map((manager) => <option value={manager.id} key={manager.id}>{manager.name} — {manager.department}</option>)}
                    </select></label>
                  </div>}
                  {['field_agent', 'team_leader', 'department_manager'].includes(adminForm.organizational_role) && <div className="leave-form-row">
                    <label>Department role<select value={adminForm.department_role} onChange={(event) => setAdminForm({ ...adminForm, department_role: event.target.value })} required>
                      <option value="">Select department access</option>
                      {departmentRoleFor(adminForm.department) === 'sales' && <option value="sales">Sales and Marketing</option>}
                      {departmentRoleFor(adminForm.department) === 'debt_collection' && <option value="debt_collection">Debt Collection</option>}
                      {departmentRoleFor(adminForm.department) === 'customer_care' && <option value="customer_care">Customer Care</option>}
                    </select></label>
                  </div>}
                  <div className="leave-form-row">
                    <label>Employer<input value={adminForm.employer} onChange={(event) => setAdminForm({ ...adminForm, employer: event.target.value })} /></label>
                    <label>Password<input type="password" value={adminForm.password} onChange={(event) => setAdminForm({ ...adminForm, password: event.target.value })} required /></label>
                  </div>
                  
                  <div className="leave-modal-actions"><button type="submit" className="leave-primary-button">Create user</button></div>
                </form>
                {editingAdminUserId && <div className="leave-modal-backdrop employee-edit-backdrop" role="presentation"><div className="leave-modal employee-edit-modal" role="dialog" aria-modal="true" aria-labelledby="admin-user-edit-title"><div className="leave-modal-heading"><div><p className="leave-kicker">AUTHORITY</p><h2 id="admin-user-edit-title">Edit user profile</h2><p className="employee-edit-subtitle">Update {adminUsers.find((user) => user.id === editingAdminUserId)?.full_name || 'this user'}'s details and access.</p></div><button type="button" className="leave-close" onClick={() => setEditingAdminUserId(null)} aria-label="Close user editor">×</button></div><form onSubmit={saveAdminUser} className="admin-form admin-edit-form"><div className="employee-edit-section"><h3>Profile details</h3><div className="leave-form-row"><label>Full name<input value={adminUserForm.full_name} onChange={(event) => setAdminUserForm({ ...adminUserForm, full_name: event.target.value })} required /></label><label>Official email<input type="email" autoComplete="email" value={adminUserForm.email} onChange={(event) => setAdminUserForm({ ...adminUserForm, email: event.target.value })} required /></label></div><div className="leave-form-row"><label>Phone<input autoComplete="tel" value={adminUserForm.phone_number} onChange={(event) => setAdminUserForm({ ...adminUserForm, phone_number: event.target.value })} required /></label><label>Department<select value={adminUserForm.department} onChange={(event) => setAdminUserForm({ ...adminUserForm, department: event.target.value })} required><option value="">Select department</option>{adminUserForm.department && !adminDepartments.some((department) => department.name === adminUserForm.department) && <option value={adminUserForm.department}>{adminUserForm.department}</option>}{adminDepartments.map((department) => <option value={department.name} key={department.id}>{department.name}</option>)}</select></label></div><div className="leave-form-row"><label>Job title<input value={adminUserForm.job_position_title} onChange={(event) => setAdminUserForm({ ...adminUserForm, job_position_title: event.target.value })} /></label><label>Employer<input value={adminUserForm.employer} onChange={(event) => setAdminUserForm({ ...adminUserForm, employer: event.target.value })} /></label></div></div>{isSuperAdmin && editingAdminUserId !== currentUser.id && <div className="employee-edit-section"><h3>Account status</h3><label>Status<select value={adminUserForm.status} onChange={(event) => setAdminUserForm({ ...adminUserForm, status: event.target.value })}><option value="pending">Pending approval</option><option value="active">Activate</option><option value="deactivated">Deactivate</option><option value="archived">Archive</option></select></label><button type="button" className="leave-secondary-button" onClick={() => updateAdminUserStatus(editingAdminUserId, adminUserForm.status)}>Update status</button></div>}{isSuperAdmin && <div className="employee-edit-section"><h3>Access level</h3><label>Role<select value={adminUserForm.role} onChange={(event) => setAdminUserForm({ ...adminUserForm, role: event.target.value })}><option value="employee">Employee</option><option value="manager">Manager</option><option value="hr_admin">HR Admin</option><option value="system_admin">System Admin</option></select></label><p className="employee-edit-note">Role changes affect dashboard access and approval permissions.</p></div>}<div className="leave-modal-actions"><button type="button" className="leave-secondary-button action-reset" onClick={() => setEditingAdminUserId(null)}>Cancel</button><button type="submit" className="leave-primary-button">Save changes</button></div></form></div></div>}
              </div>

              <div className="admin-card" id="departments">
                <h3>{editingDepartmentId ? 'Edit department' : 'Create department'}</h3>
                <form onSubmit={createDepartment} className="admin-form">
                  <label>Department name<input value={adminDepartmentName} onChange={(event) => setAdminDepartmentName(event.target.value)} placeholder="Engineering" required /></label>
                  <div className="leave-modal-actions">
                    {editingDepartmentId && <button type="button" className="leave-secondary-button" onClick={() => { setEditingDepartmentId(null); setAdminDepartmentName(''); }}>Cancel</button>}
                    <button type="submit" className="leave-primary-button">{editingDepartmentId ? 'Update department' : 'Create department'}</button>
                  </div>
                </form>
                <div className="department-list">
                  {adminDepartments.length === 0 ? <p className="leave-empty">No departments created yet.</p> : adminDepartments.map((department) => (
                    <div className="department-pill" key={department.id}>
                      <span>{department.name}</span>
                      <button type="button" className="edit-action" onClick={() => { setEditingDepartmentId(department.id); setAdminDepartmentName(department.name); }}>Edit</button>
                      <button type="button" className="danger danger-action" onClick={() => deleteDepartment(department.id)}>Delete</button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="admin-card" id="leave-types">
                <h3>{editingLeaveTypeId ? 'Edit leave type' : 'Leave types'}</h3>
                <form onSubmit={saveLeaveType} className="admin-form">
                  <div className="leave-form-row">
                    <label>Leave type name<input value={leaveTypeForm.name} onChange={(event) => setLeaveTypeForm({ ...leaveTypeForm, name: event.target.value })} required /></label>
                    <label>Code<input value={leaveTypeForm.code} onChange={(event) => setLeaveTypeForm({ ...leaveTypeForm, code: event.target.value })} required /></label>
                  </div>
                  <div className="leave-form-row">
                    <label>Default days<input type="number" min="0" value={leaveTypeForm.default_days_per_year} onChange={(event) => setLeaveTypeForm({ ...leaveTypeForm, default_days_per_year: event.target.value })} /></label>
                    <label>Paid<select value={leaveTypeForm.is_paid ? 'yes' : 'no'} onChange={(event) => setLeaveTypeForm({ ...leaveTypeForm, is_paid: event.target.value === 'yes' })}><option value="yes">Yes</option><option value="no">No</option></select></label>
                  </div>
                  <label className="checkbox-row"><input type="checkbox" checked={leaveTypeForm.requires_document} onChange={(event) => setLeaveTypeForm({ ...leaveTypeForm, requires_document: event.target.checked })} /> Requires supporting document</label>
                  <div className="leave-modal-actions">
                    {editingLeaveTypeId && <button type="button" className="leave-secondary-button" onClick={() => { setEditingLeaveTypeId(null); setLeaveTypeForm({ name: '', code: '', is_paid: true, requires_document: false, default_days_per_year: 21 }); }}>Cancel</button>}
                    <button type="submit" className="leave-primary-button">{editingLeaveTypeId ? 'Update leave type' : 'Create leave type'}</button>
                  </div>
                </form>
                <div className="department-list">
                  {adminLeaveTypes.length === 0 ? <p className="leave-empty">No leave types configured.</p> : adminLeaveTypes.map((leaveType) => (
                    <div className="department-pill" key={leaveType.id}>
                      <span>{leaveType.name} ({leaveType.code})</span>
                      <button type="button" className="edit-action" onClick={() => { setEditingLeaveTypeId(leaveType.id); setLeaveTypeForm({ name: leaveType.name, code: leaveType.code, is_paid: leaveType.is_paid, requires_document: leaveType.requires_document, default_days_per_year: leaveType.default_days_per_year }); }}>Edit</button>
                      <button type="button" className="danger danger-action" onClick={() => deleteLeaveType(leaveType.id)}>Delete</button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="admin-card" id="workflow-settings">
                <h3>Workflow settings</h3>
                <form onSubmit={saveWorkflowSettings} className="admin-form">
                  <div className="leave-form-row">
                    <label>Handover threshold (days)<input type="number" min="1" value={adminWorkflowSettings.handover_threshold_days} onChange={(event) => setAdminWorkflowSettings({ ...adminWorkflowSettings, handover_threshold_days: Number(event.target.value) || 2 })} /></label>
                    <label>Handover report threshold (days)<input type="number" min="1" value={adminWorkflowSettings.handover_report_threshold_days} onChange={(event) => setAdminWorkflowSettings({ ...adminWorkflowSettings, handover_report_threshold_days: Number(event.target.value) || 3 })} /></label>
                  </div>
                  <label>Approval routing<select value={adminWorkflowSettings.approval_routing} onChange={(event) => setAdminWorkflowSettings({ ...adminWorkflowSettings, approval_routing: event.target.value })}><option value="manager_then_hr">Manager then HR</option><option value="hr_only">HR only</option></select></label>
                  <label className="checkbox-row"><input type="checkbox" checked={adminWorkflowSettings.hr_verification_required} onChange={(event) => setAdminWorkflowSettings({ ...adminWorkflowSettings, hr_verification_required: event.target.checked })} /> HR verification required</label>
                  <label className="checkbox-row"><input type="checkbox" checked={adminWorkflowSettings.require_delegate_for_extended_leave} onChange={(event) => setAdminWorkflowSettings({ ...adminWorkflowSettings, require_delegate_for_extended_leave: event.target.checked })} /> Require delegate for extended leave</label>
                  <div className="leave-modal-actions"><button type="submit" className="leave-primary-button">Save workflow</button></div>
                </form>
              </div>

              <div className="admin-card" id="security-events">
                <h3>Security events</h3>
                <div className="leave-table-wrap compact-table">
                  <table className="leave-table">
                    <thead><tr><th>Event</th><th>Actor</th><th>Time</th></tr></thead>
                    <tbody>
                      {securityEvents.length === 0 ? <tr><td colSpan="3">No security events recorded.</td></tr> : securityEvents.map((event) => (
                        <tr key={event.id}><td>{event.message || event.action}</td><td>{event.actor}</td><td>{event.timestamp ? new Date(event.timestamp).toLocaleString() : '-'}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="admin-card" id="system-health">
                <h3>System health</h3>
                <ul className="health-list">
                  <li><span>Database</span><strong>{adminHealth.database || 'unknown'}</strong></li>
                  <li><span>Uploads directory</span><strong>{adminHealth.uploads_ready ? 'Ready' : 'Not ready'}</strong></li>
                  <li><span>Active users</span><strong>{adminHealth.active_users || 0}</strong></li>
                  <li><span>Pending users</span><strong>{adminHealth.pending_users || 0}</strong></li>
                </ul>
              </div>
            </div>
            {canAccessSalesReports && <SalesReportsPage reports={salesReports} canEdit={canEditOperations && !canViewEmployeePerformance} canAddClient={isSalesEmployee && !canViewEmployeePerformance} canManageAgentRecords={isSalesEmployee || canEditOperations || isSuperAdmin} canViewEmployeePerformance={canViewEmployeePerformance || isSuperAdmin} isFieldAgent={organizationalRole === 'field_agent' && isSalesEmployee} onSubmitted={(report) => setSalesReports((current) => [report, ...current])} />}
        {canAccessDebtCollection && activeSection === 'debt-collection' && <DebtCollectionPage />}
          </section>
        )}

        {(isSuperAdmin || role === 'system_admin') && (
          <section className="admin-card dashboard-feature-settings" id="dashboard-feature-access" aria-label="Dashboard feature settings">
            <div className="leave-section-heading">
              <div><p className="leave-kicker">SYSTEM SETTINGS</p><h2>Dashboard feature access</h2></div>
            </div>
            <div className="dashboard-feature-list">
              {Object.keys(dashboardRoleFeatures).map((roleName) => (
                <div className="dashboard-feature-row" key={roleName}>
                  <span>{roleName.replace('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())}</span>
                  <div className="dashboard-feature-toggle-group">
                    <label className="dashboard-feature-control">
                      <input
                        type="checkbox"
                        checked={dashboardRoleFeatures[roleName]?.sales_reports !== false}
                        onChange={(event) => updateDashboardRoleFeature(roleName, 'sales_reports', event.target.checked)}
                        aria-label={`Sales Reports for ${roleName.replace('_', ' ').toLowerCase()}`}
                      />
                      <span>Sales Reports</span>
                      <strong>{dashboardRoleFeatures[roleName]?.sales_reports === false ? 'Disabled' : 'Enabled'}</strong>
                    </label>
                    <label className="dashboard-feature-control">
                      <input
                        type="checkbox"
                        checked={dashboardRoleFeatures[roleName]?.debt_collection !== false}
                        onChange={(event) => updateDashboardRoleFeature(roleName, 'debt_collection', event.target.checked)}
                        aria-label={`Debt Collection for ${roleName.replace('_', ' ').toLowerCase()}`}
                      />
                      <span>Debt Collection</span>
                      <strong>{dashboardRoleFeatures[roleName]?.debt_collection === false ? 'Disabled' : 'Enabled'}</strong>
                    </label>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {canApprove && <ManagedUsersPanel users={adminUsers} departments={adminDepartments} currentUser={currentUser} isSuperAdmin={isSuperAdmin} canCreateEmployee={currentUser.role === 'manager' || ['general_manager', 'department_manager', 'team_leader'].includes(currentUser.active_assignment?.organizational_role)} focusCreate={activeSection === 'create-employee'} onRefresh={loadSuperAdminData} onMessage={(text, type = 'success') => setMessage({ type, text })} />}
        {false && isHr && <HrOperationsPanel leaveTypes={adminLeaveTypes} departments={adminDepartments} audit={adminAudit} />}
        {false && isHr && <HrModulePanel employees={adminUsers} departments={adminDepartments} isSuperAdmin={isSuperAdmin} onRefresh={loadSuperAdminData} />}

        {!isSuperAdmin && (activeSection === 'sales-reports' && canAccessSalesReports ? <SalesReportsPage reports={salesReports} canEdit={canEditOperations && !canViewEmployeePerformance} canAddClient={isSalesEmployee && !canViewEmployeePerformance} canManageAgentRecords={isSalesEmployee || canEditOperations || isSuperAdmin} canViewEmployeePerformance={canViewEmployeePerformance} isFieldAgent={organizationalRole === 'field_agent' && isSalesEmployee} onSubmitted={(report) => setSalesReports((current) => [report, ...current])} /> : activeSection === 'debt-collection' && canAccessDebtCollection ? <DebtCollectionPage /> : (loading ? <div className="leave-loading">Loading your leave information...</div> : (
          <>
            <section className="leave-stat-grid" id="overview" aria-label="Leave summary">
              <div className="leave-stat-card accent-blue"><span>Available days</span><strong>{availableDays}</strong><small>Across all leave types</small></div>
              <div className="leave-stat-card accent-teal"><span>Days taken</span><strong>{usedDays}</strong><small>This leave year</small></div>
              <div className="leave-stat-card accent-amber"><span>Pending requests</span><strong>{pendingCount}</strong><small>Awaiting a decision</small></div>
            </section>

            {isSalesEmployee && canAccessSalesReports && <SalesDailyReportForm isFieldAgent={isSalesEmployee} onSubmitted={(report) => setSalesReports((current) => [report, ...current])} />}
            {canAccessSalesReports && <SalesReportsPanel reports={salesReports} />}
            {canAccessDebtCollection && <DebtCollectionPage compact />}

            {canApprove && <>
              <section className="leave-section admin-feature-section" id="team-calendar">
                <div className="leave-section-heading"><div><p className="leave-kicker">TEAM PLANNING</p><h2>Team calendar</h2></div><div className="calendar-controls"><button type="button" className="leave-secondary-button" onClick={() => setCalendarMonth(new Date(calendarDate.getFullYear(), calendarDate.getMonth() - 1, 1))} aria-label="Previous month">←</button><span className="section-meta">{calendarDate.toLocaleString(undefined, { month: 'long', year: 'numeric' })}</span><button type="button" className="leave-secondary-button" onClick={() => setCalendarMonth(new Date(calendarDate.getFullYear(), calendarDate.getMonth() + 1, 1))} aria-label="Next month">→</button><button type="button" className="leave-text-button" onClick={() => setCalendarMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}>Today</button></div></div>
                <div className="calendar-grid">{['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => <strong key={day}>{day}</strong>)}{Array.from({ length: calendarOffset }).map((_, index) => <span className="calendar-empty" key={`offset-${index}`} />)}{calendarDays.map((day) => { const events = calendarRequestsForDay(day); const selected = selectedCalendarDate === day; return <button type="button" className={`calendar-day ${events.length ? 'has-events' : ''} ${selected ? 'is-selected' : ''}`} key={day} onClick={() => setSelectedCalendarDate(selected ? null : day)}><span>{day}</span>{events.slice(0, 2).map((event) => <small key={event.id}>{event.requester_name || currentUser.name} · {event.department_name || 'Unassigned'} · {leaveTypeName(event)}</small>)}{events.length > 2 && <em>+{events.length - 2} more</em>}</button>; })}</div>
                {selectedCalendarDate && <div className="calendar-selection"><strong>{calendarDate.toLocaleString(undefined, { month: 'long' })} {selectedCalendarDate}</strong>{selectedCalendarEvents.length === 0 ? <span>No leave scheduled.</span> : selectedCalendarEvents.map((event) => <button type="button" className="calendar-event-detail" key={event.id} onClick={() => openRequestView(event, 'request')}><span>{event.requester_name || currentUser.name}</span><small>{event.department_name || 'Unassigned'} · {leaveTypeName(event)} · {formatDate(event.start_date)} - {formatDate(event.end_date)} · {workflowLabel(event)}</small></button>)}</div>}
              </section>
              <section className="leave-section admin-feature-section" id="reports">
                <div className="leave-section-heading"><div><p className="leave-kicker">OPERATIONS INSIGHT</p><h2>Leave reports</h2><p className="leave-muted">Filter, inspect, and export leave activity.</p></div><div className="report-actions"><button type="button" className="leave-secondary-button action-export" onClick={exportReport}>Export CSV</button></div></div>
                <div className="report-card-grid"><div className="report-card"><span>Matching requests</span><strong>{reportFilteredRequests.length}</strong></div><div className="report-card"><span>Approved</span><strong>{reportApproved}</strong></div><div className="report-card"><span>Rejected</span><strong>{reportRejected}</strong></div><div className="report-card"><span>Days requested</span><strong>{reportFilteredRequests.reduce((sum, request) => sum + Number(request.days_requested || 0), 0)}</strong></div></div>
                <div className="report-filter-bar"><label>From<input type="date" value={reportFilters.from} onChange={(event) => setReportFilters({ ...reportFilters, from: event.target.value })} /></label><label>To<input type="date" value={reportFilters.to} onChange={(event) => setReportFilters({ ...reportFilters, to: event.target.value })} /></label><label>Employee<input placeholder="Search name" value={reportFilters.user} onChange={(event) => setReportFilters({ ...reportFilters, user: event.target.value })} /></label><label>Status<select value={reportFilters.status} onChange={(event) => setReportFilters({ ...reportFilters, status: event.target.value })}><option value="">All statuses</option><option value="handover_pending">Waiting for delegate</option><option value="team_leader_pending">Waiting for Team Leader</option><option value="department_manager_pending">Waiting for Department Manager</option><option value="general_manager_pending">Waiting for General Manager</option><option value="hr_verification">Waiting for HR</option><option value="approved">Approved</option><option value="completed">Completed</option><option value="rejected">Rejected</option><option value="deferred">Deferred</option></select></label><label>Leave type<select value={reportFilters.leaveType} onChange={(event) => setReportFilters({ ...reportFilters, leaveType: event.target.value })}><option value="">All leave types</option>{overview.types.map((type) => <option value={type.id} key={type.id}>{type.name}</option>)}</select></label><label>Region<input placeholder="City or country" value={reportFilters.region} onChange={(event) => setReportFilters({ ...reportFilters, region: event.target.value })} /></label><button type="button" className="leave-text-button" onClick={() => setReportFilters({ from: '', to: '', user: '', status: '', leaveType: '', region: '' })}>Clear</button></div>
                <div className="report-view-tabs"><button type="button" className={reportMode === 'summary' ? 'is-active' : ''} onClick={() => setReportMode('summary')}>By leave type</button><button type="button" className={reportMode === 'details' ? 'is-active' : ''} onClick={() => setReportMode('details')}>Request details</button></div>
                <div className="leave-table-wrap compact-table"><table className="leave-table"><thead><tr>{reportMode === 'summary' ? <><th>Leave type</th><th>Requests</th><th>Days requested</th></> : <><th>Employee</th><th>Department</th><th>Leave type</th><th>Dates</th><th>Region</th><th>Status</th></>}</tr></thead><tbody>{reportMode === 'summary' ? overview.types.map((type) => { const requests = reportFilteredRequests.filter((request) => request.leave_type_id === type.id); return <tr key={type.id}><td>{type.name}</td><td>{requests.length}</td><td>{requests.reduce((sum, request) => sum + Number(request.days_requested || 0), 0)}</td></tr>; }) : reportFilteredRequests.map((request) => <tr key={`report-${request.id}`}><td>{request.requester_name || request.user_name || 'Employee'}</td><td>{request.department_name || 'Unassigned'}</td><td>{leaveTypeName(request)}</td><td>{formatDate(request.start_date)} - {formatDate(request.end_date)}</td><td>{[request.city, request.country].filter(Boolean).join(', ') || '-'}</td><td><span className={workflowStatusClass(request)}>{workflowLabel(request)}</span></td></tr>)}</tbody></table></div>
              </section>
              <section className="leave-section admin-feature-section" id="compliance">
                <div className="leave-section-heading"><div><p className="leave-kicker">CONTROL CHECKS</p><h2>Compliance</h2></div></div>
                <div className="compliance-summary"><div><strong>{reportHandoverGaps}</strong><span>pending requests with handover gaps</span></div><div><strong>{pendingRequests.length - reportHandoverGaps}</strong><span>pending requests ready for review</span></div><button className="leave-primary-button" type="button" onClick={() => navigateToSection('approvals')}>Review approvals</button></div>
              </section>
            </>}

            <section className="leave-section" id="balances">
              <div className="leave-section-heading"><div><p className="leave-kicker">YOUR ENTITLEMENT</p><h2>Leave balances</h2></div></div>
              <div className="leave-balance-grid">
                {overview.balances.length === 0 ? <p className="leave-empty">No leave balances have been configured yet.</p> : overview.balances.map((balance) => (
                  <article className="leave-balance-card" key={balance.leave_type_id}>
                    <div><h3>{balance.name}</h3><span>{balance.code}</span></div>
                    <strong>{balance.available_days}</strong>
                    <p>available of {balance.entitled_days} days</p>
                    <div className="leave-progress"><span style={{ width: `${Math.min(100, (Number(balance.used_days) / Math.max(1, Number(balance.entitled_days))) * 100)}%` }} /></div>
                    <small>{balance.used_days} used · {balance.pending_days} pending</small>
                  </article>
                ))}
              </div>
            </section>

            <section className="leave-section" id="requests">
              <div className="leave-section-heading"><div><p className="leave-kicker">TIME AWAY</p><h2>My leave requests</h2></div></div>
              <div className="leave-table-wrap">
                {overview.requests.length === 0 ? <p className="leave-empty">You have not submitted any leave requests.</p> : <table className="leave-table"><thead><tr><th>Department</th><th>Leave type</th><th>Dates</th><th>Days</th><th>Status</th><th>Actions</th></tr></thead><tbody>{overview.requests.map((request) => { const chatStage = getChatStage(request); return <tr key={request.id}><td>{request.department_name || 'Unassigned'}</td><td>{request.type_name || request.leave_type_name || leaveTypeName(request)}</td><td>{formatDate(request.start_date)} - {formatDate(request.end_date)}</td><td>{request.days_requested}</td><td><span className={workflowStatusClass(request)}>{workflowLabel(request)}</span></td><td>{request.status === 'pending' && <button type="button" className="leave-text-button" onClick={() => cancelRequest(request.id)}>Cancel</button>}{Number(request.days_requested) > 2 && <button type="button" className="leave-text-button" onClick={() => setOpenHandoverId(openHandoverId === request.id ? null : request.id)}>{openHandoverId === request.id ? 'Hide handover' : 'Handover report'}</button>}{chatStage && <button type="button" className="leave-text-button leave-request-chat-button" onClick={() => openStatusChat(request)}>Chat {chatStage}</button>}</td></tr>; })}</tbody></table>}
              </div>
              {overview.requests.filter((request) => request.id === openHandoverId).map((request) => <HandoverReportForm key={request.id} requestId={request.id} onClose={() => setOpenHandoverId(null)} onSubmitted={() => { setMessage({ type: 'success', text: 'Handover report submitted.' }); loadData(); }} />)}
            </section>

            <section className="leave-section" id="history">
              <div className="leave-section-heading"><div><p className="leave-kicker">RECORDS</p><h2>Leave history</h2><p className="leave-muted">A complete record of your submitted leave requests.</p></div></div>
              <div className="leave-table-wrap">
                {historyRequests.length === 0 ? <p className="leave-empty">Your leave history is empty.</p> : <table className="leave-table"><thead><tr><th>Leave type</th><th>Applied</th><th>Dates</th><th>Days</th><th>Status</th><th>Decision</th><th>Actions</th></tr></thead><tbody>{historyRequests.map((request) => { const chatStage = getChatStage(request); return <tr key={`history-${request.id}`}><td>{request.type_name || request.leave_type_name || leaveTypeName(request)}</td><td>{request.applied_at ? new Date(request.applied_at).toLocaleDateString() : '-'}</td><td>{formatDate(request.start_date)} - {formatDate(request.end_date)}</td><td>{request.days_requested}</td><td><span className={workflowStatusClass(request)}>{workflowLabel(request)}</span></td><td>{request.decision_comment || (request.decided_at ? new Date(request.decided_at).toLocaleDateString() : 'Pending')}</td><td>{chatStage && <button type="button" className="leave-text-button leave-request-chat-button" onClick={() => openStatusChat(request)}>Chat {chatStage}</button>}</td></tr>; })}</tbody></table>}
              </div>
            </section>

            <section className="leave-section" id="settings">
              <div className="leave-section-heading"><div><p className="leave-kicker">ACCOUNT</p><h2>Settings</h2></div></div>
              <label className="checkbox-row"><input type="checkbox" checked={emailNotifications} onChange={(event) => { setEmailNotifications(event.target.checked); window.sessionStorage.setItem('okoa_email_notifications', String(event.target.checked)); }} /> Receive leave and handover notifications</label>
            </section>

            <section className="leave-section" id="delegations"><div className="leave-section-heading"><div><p className="leave-kicker">HANDOVER</p><h2>Handover report</h2><p className="leave-muted">Leave handovers assigned to you by colleagues.</p></div></div>{delegations.length === 0 ? <p className="leave-empty">No handover reports have been assigned to you.</p> : delegations.map((request) => <div className="profile-summary delegate-card" key={request.id}><div><strong>{request.requester_name || 'Employee'} · {leaveTypeName(request)} · {formatDate(request.start_date)} - {formatDate(request.end_date)} · {request.days_requested} days</strong><p>{request.handover_statement ? `Current status: ${request.handover_statement}` : 'Briefing: pending your confirmation.'}</p><div className="delegate-card-actions"><button type="button" className="leave-secondary-button" onClick={() => openRequestView(request, 'request')}>View Request</button><button type="button" className="leave-secondary-button" onClick={() => openRequestView(request, 'report')}>View report</button><button type="button" className="leave-secondary-button" onClick={() => openRequestChat(request)}>Chat requester</button></div></div>{request.handover_statement && !request.handover_statement.startsWith('DECLINED:') ? <><p className="leave-muted">This handover has been actioned.</p><HandoverReportForm requestId={request.id} readOnly /></> : <HandoverAcceptance requestId={request.id} onComplete={loadData} />}</div>)}</section>
            {canApprove && <section className="leave-section" id="approvals"><div className="leave-section-heading"><div><p className="leave-kicker">TEAM WORKFLOW</p><h2>Leave approvals</h2><p className="leave-muted">Review submitted requests and complete the next permitted action.</p></div></div><div className="approval-card-list">{pendingRequests.length === 0 ? <p className="leave-empty">No submitted leave requests are currently assigned to this approval queue.</p> : pendingRequests.map((request) => { const gate = request.handover_gate || {}; const handoverReady = !gate.required || (gate.assigned && gate.accepted && (!gate.report_required || gate.report_submitted)); return <ApprovalRequestCard key={`card-${request.id}`} request={request} leaveType={request.type_name} formatDate={formatDate} workflowLabel={workflowLabel} workflowStatusClass={workflowStatusClass} handoverReady={handoverReady} canVerify={(isHr || isSuperAdmin) && request.workflow_state === 'hr_verification'} waitingForDelegate={false} waitingForManager={false} onView={openRequestView} onChat={openRequestChat} onDecide={decideRequest} onChase={chaseDelegate} onVerify={verifyRequest} />; })}</div></section>}

            {isSuperAdmin && (
              <>
                <section className="leave-section" id="user-management">
                  <div className="leave-section-heading"><div><p className="leave-kicker">AUTHORITY</p><h2>User management</h2></div></div>
                  {canAssignEmployeeDuties && <label className="user-duty-search">Find employee<input type="search" value={userDutySearch} onChange={(event) => setUserDutySearch(event.target.value)} placeholder="Name, email or employee ID" /></label>}
                  <div className="leave-table-wrap">
                    <table className="leave-table">
                      <thead>
                        <tr><th>Name</th><th>Account role</th><th>Assigned duties</th><th>Status</th><th>Phone</th><th>Department</th><th>Actions</th></tr>
                      </thead>
                      <tbody>
                        {filteredDutyUsers.map((user) => (
                          <tr key={user.id}>
                            <td>{user.full_name}</td>
                            <td>
                              <select value={user.role} onChange={(event) => updateAdminUserRole(user.id, event.target.value, user.is_superuser)}>
                                <option value="employee">Employee</option>
                                <option value="manager">Manager</option>
                                <option value="hr_admin">HR Admin</option>
                              </select>
                            </td>
                            <td>
                              {canAssignEmployeeDuties ? (
                                <div className="employee-duty-toggles">
                                  <label className="role-toggle"><input type="checkbox" checked={(userDuties[user.id] || []).includes('departmental_manager')} onChange={(event) => updateUserDuty(user.id, 'departmental_manager', event.target.checked)} /> Departmental Manager</label>
                                  <label className="role-toggle"><input type="checkbox" checked={(userDuties[user.id] || []).includes('sales_marketing_executive')} onChange={(event) => updateUserDuty(user.id, 'sales_marketing_executive', event.target.checked)} /> Sales and Marketing Executive</label>
                                  <label className="role-toggle"><input type="checkbox" checked={(userDuties[user.id] || []).includes('debt_collector_agent')} onChange={(event) => updateUserDuty(user.id, 'debt_collector_agent', event.target.checked)} /> Debt Collector Agent</label>
                                </div>
                              ) : (userDuties[user.id] || []).join(', ') || 'No assigned duties'}
                            </td>
                            <td>{user.account_status === 'pending' ? 'Pending approval' : (user.state || (user.is_active ? 'Active' : 'Deactivated'))}</td>
                            <td>{user.phone_number}</td>
                            <td>{user.department || 'General'}</td>
                            <td>
                              {currentUser?.id !== user.id && (
                                <label className="role-toggle">
                                  <input type="checkbox" checked={Boolean(user.is_superuser)} onChange={(event) => updateAdminUserRole(user.id, user.role, event.target.checked)} />
                                  Super admin
                                </label>
                              )}
                              <button className="leave-text-button edit-action" type="button" onClick={() => startAdminUserEdit(user)}>Edit</button>
                              {currentUser?.id !== user.id && <button className="leave-text-button danger-action" type="button" onClick={() => deleteAdminUser(user.id)}>Delete</button>}
                            </td>
                          </tr>
                        ))}
                        {filteredDutyUsers.length === 0 && <tr><td colSpan="7">No employees match this search.</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="leave-section" id="audit-log">
                  <div className="leave-section-heading"><div><p className="leave-kicker">SYSTEM LOGS</p><h2>Audit feed</h2></div></div>
                  <div className="leave-table-wrap">
                    <table className="leave-table">
                      <thead><tr><th>Action</th><th>Actor</th><th>Time</th></tr></thead>
                      <tbody>
                        {adminAudit.length === 0 ? <tr><td colSpan="3">No audit entries yet.</td></tr> : adminAudit.map((entry) => (
                          <tr key={entry.id}><td>{entry.action}</td><td>{entry.actor}</td><td>{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '-'}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
          </>
        )))}
      </main>

      {requestView && <div className="leave-modal-backdrop" role="presentation"><div className="leave-modal leave-modal-wide request-view-modal" role="dialog" aria-modal="true" aria-labelledby="request-view-title"><div className="leave-modal-heading"><div><p className="leave-kicker">LEAVE REQUEST #{requestView.request.id}</p><h2 id="request-view-title">{requestView.view === 'handover' ? 'Handover details' : requestView.view === 'report' ? 'Handover report' : requestView.view === 'more' ? 'Request actions' : 'Request details'}</h2></div><button className="leave-close" type="button" onClick={() => setRequestView(null)} aria-label="Close">×</button></div>{requestView.view === 'report' || requestView.view === 'handover' ? <><div className="request-summary-strip"><strong>{requestView.request.requester_name || currentUser.name}</strong><span>{requestView.request.department_name || 'Unassigned'} · {leaveTypeName(requestView.request)} · {formatDate(requestView.request.start_date)} - {formatDate(requestView.request.end_date)}</span></div><HandoverReportForm requestId={requestView.request.id} readOnly /></> : requestView.view === 'more' ? <div className="request-action-menu"><button type="button" className="leave-secondary-button" onClick={() => openRequestView(requestView.request, 'report')}>View Report</button><button type="button" className="leave-secondary-button" onClick={() => openRequestView(requestView.request, 'delegate')}>View Delegate</button><button type="button" className="leave-secondary-button" onClick={() => openRequestView(requestView.request, 'history')}>View History</button><a className="leave-secondary-button" href={`/api/leave/requests/${requestView.request.id}/handover/pdf`} target="_blank" rel="noreferrer">View PDF</a><button type="button" className="leave-secondary-button" onClick={() => openRequestChat(requestView.request)}>View Chat</button></div> : requestView.view === 'delegate' ? <div className="request-detail-grid"><strong>Delegate</strong><span>{requestView.request.handover_name || chatUsers.find((peer) => peer.id === requestView.request.handover_user_id)?.name || 'Not assigned'}</span><strong>Acceptance</strong><span>{requestView.request.handover_agreed_at ? new Date(requestView.request.handover_agreed_at).toLocaleString() : 'Pending'}</span></div> : requestView.view === 'history' ? <div className="request-detail-grid"><strong>Submitted</strong><span>{requestView.request.applied_at ? new Date(requestView.request.applied_at).toLocaleString() : '-'}</span><strong>Workflow</strong><span>{workflowLabel(requestView.request)}</span><strong>Supervisor</strong><span>{requestView.request.supervisor_name || 'Pending'}</span><strong>Decision</strong><span>{requestView.request.supervisor_decision || 'Pending'}</span><strong>HR verification</strong><span>{requestView.request.hr_verification_date ? new Date(requestView.request.hr_verification_date).toLocaleString() : 'Pending'}</span></div> : <div className="request-detail-grid"><strong>Employee</strong><span>{requestView.request.requester_name || currentUser.name}</span><strong>Department</strong><span>{requestView.request.department_name || 'Unassigned'}</span><strong>Leave type</strong><span>{leaveTypeName(requestView.request)}</span><strong>Dates</strong><span>{formatDate(requestView.request.start_date)} - {formatDate(requestView.request.end_date)}</span><strong>Days</strong><span>{requestView.request.days_requested}</span><strong>Reason</strong><span>{requestView.request.reason || '-'}</span><strong>Status</strong><span>{workflowLabel(requestView.request)}</span><strong>Decision comment</strong><span>{requestView.request.decision_comment || 'No feedback recorded.'}</span></div>}<div className="leave-modal-actions"><button type="button" className="leave-secondary-button" onClick={() => openRequestChat(requestView.request)}>View Chat</button><button type="button" className="leave-secondary-button" onClick={() => setRequestView(null)}>Close</button></div></div></div>}

      {showRequestForm && <LeaveApplicationWizard currentUser={currentUser} leaveTypes={overview.types} colleagues={chatUsers} onClose={() => setShowRequestForm(false)} onSubmitted={async () => { setShowRequestForm(false); setMessage({ type: 'success', text: 'Leave request submitted.' }); await loadData(); }} />}

      {showLegacyRequestForm && <div className="leave-modal-backdrop" role="presentation"><div className="leave-modal leave-modal-wide" role="dialog" aria-modal="true" aria-labelledby="request-leave-title"><div className="leave-modal-heading"><div><p className="leave-kicker">NEW REQUEST</p><h2 id="request-leave-title">Request leave</h2></div><button className="leave-close" onClick={() => setShowLegacyRequestForm(false)} aria-label="Close">×</button></div><form onSubmit={submitRequest}><label>Leave type<select name="leave_type_id" value={form.leave_type_id} onChange={updateForm} required><option value="">Select leave type</option>{overview.types.map((type) => <option value={type.id} key={type.id}>{type.name}</option>)}</select></label><div className="leave-form-row"><label>First day<input type="date" name="start_date" value={form.start_date} onChange={updateForm} required /></label><label>Last day<input type="date" name="end_date" value={form.end_date} onChange={updateForm} required /></label><div className="days-preview"><span>Working days</span><strong>{workingDays()}</strong></div></div><label>Reason<textarea name="reason" value={form.reason} onChange={updateForm} rows="3" placeholder="Add a short reason for your request" required /></label><fieldset className="leave-fieldset"><legend>How we can reach you while away</legend><div className="leave-form-row"><label>Contact phone<input name="contact_phone" value={form.contact_phone} onChange={updateForm} required /></label><label>Contact email<input type="email" name="contact_email" value={form.contact_email} onChange={updateForm} required /></label></div><div className="leave-form-row"><label>Address<input name="address_line1" value={form.address_line1} onChange={updateForm} required /></label><label>City<input name="city" value={form.city} onChange={updateForm} required /></label></div><div className="leave-form-row"><label>Country<input name="country" value={form.country} onChange={updateForm} required /></label><label>Postal code<input name="postal_code" value={form.postal_code} onChange={updateForm} /></label></div></fieldset>{workingDays() > 2 && <fieldset className="leave-fieldset"><legend>Handover</legend><label>Colleague responsible<select name="handover_user_id" value={form.handover_user_id} onChange={updateForm} required><option value="">Select a colleague</option>{chatUsers.map((peer) => <option value={peer.id} key={peer.id}>{peer.name}</option>)}</select></label>{workingDays() > 3 && <label>Full handover report<textarea name="handover_report" value={form.handover_report} onChange={updateForm} rows="4" required placeholder="List work, deadlines, contacts, and risks." /></label>}<p className="leave-helper">The assigned colleague must acknowledge responsibility before the request can be fully handed over.</p></fieldset>}<div className="leave-modal-actions"><button type="button" className="leave-secondary-button" onClick={() => setShowLegacyRequestForm(false)}>Back</button><button type="submit" className="leave-primary-button" disabled={submitting}>{submitting ? 'Submitting...' : 'Submit request'}</button></div></form></div></div>}
      {showProfile && <div className="leave-modal-backdrop" role="presentation"><div className="leave-modal leave-modal-wide" role="dialog" aria-modal="true" aria-labelledby="profile-title"><div className="leave-modal-heading"><div><p className="leave-kicker">YOUR DETAILS</p><h2 id="profile-title">Edit profile</h2></div><button className="leave-close" onClick={() => setShowProfile(false)} aria-label="Close">×</button></div><form onSubmit={saveProfile}><label>Profile photo<input type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={changeProfilePhoto} /><span className="leave-helper">JPG, PNG, GIF, or WEBP up to 5 MB.</span></label>{profilePhoto && <button type="button" className="leave-text-button" onClick={removeProfilePhoto}>Remove photo</button>}<div className="leave-form-row">{[['employee_name','Employee name'],['job_position_title','Job position title']].map(([name,label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} required /></label>)}</div><div className="leave-form-row">{[['employer','Employer'],['department','Department']].map(([name,label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} required /></label>)}</div><fieldset className="leave-fieldset"><legend>Contact and address</legend><div className="leave-form-row">{[['contact_phone','Phone'],['contact_email','Email']].map(([name,label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} /></label>)}</div><div className="leave-form-row">{[['address_line1','Address'],['address_line2','Address line 2'],['city','City'],['country','Country'],['postal_code','Postal code']].map(([name,label]) => <label key={name}>{label}<input name={name} value={profileForm[name] || ''} onChange={(event) => setProfileForm({ ...profileForm, [name]: event.target.value })} /></label>)}</div></fieldset><div className="leave-modal-actions"><button type="button" className="leave-secondary-button" onClick={() => setShowProfile(false)}>Back</button><button type="submit" className="leave-primary-button">Save profile</button></div></form></div></div>}
      {showChat && <div className="leave-modal-backdrop" role="presentation"><div className="leave-modal chat-modal" role="dialog" aria-modal="true" aria-labelledby="chat-title"><div className="leave-modal-heading"><div><p className="leave-kicker">TEAM CHAT</p><h2 id="chat-title">Messages</h2></div><button className="leave-close" type="button" onClick={() => { setShowChat(false); setChatTarget(null); }} aria-label="Close">×</button></div>{chatTarget?.role === 'manager' && <p className="leave-muted">Choose a manager for {chatTarget.department || 'your department'}.</p>}<label>{chatTarget?.role === 'manager' ? 'Manager' : 'Chat with'}<select value={chatPeer} onChange={(event) => setChatPeer(event.target.value)}><option value="">{chatTarget?.role === 'manager' ? 'Select a manager' : 'Select a colleague'}</option>{chatUsers.map((peer) => <option value={peer.id} key={peer.id}>{peer.name}</option>)}</select></label>{chatError && <div className="leave-alert error chat-error" role="alert">{chatError}<button type="button" className="leave-text-button" onClick={loadChat}>Try again</button></div>}<div className="chat-messages" aria-live="polite">{chatLoading ? <p className="leave-empty">Loading messages...</p> : chatMessages.length === 0 ? <p className="leave-empty">No messages yet. Start the conversation below.</p> : chatMessages.map((item) => <div className={`chat-message ${item.sender_id === currentUser.id ? 'mine' : ''}`} key={item.id}><span>{item.sender_name} · {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><p>{item.body}</p></div>)}</div><form className="chat-compose" onSubmit={submitChat}><input value={chatBody} onChange={(event) => setChatBody(event.target.value)} placeholder="Write a message" maxLength="2000" disabled={!chatPeer || chatLoading} /><button className="leave-primary-button" type="submit" disabled={!chatPeer || !chatBody.trim() || chatLoading}>Send</button></form></div></div>}
      {decisionDialog?.request && (
        <div className="leave-modal-backdrop decision-backdrop" role="presentation">
          <div className={`leave-modal decision-modal decision-${decisionDialog.decision}`} role="dialog" aria-modal="true" aria-labelledby="decision-title">
            <div className="decision-modal-icon" aria-hidden="true">{decisionDialog.decision === 'approve' ? '✓' : decisionDialog.decision === 'reject' ? '!' : '…'}</div>
            <div className="leave-modal-heading">
              <div>
                <p className="leave-kicker">WORKFLOW DECISION</p>
                <h2 id="decision-title">{decisionDialog.decision === 'approve' ? 'Approve leave request?' : decisionDialog.decision === 'reject' ? 'Reject leave request?' : 'Defer leave request?'}</h2>
              </div>
              <button className="leave-close" type="button" onClick={() => setDecisionDialog(null)} aria-label="Close decision dialog">×</button>
            </div>
            <div className="decision-request-summary">
              <strong>{decisionDialog.request.requester_name || 'Employee'}</strong>
              <span>{leaveTypeName(decisionDialog.request)} · {formatDate(decisionDialog.request.start_date)} - {formatDate(decisionDialog.request.end_date)} · {decisionDialog.request.days_requested} days</span>
            </div>
            <p className="decision-message">{decisionDialog.decision === 'approve' ? 'This request has completed its handover checks and will move to the next workflow stage.' : decisionDialog.decision === 'reject' ? 'The employee will be notified that this leave request was not approved.' : 'The request will remain pending and can be reviewed again later.'}</p>
            <fieldset className="leave-fieldset">
              <legend>Immediate Supervisor</legend>
              <div className="leave-form-row">
                <label>Name<input value={currentUser?.full_name || currentUser?.name || ''} readOnly /></label>
                <label>Signature<input value={decisionSignature} onChange={(event) => setDecisionSignature(event.target.value)} required /></label>
                <label>Date<input type="date" value={new Date().toISOString().slice(0, 10)} readOnly /></label>
              </div>
            </fieldset>
            <label className="decision-comment-label">{decisionDialog.decision === 'approve' ? 'Comment (optional)' : 'Reason (minimum 10 characters)'}<textarea value={decisionComment} onChange={(event) => setDecisionComment(event.target.value)} placeholder={decisionDialog.decision === 'approve' ? 'Add a note for the employee' : 'Explain the decision clearly'} rows="4" autoFocus /></label>
            <div className="decision-modal-actions">
              <button type="button" className="leave-secondary-button" onClick={() => setDecisionDialog(null)}>Cancel</button>
              <button type="button" className={decisionDialog.decision === 'reject' ? 'leave-danger-button' : decisionDialog.decision === 'defer' ? 'leave-secondary-button' : 'leave-primary-button'} onClick={submitDecision}>{decisionDialog.decision === 'approve' ? 'Approve request' : decisionDialog.decision === 'reject' ? 'Reject request' : 'Defer request'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LeaveDashboard;
