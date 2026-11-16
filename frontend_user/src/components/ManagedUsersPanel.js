import React, { useEffect, useRef, useState } from 'react';
import { getAuthToken } from '../services/authStorage';
import { apiUrl, readJsonResponse } from '../services/apiConfig';
import { organizationApi } from '../services/organizationApi';

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

const getUserStatus = (user) => {
  const accountStatus = String(user.account_status || '').trim().toLowerCase();
  const state = String(user.state || '').trim().toLowerCase();

  if (user.is_deleted || state === 'deleted') return 'deleted';
  if (user.is_archived || state === 'archived') return 'archived';
  if (accountStatus === 'pending' || state === 'pending') return 'pending';
  if (['banned', 'suspended'].includes(accountStatus)) return accountStatus;
  if (['deactivated', 'inactive'].includes(accountStatus) || state === 'deactivated' || user.is_active === false) {
    return 'deactivated';
  }
  if (['approved', 'active'].includes(accountStatus) || state === 'active' || user.is_active === true) {
    return 'active';
  }
  return 'unknown';
};

const canManageUser = (user, currentUser, isSuperAdmin) => {
  const role = String(currentUser?.role || 'employee').toLowerCase();
  return isSuperAdmin
    || ['hr_admin', 'system_admin', 'super_admin'].includes(role)
    || user.id === currentUser?.id
    || user.manager_id === currentUser?.id;
};

const formatFilterOption = (value) => {
  const labels = {
    active: 'Active',
    archived: 'Archived',
    banned: 'Banned',
    deactivated: 'Deactivated',
    deleted: 'Deleted',
    pending: 'Pending approval',
    suspended: 'Suspended',
    unknown: 'Unknown',
  };
  return labels[value] || value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
};
const formatOrganizationRole = (user) => (
  organizationRoleLabels[user.organizational_role]
  || user.job_position_title
  || formatFilterOption(user.role || 'employee')
);
const getUserDepartment = (user) => (
  user.organizational_role === 'general_manager'
    ? 'All'
    : user.department || user.department_details?.name || ''
);
const formatManagerOption = (manager) => (
  `${manager.name} — ${manager.organizational_role === 'general_manager' ? 'All' : manager.department}`
);

export default function ManagedUsersPanel({ users, departments = [], currentUser, isSuperAdmin, canCreateEmployee: hasCreateEmployeePermission = false, onRefresh, onMessage, focusCreate = false }) {
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [creating, setCreating] = useState(focusCreate);
  const [organizationCandidates, setOrganizationCandidates] = useState([]);
  const [managerError, setManagerError] = useState('');
  const [departmentRoles, setDepartmentRoles] = useState({});
  const [selectedUserIds, setSelectedUserIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const selectAllRef = useRef(null);
  const isSystemAdminTarget = Boolean(
    editing
    && (
      editing.is_superuser
      || ['system_admin', 'super_admin'].includes(String(editing.role || '').toLowerCase())
    )
  );
  const canCreateEmployee = hasCreateEmployeePermission && !isSystemAdminTarget;
  const [filters, setFilters] = useState({
    name: '',
    role: '',
    status: '',
    department: '',
    departmentAccess: '',
    action: '',
  });
  const [createForm, setCreateForm] = useState({
    full_name: '',
    email: '',
    phone_number: '',
    password: '',
    department: currentUser.department || '',
    department_role: departmentRoleFor(currentUser.department),
    organizational_role: 'field_agent',
    manager_id: '',
    job_position_title: 'Field Agent',
    employer: currentUser.employer || 'Okoa Float Ltd',
    role: 'employee',
  });

  useEffect(() => {
    if (focusCreate) setCreating(true);
  }, [focusCreate]);

  useEffect(() => {
    if (!creating && !editing) return undefined;
    let active = true;
    organizationApi.getTransferCandidates()
      .then((candidates) => {
        if (active) {
          setOrganizationCandidates(candidates || []);
          setManagerError('');
        }
      })
      .catch((error) => {
        if (active) setManagerError(error.message);
      });
    return () => { active = false; };
  }, [creating, editing]);

  useEffect(() => {
    setDepartmentRoles(Object.fromEntries(users.map((user) => [user.id, user.rbac_role || ''])));
  }, [users]);

  const departmentOptions = [...new Set([
    ...departments.map((department) => department.name),
    ...users.map(getUserDepartment),
  ].filter(Boolean))].sort((first, second) => first.localeCompare(second));
  const hasGeneralManager = users.some((user) => user.organizational_role === 'general_manager');

  const roleOptions = [...new Set(users.map((user) => (
    user.organizational_role || user.job_position_title || user.role || 'employee'
  )))]
    .sort((first, second) => first.localeCompare(second));
  const departmentAccessOptions = [...new Set(users.map((user) => user.rbac_role).filter(Boolean))]
    .sort((first, second) => first.localeCompare(second));
  const statusOptions = [...new Set(users.map(getUserStatus))]
    .sort((first, second) => first.localeCompare(second));
  const filteredUsers = users.filter((user) => {
    const searchableText = [user.full_name, user.email, user.phone_number, user.contact_phone]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    const role = String(user.organizational_role || user.job_position_title || user.role || 'employee').toLowerCase();
    const status = getUserStatus(user);
    const department = getUserDepartment(user).toLowerCase();
    const access = String(user.rbac_role || '').toLowerCase();
    const canManage = canManageUser(user, currentUser, isSuperAdmin);
    const selectedAction = filters.action.toLowerCase();
    const matchesAction = !selectedAction
      || (selectedAction === 'approve' && user.account_status === 'pending')
      || (selectedAction === 'edit' && canManage)
      || (selectedAction === 'delete' && canManage && user.id !== currentUser?.id)
      || (selectedAction === 'view only' && !canManage && user.account_status !== 'pending');

    return searchableText.includes(filters.name.trim().toLowerCase())
      && (!filters.role || role === filters.role.toLowerCase())
      && (!filters.status || status === filters.status)
      && (!filters.department || department === filters.department.toLowerCase())
      && (!filters.departmentAccess
        || (filters.departmentAccess === '__unassigned__' ? !access : access === filters.departmentAccess.toLowerCase()))
      && matchesAction;
  });
  const selectableFilteredUsers = filteredUsers.filter((user) => (
    canManageUser(user, currentUser, isSuperAdmin)
    && user.id !== currentUser?.id
    && getUserStatus(user) !== 'deleted'
  ));
  const selectedUsers = users.filter((user) => (
    selectedUserIds.has(user.id)
    && canManageUser(user, currentUser, isSuperAdmin)
    && user.id !== currentUser?.id
    && getUserStatus(user) !== 'deleted'
  ));
  const selectedFilteredCount = selectableFilteredUsers.filter((user) => selectedUserIds.has(user.id)).length;
  const allFilteredSelected = selectableFilteredUsers.length > 0
    && selectedFilteredCount === selectableFilteredUsers.length;
  const selectedPendingCount = selectedUsers.filter((user) => getUserStatus(user) === 'pending').length;
  const selectedInactiveCount = selectedUsers.filter((user) => ['deactivated', 'archived'].includes(getUserStatus(user))).length;
  const selectedActiveCount = selectedUsers.filter((user) => getUserStatus(user) === 'active').length;
  const selectedArchivableCount = selectedUsers.filter((user) => !['archived', 'deleted'].includes(getUserStatus(user))).length;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedFilteredCount > 0 && !allFilteredSelected;
    }
  }, [allFilteredSelected, selectedFilteredCount]);

  const updateFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
  };
  const toggleUserSelection = (userId) => {
    setSelectedUserIds((current) => {
      const next = new Set(current);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };
  const toggleFilteredSelection = () => {
    setSelectedUserIds((current) => {
      const next = new Set(current);
      if (allFilteredSelected) selectableFilteredUsers.forEach((user) => next.delete(user.id));
      else selectableFilteredUsers.forEach((user) => next.add(user.id));
      return next;
    });
  };
  const runBulkAction = async (action, targets) => {
    if (bulkBusy || targets.length === 0) return;
    const actionLabels = {
      approve: 'approve',
      active: 'activate',
      deactivated: 'deactivate',
      archived: 'archive',
      delete: 'permanently delete',
    };
    const actionLabel = actionLabels[action];
    if (action === 'delete') {
      if (!isSuperAdmin) {
        onMessage('Only the super administrator can permanently delete users.', 'error');
        return;
      }
      const detail = ' This permanently erases the selected accounts and their associated records. This cannot be undone.';
      if (!window.confirm(`Permanently delete ${targets.length} selected user${targets.length === 1 ? '' : 's'}?${detail}`)) return;

      setBulkBusy(true);
      try {
        const response = await fetch(apiUrl('/api/auth/admin/users/bulk-delete'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getAuthToken()}`,
          },
          body: JSON.stringify({ user_ids: targets.map((user) => user.id) }),
        });
        const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
        if (!response.ok) throw new Error(payload.error?.message || 'Unable to permanently delete selected users.');
        setSelectedUserIds(new Set());
        onMessage(payload.message || `Permanently deleted ${targets.length} user${targets.length === 1 ? '' : 's'}.`);
        await onRefresh();
      } catch (error) {
        onMessage(error.message, 'error');
      } finally {
        setBulkBusy(false);
      }
      return;
    }

    if (['deactivated', 'archived', 'delete'].includes(action)) {
      if (!window.confirm(`${actionLabel[0].toUpperCase()}${actionLabel.slice(1)} ${targets.length} selected user${targets.length === 1 ? '' : 's'}?`)) return;
    }

    setBulkBusy(true);
    const outcomes = [];
    let nextIndex = 0;
    const worker = async () => {
      while (nextIndex < targets.length) {
        const user = targets[nextIndex];
        nextIndex += 1;
        try {
          const isApprove = action === 'approve';
          const url = isApprove
            ? `/api/auth/accounts/${user.id}/approve`
            : `/api/auth/admin/users/${user.id}/status`;
          const response = await fetch(apiUrl(url), {
            method: 'POST',
            headers: {
              ...(!isApprove ? { 'Content-Type': 'application/json' } : {}),
              Authorization: `Bearer ${getAuthToken()}`,
            },
            ...(!isApprove ? { body: JSON.stringify({ status: action }) } : {}),
          });
          const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
          if (!response.ok) throw new Error(payload.error?.message || `Unable to ${actionLabel} ${user.full_name}.`);
          outcomes.push({ ok: true });
        } catch (error) {
          outcomes.push({ ok: false, message: error.message });
        }
      }
    };

    try {
      await Promise.all(Array.from({ length: Math.min(4, targets.length) }, worker));
      const succeeded = outcomes.filter((outcome) => outcome.ok).length;
      const failed = outcomes.length - succeeded;
      setSelectedUserIds(new Set());
      if (failed) {
        const firstFailure = outcomes.find((outcome) => !outcome.ok);
        onMessage(`${succeeded} user${succeeded === 1 ? '' : 's'} ${actionLabel}d; ${failed} failed. ${firstFailure.message}`, 'error');
      } else {
        onMessage(`${succeeded} user${succeeded === 1 ? '' : 's'} ${actionLabel}d successfully.`);
      }
      await onRefresh();
    } finally {
      setBulkBusy(false);
    }
  };
  const hasActiveFilters = Object.values(filters).some(Boolean);
  const parentRole = managerRoleByPosition[createForm.organizational_role];
  const managerCandidates = organizationCandidates.filter((candidate) => (
    candidate.organizational_role === parentRole
    && (
      createForm.organizational_role === 'department_manager'
      || candidate.department_id === departments.find(
        (department) => department.name === createForm.department,
      )?.id
    )
  ));
  const editParentRole = managerRoleByPosition[form.organizational_role];
  const editManagerCandidates = organizationCandidates.filter((candidate) => (
    candidate.id !== editing?.id
    && candidate.organizational_role === editParentRole
    && (
      form.organizational_role === 'department_manager'
      || candidate.department_id === departments.find(
        (department) => department.name === form.department,
      )?.id
    )
  ));

  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const assignDepartmentRole = async (user) => {
    const role = departmentRoles[user.id];
    if (!role) {
      onMessage('Choose a department role before assigning access.', 'error');
      return;
    }
    try {
      const response = await fetch(apiUrl(`/api/admin/users/${user.id}/department-role`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: ['Bearer', getAuthToken()].join(' ') },
        body: JSON.stringify({ role }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to assign department role.');
      onMessage(`Department access set to ${role.replace('_', ' ')} for ${user.full_name}.`);
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const createEmployee = async (event) => {
    event.preventDefault();
    if (
      ['field_agent', 'team_leader', 'department_manager'].includes(createForm.organizational_role)
      && departmentRoleFor(createForm.department)
      && !createForm.department_role
    ) {
      onMessage('Select the operational role matching the chosen department.', 'error');
      return;
    }
    if (createForm.organizational_role !== 'general_manager' && !createForm.manager_id) {
      onMessage('Select the employee’s manager in the organizational hierarchy.', 'error');
      return;
    }
    try {
      const { email, ...employeeFields } = createForm;
      const response = await fetch(apiUrl('/api/auth/admin/users'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` }, body: JSON.stringify({ ...employeeFields, official_email: email }) });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to create employee.');
      setCreateForm((current) => ({
        ...current,
        full_name: '',
        email: '',
        phone_number: '',
        password: '',
        manager_id: '',
      }));
      setCreating(false);
      onMessage('Employee created successfully.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const save = async (event) => {
    event.preventDefault();
    try {
      const { status, email, ...profileFields } = form;
      const profilePayload = {
        full_name: profileFields.full_name,
        official_email: email,
        phone_number: profileFields.phone_number,
        job_position_title: profileFields.job_position_title,
        employer: profileFields.employer,
        ...(isSuperAdmin ? {
          role: profileFields.role,
          is_superuser: profileFields.is_superuser,
        } : {}),
      };
      const profileResponse = await fetch(apiUrl(`/api/auth/admin/users/${editing.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: ['Bearer', getAuthToken()].join(' ') },
        body: JSON.stringify(profilePayload),
      });
      const profileResult = await readJsonResponse(profileResponse, 'The server responded unexpectedly.');
      if (!profileResponse.ok) throw new Error(profileResult.error?.message || 'Unable to update user details.');

      const assignmentChanged = !isSystemAdminTarget && (
        form.department !== (editing.department || editing.department_details?.name || '')
        || form.organizational_role !== (editing.organizational_role || 'field_agent')
        || form.department_role !== (editing.department_role || editing.rbac_role || '')
        || String(form.manager_id || '') !== String(editing.manager_id || '')
      );
      if (assignmentChanged) {
        if (
          ['field_agent', 'team_leader', 'department_manager'].includes(form.organizational_role)
          && departmentRoleFor(form.department)
          && !form.department_role
        ) {
          onMessage('Profile details saved. Select the operational role matching the chosen department before saving the organizational assignment.', 'error');
          await onRefresh();
          return;
        }
        if (form.organizational_role !== 'general_manager' && !form.manager_id) {
          onMessage('Profile details saved. Select the employee’s manager before saving the organizational assignment.', 'error');
          await onRefresh();
          return;
        }
        const assignmentResponse = await fetch(apiUrl(`/api/auth/admin/users/${editing.id}`), {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', Authorization: ['Bearer', getAuthToken()].join(' ') },
          body: JSON.stringify({
            department: form.department,
            organizational_role: form.organizational_role,
            department_role: form.department_role || null,
            manager_id: form.manager_id || null,
          }),
        });
        const assignmentResult = await readJsonResponse(assignmentResponse, 'The server responded unexpectedly.');
        if (!assignmentResponse.ok) {
          onMessage(`Profile details saved. Organizational assignment was not changed: ${assignmentResult.error?.message || 'Unable to update the assignment.'}`, 'error');
          await onRefresh();
          return;
        }
      }

      if (isSuperAdmin && editing.id !== currentUser?.id && status !== getUserStatus(editing)) {
        const statusResponse = await fetch(apiUrl(`/api/auth/admin/users/${editing.id}/status`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: ['Bearer', getAuthToken()].join(' ') },
          body: JSON.stringify({ status }),
        });
        const statusPayload = await readJsonResponse(
          statusResponse,
          'The server returned an invalid response while updating account status.',
        );
        if (!statusResponse.ok) {
          onMessage(`Profile details saved. Account status was not changed: ${statusPayload.error?.message || 'Unable to update account status.'}`, 'error');
          await onRefresh();
          return;
        }
      }
      setEditing(null);
      onMessage('User updated successfully.');
      await onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const changeStatus = async (userId, status) => {
    try {
      const response = await fetch(apiUrl(`/api/auth/admin/users/${userId}/status`), {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify({ status }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update status.');
      onMessage(payload.message || 'User status updated.');
      setEditing(null);
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const approve = async (userId) => {
    try {
      const response = await fetch(apiUrl(`/api/auth/accounts/${userId}/approve`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to approve account.');
      onMessage(payload.message || 'Account approved.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const remove = async (userId) => {
    if (!isSuperAdmin) {
      onMessage('Only the super administrator can permanently delete users.', 'error');
      return;
    }
    if (!window.confirm('Permanently delete this user and all associated records? This cannot be undone.')) return;
    try {
      const response = await fetch(apiUrl('/api/auth/admin/users/bulk-delete'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getAuthToken()}`,
        },
        body: JSON.stringify({ user_ids: [userId] }),
      });
      const payload = await readJsonResponse(response, 'The server responded unexpectedly.');
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to delete user.');
      onMessage(payload.message || 'User permanently deleted.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  return (
    <section className="leave-section" id="managed-users">
      <div className="leave-section-heading"><div><p className="leave-kicker">TEAM DIRECTORY</p><h2>Manage users</h2></div></div>
      {hasActiveFilters && <button type="button" className="leave-text-button user-directory-clear-filters" onClick={() => setFilters({ name: '', role: '', status: '', department: '', departmentAccess: '', action: '' })}>Clear filters</button>}
      {canCreateEmployee && <button type="button" className="leave-primary-button" onClick={() => setCreating((value) => !value)}>{creating ? 'Close employee form' : 'Create employee'}</button>}
      {selectedUsers.length > 0 && <div className="user-bulk-toolbar" aria-live="polite">
        <div className="user-bulk-summary"><strong>{selectedUsers.length} selected</strong><span>Actions apply only to accounts in a compatible status.</span></div>
        <div className="user-bulk-actions">
          {selectedPendingCount > 0 && <button type="button" className="leave-text-button success-action" disabled={bulkBusy} onClick={() => runBulkAction('approve', selectedUsers.filter((user) => getUserStatus(user) === 'pending'))}>Approve ({selectedPendingCount})</button>}
          {selectedInactiveCount > 0 && <button type="button" className="leave-text-button success-action" disabled={bulkBusy} onClick={() => runBulkAction('active', selectedUsers.filter((user) => ['deactivated', 'archived'].includes(getUserStatus(user))))}>Activate ({selectedInactiveCount})</button>}
          {selectedActiveCount > 0 && <button type="button" className="leave-text-button warning-action" disabled={bulkBusy} onClick={() => runBulkAction('deactivated', selectedUsers.filter((user) => getUserStatus(user) === 'active'))}>Deactivate ({selectedActiveCount})</button>}
          {selectedArchivableCount > 0 && <button type="button" className="leave-text-button warning-action" disabled={bulkBusy} onClick={() => runBulkAction('archived', selectedUsers.filter((user) => !['archived', 'deleted'].includes(getUserStatus(user))))}>Archive ({selectedArchivableCount})</button>}
          {isSuperAdmin && <button type="button" className="leave-text-button danger-action" disabled={bulkBusy} onClick={() => runBulkAction('delete', selectedUsers)}>{bulkBusy ? 'Deleting…' : `Permanently delete (${selectedUsers.length})`}</button>}
          <button type="button" className="leave-text-button" disabled={bulkBusy} onClick={() => setSelectedUserIds(new Set())}>Clear selection</button>
        </div>
      </div>}
      {creating && <form className="admin-form admin-edit-form" onSubmit={createEmployee}>
        <h3>Create employee</h3>
        <div className="leave-form-row">
          <label>Full name<input autoComplete="name" value={createForm.full_name} onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })} required /></label>
          <label>Official email<input type="email" autoComplete="email" value={createForm.email} onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })} required /></label>
          <label>Phone<input autoComplete="tel" value={createForm.phone_number} onChange={(event) => setCreateForm({ ...createForm, phone_number: event.target.value })} required /></label>
        </div>
        <div className="leave-form-row">
          <label>Password<input type="password" autoComplete="new-password" minLength="8" value={createForm.password} onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })} required /></label>
          {createForm.organizational_role === 'general_manager' ? (
            <label>Department<input value="All" readOnly /></label>
          ) : (
            <label>Department<select value={createForm.department} onChange={(event) => setCreateForm({
            ...createForm,
            department: event.target.value,
            department_role: departmentRoleFor(event.target.value),
            manager_id: '',
            })} required><option value="">Select department</option>{departments.map((department) => <option value={department.name} key={department.id}>{department.name}</option>)}</select></label>
          )}
          <label>Organizational role<select value={createForm.organizational_role} onChange={(event) => setCreateForm({
            ...createForm,
            organizational_role: event.target.value,
            job_position_title: organizationRoleLabels[event.target.value],
            manager_id: '',
            department_role: event.target.value === 'general_manager'
              ? ''
              : departmentRoleFor(createForm.department),
          })} required>{Object.entries(organizationRoleLabels).filter(([value]) => value !== 'general_manager' || (isSuperAdmin && !hasGeneralManager)).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        </div>
        {createForm.organizational_role !== 'general_manager' && (
          <div className="leave-form-row">
            <label>Reports to — {organizationRoleLabels[parentRole]}<select value={createForm.manager_id} onChange={(event) => setCreateForm({ ...createForm, manager_id: event.target.value })} required>
              <option value="">Select manager</option>
              {managerCandidates.map((manager) => <option value={manager.id} key={manager.id}>{formatManagerOption(manager)}</option>)}
            </select></label>
          </div>
        )}
        {['field_agent', 'team_leader', 'department_manager'].includes(createForm.organizational_role) && departmentRoleFor(createForm.department) && (
          <div className="leave-form-row">
            <label>Department role<select value={createForm.department_role} onChange={(event) => setCreateForm({ ...createForm, department_role: event.target.value })} required>
              <option value="">Select department access</option>
              {departmentRoleFor(createForm.department) === 'sales' && <option value="sales">Sales and Marketing</option>}
              {departmentRoleFor(createForm.department) === 'debt_collection' && <option value="debt_collection">Debt Collection</option>}
              {departmentRoleFor(createForm.department) === 'customer_care' && <option value="customer_care">Customer Care</option>}
            </select></label>
          </div>
        )}
        {managerError && <p role="alert">{managerError}</p>}
        <div className="leave-modal-actions"><button type="submit" className="leave-primary-button">Create employee</button></div>
      </form>}
      <div className="leave-table-wrap">
        <table className="leave-table"><thead><tr><th><label className="user-select-all-label"><input ref={selectAllRef} type="checkbox" aria-label={`Select all ${selectableFilteredUsers.length} matching manageable users`} checked={allFilteredSelected} disabled={selectableFilteredUsers.length === 0 || bulkBusy} onChange={toggleFilteredSelection} /><span>Select</span></label></th><th>Name</th><th>Role</th><th>Status</th><th>Department</th><th>Department access</th><th>Actions</th></tr><tr className="user-directory-filter-row">
          <th />
          <th><input type="search" aria-label="Search users by name, email or phone" placeholder="Name, email or phone" value={filters.name} onChange={(event) => updateFilter('name', event.target.value)} /></th>
          <th><select aria-label="Filter by role" value={filters.role} onChange={(event) => updateFilter('role', event.target.value)}><option value="">All roles</option>{roleOptions.map((role) => <option value={role} key={role}>{formatFilterOption(role)}</option>)}</select></th>
          <th><select aria-label="Filter by status" value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}><option value="">All statuses</option>{statusOptions.map((status) => <option value={status} key={status}>{formatFilterOption(status)}</option>)}</select></th>
          <th><select aria-label="Filter by department" value={filters.department} onChange={(event) => updateFilter('department', event.target.value)}><option value="">All departments</option>{departmentOptions.map((department) => <option value={department} key={department}>{department}</option>)}</select></th>
          <th><select aria-label="Filter by department access" value={filters.departmentAccess} onChange={(event) => updateFilter('departmentAccess', event.target.value)}><option value="">All access</option><option value="__unassigned__">Not assigned</option>{departmentAccessOptions.map((access) => <option value={access} key={access}>{formatFilterOption(access)}</option>)}</select></th>
          <th><select aria-label="Filter by available action" value={filters.action} onChange={(event) => updateFilter('action', event.target.value)}><option value="">All actions</option><option value="approve">Approve</option><option value="edit">Edit</option><option value="delete">Delete</option><option value="view only">View only</option></select></th>
        </tr></thead>
          <tbody>
            {filteredUsers.length === 0 ? <tr><td colSpan="7">{users.length === 0 ? 'No users found.' : 'No users match these filters.'}</td></tr> : filteredUsers.map((user) => {
              const canManage = canManageUser(user, currentUser, isSuperAdmin);
              const canSelect = canManage && user.id !== currentUser?.id && getUserStatus(user) !== 'deleted';
              const userStatus = getUserStatus(user);
              const status = formatFilterOption(userStatus);
              return (
                <tr key={user.id} className={selectedUserIds.has(user.id) ? 'user-row-selected' : undefined}>
                  <td><input type="checkbox" aria-label={`Select ${user.full_name}`} checked={selectedUserIds.has(user.id)} disabled={!canSelect || bulkBusy} onChange={() => toggleUserSelection(user.id)} /></td>
                  <td>{user.full_name}</td>
                  <td>{formatOrganizationRole(user)}</td>
                  <td><span className={`employee-account-status status-${userStatus}`} aria-label={`Account status: ${status}`}>{status}</span></td>
                  <td>{getUserDepartment(user) || '-'}</td>
                  <td>
                    {isSuperAdmin ? (
                      <div className="department-role-control">
                        <select
                          aria-label={`Department access for ${user.full_name}`}
                          value={departmentRoles[user.id] || ''}
                          onChange={(event) => setDepartmentRoles((current) => ({
                            ...current,
                            [user.id]: event.target.value,
                          }))}
                        >
                          <option value="">Not assigned</option>
                          <option value="customer_care">Customer Care</option>
                          <option value="debt_collection">Debt Collection</option>
                          <option value="sales">Sales</option>
                        </select>
                        <button
                          type="button"
                          className="leave-text-button edit-action"
                          disabled={!departmentRoles[user.id]}
                          onClick={() => assignDepartmentRole(user)}
                        >
                          Assign
                        </button>
                      </div>
                    ) : (user.rbac_role || 'Not assigned').replace('_', ' ')}
                  </td>
                  <td>
                    {user.account_status === 'pending' && <button type="button" className="leave-text-button edit-action" onClick={() => approve(user.id)}>Approve</button>}
                    {canManage && <button type="button" className="leave-text-button edit-action" onClick={() => {
                      setEditing(user);
                      setForm({
                        full_name: user.full_name || '',
                        email: user.email || '',
                        phone_number: user.phone_number || '',
                        department: user.organizational_role === 'general_manager'
                          ? 'All'
                          : user.department || '',
                        organizational_role: user.organizational_role || 'field_agent',
                        department_role: user.department_role || user.rbac_role || '',
                        manager_id: user.manager_id ? String(user.manager_id) : '',
                        job_position_title: user.job_position_title || '',
                        employer: user.employer || '',
                        status: user.account_status === 'pending' ? 'pending' : (user.state || (user.is_active ? 'active' : 'deactivated')),
                        ...(isSuperAdmin ? { role: user.role, is_superuser: Boolean(user.is_superuser) } : {}),
                      });
                    }}>Edit</button>}
                    {isSuperAdmin && canManage && user.id !== currentUser?.id && <button type="button" className="leave-text-button danger-action" onClick={() => remove(user.id)}>Delete permanently</button>}
                    {!canManage && user.account_status !== 'pending' && <span className="user-management-readonly">View only</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editing && <div className="leave-modal-backdrop employee-edit-backdrop" role="presentation"><div className="leave-modal employee-edit-modal" role="dialog" aria-modal="true" aria-labelledby="employee-edit-title"><div className="leave-modal-heading"><div><p className="leave-kicker">TEAM DIRECTORY</p><h2 id="employee-edit-title">Edit employee profile</h2><p className="employee-edit-subtitle">Update {editing.full_name || 'this employee'}'s details and access.</p></div><button type="button" className="leave-close" onClick={() => setEditing(null)} aria-label="Close employee editor">×</button></div><form className="admin-form admin-edit-form" onSubmit={save}><div className="employee-edit-section"><h3>Contact details</h3><div className="leave-form-row"><label>Full name<input value={form.full_name} onChange={(event) => update('full_name', event.target.value)} required /></label><label>Official email<input type="email" autoComplete="email" value={form.email} onChange={(event) => update('email', event.target.value)} required /></label></div><div className="leave-form-row"><label>Phone<input autoComplete="tel" value={form.phone_number} onChange={(event) => update('phone_number', event.target.value)} required /></label></div></div>{canCreateEmployee && <div className="employee-edit-section"><h3>Organizational assignment</h3><div className="leave-form-row">{form.organizational_role === 'general_manager' ? <label>Department<input value="All" readOnly /></label> : <label>Department<select className="department-select" value={form.department} onChange={(event) => setForm((current) => ({ ...current, department: event.target.value, department_role: departmentRoleFor(event.target.value), manager_id: '' }))} required><option value="">Select department</option>{departmentOptions.map((department) => <option value={department} key={department}>{department}</option>)}</select></label>}<label>Organizational role<select value={form.organizational_role} onChange={(event) => setForm((current) => ({ ...current, organizational_role: event.target.value, job_position_title: organizationRoleLabels[event.target.value],       department_role: event.target.value === 'general_manager' ? '' : departmentRoleFor(current.department), manager_id: '' }))} required>{Object.entries(organizationRoleLabels).filter(([value]) => value !== 'general_manager' || (isSuperAdmin && (!hasGeneralManager || editing.organizational_role === 'general_manager'))).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div>{form.organizational_role !== 'general_manager' && <label>Reports to — {organizationRoleLabels[editParentRole]}<select value={form.manager_id} onChange={(event) => update('manager_id', event.target.value)} required><option value="">Select manager</option>{editManagerCandidates.map((manager) => <option value={manager.id} key={manager.id}>{formatManagerOption(manager)}</option>)}</select></label>}{['field_agent', 'team_leader', 'department_manager'].includes(form.organizational_role) && <label>Department role<select value={form.department_role} onChange={(event) => update('department_role', event.target.value)} required><option value="">Select department access</option>{departmentRoleFor(form.department) === 'sales' && <option value="sales">Sales and Marketing</option>}{departmentRoleFor(form.department) === 'debt_collection' && <option value="debt_collection">Debt Collection</option>}{departmentRoleFor(form.department) === 'customer_care' && <option value="customer_care">Customer Care</option>}</select></label>}{managerError && <p role="alert">{managerError}</p>}<p className="employee-edit-note">Changing departments or roles updates active access and keeps the previous assignment in history.</p></div>}{isSuperAdmin && editing.id !== currentUser.id && <div className="employee-edit-section"><h3>Account status</h3><label>Status<select value={form.status} onChange={(event) => update('status', event.target.value)}><option value="pending">Pending approval</option><option value="active">Activate</option><option value="deactivated">Deactivate</option><option value="archived">Archive</option></select></label><button type="button" className="leave-secondary-button" onClick={() => changeStatus(editing.id, form.status)}>Update status</button></div>}{isSuperAdmin && <div className="employee-edit-section"><h3>Access level</h3><label>Role<select value={form.role} onChange={(event) => update('role', event.target.value)}><option value="employee">Employee</option><option value="manager">Manager</option><option value="hr_admin">HR Admin</option><option value="system_admin">System Admin</option></select></label><p className="employee-edit-note">Role changes affect the employee's dashboard access and approval permissions.</p></div>}<div className="leave-modal-actions"><button type="button" className="leave-secondary-button action-reset" onClick={() => setEditing(null)}>Cancel</button><button type="submit" className="leave-primary-button">Save changes</button></div></form></div></div>}
    </section>
  );
}
