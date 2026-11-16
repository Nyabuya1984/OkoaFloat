import React, { useEffect, useMemo, useState } from 'react';
import { getAuthToken, refreshAuthToken } from '../services/authStorage';
import ActiveFieldVisitLocation from './ActiveFieldVisitLocation';
import './SalesDailyReportForm.css';

const API_ORIGIN = process.env.REACT_APP_API_URL || '';

const emptyContact = () => ({ name: '', idNumber: '', phoneNumber: '' });
const emptyExisting = () => ({ category: '', agentName: '', agentNumber: '', storeNumber: '', businessLocation: '', ownerName: '', ownerIdNumber: '', ownerPhoneNumber: '', remarks: '', referralAgreed: '', referralName: '', referralContactNumber: '', referralDetails: '' });
const emptyNew = () => ({ status: '', agentName: '', agentNumber: '', storeNumber: '', businessLocation: '', remarks: '', appointmentDate: '', appointmentTime: '', registrationDate: '', category: '', documents: {}, witness: emptyContact() });
const documentLists = {
  mpesa_sub_agent: [['business_permit', 'Business permit'], ['individual_kra_pin', 'Individual KRA PIN'], ['six_months_commission', 'Six months Commission Statement'], ['subagent_agent_contract', 'Contract Between Sub-Agent & Agent'], ['owner_national_id', 'National ID of the owner'], ['sign_contract', 'Sign Contract']],
  mpesa_agent_dealer: [['certificate_of_incorporation', 'Certificate of incorporation / Registration'], ['company_kra_pin', 'Company KRA PIN Certificate (or individual KRA PIN of the Business owners for sole proprietors / partnerships)'], ['six_months_commission', 'Six months Commission Statement'], ['owners_directors_national_ids', 'National IDs of the owners / Directors'], ['cr12_directors', 'CR12 for directors']],
};
const apiCategory = (category) => category === 'mpesa_sub_agent' ? 'sub_agent' : 'agent';
const categoryLabel = (category) => category === 'mpesa_sub_agent' ? 'M-Pesa Sub-Agent' : ['mpesa_agent', 'mpesa_agent_dealer'].includes(category) ? 'M-Pesa Agent / Dealer' : 'Not recorded';
const documentsForCategory = (category) => documentLists[category === 'mpesa_agent' ? 'mpesa_agent_dealer' : category] || [];
const draftKey = 'okoa_sales_daily_report_draft';
const loadDraft = (key = draftKey) => {
  try {
    const saved = window.sessionStorage.getItem(key);
    return saved ? JSON.parse(saved) : null;
  } catch (error) {
    return null;
  }
};

export default function SalesDailyReportForm({
  onSubmitted,
  initialStatus,
  draftStorageKey = draftKey,
  submitButtonLabel = 'Add Client',
  headingTitle = 'Daily client report',
  showHeadingEyebrow = true,
  showHeadingSubtitle = true,
  isFieldAgent = false,
}) {
  const savedDraft = initialStatus ? null : loadDraft(draftStorageKey);
  const [clientType, setClientType] = useState(() => (initialStatus ? 'new' : savedDraft?.clientType || ''));
  const [existing, setExisting] = useState(() => ({ ...emptyExisting(), ...(savedDraft?.existing || {}) }));
  const [newClient, setNewClient] = useState(() => ({ ...emptyNew(), status: initialStatus || savedDraft?.newClient?.status || '', ...(savedDraft?.newClient || {}), witness: { ...emptyContact(), ...(savedDraft?.newClient?.witness || {}) } }));
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [step, setStep] = useState('form');
  const [savedReport, setSavedReport] = useState(null);
  const [lookupField, setLookupField] = useState('agent_number');
  const [lookupText, setLookupText] = useState('');
  const [lookupResults, setLookupResults] = useState([]);
  const [lookupPerformed, setLookupPerformed] = useState(false);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState('');
  const [visitMode, setVisitMode] = useState(() => savedDraft?.visitMode || 'field_visit');
  const [lookupClient, setLookupClient] = useState(() => savedDraft?.lookupClient || null);
  const [lookupConfirmed, setLookupConfirmed] = useState(() => Boolean(savedDraft?.lookupConfirmed));
  const [autofillConfirmed, setAutofillConfirmed] = useState(false);
  const [visitEndSignal, setVisitEndSignal] = useState(0);
  const visibleDocuments = useMemo(() => documentLists[newClient.category] || [], [newClient.category]);
  const missingWitnessDetails = [
    !newClient.witness.name.trim() && 'Witness name',
    !newClient.witness.idNumber.trim() && 'Witness ID number',
    !newClient.witness.phoneNumber.trim() && 'Witness phone',
  ].filter(Boolean);
  const registrationStatus = useMemo(
    () => visibleDocuments.length > 0
      && visibleDocuments.every(([key]) => newClient.documents[key] === true)
      && !missingWitnessDetails.length
      ? 'COMPLETE'
      : 'INCOMPLETE',
    [newClient.documents, visibleDocuments, missingWitnessDetails.length],
  );
  const missingDocuments = visibleDocuments.filter(([key]) => newClient.documents[key] !== true).map(([, label]) => label);

  useEffect(() => {
    window.sessionStorage.setItem(draftStorageKey, JSON.stringify({ clientType, existing, newClient, lookupClient, lookupConfirmed, visitMode }));
  }, [clientType, existing, newClient, lookupClient, lookupConfirmed, visitMode, draftStorageKey]);

  const chooseStatus = (status) => { setNewClient({ ...emptyNew(), status }); setFeedback(null); };
  const chooseCategory = (category) => setNewClient((current) => ({ ...current, category, documents: {} }));
  const updateExisting = (field, value) => setExisting((current) => ({ ...current, [field]: value }));
  const updateNew = (field, value) => setNewClient((current) => ({ ...current, [field]: value }));
  const updateWitness = (field, value) => setNewClient((current) => ({ ...current, witness: { ...current.witness, [field]: value } }));
  const setReferralAgreed = (value) => setExisting((current) => ({ ...current, referralAgreed: value, ...(value === 'no' ? { referralName: '', referralContactNumber: '', referralDetails: '' } : {}) }));
  const toggleDocument = (key) => setNewClient((current) => ({ ...current, documents: { ...current.documents, [key]: !current.documents[key] } }));

  const searchClients = async (event) => {
    event.preventDefault();
    if (!lookupText.trim()) return;
    setLookupLoading(true);
    setLookupError('');
    setLookupResults([]);
    setLookupPerformed(false);
    try {
      const searchUrl = API_ORIGIN + '/api/sales/clients/lookup?field='
        + encodeURIComponent(lookupField) + '&q=' + encodeURIComponent(lookupText.trim());
      const search = async () => fetch(
        searchUrl,
        { headers: { Authorization: ['Bearer', getAuthToken()].join(' ') } },
      );
      let response = await search();
      if (response.status === 401 && await refreshAuthToken()) response = await search();
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(response.status === 401
          ? 'Your session has expired. Please sign in again and retry.'
          : payload.error?.message || 'Unable to search the client directory.');
      }
      setLookupResults(payload.data?.matches || []);
      setLookupPerformed(true);
    } catch (error) {
      setLookupError(error.message || 'Unable to search the client directory.');
    } finally {
      setLookupLoading(false);
    }
  };

  const selectLookupClient = (match) => {
    setLookupClient(match);
    setLookupConfirmed(true);
    setAutofillConfirmed(false);
    setExisting({
      ...emptyExisting(),
      category: match.category || '',
      agentName: match.agent_name || '',
      agentNumber: match.agent_number || '',
      storeNumber: match.store_number || '',
      businessLocation: match.business_location || '',
      ownerName: match.owner_name || '',
      ownerIdNumber: match.owner_id_number || '',
      ownerPhoneNumber: match.owner_phone_number || '',
      documents: match.documents || {},
    });
    setNewClient(emptyNew());
    setClientType('existing');
    setStep('form');
    setFeedback(null);
  };

  const continueAsNewClient = () => {
    setLookupClient(null);
    setAutofillConfirmed(false);
    setExisting(emptyExisting());
    setNewClient(emptyNew());
    setClientType('new');
    setLookupConfirmed(false);
    setStep('form');
    setFeedback(null);
  };

  const returnToLookup = () => {
    setClientType('');
    setLookupClient(null);
    setLookupConfirmed(false);
    setAutofillConfirmed(false);
    setLookupText('');
    setLookupResults([]);
    setLookupPerformed(false);
    setExisting(emptyExisting());
    setNewClient(emptyNew());
    setStep('form');
  };

  const beginExistingClient = () => {
    setClientType('existing');
    setLookupClient(null);
    setLookupConfirmed(true);
    setExisting(emptyExisting());
    setStep('form');
    setFeedback(null);
  };

  const continueWithExistingDetails = () => {
    setLookupConfirmed(true);
    setLookupClient(null);
    setFeedback(null);
  };

  const findExistingProfile = () => {
    setLookupText('');
    setLookupResults([]);
    setLookupPerformed(false);
    setLookupError('');
    setLookupConfirmed(false);
  };

  const submit = (event) => {
    event.preventDefault();
    if (step === 'review') return;
    if (!event.currentTarget.checkValidity()) {
      event.currentTarget.reportValidity();
      return;
    }
    setFeedback(null);
    setStep('review');
  };

  const confirmAddClient = async () => {
    setSubmitting(true);
    setFeedback(null);
    const record = clientType === 'existing'
      ? { clientType, existing: { ...existing } }
      : { clientType, new: { ...newClient, ...(newClient.status === 'ready_to_register' ? { registrationStatus } : {}) } };
    try {
      const branch = clientType === 'existing' ? record.existing : record.new;
      const body = new FormData();
      body.append('agent_name', branch.agentName); body.append('agent_number', branch.agentNumber); body.append('store_number', branch.storeNumber);
      body.append('business_location', branch.businessLocation || ''); body.append('date_visited', new Date().toISOString().slice(0, 10));
      body.append('business_owner_name', branch.ownerName || ''); body.append('id_number', branch.ownerIdNumber || ''); body.append('contact_phone', branch.ownerPhoneNumber || '');
      body.append('customer_type', apiCategory(branch.category || 'mpesa_agent')); body.append('outcome', clientType === 'existing' ? 'existing' : branch.status);
      body.append('visit_mode', visitMode);
      body.append('new_client', String(clientType === 'new')); body.append('notes', branch.remarks || ''); body.append('referral_agreed', branch.referralAgreed || '');
      body.append('referral_name', branch.referralName || ''); body.append('referral_contact_number', branch.referralContactNumber || '');
      body.append('referral_details', branch.referralDetails || ''); body.append('appointment_date', branch.appointmentDate || ''); body.append('appointment_time', branch.appointmentTime || '');
      body.append('registration_date', branch.registrationDate || '');
      body.append('registration_status', branch.registrationStatus || '');
      if (clientType === 'new' && branch.status === 'ready_to_register') {
        Object.entries(branch.documents).forEach(([key, value]) => body.append(key, String(value)));
        body.append('witness_name', branch.witness.name); body.append('witness_id_number', branch.witness.idNumber); body.append('witness_phone', branch.witness.phoneNumber);
      }
      let response = await fetch(API_ORIGIN + '/api/sales/reports', { method: 'POST', headers: { Authorization: ['Bearer', getAuthToken()].join(' ') }, body });
      if (response.status === 401 && await refreshAuthToken()) {
        response = await fetch(API_ORIGIN + '/api/sales/reports', { method: 'POST', headers: { Authorization: ['Bearer', getAuthToken()].join(' ') }, body });
      }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Please sign in again and retry.' : payload.error?.message || payload.msg || payload.message || 'Unable to add client.');
      setVisitEndSignal((current) => current + 1);
      window.sessionStorage.removeItem(draftStorageKey);
      setClientType(''); setLookupClient(null); setLookupConfirmed(false); setAutofillConfirmed(false); setLookupText(''); setLookupResults([]); setLookupPerformed(false); setExisting(emptyExisting()); setNewClient(emptyNew()); setStep('form'); setSavedReport(payload.data || {}); setFeedback({ type: 'success', text: 'Customer record added successfully. The form is ready for the next client.' }); onSubmitted?.({ ...payload.data, client_record: record });
    } catch (error) { setFeedback({ type: 'error', text: error.message }); } finally { setSubmitting(false); }
  };

  const identityFields = (branch, updateBranch) => <><label>Agent Name<input name="agent_name" value={branch.agentName} onChange={(event) => updateBranch('agentName', event.target.value)} required /></label><label>Agent Number<input name="agent_number" value={branch.agentNumber} onChange={(event) => updateBranch('agentNumber', event.target.value)} required /></label><label>Store Number<input name="store_number" value={branch.storeNumber} onChange={(event) => updateBranch('storeNumber', event.target.value)} required /></label></>;
  const displayValue = (value) => value || '—';
  const reviewField = (label, value) => <div key={label}><dt>{label}</dt><dd>{displayValue(value)}</dd></div>;
  const clientBranch = clientType === 'existing' ? existing : newClient;
  const reviewCategory = clientType === 'existing'
    ? categoryLabel(existing.category)
    : (newClient.category === 'mpesa_sub_agent' ? 'M-Pesa Sub-Agent' : 'M-Pesa Agent / Dealer');
  return <section className="leave-section sales-report-section" id="sales-daily-report">
    <div className="leave-section-heading"><div>{showHeadingEyebrow && <p className="leave-kicker">SALES REPORT</p>}<h2>{headingTitle}</h2>{showHeadingSubtitle && <p className="leave-muted">Add one client record at a time.</p>}</div></div>
    {feedback && <div className={['leave-alert', feedback.type].join(' ')} role="status">{feedback.text}</div>}
    {savedReport && <div className="sales-saved-result" role="status" aria-live="polite"><strong>Saved client record</strong><span>Record #{savedReport.id || 'saved'}</span>{savedReport.outcome && <span>Result: {savedReport.outcome.replaceAll('_', ' ')}</span>}{savedReport.registration_status && <span>Registration status: {savedReport.registration_status}</span>}<span>Step 1 is ready for the next client.</span></div>}
    <form className="sales-report-form" onSubmit={submit}>
      {!clientType && <div className="sales-lookup-panel">
        <div className="sales-form-step"><span>STEP 1</span><h3>Choose client type</h3></div>
        <p>Start by selecting whether this is a new or existing client.</p>
        <div className="sales-choice-buttons"><button type="button" onClick={continueAsNewClient}>New Client</button><button type="button" onClick={beginExistingClient}>Existing Client</button></div>
      </div>}
      {clientType === 'existing' && !lookupConfirmed && <div className="sales-lookup-panel">
        <div className="sales-form-step"><span>STEP 2</span><h3>Find the existing client</h3></div>
        <p>Search to load an existing profile, or continue to enter its details manually.</p>
        <div className="sales-lookup-controls">
          <label>Search using<select value={lookupField} onChange={(event) => setLookupField(event.target.value)}><option value="agent_name">Client / Agent Name</option><option value="agent_number">Agent Number</option><option value="store_number">Store Number</option></select></label>
          <label>Lookup value<input value={lookupText} onChange={(event) => setLookupText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') searchClients(event); }} placeholder={lookupField === 'agent_name' ? 'Enter client or agent name' : lookupField === 'agent_number' ? 'Enter agent number' : 'Enter store number'} /></label>
          <button type="button" className="sales-submit-button" disabled={lookupLoading || !lookupText.trim()} onClick={searchClients}>{lookupLoading ? 'Searching…' : 'Search clients'}</button>
        </div>
        {lookupError && <div className="sales-lookup-message is-error" role="alert">{lookupError}</div>}
        {lookupPerformed && lookupResults.length > 0 && <div className="sales-lookup-results" role="list" aria-label="Matching clients">
          <strong>Matching profiles — choose the correct client to auto-fill the report.</strong>
          {lookupResults.map((match, index) => <button className="sales-lookup-result" type="button" key={(match.agent_number || match.store_number || match.agent_name) + '-' + index} onClick={() => selectLookupClient(match)}>
            <span><strong>{match.agent_name || 'Name not recorded'}</strong><small>{match.agent_number || 'No agent number'} · {match.store_number || 'No store number'}</small></span>
            <span>{categoryLabel(match.category)} · {match.business_location || 'Location not recorded'}</span>
            <small>Source: {match.source}</small>
          </button>)}
        </div>}
        {lookupPerformed && lookupResults.length === 0 && <div className="sales-lookup-message" role="status"><span>No matching client was found.</span><button type="button" className="sales-submit-button" onClick={continueWithExistingDetails}>Enter Existing Client Details</button></div>}
        <button type="button" className="sales-submit-button" onClick={continueWithExistingDetails}>Continue with Existing Client</button>
      </div>}
      {clientType && (clientType !== 'existing' || lookupConfirmed) && <div className="sales-form-step"><span>STEP {step === 'review' ? '3' : '2'} OF 3</span><h3>{step === 'review' ? 'Review client report' : clientType === 'existing' ? 'Existing client interaction' : 'New client details'}</h3>{clientType === 'existing' && !lookupClient && <button className="sales-back-to-lookup" type="button" onClick={findExistingProfile}>Search saved client profile</button>}<button className="sales-back-to-lookup" type="button" onClick={returnToLookup}>Choose client type</button></div>}
      {step === 'form' && (clientType !== 'existing' || lookupConfirmed) && <>
      {clientType === 'existing' && <div className="sales-conditional-grid">
        <label>Category<select value={existing.category} onChange={(event) => updateExisting('category', event.target.value)} required><option value="">Select category</option><option value="mpesa_agent">M-Pesa Agent / Dealer</option><option value="mpesa_sub_agent">M-Pesa Sub-Agent</option></select></label>
        {identityFields(existing, updateExisting)}
        <label>Business Location<input name="business_location" value={existing.businessLocation} onChange={(event) => updateExisting('businessLocation', event.target.value)} required /></label>
        {lookupClient && <div className="sales-existing-documents sales-full-field">
          <strong>Previously recorded document checklist <small>Source: {lookupClient.source}. These are saved checklist responses, not an independent document-verification audit.</small></strong>
          <div>{documentsForCategory(lookupClient.category).map(([key, label]) => <span key={key} className={lookupClient.documents?.[key] ? 'is-recorded' : ''}>{lookupClient.documents?.[key] ? 'YES' : 'Not recorded'} · {label}</span>)}</div>
        </div>}
        <label className="sales-full-field">Remarks<textarea value={existing.remarks} onChange={(event) => updateExisting('remarks', event.target.value)} rows="4" required /></label>
        <fieldset className="sales-choice-fieldset sales-full-field"><legend>Did they agree to give a referral?</legend><div className="sales-choice-buttons"><button type="button" className={existing.referralAgreed === 'yes' ? 'selected' : ''} onClick={() => setReferralAgreed('yes')}>YES</button><button type="button" className={existing.referralAgreed === 'no' ? 'selected' : ''} onClick={() => setReferralAgreed('no')}>NO</button></div></fieldset>
        {existing.referralAgreed === 'yes' && <><label>Referral Name<input name="referral_name" value={existing.referralName} onChange={(event) => updateExisting('referralName', event.target.value)} required /></label><label>Referral Contact Number<input name="referral_contact_number" value={existing.referralContactNumber} onChange={(event) => updateExisting('referralContactNumber', event.target.value)} required /></label><label className="sales-full-field">Additional Referral Notes (optional)<textarea name="referral_details" value={existing.referralDetails} onChange={(event) => updateExisting('referralDetails', event.target.value)} rows="3" /></label></>}
      </div>}
      {clientType === 'new' && <>{initialStatus
        ? <p className="sales-full-field">Status: <strong>{initialStatus.replaceAll('_', ' ')}</strong></p>
        : <label>Status<select value={newClient.status} onChange={(event) => chooseStatus(event.target.value)} required><option value="">Select status</option><option value="interested">Interested</option><option value="not_interested">Not Interested</option><option value="appointment">Appointment</option><option value="ready_to_register">Ready to Register</option></select></label>}
        {newClient.status && <div className="sales-conditional-grid">
          {newClient.status === 'ready_to_register' && <label>Category<select value={newClient.category} onChange={(event) => chooseCategory(event.target.value)} required><option value="">Select category</option><option value="mpesa_agent_dealer">M-Pesa Agent / M-Pesa Dealer</option><option value="mpesa_sub_agent">M-Pesa Sub-Agent</option></select></label>}
          {identityFields(newClient, updateNew)}
          {newClient.status !== 'ready_to_register' && <label>Business Location<input name="business_location" value={newClient.businessLocation} onChange={(event) => updateNew('businessLocation', event.target.value)} required /></label>}
          {newClient.status === 'appointment' && <><label>Appointment Date<input type="date" value={newClient.appointmentDate} onChange={(event) => updateNew('appointmentDate', event.target.value)} required /></label><label>Appointment Time<input type="time" value={newClient.appointmentTime} onChange={(event) => updateNew('appointmentTime', event.target.value)} required /></label></>}
          {newClient.status !== 'ready_to_register' && <label className="sales-full-field">Remarks<textarea value={newClient.remarks} onChange={(event) => updateNew('remarks', event.target.value)} rows="4" required /></label>}
          {newClient.status === 'ready_to_register' && <>
            <label>Business Location<input name="business_location" value={newClient.businessLocation} onChange={(event) => updateNew('businessLocation', event.target.value)} required /></label>
            <label className="sales-full-field">Remarks<textarea name="notes" value={newClient.remarks} onChange={(event) => updateNew('remarks', event.target.value)} rows="4" /></label>
          </>}
          {newClient.status === 'ready_to_register' && newClient.category && <>
            <fieldset className="sales-documents sales-full-field"><legend>Documents submitted</legend><div className={['sales-toggle-grid', newClient.category === 'mpesa_agent_dealer' ? 'sales-toggle-grid-agent' : ''].filter(Boolean).join(' ')}>{visibleDocuments.map(([key, label]) => <button type="button" key={key} className={newClient.documents[key] ? 'active' : ''} aria-pressed={Boolean(newClient.documents[key])} onClick={() => toggleDocument(key)}>{label}</button>)}</div></fieldset>
            <label>Registration Date<input type="date" name="registration_date" value={newClient.registrationDate} onChange={(event) => updateNew('registrationDate', event.target.value)} required /></label>
            <fieldset className="sales-witness sales-full-field"><legend>The contract was signed in the presence of:</legend><label>Name<input value={newClient.witness.name} onChange={(event) => updateWitness('name', event.target.value)} required /></label><label>ID Number<input value={newClient.witness.idNumber} onChange={(event) => updateWitness('idNumber', event.target.value)} required /></label><label>Phone Number<input value={newClient.witness.phoneNumber} onChange={(event) => updateWitness('phoneNumber', event.target.value)} required /></label></fieldset>
            <div className={['registration-status', registrationStatus.toLowerCase()].join(' ')}><strong>{registrationStatus}</strong><span>Based on required documents and witness details</span></div>
            {missingDocuments.length > 0 && <div className="sales-missing-documents" role="status"><strong>Missing required documents:</strong><ul>{missingDocuments.map((label) => <li key={label}>{label}</li>)}</ul><span>You may still submit this report as INCOMPLETE.</span></div>}
            {missingWitnessDetails.length > 0 && <div className="sales-missing-documents" role="status"><strong>Missing witness details:</strong><ul>{missingWitnessDetails.map((label) => <li key={label}>{label}</li>)}</ul></div>}
          </>}
        </div>}
      </>}
      {clientType && <label className="sales-visit-mode">Interaction type<select value={visitMode} onChange={(event) => setVisitMode(event.target.value)}><option value="field_visit">Field visit</option><option value="telesales">Telesales</option></select></label>}
      <ActiveFieldVisitLocation enabled={isFieldAgent && Boolean(clientType) && visitMode === 'field_visit'} endSignal={visitEndSignal} />
      {clientType && (clientType !== 'existing' || lookupConfirmed) && ((clientType === 'existing' && existing.referralAgreed) || (clientType === 'new' && newClient.status)) && <div className="form-actions"><button type="submit" className="sales-submit-button">Review report</button></div>}
      </>}
      {step === 'review' && (clientType !== 'existing' || lookupConfirmed) && <div className="sales-review-summary" aria-label="Client report summary">
        <p>Check all details before saving. No report is submitted until you select <strong>Add Client</strong>.</p>
        <dl>
          {reviewField('Client type', clientType === 'existing' ? 'Existing Client' : 'New Client')}
          {(clientType === 'existing' || newClient.status === 'ready_to_register') && reviewField('Category', reviewCategory)}
          {lookupClient && reviewField('Profile source', lookupClient.source)}
          {reviewField('Agent name', clientBranch.agentName)}
          {reviewField('Agent number', clientBranch.agentNumber)}
          {reviewField('Store number', clientBranch.storeNumber)}
          {(clientBranch.ownerName || clientBranch.ownerIdNumber || clientBranch.ownerPhoneNumber) && <>
            {reviewField('Business owner name', clientBranch.ownerName)}
            {reviewField('Business owner ID number', clientBranch.ownerIdNumber)}
            {reviewField('Business owner phone number', clientBranch.ownerPhoneNumber)}
          </>}
          {reviewField('Business location', clientBranch.businessLocation)}
          {clientType === 'existing' ? <>
            {lookupClient && <div className="sales-review-documents"><dt>Previously recorded documents</dt><dd>{documentsForCategory(lookupClient.category).map(([key, label]) => <span className={lookupClient.documents?.[key] ? '' : 'missing'} key={key}>{lookupClient.documents?.[key] ? 'Recorded: ' : 'Not recorded: '}{label}</span>)}</dd></div>}
            {reviewField('Remarks', existing.remarks)}
            {reviewField('Referral agreed', existing.referralAgreed.toUpperCase())}
            {existing.referralAgreed === 'yes' && <>{reviewField('Referral name', existing.referralName)}{reviewField('Referral contact', existing.referralContactNumber)}{reviewField('Additional referral notes', existing.referralDetails)}</>}
          </> : <>
            {reviewField('Status', newClient.status.replaceAll('_', ' '))}
            {newClient.status !== 'ready_to_register' && reviewField('Remarks', newClient.remarks)}
            {newClient.status === 'appointment' && <>{reviewField('Appointment date', newClient.appointmentDate)}{reviewField('Appointment time', newClient.appointmentTime)}</>}
            {newClient.status === 'ready_to_register' && <>
              {reviewField('Remarks', newClient.remarks)}
              {reviewField('Registration status', registrationStatus)}
              {reviewField('Registration date', newClient.registrationDate)}
              {reviewField('Witness name', newClient.witness.name)}
              {reviewField('Witness ID number', newClient.witness.idNumber)}
              {reviewField('Witness phone', newClient.witness.phoneNumber)}
              <div className="sales-review-documents"><dt>Required documents</dt><dd>{visibleDocuments.filter(([key]) => newClient.documents[key]).map(([, label]) => <span key={label}>✓ {label}</span>)}{missingDocuments.map((label) => <span className="missing" key={label}>Missing: {label}</span>)}</dd></div>
            </>}
          </>}
        </dl>
        {lookupClient && <label className="sales-autofill-confirm"><input type="checkbox" checked={autofillConfirmed} onChange={(event) => setAutofillConfirmed(event.target.checked)} />I reviewed and confirm the auto-populated client details and previously recorded documents.</label>}
        <div className="form-actions"><button type="button" className="sales-submit-button" onClick={() => { setStep('form'); setFeedback(null); }}>Edit details</button><button type="button" className="sales-submit-button" disabled={submitting || (Boolean(lookupClient) && !autofillConfirmed)} onClick={confirmAddClient}>{submitting ? 'Submitting...' : submitButtonLabel}</button></div>
      </div>}
    </form>
  </section>;
}
