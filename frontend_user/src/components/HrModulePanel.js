import React, { useEffect, useState } from 'react';
import { getAuthToken } from '../services/authStorage';
import { apiUrl } from '../services/apiConfig';
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

const hrHighlights = [
  { label: 'Active employees', value: '284', detail: 'Across all departments', tone: 'blue' },
  { label: 'Open vacancies', value: '08', detail: 'Hiring in progress', tone: 'orange' },
  { label: 'Asset assignments', value: '36', detail: 'Equipment in circulation', tone: 'teal' },
];

const moduleCards = [
  { title: 'Employee Profiles', description: 'Maintain identity, role, policy, and emergency contact details.', status: 'Live', accent: 'blue' },
  { title: 'Asset Management', description: 'Track laptops, phones, and issued equipment by employee and status.', status: 'Ready', accent: 'teal' },
  { title: 'Recruitment', description: 'Manage job requisitions, candidates, interviews, and offers.', status: 'Drafting', accent: 'orange' },
  { title: 'Shift Scheduling', description: 'Assign daily rosters, rotate coverage, and monitor attendance.', status: 'Active', accent: 'blue' },
  { title: 'Performance', description: 'Capture KPIs, review cycles, and development goals.', status: 'Queued', accent: 'teal' },
];

const moduleWorkspaces = {
  'Asset Management': { key: 'assets', subtitle: 'Track issued equipment and ownership.', fields: [['asset', 'Asset type'], ['tag', 'Asset tag'], ['employee', 'Assigned employee'], ['status', 'Status']] },
  Recruitment: { key: 'recruitment', subtitle: 'Track open roles and hiring progress.', fields: [['role', 'Role'], ['department', 'Department'], ['owner', 'Hiring manager'], ['stage', 'Stage']] },
  'Shift Scheduling': { key: 'shifts', subtitle: 'Plan coverage and record team rosters.', fields: [['date', 'Date'], ['employee', 'Employee'], ['start', 'Start time'], ['end', 'End time'], ['location', 'Location']] },
  Performance: { key: 'performance', subtitle: 'Track review cycles and development goals.', fields: [['employee', 'Employee'], ['cycle', 'Review cycle'], ['focus', 'KPI focus'], ['status', 'Status']] },
};

const emptyProfileForm = {
  full_name: '',
  email: '',
  phone_number: '',
  department: 'General',
  role: 'employee',
  job_position_title: organizationRoleLabels.field_agent,
  organizational_role: 'field_agent',
  department_role: '',
  manager_id: '',
  employer: 'Okoa Float Ltd',
  hire_date: '',
  city: '',
  address_line1: '',
  country: 'Kenya',
  password: '',
};

export default function HrModulePanel({ employees = [], departments = [], onRefresh, isSuperAdmin = false }) {
  const [profileForm, setProfileForm] = useState(emptyProfileForm);
  const [editingId, setEditingId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState({ type: '', message: '' });
  const [organizationCandidates, setOrganizationCandidates] = useState([]);
  const [activeModule, setActiveModule] = useState(null);
  const [moduleForm, setModuleForm] = useState({});
  const [moduleRecords, setModuleRecords] = useState(() => {
    try { return JSON.parse(window.sessionStorage.getItem('okoa_hr_module_records') || '{"assets":[],"recruitment":[],"shifts":[],"performance":[]}'); } catch { return { assets: [], recruitment: [], shifts: [], performance: [] }; }
  });
  const managerRole = managerRoleByPosition[profileForm.organizational_role];
  const managerCandidates = organizationCandidates.filter((candidate) => (
    candidate.organizational_role === managerRole
    && (
      profileForm.organizational_role === 'department_manager'
      || candidate.department_id === departments.find(
        (department) => department.name === profileForm.department,
      )?.id
    )
  ));

  useEffect(() => {
    let active = true;
    organizationApi.getTransferCandidates()
      .then((candidates) => {
        if (active) setOrganizationCandidates(candidates || []);
      })
      .catch((error) => {
        if (active) setFeedback({ type: 'error', message: error.message });
      });
    return () => { active = false; };
  }, []);

  const employeeDirectory = employees.length
    ? employees.map((employee) => ({
        id: employee.id,
        full_name: employee.full_name || employee.name || 'Unnamed employee',
        name: employee.full_name || employee.name || 'Unnamed employee',
        role: employee.role || employee.job_position_title || 'Employee',
        department: employee.department || employee.department_details?.name || departments.find((item) => item.id === employee.department_id)?.name || 'General',
        location: employee.location || employee.city || employee.contact?.city || 'Nairobi',
        email: employee.email || employee.contact?.email || '',
        phone: employee.phone_number || employee.contact?.phone || '',
        phone_number: employee.phone_number || employee.contact?.phone || '',
        job_position_title: employee.job_position_title || '',
        employer: employee.employer || 'Okoa Float Ltd',
        hire_date: employee.hire_date || '',
        city: employee.city || employee.contact?.city || '',
        country: employee.country || employee.contact?.country || 'Kenya',
        address_line1: employee.address_line1 || employee.contact?.address_line1 || '',
        address_line2: employee.address_line2 || employee.contact?.address_line2 || '',
        contact: employee.contact || {},
      }))
    : [{ id: 'empty', name: 'No employees yet', role: '—', department: '—', location: '—', email: '', phone: '' }];

  const handleFieldChange = (field, value) => {
    setProfileForm((current) => ({ ...current, [field]: value }));
  };

  const resetForm = () => {
    setProfileForm(emptyProfileForm);
    setEditingId(null);
  };

  const startEdit = (employee) => {
    setEditingId(employee.id);
    setProfileForm({
      full_name: employee.full_name || '',
      email: employee.email || '',
      phone_number: employee.phone_number || employee.contact?.phone || '',
      department: employee.department || employee.department_details?.name || 'General',
      role: employee.role || 'employee',
      job_position_title: employee.job_position_title || '',
      organizational_role: 'field_agent',
      department_role: '',
      manager_id: '',
      employer: employee.employer || 'Okoa Float Ltd',
      hire_date: employee.hire_date || '',
      city: employee.city || employee.contact?.city || '',
      address_line1: employee.address_line1 || employee.contact?.address_line1 || '',
      country: employee.country || employee.contact?.country || 'Kenya',
      password: '',
    });
  };

  const submitProfile = async (event) => {
    event.preventDefault();
    setFeedback({ type: '', message: '' });
    if (
      !editingId
      && ['field_agent', 'team_leader', 'department_manager'].includes(profileForm.organizational_role)
      && !profileForm.department_role
    ) {
      setFeedback({ type: 'error', message: 'Select the operational role matching the chosen department.' });
      return;
    }
    if (
      !editingId
      && profileForm.organizational_role !== 'general_manager'
      && !profileForm.manager_id
    ) {
      setFeedback({ type: 'error', message: 'Select the employee’s manager in the organizational hierarchy.' });
      return;
    }
    setSubmitting(true);

    try {
      const token = getAuthToken();
      const normalizedRole = String(profileForm.role || 'employee').trim().toLowerCase();
      const payload = {
        ...profileForm,
        role: normalizedRole === 'super_admin' ? 'system_admin' : ['employee', 'manager', 'hr_admin', 'system_admin'].includes(normalizedRole) ? normalizedRole : 'employee',
        full_name: profileForm.full_name.trim(),
        email: profileForm.email.trim(),
        phone_number: profileForm.phone_number.trim(),
        department: profileForm.department.trim() || 'General',
        job_position_title: profileForm.job_position_title.trim(),
        employer: profileForm.employer.trim() || 'Okoa Float Ltd',
        city: profileForm.city.trim(),
        address_line1: profileForm.address_line1.trim(),
        country: profileForm.country.trim() || 'Kenya',
        ...(!editingId ? {
          organizational_role: profileForm.organizational_role,
          department_role: profileForm.department_role,
          manager_id: profileForm.manager_id,
        } : {}),
      };
      if (editingId) {
        delete payload.organizational_role;
        delete payload.department_role;
        delete payload.manager_id;
      }

      const requestOptions = {
        method: editingId ? 'PATCH' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      };

      const response = await fetch(apiUrl(editingId ? `/api/auth/admin/users/${editingId}` : '/api/auth/admin/users'), requestOptions);
      const payloadData = await response.json();
      if (!response.ok) {
        throw new Error(payloadData?.error?.message || 'Unable to save employee profile.');
      }

      setFeedback({ type: 'success', message: editingId ? 'Employee profile updated.' : 'Employee profile created.' });
      resetForm();
      if (typeof onRefresh === 'function') {
        await onRefresh();
      }
    } catch (error) {
      setFeedback({ type: 'error', message: error.message || 'Unable to save employee profile.' });
    } finally {
      setSubmitting(false);
    }
  };

  const profileFormContent = () => (
    <form onSubmit={submitProfile} className="admin-form hr-profile-form">
      <div className="leave-form-row">
        <label>Full name<input value={profileForm.full_name} onChange={(event) => handleFieldChange('full_name', event.target.value)} required /></label>
        {isSuperAdmin && <label>Role<select value={profileForm.role} onChange={(event) => handleFieldChange('role', event.target.value)}><option value="employee">Employee</option><option value="manager">Manager</option><option value="hr_admin">HR Admin</option><option value="system_admin">System Admin</option></select></label>}
      </div>
      <div className="leave-form-row">
        <label>Official email<input type="email" autoComplete="email" value={profileForm.email} onChange={(event) => handleFieldChange('email', event.target.value)} required /></label>
        <label>Phone<input value={profileForm.phone_number} onChange={(event) => handleFieldChange('phone_number', event.target.value)} required /></label>
      </div>
      <div className="leave-form-row">
        <label>Department<select value={profileForm.department} onChange={(event) => setProfileForm((current) => ({
          ...current,
          department: event.target.value,
          department_role: departmentRoleFor(event.target.value),
          manager_id: '',
        }))} required><option value="">Select department</option>{departments.map((department) => <option value={department.name} key={department.id}>{department.name}</option>)}</select></label>
        <label>Organizational role<select value={profileForm.organizational_role} onChange={(event) => setProfileForm((current) => ({
          ...current,
          organizational_role: event.target.value,
          job_position_title: organizationRoleLabels[event.target.value],
          department_role: event.target.value === 'general_manager'
            ? ''
            : departmentRoleFor(current.department),
          manager_id: '',
        }))}>{Object.entries(organizationRoleLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      </div>
      {!editingId && profileForm.organizational_role !== 'general_manager' && <label>Reports to — {organizationRoleLabels[managerRole]}<select value={profileForm.manager_id} onChange={(event) => handleFieldChange('manager_id', event.target.value)} required><option value="">Select manager</option>{managerCandidates.map((manager) => <option value={manager.id} key={manager.id}>{manager.name} — {manager.department}</option>)}</select></label>}
      {['field_agent', 'team_leader', 'department_manager'].includes(profileForm.organizational_role) && <label>Department role<select value={profileForm.department_role} onChange={(event) => handleFieldChange('department_role', event.target.value)} required={!editingId}><option value="">Select department access</option>{departmentRoleFor(profileForm.department) === 'sales' && <option value="sales">Sales and Marketing</option>}{departmentRoleFor(profileForm.department) === 'debt_collection' && <option value="debt_collection">Debt Collection</option>}{departmentRoleFor(profileForm.department) === 'customer_care' && <option value="customer_care">Customer Care</option>}</select></label>}
      <div className="leave-form-row">
        <label>Employer<input value={profileForm.employer} onChange={(event) => handleFieldChange('employer', event.target.value)} /></label>
        <label>Hire date<input type="date" value={profileForm.hire_date} onChange={(event) => handleFieldChange('hire_date', event.target.value)} /></label>
      </div>
      <div className="leave-form-row">
        <label>City<input value={profileForm.city} onChange={(event) => handleFieldChange('city', event.target.value)} /></label>
        <label>Country<input value={profileForm.country} onChange={(event) => handleFieldChange('country', event.target.value)} /></label>
      </div>
      <label>Address<input value={profileForm.address_line1} onChange={(event) => handleFieldChange('address_line1', event.target.value)} /></label>
      {!editingId && <label>Password<input type="password" value={profileForm.password} onChange={(event) => handleFieldChange('password', event.target.value)} placeholder="Minimum 8 characters" required /></label>}
      <div className="leave-modal-actions">
        {editingId && <button type="button" className="leave-secondary-button action-reset" onClick={resetForm}>Cancel</button>}
        <button type="submit" className="leave-primary-button" disabled={submitting}>{submitting ? (editingId ? 'Saving...' : 'Creating...') : (editingId ? 'Save profile' : 'Create profile')}</button>
      </div>
    </form>
  );

  const openModule = (title) => {
    if (title === 'Employee Profiles') {
      document.getElementById('hr-directory')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setModuleForm({});
    setActiveModule(title);
  };

  const saveModuleRecord = (event) => {
    event.preventDefault();
    const definition = moduleWorkspaces[activeModule];
    if (!definition || Object.values(moduleForm).some((value) => !String(value || '').trim())) return;
    const nextRecords = { ...moduleRecords, [definition.key]: [...(moduleRecords[definition.key] || []), { ...moduleForm, id: Date.now() }] };
    setModuleRecords(nextRecords);
    window.sessionStorage.setItem('okoa_hr_module_records', JSON.stringify(nextRecords));
    setModuleForm({});
  };

  return (
    <section className="hr-module-panel leave-section" id="hr-module" aria-label="HR module overview">
      <div className="leave-section-heading">
        <div>
          <p className="leave-kicker">HR MODULE</p>
          <h2>People operations</h2>
        </div>
        <button type="button" className="leave-secondary-button">View all modules</button>
      </div>

      <div className="hr-module-stat-grid">
        {hrHighlights.map((item) => (
          <div key={item.label} className={`leave-stat-card accent-${item.tone}`}>
            <span>{item.label}</span>
            <strong>{item.label === 'Active employees' ? employees.length : item.value}</strong>
            <small>{item.detail}</small>
          </div>
        ))}
      </div>

      <div className="hr-module-grid">
        <div className="admin-card hr-feature-card">
          <h3>Core modules</h3>
          <div className="hr-feature-list">
            {moduleCards.map((card) => (
              <article key={card.title} className={`hr-feature-item ${card.accent}`}>
                <div>
                  <strong>{card.title}</strong>
                  <p>{card.description}</p>
                </div>
                <div className="hr-feature-actions"><span>{card.status}</span><button type="button" className="leave-secondary-button action-view" onClick={() => openModule(card.title)}>{card.title === 'Employee Profiles' ? 'Open directory' : 'Open workspace'}</button></div>
              </article>
            ))}
          </div>
        </div>

        <div className="admin-card hr-directory-card" id="hr-directory">
          <h3>Employee directory</h3>
          <div className="leave-table-wrap compact-table">
            <table className="leave-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Location</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {employeeDirectory.map((employee) => (
                  <tr key={employee.id || `${employee.name}-${employee.role}`}>
                    <td>{employee.name}</td>
                    <td>{employee.role}</td>
                    <td>{employee.department}</td>
                    <td>{employee.location}</td>
                    <td>{employee.id ? <button type="button" className="leave-text-button" onClick={() => startEdit(employee)}>Edit</button> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {editingId && <div className="leave-modal-backdrop employee-edit-backdrop" role="presentation"><div className="leave-modal employee-edit-modal" role="dialog" aria-modal="true" aria-labelledby="hr-profile-edit-title"><div className="leave-modal-heading"><div><p className="leave-kicker">EMPLOYEE DIRECTORY</p><h2 id="hr-profile-edit-title">Update employee profile</h2><p className="employee-edit-subtitle">Update the employee's identity, role, and contact details.</p></div><button type="button" className="leave-close" onClick={resetForm} aria-label="Close employee profile editor">×</button></div>{feedback.message && <div className={`leave-alert ${feedback.type === 'success' ? 'success' : 'error'}`}>{feedback.message}</div>}{profileFormContent()}</div></div>}
      {activeModule && <div className="leave-modal-backdrop" role="presentation"><div className="leave-modal hr-workspace-modal" role="dialog" aria-modal="true" aria-labelledby="hr-workspace-title"><div className="leave-modal-heading"><div><p className="leave-kicker">PEOPLE OPERATIONS</p><h2 id="hr-workspace-title">{activeModule}</h2><p className="employee-edit-subtitle">{moduleWorkspaces[activeModule].subtitle}</p></div><button type="button" className="leave-close" onClick={() => setActiveModule(null)} aria-label="Close module workspace">×</button></div><form className="hr-workspace-form" onSubmit={saveModuleRecord}>{moduleWorkspaces[activeModule].fields.map(([name, label]) => <label key={name}>{label}{name === 'employee' ? <select value={moduleForm[name] || ''} onChange={(event) => setModuleForm({ ...moduleForm, [name]: event.target.value })} required><option value="">Select employee</option>{employeeDirectory.filter((employee) => employee.id !== 'empty').map((employee) => <option value={employee.name} key={employee.id}>{employee.name}</option>)}</select> : <input type={name === 'date' ? 'date' : name === 'start' || name === 'end' ? 'time' : 'text'} value={moduleForm[name] || ''} onChange={(event) => setModuleForm({ ...moduleForm, [name]: event.target.value })} required />}</label>)}<div className="leave-modal-actions"><button type="button" className="leave-secondary-button action-reset" onClick={() => setActiveModule(null)}>Close</button><button type="submit" className="leave-primary-button">Add record</button></div></form><div className="hr-workspace-report"><div className="leave-section-heading"><h3>Current records</h3><span>{(moduleRecords[moduleWorkspaces[activeModule].key] || []).length} saved</span></div>{(moduleRecords[moduleWorkspaces[activeModule].key] || []).length === 0 ? <p className="leave-empty">No records yet. Add the first one above.</p> : <div className="hr-workspace-records">{moduleRecords[moduleWorkspaces[activeModule].key].map((record) => <article key={record.id}><strong>{record.employee || record.role || record.asset}</strong><span>{Object.entries(record).filter(([key]) => key !== 'id' && key !== 'employee' && key !== 'role' && key !== 'asset').map(([, value]) => value).join(' · ')}</span></article>)}</div>}</div></div></div>}
    </section>
  );
}
