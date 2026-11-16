import React, { useMemo, useRef, useState } from 'react';
import { createLeaveRequest } from '../services/leaveApi';
import HandoverReportForm, { emptyReport } from './HandoverReportForm';
import { getAuthToken } from '../services/authStorage';

const declaration = 'I confirm that the information provided is accurate and understand that leave approval follows the organization workflow.';

const workingDays = (start, end) => {
  if (!start || !end) return 0;
  const first = new Date(`${start}T00:00:00`);
  const last = new Date(`${end}T00:00:00`);
  if (last < first) return 0;
  let days = 0;
  for (const date = new Date(first); date <= last; date.setDate(date.getDate() + 1)) {
    if (date.getDay() !== 0 && date.getDay() !== 6) days += 1;
  }
  return days;
};

export default function LeaveApplicationWizard({ currentUser, leaveTypes, balances = [], colleagues, onClose, onSubmitted, onViewRequests }) {
  const [draft] = useState(() => {
    try {
      return JSON.parse(window.sessionStorage.getItem('okoa-leave-draft') || '{}') || {};
    } catch {
      return {};
    }
  });
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [requestSubmitted, setRequestSubmitted] = useState(false);
  const [showHandoverModal, setShowHandoverModal] = useState(false);
  const [handoverReport, setHandoverReport] = useState(() => draft.handover_report_details || emptyReport());
  const [handoverReportSubmitted, setHandoverReportSubmitted] = useState(() => Boolean(draft.handover_report_submitted));
  const [createdRequestId, setCreatedRequestId] = useState(() => draft.created_leave_request_id || null);
  const [supportingFiles, setSupportingFiles] = useState([]);
  const attachmentInput = useRef(null);
  const [form, setForm] = useState(() => ({
    leave_type_id: '', start_date: '', end_date: '', reason: '', declaration: false, employee_signature: currentUser?.name || currentUser?.full_name || '', declaration_date: new Date().toISOString().slice(0, 10),
    handover_user_id: '', handover_notes: '', supporting_info: '', contact_phone: currentUser?.contact?.phone || currentUser?.phone || '', contact_email: currentUser?.contact?.email || currentUser?.email || '',
    ...draft,
  }));
  const days = useMemo(() => workingDays(form.start_date, form.end_date), [form.start_date, form.end_date]);
  const selectedType = leaveTypes.find((type) => String(type.id) === String(form.leave_type_id));
  const selectedBalance = balances.find((balance) => String(balance.leave_type_id) === String(form.leave_type_id));
  const remainingAfterRequest = selectedBalance
    ? Number(selectedBalance.available_days || 0) - days
    : null;
  const handoverRequired = days > 2;
  const reportRequired = days > 3 && selectedType && !['SICK', 'UNPAID'].includes(String(selectedType.code || '').toUpperCase());
  const update = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    if (['leave_type_id', 'start_date', 'end_date'].includes(field)) setHandoverReportSubmitted(false);
  };

  const validateStep = () => {
    if (step === 1) {
      if (!form.leave_type_id || !form.start_date || !form.end_date || !form.reason.trim()) return 'Complete leave type, dates, and reason.';
      if (days <= 0) return 'Choose a date range containing at least one working day.';
      if (!form.declaration || !form.employee_signature.trim() || !form.declaration_date) return 'Accept the declaration and provide your typed signature and date.';
    }
    if (step === 2 && handoverRequired && (!form.handover_user_id || !form.handover_notes.trim())) return 'A handover person and handover notes are required for leaves longer than 2 days.';
    if (step === 2 && reportRequired && !handoverReportSubmitted) return 'Complete and submit the full handover report before proceeding.';
    if (step === 3 && reportRequired && !handoverReportSubmitted) return 'Submit the required full handover report before submitting this leave request.';
    return '';
  };

  const next = () => {
    const validationError = validateStep();
    if (validationError) { setError(validationError); return; }
    setError('');
    setStep((current) => Math.min(3, current + 1));
  };

  const saveDraft = () => {
    window.sessionStorage.setItem('okoa-leave-draft', JSON.stringify({
      ...form,
      handover_report_details: handoverReport,
      handover_report_submitted: handoverReportSubmitted,
      created_leave_request_id: createdRequestId,
    }));
    setError('Draft saved in this browser tab.');
  };

  const submit = async (event) => {
    event.preventDefault();
    const validationError = validateStep();
    if (validationError) { setError(validationError); return; }
    setSaving(true);
    setError('');
    try {
      const leaveForm = Object.fromEntries(Object.entries(form).filter(([field]) => !['address_line1', 'address_line2', 'city', 'country', 'postal_code', 'handover_report_details', 'handover_report_submitted', 'created_leave_request_id'].includes(field)));
      const payload = {
        ...leaveForm,
        leave_type_id: Number(form.leave_type_id),
        handover_report: form.handover_notes,
        ...(reportRequired ? { handover_report_details: handoverReport } : {}),
        supporting_attachments_expected: supportingFiles.length > 0,
        declaration_accepted: form.declaration,
        handover_name: colleagues.find((item) => String(item.id) === String(form.handover_user_id))?.name || '',
      };
      const created = createdRequestId ? { data: { id: createdRequestId } } : await createLeaveRequest(payload);
      const requestId = created.data?.id;
      if (requestId && !createdRequestId) setCreatedRequestId(requestId);
      if (requestId && supportingFiles.length) {
        for (const file of supportingFiles) {
          const upload = new FormData();
          upload.append('file', file);
          const response = await fetch(`/api/leave/requests/${requestId}/handover/attachment`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${getAuthToken()}` },
            body: upload,
          });
          const result = await response.json();
          if (!response.ok) throw new Error(`Leave request submitted, but ${file.name} could not be attached: ${result.error?.message || 'upload failed'}`);
          setSupportingFiles((files) => files.filter((pendingFile) => pendingFile !== file));
        }
      }
      window.sessionStorage.removeItem('okoa-leave-draft');
      if (onSubmitted) onSubmitted();
      else setRequestSubmitted(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="leave-section leave-application-page" aria-labelledby="wizard-title">
      <div className="leave-section-heading"><div><p className="leave-kicker">NEW REQUEST · STEP {step} OF 3</p><h2 id="wizard-title">Apply for leave</h2></div><button className="leave-secondary-button" type="button" onClick={onClose}>Cancel</button></div>
      {error && <div className="leave-alert error" role="alert">{error}</div>}
      {requestSubmitted ? (
        <div className="leave-alert success" role="status">
          Your leave request has been submitted successfully.
          <button type="button" className="leave-primary-button" onClick={onViewRequests}>View my leave requests</button>
        </div>
      ) : <form onSubmit={submit}>
        {step === 1 && <fieldset className="leave-fieldset"><legend>Leave details</legend><label>Leave type<select value={form.leave_type_id} onChange={(event) => update('leave_type_id', event.target.value)} required><option value="">Select leave type</option>{leaveTypes.map((type) => <option value={type.id} key={type.id}>{type.name}</option>)}</select></label><div className="leave-form-row"><label>First day<input type="date" value={form.start_date} onChange={(event) => update('start_date', event.target.value)} required /></label><label>Last day<input type="date" value={form.end_date} onChange={(event) => update('end_date', event.target.value)} required /></label><div className="days-preview"><span>Number of days</span><strong>{days}</strong></div></div>{selectedType && selectedType.code?.toUpperCase() !== 'UNPAID' && <div className="leave-balance-preview" aria-live="polite"><div><span>Available before request</span><strong>{selectedBalance?.available_days ?? selectedType.annual_entitlement_days ?? selectedType.default_days_per_year ?? 0} days</strong></div><div><span>Estimated remaining after request</span><strong className={remainingAfterRequest !== null && remainingAfterRequest < 0 ? 'negative' : ''}>{remainingAfterRequest === null ? 'Balance loading' : `${remainingAfterRequest} days`}</strong></div><small>Final working-day count and balance are confirmed when you submit.</small></div>}<label>Reason<textarea value={form.reason} onChange={(event) => update('reason', event.target.value)} required /></label><label className="checkbox-row"><input type="checkbox" checked={form.declaration} onChange={(event) => update('declaration', event.target.checked)} /> {declaration}</label><div className="leave-form-row"><label>Typed signature<input value={form.employee_signature} onChange={(event) => update('employee_signature', event.target.value)} required /></label><label>Declaration date<input type="date" value={form.declaration_date} onChange={(event) => update('declaration_date', event.target.value)} required /></label></div></fieldset>}
        {step === 2 && (
          <fieldset className="leave-fieldset">
            <legend>Handover requirement</legend>
            <p className="leave-muted">
              {handoverRequired
                ? 'If taking more than two days, indicate below the person who will handle your work during your absence.'
                : 'No handover is required for leaves of 2 working days or fewer.'}
            </p>
            {handoverRequired && <>
              <label>Handover person<select value={form.handover_user_id} onChange={(event) => update('handover_user_id', event.target.value)} required><option value="">Select colleague</option>{colleagues.map((person) => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label>
              <label>Handover notes<textarea value={form.handover_notes} onChange={(event) => update('handover_notes', event.target.value)} required /></label>
            </>}
            <label>Supporting information<textarea value={form.supporting_info} onChange={(event) => update('supporting_info', event.target.value)} /></label>
            <label className="leave-supporting-upload">Supporting attachment (optional)
              <input ref={attachmentInput} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple onChange={(event) => {
                const selected = Array.from(event.target.files || []);
                const invalid = selected.find((file) => {
                  const validType = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'].includes(file.type)
                    || /\.(pdf|docx)$/i.test(file.name);
                  return !validType || file.size > 10 * 1024 * 1024;
                });
                if (invalid) {
                  setError('Choose PDF or DOCX files up to 10 MB each.');
                  event.target.value = '';
                  return;
                }
                setError('');
                setSupportingFiles((files) => [...files, ...selected]);
                event.target.value = '';
              }} />
              {supportingFiles.length > 0 && <ul>{supportingFiles.map((file, index) => <li key={`${file.name}-${index}`}>{file.name}<button type="button" aria-label={`Remove ${file.name}`} onClick={() => setSupportingFiles((files) => files.filter((_, fileIndex) => fileIndex !== index))}>×</button></li>)}</ul>}
            </label>
            {reportRequired && <p className="leave-muted">
              For a planned absence exceeding 3 days, a full handover report must be submitted before proceeding. <button className="leave-text-button" type="button" onClick={() => setShowHandoverModal(true)}>Handover report</button>
            </p>}
          </fieldset>
        )}
        {step === 3 && <>
          <fieldset className="leave-fieldset">
            <legend>Review and submit</legend>
            <dl className="review-list">
              <div><dt>Leave type</dt><dd>{selectedType?.name || '-'}</dd></div>
              <div><dt>Dates</dt><dd>{form.start_date || '-'} to {form.end_date || '-'}</dd></div>
              <div><dt>Number of days</dt><dd>{days}</dd></div>
              <div><dt>Handover</dt><dd>{handoverRequired ? `${colleagues.find((item) => String(item.id) === String(form.handover_user_id))?.name || 'Not selected'} · pending acceptance` : 'Not required'}</dd></div>
              {reportRequired && <div><dt>Full report</dt><dd>{handoverReportSubmitted ? 'Submitted' : 'Required before leave submission'}</dd></div>}
            </dl>
            <label>Contact phone<input value={form.contact_phone} onChange={(event) => update('contact_phone', event.target.value)} required /></label>
            <label>Contact email<input type="email" value={form.contact_email} onChange={(event) => update('contact_email', event.target.value)} required /></label>
          </fieldset>
        </>}
        <div className="leave-modal-actions">
          {step > 1 && <button type="button" className="leave-secondary-button" onClick={() => { setError(''); setStep((current) => current - 1); }}>Back</button>}
          {step < 3 ? <button type="button" className="leave-primary-button" onClick={next} disabled={step === 2 && reportRequired && !handoverReportSubmitted} title={step === 2 && reportRequired && !handoverReportSubmitted ? 'Submit the full handover report before continuing' : undefined}>Next</button> : <>
            <button type="button" className="leave-secondary-button" onClick={saveDraft}>Save as Draft</button>
            <button type="submit" className="leave-primary-button" disabled={saving || (reportRequired && !handoverReportSubmitted)} title={reportRequired && !handoverReportSubmitted ? 'Submit the full handover report first' : undefined}>{saving ? 'Submitting…' : 'Submit Leave Request'}</button>
          </>}
        </div>
      </form>}
      {showHandoverModal && reportRequired && <div className="leave-modal-backdrop handover-modal-backdrop" role="presentation">
        <section className="leave-modal leave-modal-wide handover-request-modal" role="dialog" aria-modal="true" aria-labelledby="request-handover-title">
          <div className="leave-modal-heading">
            <div><p className="leave-kicker">REQUIRED FOR PLANNED ABSENCE OVER 3 DAYS</p><h2 id="request-handover-title">Handover report</h2></div>
            <button className="leave-close" type="button" onClick={() => setShowHandoverModal(false)} aria-label="Close handover report">×</button>
          </div>
          <p className="leave-muted">Complete the required summary and active tasks, then submit the report before continuing. Attachments are optional.</p>
          <HandoverReportForm
            preSubmit
            initialReport={handoverReport}
            onChange={(report) => { setHandoverReport(report); setHandoverReportSubmitted(false); }}
            onSubmitted={(report) => { setHandoverReport(report); setHandoverReportSubmitted(true); setError(''); setShowHandoverModal(false); }}
          />
        </section>
      </div>}
    </section>
  );
}
