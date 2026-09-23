import React, { useEffect, useState } from 'react';
import { getAuthToken } from '../services/authStorage';
import { apiUrl } from '../services/apiConfig';

export default function ManagedUsersPanel({ users, departments = [], currentUser, isSuperAdmin, canCreateEmployee = false, onRefresh, onMessage, focusCreate = false }) {
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [creating, setCreating] = useState(focusCreate);
  const [createForm, setCreateForm] = useState({ full_name: '', email: '', phone_number: '', password: '', department: currentUser.department || '', job_position_title: 'Staff', employer: currentUser.employer || 'Okoa Float Ltd', role: 'employee' });

  useEffect(() => {
    if (focusCreate) setCreating(true);
  }, [focusCreate]);

  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const createEmployee = async (event) => {
    event.preventDefault();
    try {
      const response = await fetch(apiUrl('/api/auth/admin/users'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` }, body: JSON.stringify(createForm) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to create employee.');
      setCreateForm({ ...createForm, full_name: '', email: '', phone_number: '', password: '' });
      setCreating(false);
      onMessage('Employee created successfully.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const save = async (event) => {
    event.preventDefault();
    try {
      const response = await fetch(apiUrl(`/api/auth/admin/users/${editing.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify(form),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update user.');
      setEditing(null);
      onMessage('User updated successfully.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const changeStatus = async (userId, status) => {
    try {
      const response = await fetch(apiUrl(`/api/auth/admin/users/${userId}/status`), {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify({ status }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to update status.');
      onMessage(payload.message || 'User status updated.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const approve = async (userId) => {
    try {
      const response = await fetch(apiUrl(`/api/auth/accounts/${userId}/approve`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to approve account.');
      onMessage(payload.message || 'Account approved.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  const remove = async (userId) => {
    if (!window.confirm('Delete this user account?')) return;
    try {
      const response = await fetch(apiUrl(`/api/auth/admin/users/${userId}`), { method: 'DELETE', headers: { Authorization: `Bearer ${getAuthToken()}` } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to delete user.');
      onMessage(payload.message || 'User deleted.');
      onRefresh();
    } catch (error) { onMessage(error.message, 'error'); }
  };

  return (
    <section className="leave-section" id="managed-users">
      <div className="leave-section-heading"><div><p className="leave-kicker">TEAM DIRECTORY</p><h2>Managed users</h2></div></div>
      {canCreateEmployee && <button type="button" className="leave-primary-button" onClick={() => setCreating((value) => !value)}>{creating ? 'Close employee form' : 'Create employee'}</button>}
      {creating && <form className="admin-form admin-edit-form" onSubmit={createEmployee}><h3>Create employee</h3><div className="leave-form-row"><label>Full name<input value={createForm.full_name} onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })} required /></label><label>Email<input type="email" value={createForm.email} onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })} required /></label></div><div className="leave-form-row"><label>Phone<input value={createForm.phone_number} onChange={(event) => setCreateForm({ ...createForm, phone_number: event.target.value })} required /></label><label>Password<input type="password" minLength="8" value={createForm.password} onChange={(event) => setCreateForm({ ...createForm, password: event.target.value })} required /></label></div><label>Department<select value={createForm.department} onChange={(event) => setCreateForm({ ...createForm, department: event.target.value })} required><option value="">Select department</option>{departments.map((department) => <option value={department.name} key={department.id}>{department.name}</option>)}</select></label><div className="leave-modal-actions"><button type="submit" className="leave-primary-button">Create employee</button></div></form>}
      <div className="leave-table-wrap">
        <table className="leave-table"><thead><tr><th>Name</th><th>Role</th><th>Status</th><th>Department</th><th>Actions</th></tr></thead>
          <tbody>{users.length === 0 ? <tr><td colSpan="5">No users found.</td></tr> : users.map((user) => { const role = String(currentUser?.role || 'employee').toLowerCase(); const canManageUser = isSuperAdmin || ['hr_admin', 'system_admin', 'super_admin'].includes(role) || user.id === currentUser.id || user.manager_id === currentUser.id; return <tr key={user.id}>
            <td>{user.full_name}</td><td>{user.role}</td>
            <td><select value={user.account_status === 'pending' ? 'pending' : (user.state || (user.is_active ? 'active' : 'deactivated'))} disabled={user.id === currentUser.id || user.account_status === 'pending'} onChange={(event) => changeStatus(user.id, event.target.value)}><option value="pending">Pending approval</option><option value="active">Active</option><option value="deactivated">Deactivated</option><option value="archived">Archived</option></select></td>
            <td>{user.department || user.department_details?.name || '-'}</td>
            <td>{user.account_status === 'pending' && <button type="button" className="leave-text-button edit-action" onClick={() => approve(user.id)}>Approve</button>}{canManageUser ? <><button type="button" className="leave-text-button edit-action" onClick={() => { setEditing(user); setForm({ full_name: user.full_name || '', email: user.email || '', phone_number: user.phone_number || '', department: user.department || '', job_position_title: user.job_position_title || '', employer: user.employer || '', ...(isSuperAdmin ? { role: user.role, is_superuser: Boolean(user.is_superuser) } : {}) }); }}>Edit</button>{user.id !== currentUser.id && <button type="button" className="leave-text-button danger-action" onClick={() => remove(user.id)}>Delete</button>}</> : user.account_status !== 'pending' && <span className="user-management-readonly">View only</span>}</td>
          </tr>; })}</tbody>
        </table>
      </div>
      {editing && <div className="leave-modal-backdrop employee-edit-backdrop" role="presentation"><div className="leave-modal employee-edit-modal" role="dialog" aria-modal="true" aria-labelledby="employee-edit-title"><div className="leave-modal-heading"><div><p className="leave-kicker">TEAM DIRECTORY</p><h2 id="employee-edit-title">Edit employee profile</h2><p className="employee-edit-subtitle">Update {editing.full_name || 'this employee'}'s details and access.</p></div><button type="button" className="leave-close" onClick={() => setEditing(null)} aria-label="Close employee editor">×</button></div><form className="admin-form admin-edit-form" onSubmit={save}><div className="employee-edit-section"><h3>Contact details</h3><div className="leave-form-row"><label>Full name<input value={form.full_name} onChange={(event) => update('full_name', event.target.value)} required /></label><label>Email<input type="email" value={form.email} onChange={(event) => update('email', event.target.value)} required /></label></div><div className="leave-form-row"><label>Phone<input value={form.phone_number} onChange={(event) => update('phone_number', event.target.value)} required /></label><label>Department<input value={form.department} onChange={(event) => update('department', event.target.value)} required /></label></div></div>{isSuperAdmin && <div className="employee-edit-section"><h3>Access level</h3><label>Role<select value={form.role} onChange={(event) => update('role', event.target.value)}><option value="employee">Employee</option><option value="manager">Manager</option><option value="hr_admin">HR Admin</option><option value="system_admin">System Admin</option></select></label><p className="employee-edit-note">Role changes affect the employee's dashboard access and approval permissions.</p></div>}<div className="leave-modal-actions"><button type="button" className="leave-secondary-button action-reset" onClick={() => setEditing(null)}>Cancel</button><button type="submit" className="leave-primary-button">Save changes</button></div></form></div></div>}
    </section>
  );
}
