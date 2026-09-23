import React, { useEffect, useMemo, useState } from 'react';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';

const API_ORIGIN = process.env.REACT_APP_API_URL || '';

const emptyContact = () => ({ name: '', idNumber: '', phoneNumber: '' });
const emptyExisting = () => ({ category: '', client: emptyContact(), mpesaAdmin: emptyContact(), agentName: '', agentNumber: '', storeNumber: '', businessLocation: '', remarks: '', referralAgreed: '', referralContactNumber: '', referralDetails: '' });
const emptyNew = () => ({ status: '', client: emptyContact(), mpesaAdmin: emptyContact(), agentName: '', agentNumber: '', storeNumber: '', businessLocation: '', remarks: '', appointmentDate: '', appointmentTime: '', category: '', documents: {}, registrationDate: '', witness: emptyContact() });
const documentLists = {
  mpesa_sub_agent: [['business_permit', 'Business permit'], ['individual_kra_pin', 'Individual KRA PIN'], ['six_months_commission', 'Six months Commission Statement'], ['subagent_agent_contract', 'Contract Between Sub-Agent & Agent'], ['owner_national_id', 'National ID of the owner'], ['sign_contract', 'Sign Contract']],
  mpesa_agent_dealer: [['certificate_of_incorporation', 'Certificate of incorporation / Registration'], ['company_kra_pin', 'Company KRA PIN Certificate (or individual KRA PIN of the Business owners for sole proprietors / partnerships)'], ['six_months_commission', 'Six months Commission Statement'], ['owners_directors_national_ids', 'National IDs of the owners / Directors'], ['cr12_directors', 'CR12 for directors']],
};
const apiCategory = (category) => category === 'mpesa_sub_agent' ? 'sub_agent' : 'agent';
const draftKey = 'okoa_sales_daily_report_draft';
const loadDraft = () => {
  try {
    const saved = window.sessionStorage.getItem(draftKey);
    return saved ? JSON.parse(saved) : null;
  } catch (error) {
    return null;
  }
};

export default function SalesDailyReportForm({ onSubmitted }) {
  const savedDraft = loadDraft();
  const [clientType, setClientType] = useState(() => savedDraft?.clientType || '');
  const [existing, setExisting] = useState(() => ({ ...emptyExisting(), ...(savedDraft?.existing || {}), client: { ...emptyContact(), ...(savedDraft?.existing?.client || {}) }, mpesaAdmin: { ...emptyContact(), ...(savedDraft?.existing?.mpesaAdmin || {}) } }));
  const [newClient, setNewClient] = useState(() => ({ ...emptyNew(), ...(savedDraft?.newClient || {}), client: { ...emptyContact(), ...(savedDraft?.newClient?.client || {}) }, mpesaAdmin: { ...emptyContact(), ...(savedDraft?.newClient?.mpesaAdmin || {}) }, witness: { ...emptyContact(), ...(savedDraft?.newClient?.witness || {}) } }));
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [savedNotice, setSavedNotice] = useState(false);
  const [clientAdded, setClientAdded] = useState(false);
  const visibleDocuments = useMemo(() => documentLists[newClient.category] || [], [newClient.category]);
  const registrationStatus = useMemo(() => visibleDocuments.length > 0 && visibleDocuments.every(([key]) => newClient.documents[key] === true) ? 'COMPLETE' : 'INCOMPLETE', [newClient.documents, visibleDocuments]);

  useEffect(() => {
    window.sessionStorage.setItem(draftKey, JSON.stringify({ clientType, existing, newClient }));
  }, [clientType, existing, newClient]);

  const chooseClientType = (value) => { setClientType(value); if (value === 'existing') setNewClient(emptyNew()); if (value === 'new') setExisting(emptyExisting()); setFeedback(null); };
  const chooseStatus = (status) => { setNewClient({ ...emptyNew(), status }); setFeedback(null); };
  const chooseCategory = (category) => setNewClient((current) => ({ ...current, category, documents: {} }));
  const updateExisting = (field, value) => setExisting((current) => ({ ...current, [field]: value }));
  const updateNew = (field, value) => setNewClient((current) => ({ ...current, [field]: value }));
  const updateWitness = (field, value) => setNewClient((current) => ({ ...current, witness: { ...current.witness, [field]: value } }));
  const updateContact = (branch, setBranch, contact, field, value) => setBranch((current) => ({ ...current, [contact]: { ...current[contact], [field]: value } }));
  const setReferralAgreed = (value) => setExisting((current) => ({ ...current, referralAgreed: value, ...(value === 'no' ? { referralContactNumber: '', referralDetails: '' } : {}) }));
  const toggleDocument = (key) => setNewClient((current) => ({ ...current, documents: { ...current.documents, [key]: !current.documents[key] } }));

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setFeedback(null);
    const record = clientType === 'existing'
      ? { clientType, existing: { ...existing, ...(existing.referralAgreed === 'yes' ? { referralDetails: { contactNumber: existing.referralContactNumber, notes: existing.referralDetails } } : {}) } }
      : { clientType, new: { ...newClient, ...(newClient.status === 'ready_to_register' ? { registrationStatus } : {}) } };
    try {
      const branch = clientType === 'existing' ? record.existing : record.new;
      const body = new FormData();
      body.append('agent_name', branch.agentName); body.append('agent_number', branch.agentNumber); body.append('store_number', branch.storeNumber);
      body.append('business_owner_name', branch.client.name || ''); body.append('id_number', branch.client.idNumber || ''); body.append('contact_phone', branch.client.phoneNumber || '');
      body.append('admin_name', branch.mpesaAdmin.name || ''); body.append('mpesa_admin_id_number', branch.mpesaAdmin.idNumber || ''); body.append('mpesa_admin_phone', branch.mpesaAdmin.phoneNumber || '');
      body.append('business_location', branch.businessLocation || ''); body.append('date_visited', new Date().toISOString().slice(0, 10));
      body.append('customer_type', apiCategory(branch.category || 'mpesa_agent')); body.append('outcome', clientType === 'existing' ? 'existing' : branch.status);
      body.append('new_client', String(clientType === 'new')); body.append('notes', branch.remarks || ''); body.append('referral_agreed', branch.referralAgreed || '');
      body.append('referral_details', branch.referralDetails?.notes || branch.referralDetails || ''); body.append('appointment_date', branch.appointmentDate || ''); body.append('appointment_time', branch.appointmentTime || '');
      body.append('registration_date', branch.registrationDate || ''); body.append('registration_status', branch.registrationStatus || '');
      if (clientType === 'new' && branch.status === 'ready_to_register') {
        Object.entries(branch.documents).forEach(([key, value]) => body.append(key, String(value)));
        body.append('witness_name', branch.witness.name); body.append('witness_id_number', branch.witness.idNumber); body.append('witness_phone', branch.witness.phoneNumber);
      }
      let response = await fetch(`${API_ORIGIN}/api/sales/reports`, { method: 'POST', headers: { Authorization: `Bearer ${getAuthToken()}` }, body });
      if (response.status === 401 && await refreshAuthToken()) {
        response = await fetch(`${API_ORIGIN}/api/sales/reports`, { method: 'POST', headers: { Authorization: `Bearer ${getAuthToken()}` }, body });
      }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Please sign in again and retry.' : payload.error?.message || payload.msg || payload.message || 'Unable to add client.');
      window.sessionStorage.removeItem(draftKey);
      setClientType(''); setExisting(emptyExisting()); setNewClient(emptyNew()); setFeedback({ type: 'success', text: 'Customer Record added successfully.' }); setSavedNotice(true); window.setTimeout(() => setSavedNotice(false), 1500); onSubmitted?.({ ...payload.data, client_record: record });
      setClientAdded(true);
    } catch (error) { setFeedback({ type: 'error', text: error.message }); } finally { setSubmitting(false); }
  };

  const identityFields = (branch, updateBranch) => <><label>Agent Name<input value={branch.agentName} onChange={(event) => updateBranch('agentName', event.target.value)} required /></label><label>Agent Number<input value={branch.agentNumber} onChange={(event) => updateBranch('agentNumber', event.target.value)} required /></label><label>Store Number<input value={branch.storeNumber} onChange={(event) => updateBranch('storeNumber', event.target.value)} required /></label></>;
  const contactFields = (branch, updateBranch) => <><fieldset className="sales-contact-fieldset sales-full-field"><legend>Owner details</legend><label>Owner&apos;s Name<input value={branch.client.name} onChange={(event) => updateContact(branch, updateBranch, 'client', 'name', event.target.value)} required /></label><label>ID Number<input value={branch.client.idNumber} onChange={(event) => updateContact(branch, updateBranch, 'client', 'idNumber', event.target.value)} required /></label><label>Phone Number<input value={branch.client.phoneNumber} onChange={(event) => updateContact(branch, updateBranch, 'client', 'phoneNumber', event.target.value)} required /></label></fieldset><fieldset className="sales-contact-fieldset sales-full-field"><legend>M-Pesa Admin details (optional)</legend><label>Name<input value={branch.mpesaAdmin.name} onChange={(event) => updateContact(branch, updateBranch, 'mpesaAdmin', 'name', event.target.value)} /></label><label>ID Number<input value={branch.mpesaAdmin.idNumber} onChange={(event) => updateContact(branch, updateBranch, 'mpesaAdmin', 'idNumber', event.target.value)} /></label><label>Phone Number<input value={branch.mpesaAdmin.phoneNumber} onChange={(event) => updateContact(branch, updateBranch, 'mpesaAdmin', 'phoneNumber', event.target.value)} /></label></fieldset></>;

  return <section className="leave-section sales-report-section" id="sales-daily-report">
    <div className="leave-section-heading"><div><p className="leave-kicker">SALES REPORT</p><h2>Daily client report</h2><p className="leave-muted">Add one client record at a time.</p></div></div>
    {savedNotice && <div className="save-success-modal" role="status" aria-live="polite"><span aria-hidden="true">✓</span><strong>Customer Record added successfully</strong></div>}
    {feedback && <div className={`leave-alert ${feedback.type}`} role="status">{feedback.text}</div>}
    <form className="sales-report-form" onSubmit={submit}>
      <label>Are you recording a New or Existing client?<select value={clientType} onChange={(event) => chooseClientType(event.target.value)} required><option value="">Select client type</option><option value="existing">Existing Client</option><option value="new">New Client</option></select></label>
      {clientType === 'existing' && <div className="sales-conditional-grid">
        <label>Category<select value={existing.category} onChange={(event) => updateExisting('category', event.target.value)} required><option value="">Select category</option><option value="mpesa_agent">M-Pesa Agent / Dealer</option><option value="mpesa_sub_agent">M-Pesa Sub-Agent</option></select></label>
        {identityFields(existing, updateExisting)}
        <label>Business Location<input value={existing.businessLocation} onChange={(event) => updateExisting('businessLocation', event.target.value)} required /></label>
        {contactFields(existing, setExisting)}
        <label className="sales-full-field">Other Remarks<textarea value={existing.remarks} onChange={(event) => updateExisting('remarks', event.target.value)} rows="4" /></label>
        <fieldset className="sales-choice-fieldset sales-full-field"><legend>Did they agree to give a referral?</legend><div className="sales-choice-buttons"><button type="button" className={existing.referralAgreed === 'yes' ? 'selected' : ''} onClick={() => setReferralAgreed('yes')}>YES</button><button type="button" className={existing.referralAgreed === 'no' ? 'selected' : ''} onClick={() => setReferralAgreed('no')}>NO</button></div></fieldset>
        {existing.referralAgreed === 'yes' && <><label>Referral Contact Number<input value={existing.referralContactNumber} onChange={(event) => updateExisting('referralContactNumber', event.target.value)} required /></label><label>Referral Details (optional)<textarea value={existing.referralDetails} onChange={(event) => updateExisting('referralDetails', event.target.value)} rows="3" /></label></>}
      </div>}
      {clientType === 'new' && <><label>Status<select value={newClient.status} onChange={(event) => chooseStatus(event.target.value)} required><option value="">Select status</option><option value="interested">Interested</option><option value="not_interested">Not Interested</option><option value="appointment">Appointment</option><option value="ready_to_register">Ready to Register</option></select></label>
        {newClient.status && <div className="sales-conditional-grid">
          <label>Category<select value={newClient.category} onChange={(event) => chooseCategory(event.target.value)} required><option value="">Select category</option><option value="mpesa_sub_agent">M-Pesa Sub-Agent</option><option value="mpesa_agent_dealer">M-Pesa Agent / M-Pesa Dealer</option></select></label>
          {identityFields(newClient, updateNew)}
          {newClient.status !== 'ready_to_register' && <label>Business Location<input value={newClient.businessLocation} onChange={(event) => updateNew('businessLocation', event.target.value)} required /></label>}
          {newClient.status === 'appointment' && <><label>Appointment Date<input type="date" value={newClient.appointmentDate} onChange={(event) => updateNew('appointmentDate', event.target.value)} required /></label><label>Appointment Time<input type="time" value={newClient.appointmentTime} onChange={(event) => updateNew('appointmentTime', event.target.value)} required /></label></>}
          {contactFields(newClient, setNewClient)}
          {newClient.status !== 'ready_to_register' && <label className="sales-full-field">Other Remarks<textarea value={newClient.remarks} onChange={(event) => updateNew('remarks', event.target.value)} rows="4" /></label>}
          {newClient.status === 'ready_to_register' && newClient.category && <>
            <fieldset className="sales-documents sales-full-field"><legend>Documents submitted</legend><div className="sales-toggle-grid">{visibleDocuments.map(([key, label]) => <button type="button" key={key} className={newClient.documents[key] ? 'active' : ''} aria-pressed={Boolean(newClient.documents[key])} onClick={() => toggleDocument(key)}>{label}</button>)}</div></fieldset>
            <label>Business Location<input value={newClient.businessLocation} onChange={(event) => updateNew('businessLocation', event.target.value)} required /></label>
            <label>Registration Date<input type="date" value={newClient.registrationDate} onChange={(event) => updateNew('registrationDate', event.target.value)} required /></label>
            <fieldset className="sales-witness sales-full-field"><legend>The contract was signed in the presence of:</legend><label>Name<input value={newClient.witness.name} onChange={(event) => updateWitness('name', event.target.value)} required /></label><label>ID Number<input value={newClient.witness.idNumber} onChange={(event) => updateWitness('idNumber', event.target.value)} required /></label><label>Phone Number<input value={newClient.witness.phoneNumber} onChange={(event) => updateWitness('phoneNumber', event.target.value)} required /></label></fieldset>
            <label className="sales-full-field">Other Remarks<textarea value={newClient.remarks} onChange={(event) => updateNew('remarks', event.target.value)} rows="4" /></label>
            <div className={`registration-status ${registrationStatus.toLowerCase()}`}><strong>{registrationStatus}</strong><span>Derived from the document toggles</span></div>
          </>}
        </div>}
      </>}
      {clientType && ((clientType === 'existing' && existing.referralAgreed) || (clientType === 'new' && newClient.status)) && <div className="form-actions"><button type="submit" className="sales-submit-button" disabled={submitting}>{submitting ? 'Adding customer...' : 'Add customer'}</button></div>}
      {clientAdded && !clientType && <div className="form-actions"><button type="button" className="leave-primary-button" onClick={() => { setClientAdded(false); setFeedback({ type: 'success', text: 'Client entry saved. You can add another client.' }); }}>Save</button></div>}
    </form>
  </section>;
}
