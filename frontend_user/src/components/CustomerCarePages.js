import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, Clock3, Eye, Phone, Search, Siren, UserRound } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';
import { isGeneralManagerUser } from '../navigation';
import ClientProfileLookup from './ClientProfileLookup';
import SalesDailyReportForm from './SalesDailyReportForm';
import './CustomerCare.css';

const categories = ['Billing', 'Technical', 'Complaint', 'General Inquiry', 'Account', 'Other'];
const statuses = ['Resolved', 'Pending Follow-up', 'Escalated'];
const priorities = ['Low', 'Normal', 'Urgent'];
const callerTypes = [
  ['agent', 'M-Pesa Agent / Dealer'],
  ['sub_agent', 'Sub-Agent'],
  ['sales_rep', 'Okoa Float Sales & Marketing Representative'],
  ['potential_client', 'Potential Client'],
];
const inboundConcerns = [
  ['INFORMATION_INQUIRY', 'Okoa Float service overview'],
  ['REPAYMENT_PERIOD', 'Repayment period'],
  ['ELIGIBILITY', 'Eligibility'],
  ['LIMITS_MIN_MAX', 'Minimum / maximum float amount'],
  ['USAGE_FREQUENCY', 'Usage frequency'],
  ['TRANSFER_CHARGES', 'M-Pesa float transfer charges'],
  ['TRANSACTIONAL_CHARGES', 'Other transactional charges'],
  ['REGISTRATION_DOCS', 'Registration documents'],
  ['LOAN_BALANCE', 'Loan balance inquiry'],
  ['LOAN_LIMIT', 'Loan limit inquiry'],
  ['LOAN_INCREASE_REQUEST', 'Loan limit increase request'],
  ['REGISTRATION_PROCESS', 'Registration process'],
  ['CALLER_READY_TO_REGISTER', 'Caller ready to register'],
  ['RECONCILIATION', 'Payment reconciliation dispute'],
  ['PAYMENT_METHOD', 'Payment method'],
  ['ACCOUNT_STATUS', 'Account / loan status'],
  ['PRODUCT_INFO', 'Product information'],
  ['GENERAL_INQUIRY', 'General inquiry'],
  ['SALES_REG_VERIFICATION', 'Sales registration verification'],
];
const outboundReasons = [
  ['VERIFY_DOCS', 'Verify registration documents'],
  ['VERIFY_REGISTRATION', 'Verify new registration'],
  ['POST_LIMIT_SET', 'Follow-up after limit set'],
  ['POST_LIMIT_INCREASE', 'Follow-up after limit increase'],
  ['LIMIT_STATUS_ACCEPTED', 'Follow-up after limit accepted'],
  ['LIMIT_STATUS_REJECTED', 'Follow-up after limit rejected'],
];
const escalatedConcerns = new Set(['RECONCILIATION', 'LOAN_INCREASE_REQUEST', 'PAYMENT_METHOD']);

const customerCareRequest = async (path, options = {}) => {
  const send = () => fetch(apiUrl(path), {
    ...options,
    headers: {
      Authorization: `Bearer ${getAuthToken()}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  let response = await send();
  if (response.status === 401 && await refreshAuthToken()) response = await send();
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json().catch(() => null) : null;
  if (!payload) {
    throw new Error(`Customer Care returned an unexpected response (HTTP ${response.status}). Check that the backend is running and its migrations are current.`);
  }
  if (!response.ok) {
    throw new Error(payload.error?.message || payload.error || payload.message || 'Unable to complete the request.');
  }
  return payload;
};

const formatDateTime = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
};

const labelizeCustomer = (value) => value
  ? String(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
  : 'Not provided';

function PageHeading({ eyebrow = 'CUSTOMER CARE', title, detail, action }) {
  return (
    <header className="care-page-heading">
      <div>
        <p className="care-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {detail && <p className="care-page-description">{detail}</p>}
      </div>
      {action}
    </header>
  );
}

function CareNotice({ error, success }) {
  if (!error && !success) return null;
  return (
    <div className={`care-notice ${error ? 'is-error' : 'is-success'}`} role={error ? 'alert' : 'status'}>
      {error || success}
    </div>
  );
}

function Pagination({ page, pages, onChange }) {
  if (pages <= 1) return null;
  return (
    <div className="care-pagination" aria-label="Pagination">
      <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        <ArrowLeft size={15} aria-hidden="true" /> Previous
      </button>
      <span>Page {page} of {pages}</span>
      <button type="button" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Next <ArrowRight size={15} aria-hidden="true" />
      </button>
    </div>
  );
}

function CareTable({ children, headings }) {
  return (
    <div className="care-table-scroll">
      <table className="care-table">
        <thead><tr>{headings.map((heading) => <th key={heading}>{heading}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function SearchField({ value, onChange, placeholder = 'Search name or phone number' }) {
  return (
    <label className="care-search">
      <Search size={17} aria-hidden="true" />
      <span className="visually-hidden">Search customers</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </label>
  );
}

export function CallLogsPage({ currentUser }) {
  const isGeneralManager = isGeneralManagerUser(currentUser);
  const [logs, setLogs] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [actionError, setActionError] = useState('');
  const [confirmingResolutionId, setConfirmingResolutionId] = useState(null);
  const [resolvingId, setResolvingId] = useState(null);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ page: String(page), per_page: '25' });
      if (search.trim()) params.set('q', search.trim());
      if (status) params.set('status', status);
      if (category) params.set('category', category);
      setLoading(true);
      customerCareRequest(`/api/customer-care/logs?${params}`)
        .then((payload) => {
          if (!active) return;
          setLogs(payload.data || []);
          setPagination(payload.pagination || { page, pages: 1, total: 0 });
          setError('');
        })
        .catch((loadError) => active && setError(loadError.message))
        .finally(() => active && setLoading(false));
    }, search ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [page, search, status, category]);

  const changeFilter = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  const resolveEscalation = async (log) => {
    setResolvingId(log.id);
    setActionError('');
    setActionMessage('');
    try {
      await customerCareRequest(`/api/calls/${log.id}/resolve-escalation`, {
        method: 'PATCH',
        body: JSON.stringify({}),
      });
      setLogs((items) => items.map((item) => item.id === log.id
        ? { ...item, status: 'Resolved', escalation_resolved: true }
        : item));
      setConfirmingResolutionId(null);
      setActionMessage(`${log.reference_number || `Call #${log.id}`} was marked resolved.`);
    } catch (requestError) {
      setActionError(requestError.message);
    } finally {
      setResolvingId(null);
    }
  };

  const openEscalationCount = logs.filter(
    (log) => log.requires_escalation && !log.escalation_resolved,
  ).length;

  return (
    <section className="care-page">
      <PageHeading
        title="Call logs"
        detail={isGeneralManager
          ? 'Review customer cases, open escalation briefs, and record decisions.'
          : "Search and review your team's phone conversations, outcomes, and next steps."}
        action={!isGeneralManager && <Link className="care-primary-button" to="/dashboard/customer-care/new"><Phone size={16} /> Log a call</Link>}
      />
      {isGeneralManager && (
        <div className="care-gm-call-review">
          <div className="care-gm-call-review-icon"><Siren size={19} /></div>
          <div className="care-gm-call-review-copy">
            <strong>Executive case review</strong>
            <span>{openEscalationCount
              ? `${openEscalationCount} open escalation${openEscalationCount === 1 ? '' : 's'} in the results below ${openEscalationCount === 1 ? 'needs' : 'need'} a decision.`
              : 'No open escalations in the results below.'}</span>
          </div>
          <Link className="care-secondary-button" to="/okia/escalations">Open escalation queue <ArrowRight size={14} /></Link>
        </div>
      )}
      <CareNotice error={error || actionError} success={actionMessage} />
      <div className="care-card">
        <div className="care-filter-row">
          <SearchField value={search} onChange={changeFilter(setSearch)} placeholder="Search customer or phone number" />
          <label className="care-filter">
            <span>Status</span>
            <select value={status} onChange={(event) => changeFilter(setStatus)(event.target.value)}>
              <option value="">All statuses</option>
              {statuses.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="care-filter">
            <span>Category</span>
            <select value={category} onChange={(event) => changeFilter(setCategory)(event.target.value)}>
              <option value="">All categories</option>
              {categories.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <span className="care-result-count">{pagination.total} calls</span>
        </div>
        {loading ? <div className="care-state">Loading call logs…</div> : logs.length ? (
          <CareTable headings={[
            'Date / time', 'Customer', 'Phone number', 'Category', 'Call type', 'Priority', 'Status', 'Staff',
            ...(isGeneralManager ? ['GM actions'] : []),
          ]}>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{isGeneralManager
                  ? formatDateTime(log.created_at)
                  : <Link className="care-table-link" to={`/dashboard/customer-care/logs/${log.id}`}>{formatDateTime(log.created_at)}</Link>}
                </td>
                <td>{isGeneralManager
                  ? log.customer.name
                  : <Link className="care-table-link" to={`/dashboard/customer-care/customers/${log.customer.id}`}>{log.customer.name}</Link>}
                </td>
                <td>{log.customer.phone_number}</td>
                <td>{log.concern_category || log.outbound_reason || log.category}</td>
                <td>{log.call_type}</td>
                <td><span className={`care-badge priority-${log.priority.toLowerCase()}`}>{log.priority}</span></td>
                <td><span className={`care-badge status-${log.status.toLowerCase().replaceAll(' ', '-')}`}>{log.status}</span></td>
                <td>{log.staff_name}</td>
                {isGeneralManager && (
                  <td className="care-gm-log-actions">
                    <Link
                      className="care-secondary-button care-gm-action-button"
                      to={`/dashboard/customer-care/logs/${log.id}`}
                      aria-label={`View call ${log.reference_number || log.id}`}
                    >
                      <Eye size={14} /> View call
                    </Link>
                    <Link
                      className="care-secondary-button care-gm-action-button"
                      to={`/dashboard/customer-care/customers/${log.customer.id}`}
                      aria-label={`View customer profile for ${log.customer.name}`}
                    >
                      <UserRound size={14} /> Customer profile
                    </Link>
                    {log.requires_escalation && log.escalation_id && (
                      <Link
                        className="care-secondary-button care-gm-action-button"
                        to={`/okia/escalations/${log.escalation_id}`}
                        aria-label={`Review escalation ${log.reference_number || log.id}`}
                      >
                        <Siren size={14} /> Review escalation
                      </Link>
                    )}
                    {log.requires_escalation && !log.escalation_resolved && (
                      confirmingResolutionId === log.id ? (
                        <span className="care-gm-resolution-confirm" role="group" aria-label={`Confirm resolution for call ${log.id}`}>
                          <small>Confirm resolving this escalation?</small>
                          <button
                            className="care-primary-button care-gm-action-button"
                            type="button"
                            disabled={resolvingId === log.id}
                            onClick={() => resolveEscalation(log)}
                          >
                            <Check size={14} /> {resolvingId === log.id ? 'Saving…' : 'Confirm resolve'}
                          </button>
                          <button
                            className="care-secondary-button care-gm-action-button"
                            type="button"
                            disabled={resolvingId === log.id}
                            onClick={() => setConfirmingResolutionId(null)}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          className="care-secondary-button care-gm-action-button"
                          type="button"
                          onClick={() => {
                            setActionError('');
                            setActionMessage('');
                            setConfirmingResolutionId(log.id);
                          }}
                          aria-label={`Resolve escalation for ${log.reference_number || log.id}`}
                        >
                          <Check size={14} /> Resolve
                        </button>
                      )
                    )}
                  </td>
                )}
              </tr>
            ))}
          </CareTable>
        ) : <div className="care-state"><Phone size={24} /><strong>No call logs found</strong><span>Try changing the filters or log the first call.</span></div>}
        <Pagination page={pagination.page || page} pages={pagination.pages || 1} onChange={setPage} />
      </div>
    </section>
  );
}

function NewCallLogPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    customer_name: '',
    phone_number: '',
    email: '',
    company: '',
    caller_type: 'agent',
    location: '',
    agent_name: '',
    agent_number: '',
    store_number: '',
    call_type: 'Incoming',
    category: 'General Inquiry',
    concern_category: 'GENERAL_INQUIRY',
    outbound_reason: '',
    priority: 'Normal',
    summary: '',
    status: 'Pending Follow-up',
    follow_up_date: '',
    follow_up_notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupMessage, setLookupMessage] = useState('');
  const [error, setError] = useState('');
  const [shiftCode, setShiftCode] = useState('');
  const [selectedClientProfile, setSelectedClientProfile] = useState(null);
  const [clientProfileConfirmed, setClientProfileConfirmed] = useState(false);
  const [registrationComplete, setRegistrationComplete] = useState(false);
  const [clientAddedMessage, setClientAddedMessage] = useState('');
  const callSummaryRef = useRef(null);
  const requiresClientRegistration = (
    form.call_type === 'Incoming'
    && form.concern_category === 'CALLER_READY_TO_REGISTER'
  );

  const setField = (field) => (event) => {
    setClientProfileConfirmed(false);
    if (
      (field === 'concern_category' && event.target.value !== 'CALLER_READY_TO_REGISTER')
      || (field === 'call_type' && event.target.value !== 'Incoming')
    ) {
      setRegistrationComplete(false);
      setClientAddedMessage('');
    }
    setForm((value) => ({ ...value, [field]: event.target.value }));
  };
  const requiresAgentDetails = ['agent', 'sub_agent'].includes(form.caller_type);
  const selectedReason = form.call_type === 'Incoming' ? form.concern_category : form.outbound_reason;
  const shouldShowEscalation = form.priority === 'Urgent' || escalatedConcerns.has(selectedReason);

  useEffect(() => {
    let active = true;
    customerCareRequest('/api/shifts/current')
      .then((payload) => {
        if (active) setShiftCode(payload.data?.code || payload.data?.shift_code || '');
      })
      .catch(() => {
        if (active) setShiftCode('');
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!requiresClientRegistration || !registrationComplete || !callSummaryRef.current) return;
    callSummaryRef.current.focus({ preventScroll: true });
    callSummaryRef.current.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [registrationComplete, requiresClientRegistration]);

  const lookupCustomer = async () => {
    const phone = form.phone_number.trim();
    if (!phone) return;
    setLookingUp(true);
    setLookupMessage('');
    try {
      const params = new URLSearchParams({ q: phone, per_page: '5' });
      const payload = await customerCareRequest(`/api/customer-care/customers?${params}`);
      const customer = (payload.data || []).find((row) => row.phone_number === phone);
      if (customer) {
        setForm((value) => ({
          ...value,
          customer_name: customer.name,
          email: customer.email || value.email,
          company: customer.company || value.company,
          caller_type: customer.caller_type || value.caller_type,
          location: customer.location || value.location,
          agent_name: customer.agent_name || value.agent_name,
          agent_number: customer.agent_number || value.agent_number,
          store_number: customer.store_number || value.store_number,
        }));
        setLookupMessage('Existing customer profile found. This call will be added to their history.');
      } else {
        setLookupMessage('No profile found. A new customer record will be created with this call.');
      }
    } catch (lookupError) {
      setError(lookupError.message);
    } finally {
      setLookingUp(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (selectedClientProfile && !clientProfileConfirmed) {
      setError('Confirm the selected client profile before saving this call.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const payload = await customerCareRequest('/api/customer-care/logs', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          category: form.call_type === 'Incoming' ? form.concern_category : form.outbound_reason,
          concern_category: form.call_type === 'Incoming' ? form.concern_category : null,
          outbound_reason: form.call_type === 'Outgoing' ? form.outbound_reason : null,
          call_started_at: new Date().toISOString(),
        }),
      });
      navigate(`/dashboard/customer-care/logs/${payload.data.id}`);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const confirmClientProfile = (match) => {
    const normalizedCategory = String(match.category || '').toLowerCase();
    setForm((value) => ({
      ...value,
      customer_name: match.agent_name || value.customer_name,
      phone_number: match.phone_number || value.phone_number,
      company: match.agent_name || value.company,
      caller_type: normalizedCategory.includes('sub') ? 'sub_agent' : 'agent',
      location: match.business_location || value.location,
      agent_name: match.agent_name || value.agent_name,
      agent_number: match.agent_number || value.agent_number,
      store_number: match.store_number || value.store_number,
    }));
    setSelectedClientProfile(match);
    setClientProfileConfirmed(true);
    setError('');
  };

  return (
    <section className="care-page">
      <PageHeading
        title="Log a phone call"
        detail="Capture the customer's details and conversation while the call is fresh."
        action={<Link className="care-secondary-button" to="/dashboard/customer-care/logs"><ArrowLeft size={16} /> All call logs</Link>}
      />
      <CareNotice error={error} />
      <form className="care-card care-form" onSubmit={submit}>
        <div className="care-form-section">
          <div className="care-section-title"><span className="care-step">01</span><div><h2>Customer details</h2><p>Enter the caller's phone number to find an existing profile.</p></div></div>
          <ClientProfileLookup onConfirm={confirmClientProfile} />
          <div className="care-form-grid">
            <label className="care-field"><span>Caller type <b>*</b></span><select required value={form.caller_type} onChange={setField('caller_type')}>{callerTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label className="care-field">
              <span>Phone number <b>*</b></span>
              <div className="care-phone-control">
                <input required maxLength="40" value={form.phone_number} onChange={setField('phone_number')} placeholder="+254 700 000 000" autoComplete="tel" />
                <button type="button" onClick={lookupCustomer} disabled={!form.phone_number.trim() || lookingUp}>{lookingUp ? 'Looking…' : 'Look up'}</button>
              </div>
              {lookupMessage && <small className="care-help">{lookupMessage}</small>}
            </label>
            <label className="care-field"><span>Customer name <b>*</b></span><input required maxLength="160" value={form.customer_name} onChange={setField('customer_name')} placeholder="Full name" autoComplete="name" /></label>
            <label className="care-field"><span>Email address</span><input type="email" maxLength="255" value={form.email} onChange={setField('email')} placeholder="name@example.com" autoComplete="email" /></label>
            <label className="care-field"><span>Company</span><input maxLength="160" value={form.company} onChange={setField('company')} placeholder="Company or organization" /></label>
            {requiresAgentDetails && (
              <>
                <label className="care-field"><span>Location <b>*</b></span><input required maxLength="160" value={form.location} onChange={setField('location')} placeholder="Town, area, or market" /></label>
                <label className="care-field"><span>Agent name <b>*</b></span><input required maxLength="160" value={form.agent_name} onChange={setField('agent_name')} placeholder="Registered agent name" /></label>
                <label className="care-field"><span>Agent number <b>*</b></span><input required maxLength="40" value={form.agent_number} onChange={setField('agent_number')} placeholder="M-Pesa agent number" /></label>
                <label className="care-field"><span>Store number <b>*</b></span><input required maxLength="40" value={form.store_number} onChange={setField('store_number')} placeholder="M-Pesa store number" /></label>
              </>
            )}
          </div>
        </div>
        <div className="care-form-section">
          <div className="care-section-title"><span className="care-step">02</span><div><h2>Call details</h2><p>Record the reason for the call and the outcome.</p></div></div>
          <div className="care-form-grid care-form-grid-three">
            <label className="care-field"><span>Call type <b>*</b></span><select value={form.call_type} onChange={setField('call_type')}><option>Incoming</option><option>Outgoing</option></select></label>
            {form.call_type === 'Incoming' ? (
              <label className="care-field"><span>Concern category <b>*</b></span><select required value={form.concern_category} onChange={setField('concern_category')}>{inboundConcerns.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            ) : (
              <label className="care-field"><span>Outbound reason <b>*</b></span><select required value={form.outbound_reason} onChange={setField('outbound_reason')}><option value="">Choose a reason</option>{outboundReasons.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            )}
            <label className="care-field"><span>Priority <b>*</b></span><select value={form.priority} onChange={setField('priority')}>{priorities.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="care-field"><span>Status <b>*</b></span><select value={form.status} onChange={setField('status')}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label>
            <div className="care-call-context"><span className="care-shift-chip">Shift {shiftCode || '…'}</span><small>Shift is assigned by the server using the call start time in Africa/Nairobi.</small></div>
            {shouldShowEscalation && <div className="care-escalation-alert" role="status">⚠ This concern will be escalated to {form.concern_category === 'RECONCILIATION' ? 'IT Support and the General Manager' : 'the General Manager'}.</div>}
            {(!requiresClientRegistration || registrationComplete) && <>
            <label className="care-field care-field-wide"><span>Call summary <b>*</b></span><textarea ref={callSummaryRef} required maxLength="10000" rows="5" value={form.summary} onChange={setField('summary')} placeholder="What did the customer call about? What was discussed or agreed?" /><small className="care-help">Include enough detail so another team member can pick up the conversation.</small></label>
            </>}
          </div>
        </div>
        {(!requiresClientRegistration || registrationComplete) && <>
        <div className="care-form-section care-followup-form">
          <div className="care-section-title"><span className="care-step">03</span><div><h2>Follow-up <span className="care-optional">Optional</span></h2><p>Schedule a callback or action for yourself.</p></div></div>
          <div className="care-form-grid">
            <label className="care-field"><span>Follow-up date</span><input type="date" value={form.follow_up_date} onChange={setField('follow_up_date')} /></label>
            <label className="care-field"><span>Follow-up notes</span><input maxLength="5000" value={form.follow_up_notes} onChange={setField('follow_up_notes')} placeholder="What needs to happen next?" /></label>
          </div>
        </div>
        <div className="care-form-actions">
          <Link className="care-secondary-button" to="/dashboard/customer-care/logs">Cancel</Link>
          <button className="care-primary-button" type="submit" disabled={saving || lookingUp}>{saving ? 'Saving call…' : 'Save call log'}</button>
        </div>
        </>}
      </form>
      {requiresClientRegistration && !registrationComplete && (
        <div className="care-client-registration-workflow">
          <SalesDailyReportForm
            initialStatus="ready_to_register"
            draftStorageKey="okoa_customer_care_new_client_draft"
            submitButtonLabel="Submit"
            headingTitle="Register A Client"
            showHeadingEyebrow={false}
            showHeadingSubtitle={false}
            onSubmitted={() => {
              setRegistrationComplete(true);
              setClientAddedMessage('Client registration submitted. Complete and save the Customer Care call log below.');
            }}
          />
        </div>
      )}
      {requiresClientRegistration && registrationComplete && (
        <CareNotice success={clientAddedMessage} />
      )}
    </section>
  );
}

function CustomerDirectoryPage() {
  const [customers, setCustomers] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ page: String(page), per_page: '25' });
      if (search.trim()) params.set('q', search.trim());
      setLoading(true);
      customerCareRequest(`/api/customer-care/customers?${params}`)
        .then((payload) => {
          if (!active) return;
          setCustomers(payload.data || []);
          setPagination(payload.pagination || { page, pages: 1, total: 0 });
          setError('');
        })
        .catch((loadError) => active && setError(loadError.message))
        .finally(() => active && setLoading(false));
    }, search ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [page, search]);

  return (
    <section className="care-page">
      <PageHeading title="Customer directory" detail="Every customer profile, together with their complete phone support history." action={<Link className="care-primary-button" to="/dashboard/customer-care/new"><Phone size={16} /> Log a call</Link>} />
      <CareNotice error={error} />
      <div className="care-card">
        <div className="care-filter-row">
          <SearchField value={search} onChange={(value) => { setSearch(value); setPage(1); }} />
          <span className="care-result-count">{pagination.total} customers</span>
        </div>
        {loading ? <div className="care-state">Loading customer directory…</div> : customers.length ? (
          <CareTable headings={['Customer', 'Caller type', 'Phone number', 'Agent / store', 'Location', 'Interactions', 'Customer since', '']}>
            {customers.map((customer) => (
              <tr key={customer.id}>
                <td><Link className="care-customer-name" to={`/dashboard/customer-care/customers/${customer.id}`}><span className="care-avatar"><UserRound size={17} /></span>{customer.name}</Link></td>
                <td>{(customer.caller_type || '—').replaceAll('_', ' ')}</td>
                <td>{customer.phone_number}</td>
                <td>{[customer.agent_name, customer.agent_number, customer.store_number].filter(Boolean).join(' · ') || '—'}</td>
                <td>{customer.location || '—'}</td>
                <td><span className="care-count-pill">{customer.interaction_count}</span></td>
                <td>{formatDateTime(customer.created_at)}</td>
                <td><Link className="care-inline-link" to={`/dashboard/customer-care/customers/${customer.id}`}>View history <ArrowRight size={14} /></Link></td>
              </tr>
            ))}
          </CareTable>
        ) : <div className="care-state"><UserRound size={24} /><strong>No customers found</strong><span>Customer profiles are created automatically when you log a call.</span></div>}
        <Pagination page={pagination.page || page} pages={pagination.pages || 1} onChange={setPage} />
      </div>
    </section>
  );
}

export function CustomerProfilePage() {
  const { customerId } = useParams();
  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    customerCareRequest(`/api/customer-care/customers/${customerId}`)
      .then((payload) => active && setCustomer(payload.data))
      .catch((loadError) => active && setError(loadError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [customerId]);

  if (loading) return <section className="care-page"><div className="care-state">Loading customer profile…</div></section>;
  if (error || !customer) return <section className="care-page"><CareNotice error={error || 'Customer not found.'} /><Link className="care-secondary-button" to="/dashboard/customer-care/customers"><ArrowLeft size={16} /> Customer directory</Link></section>;

  return (
    <section className="care-page">
      <Link className="care-back-link" to="/dashboard/customer-care/customers"><ArrowLeft size={16} /> Customer directory</Link>
      <PageHeading title={customer.name} detail="Customer profile and complete phone support history." action={<Link className="care-primary-button" to="/dashboard/customer-care/new"><Phone size={16} /> Log a call</Link>} />
      <div className="care-profile-card care-card">
        <span className="care-profile-avatar"><UserRound size={27} /></span>
        <div><p className="care-eyebrow">CUSTOMER PROFILE</p><h2>{customer.name}</h2><p>{customer.phone_number}</p></div>
        <div className="care-profile-metadata"><span>Email</span><strong>{customer.email || 'Not provided'}</strong></div>
        <div className="care-profile-metadata"><span>Company</span><strong>{customer.company || 'Not provided'}</strong></div>
        <div className="care-profile-metadata"><span>Caller type</span><strong>{labelizeCustomer(customer.caller_type)}</strong></div>
        <div className="care-profile-metadata"><span>Location</span><strong>{customer.location || 'Not provided'}</strong></div>
        <div className="care-profile-metadata"><span>Agent / store</span><strong>{[customer.agent_name, customer.agent_number, customer.store_number].filter(Boolean).join(' · ') || 'Not provided'}</strong></div>
        <div className="care-profile-metadata"><span>Calls logged</span><strong>{customer.interaction_count}</strong></div>
      </div>
      {customer.call_logs?.length > 0 && (
        <div className="care-card care-okia-detail">
          <h2>Concerns history</h2>
          <CareTable headings={['Concern', 'Calls', 'Most recent']}>
            {Object.entries(customer.call_logs.reduce((counts, log) => {
              const code = log.concern_category || log.outbound_reason || log.category || 'Uncategorized';
              if (!counts[code]) counts[code] = { count: 0, latest: log.created_at };
              counts[code].count += 1;
              if (new Date(log.created_at) > new Date(counts[code].latest)) counts[code].latest = log.created_at;
              return counts;
            }, {})).map(([concern, summary]) => <tr key={concern}><td>{concern.replaceAll('_', ' ')}</td><td>{summary.count}</td><td>{formatDateTime(summary.latest)}</td></tr>)}
          </CareTable>
        </div>
      )}
      {customer.call_logs?.some((log) => log.requires_escalation && !log.escalation_resolved) && (
        <div className="care-card care-okia-detail">
          <h2>Open escalations</h2>
          {customer.call_logs.filter((log) => log.requires_escalation && !log.escalation_resolved).map((log) => (
            <p key={log.id}><Link className="care-table-link" to={`/okia/escalations/${log.escalation_id || log.id}`}>{log.reference_number || `Call #${log.id}`}</Link> · {log.escalation_reason || 'Requires attention'} · {log.escalated_to || 'General Manager'}</p>
          ))}
        </div>
      )}
      <div className="care-section-heading"><div><p className="care-eyebrow">CUSTOMER HISTORY</p><h2>Phone interactions</h2></div></div>
      {customer.call_logs?.length ? (
        <div className="care-history-list">
          {customer.call_logs.map((log) => (
            <article className="care-history-card care-card" key={log.id}>
              <div className="care-history-icon"><Phone size={18} /></div>
              <div className="care-history-content">
                <div className="care-history-title"><div><Link className="care-table-link" to={`/dashboard/customer-care/logs/${log.id}`}>{log.concern_category || log.outbound_reason || log.category}</Link><span className="care-history-date">{formatDateTime(log.created_at)}</span></div><span className={`care-badge status-${log.status.toLowerCase().replaceAll(' ', '-')}`}>{log.status}</span></div>
                <p className="care-history-summary">{log.summary}</p>
                <div className="care-history-meta"><span>{log.call_type} call</span><span>{log.priority} priority</span><span>Handled by {log.staff_name}</span>{log.shift_code && <span>Shift {log.shift_code}</span>}{log.reference_number && <span>{log.reference_number}</span>}</div>
                {log.follow_ups?.length > 0 && <div className="care-followup-note"><Clock3 size={15} /> {log.follow_ups.map((item) => `${item.is_completed ? 'Completed' : 'Due'} ${item.due_date}`).join(' · ')}</div>}
              </div>
            </article>
          ))}
        </div>
      ) : <div className="care-card care-state">No calls have been logged for this customer yet.</div>}
    </section>
  );
}

function FollowUpsPage() {
  const [followUps, setFollowUps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [completingId, setCompletingId] = useState(null);

  const loadFollowUps = () => {
    setLoading(true);
    customerCareRequest('/api/customer-care/follow-ups')
      .then((payload) => {
        setFollowUps(payload.data || []);
        setError('');
      })
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadFollowUps(); }, []);

  const complete = async (id) => {
    setCompletingId(id);
    setError('');
    try {
      await customerCareRequest(`/api/customer-care/follow-ups/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_completed: true }),
      });
      setFollowUps((items) => items.filter((item) => item.id !== id));
    } catch (completeError) {
      setError(completeError.message);
    } finally {
      setCompletingId(null);
    }
  };

  return (
    <section className="care-page">
      <PageHeading title="Pending follow-ups" detail="Callbacks and customer actions assigned to you, ordered by due date." action={<Link className="care-secondary-button" to="/dashboard/customer-care/logs"><ArrowLeft size={16} /> Call logs</Link>} />
      <CareNotice error={error} />
      {loading ? <div className="care-card care-state">Loading your follow-ups…</div> : followUps.length ? (
        <div className="care-task-list">
          {followUps.map((item) => {
            const now = new Date();
            const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
            const overdue = item.due_date < today;
            return (
              <article className={`care-task-card care-card ${overdue ? 'is-overdue' : ''}`} key={item.id}>
                <div className={`care-task-date ${overdue ? 'is-overdue' : ''}`}><span>{new Date(`${item.due_date}T00:00:00`).toLocaleDateString(undefined, { month: 'short' })}</span><strong>{new Date(`${item.due_date}T00:00:00`).getDate()}</strong></div>
                <div className="care-task-main">
                  <div className="care-task-title-row"><div><h2>{item.call_log.customer.name}</h2><span className={`care-badge ${overdue ? 'status-escalated' : 'status-pending-follow-up'}`}>{overdue ? 'Overdue' : 'Due'} {formatDateTime(`${item.due_date}T00:00:00`)}</span></div><a href={`tel:${item.call_log.customer.phone_number}`} className="care-secondary-button care-call-button"><Phone size={15} /> {item.call_log.customer.phone_number}</a></div>
                  <p>{item.notes || item.call_log.summary}</p>
                  <div className="care-task-meta"><span>{item.call_log.category}</span><span>Call #{item.call_log.id}</span><Link to={`/dashboard/customer-care/customers/${item.call_log.customer.id}`}>Customer history <ArrowRight size={13} /></Link></div>
                </div>
                <button type="button" className="care-complete-button" disabled={completingId === item.id} onClick={() => complete(item.id)}><Check size={16} /> {completingId === item.id ? 'Saving…' : 'Complete'}</button>
              </article>
            );
          })}
        </div>
      ) : <div className="care-card care-state"><Check size={25} /><strong>You're all caught up</strong><span>No pending follow-up tasks are assigned to you.</span></div>}
    </section>
  );
}

export function CustomerCareSettingsPage() {
  const [roles, setRoles] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingRole, setSavingRole] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    let active = true;
    customerCareRequest('/api/admin/dashboard-features')
      .then((payload) => {
        if (active) setRoles(payload.data?.roles || {});
      })
      .catch((loadError) => active && setError(loadError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const toggleRole = async (roleName, enabled) => {
    setSavingRole(roleName);
    setError('');
    setSuccess('');
    try {
      await customerCareRequest('/api/admin/dashboard-features', {
        method: 'PATCH',
        body: JSON.stringify({ role: roleName, feature: 'customer_care', enabled }),
      });
      setRoles((current) => ({
        ...current,
        [roleName]: { ...current[roleName], customer_care: enabled },
      }));
      setSuccess(`Customer Care ${enabled ? 'enabled' : 'disabled'} for ${roleName.replace('_', ' ').toLowerCase()} users.`);
      window.dispatchEvent(new Event('dashboard-feature-access-denied'));
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSavingRole('');
    }
  };

  return (
    <section className="care-page">
      <PageHeading
        eyebrow="ADMINISTRATION"
        title="Customer Care settings"
        detail="Control which staff roles can access customer call logs, customer histories, and follow-up tasks."
      />
      <CareNotice error={error} success={success} />
      <div className="care-card care-settings-card">
        <div className="care-settings-heading"><div><h2>Role access</h2><p>Changes take effect on the next navigation or API request.</p></div><span className="care-settings-pill">ROLE BASED</span></div>
        {loading ? <div className="care-state">Loading Customer Care settings…</div> : (
          <div className="care-settings-list">
            {Object.entries(roles).map(([roleName, features]) => {
              const enabled = features.customer_care !== false;
              return (
                <div className="care-settings-row" key={roleName}>
                  <div><strong>{roleName.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())}</strong><span>{roleName === 'SUPER_ADMIN' ? 'Full system access' : 'Staff access to Customer Care'}</span></div>
                  <label className="care-toggle">
                    <input
                      type="checkbox"
                      checked={enabled}
                      disabled={savingRole === roleName}
                      onChange={(event) => toggleRole(roleName, event.target.checked)}
                      aria-label={`Customer Care access for ${roleName}`}
                    />
                    <span>{savingRole === roleName ? 'Saving…' : enabled ? 'Enabled' : 'Disabled'}</span>
                  </label>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div className="care-settings-note"><strong>What this controls</strong><span>When disabled, the role no longer sees Customer Care navigation and its authenticated API requests are denied. Existing call logs and customer records are retained.</span></div>
    </section>
  );
}

export function CallLogDetailPage() {
  const { logId } = useParams();
  const [log, setLog] = useState(null);
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [escalationDepartment, setEscalationDepartment] = useState('general_manager');
  const [escalationReason, setEscalationReason] = useState('');
  const [escalationSaving, setEscalationSaving] = useState(false);

  useEffect(() => {
    let active = true;
    customerCareRequest(`/api/customer-care/logs/${logId}`)
      .then((payload) => {
        if (!active) return;
        setLog(payload.data);
        setForm({ summary: payload.data.summary, category: payload.data.category, status: payload.data.status });
      })
      .catch((loadError) => active && setError(loadError.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [logId]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const payload = await customerCareRequest(`/api/customer-care/logs/${logId}`, {
        method: 'PATCH',
        body: JSON.stringify(form),
      });
      setLog(payload.data);
      setForm({ summary: payload.data.summary, category: payload.data.category, status: payload.data.status });
      setSuccess('Call log updated.');
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const updateEscalation = async (action, payload = {}) => {
    setEscalationSaving(true);
    setError('');
    setSuccess('');
    try {
      const result = await customerCareRequest(`/api/calls/${logId}/${action}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      if (result.data) setLog((current) => ({ ...current, ...result.data }));
      setSuccess(action === 'escalate' ? 'Call escalated successfully.' : 'Escalation resolved.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setEscalationSaving(false);
    }
  };

  if (loading) return <section className="care-page"><div className="care-state">Loading call details…</div></section>;
  if (!log || !form) return <section className="care-page"><CareNotice error={error || 'Call log not found.'} /><Link className="care-secondary-button" to="/dashboard/customer-care/logs"><ArrowLeft size={16} /> All call logs</Link></section>;

  return (
    <section className="care-page">
      <Link className="care-back-link" to="/dashboard/customer-care/logs"><ArrowLeft size={16} /> All call logs</Link>
      <PageHeading title="Call details" detail={`${log.reference_number || `Call #${log.id}`} · ${formatDateTime(log.call_started_at || log.created_at)}`} action={<Link className="care-secondary-button" to={`/dashboard/customer-care/customers/${log.customer.id}`}>Customer profile <ArrowRight size={15} /></Link>} />
      <CareNotice error={error} success={success} />
      <div className="care-detail-layout">
        <form className="care-card care-form care-detail-form" onSubmit={save}>
          <div className="care-section-title"><span className="care-step"><Phone size={17} /></span><div><h2>Conversation</h2><p>Handled by {log.staff_name} · {log.call_type} call · {log.priority} priority</p></div></div>
          <label className="care-field"><span>Category</span><select value={form.category} onChange={(event) => setForm((value) => ({ ...value, category: event.target.value }))}>{[...new Set([...categories, form.category])].map((item) => <option key={item}>{item}</option>)}</select></label>
          <label className="care-field"><span>Status</span><select value={form.status} onChange={(event) => setForm((value) => ({ ...value, status: event.target.value }))}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label className="care-field"><span>Call summary</span><textarea rows="8" maxLength="10000" value={form.summary} onChange={(event) => setForm((value) => ({ ...value, summary: event.target.value }))} required /></label>
          <div className="care-form-actions"><button className="care-primary-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button></div>
        </form>
        <aside className="care-card care-detail-customer">
          <p className="care-eyebrow">CUSTOMER</p>
          <h2>{log.customer.name}</h2>
          <a className="care-phone-link" href={`tel:${log.customer.phone_number}`}><Phone size={15} />{log.customer.phone_number}</a>
          <p>{log.customer.email || 'No email on file'}</p>
          <div className="care-call-attributes">
            <span><small>Concern</small><strong>{log.concern_category || log.outbound_reason || log.category}</strong></span>
            <span><small>Shift</small><strong>{log.shift_code ? `Shift ${log.shift_code}` : 'Not assigned'}</strong></span>
            <span><small>Caller</small><strong>{labelizeCustomer(log.customer.caller_type)}</strong></span>
          </div>
          {log.requires_escalation && (
            <div className="care-escalation-panel">
              <div className="care-escalation-panel-heading"><strong>Escalation</strong><span className={`care-badge ${log.escalation_resolved ? 'status-resolved' : 'status-escalated'}`}>{log.escalation_resolved ? 'Resolved' : 'Needs attention'}</span></div>
              <p>{log.escalation_reason || 'Escalation required'} · {labelizeCustomer(log.escalated_to || 'general_manager')}</p>
              {log.escalation_resolved ? <small>Resolved {formatDateTime(log.escalated_at)}</small> : <button className="care-secondary-button" type="button" disabled={escalationSaving} onClick={() => updateEscalation('resolve-escalation')}>{escalationSaving ? 'Saving…' : 'Resolve escalation'}</button>}
            </div>
          )}
          {!log.requires_escalation && (
            <form className="care-escalation-form" onSubmit={(event) => { event.preventDefault(); updateEscalation('escalate', { to_dept: escalationDepartment, reason: escalationReason }); }}>
              <h3>Escalate this call</h3>
              <label className="care-field"><span>Route to</span><select value={escalationDepartment} onChange={(event) => setEscalationDepartment(event.target.value)}><option value="general_manager">General Manager</option><option value="it_support">IT Support</option><option value="supervisor">Supervisor</option></select></label>
              <label className="care-field"><span>Reason</span><textarea required maxLength="2000" rows="3" value={escalationReason} onChange={(event) => setEscalationReason(event.target.value)} /></label>
              <button className="care-secondary-button" type="submit" disabled={escalationSaving || !escalationReason.trim()}>{escalationSaving ? 'Escalating…' : 'Escalate call'}</button>
            </form>
          )}
          <Link className="care-inline-link" to={`/dashboard/customer-care/customers/${log.customer.id}`}>View customer history <ArrowRight size={14} /></Link>
          {log.follow_ups?.length > 0 && <div className="care-detail-followups"><h3>Follow-ups</h3>{log.follow_ups.map((item) => <p key={item.id}><span className={`care-badge ${item.is_completed ? 'status-resolved' : 'status-pending-follow-up'}`}>{item.is_completed ? 'Completed' : 'Pending'}</span> Due {item.due_date}{item.notes ? ` · ${item.notes}` : ''}</p>)}</div>}
        </aside>
      </div>
    </section>
  );
}

export function CustomerCarePage({ page, currentUser }) {
  if (page === 'customer-care-logs') return <CallLogsPage currentUser={currentUser} />;
  if (page === 'customer-care-new') return <NewCallLogPage />;
  if (page === 'customer-care-customers') return <CustomerDirectoryPage />;
  if (page === 'customer-care-follow-ups') return <FollowUpsPage />;
  return null;
}
