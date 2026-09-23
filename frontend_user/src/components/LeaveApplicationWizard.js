import React, { useMemo, useState } from 'react';
import { createLeaveRequest } from '../services/leaveApi';

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

const wordCount = (value = '') => value.trim() ? value.trim().split(/\s+/).length : 0;

export default function LeaveApplicationWizard({ currentUser, leaveTypes, colleagues, onClose, onSubmitted }) {
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(() => ({
    leave_type_id: '', start_date: '', end_date: '', reason: '', declaration: false, employee_signature: currentUser?.name || currentUser?.full_name || '', declaration_date: new Date().toISOString().slice(0, 10),
    handover_user_id: '', handover_notes: '', supporting_info: '', full_handover_report: '', contact_phone: currentUser?.contact?.phone || currentUser?.phone || '', contact_email: currentUser?.contact?.email || currentUser?.email || '',
  }));
  const days = useMemo(() => workingDays(form.start_date, form.end_date), [form.start_date, form.end_date]);
  const handoverRequired = days > 2;
  const reportRequired = days > 3;
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const validateStep = () => {
    if (step === 1) {
      if (!form.leave_type_id || !form.start_date || !form.end_date || !form.reason.trim()) return 'Complete leave type, dates, and reason.';
      if (days <= 0) return 'Choose a date range containing at least one working day.';
      if (!form.declaration || !form.employee_signature.trim() || !form.declaration_date) return 'Accept the declaration and provide your typed signature and date.';
    }
    if (step === 2) {
          if (handoverRequired && (!form.handover_user_id || !form.handover_notes.trim())) return 'A handover person and handover notes are required for leaves longer than 2 days.';
          if (reportRequired && form.full_handover_report.trim().length === 0) return 'A full handover report is required for leaves longer than 3 days.';
    }
    return '';
  };

  const next = () => {
    const validationError = validateStep();
    if (validationError) { setError(validationError); return; }
    setError('');
    setStep((current) => Math.min(3, current + 1));
  };

  const saveDraft = () => {
    window.sessionStorage.setItem('okoa-leave-draft', JSON.stringify(form));
    setError('Draft saved in this browser tab.');
  };

  const submit = async (event) => {
    event.preventDefault();
    const validationError = validateStep();
    if (validationError) { setError(validationError); return; }
    setSaving(true);
    setError('');
    try {
      const leaveForm = Object.fromEntries(Object.entries(form).filter(([field]) => !['address_line1', 'address_line2', 'city', 'country', 'postal_code'].includes(field)));
      const payload = {
        ...leaveForm,
        leave_type_id: Number(form.leave_type_id),
        handover_report: form.full_handover_report || form.handover_notes,
        declaration_accepted: form.declaration,
        handover_name: colleagues.find((item) => String(item.id) === String(form.handover_user_id))?.name || '',
      };
      await createLeaveRequest(payload);
      window.sessionStorage.removeItem('okoa-leave-draft');
      onSubmitted();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const selectedType = leaveTypes.find((type) => String(type.id) === String(form.leave_type_id));

  return (
    <div className="leave-modal-backdrop" role="presentation"><div className="leave-modal leave-modal-wide" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
      <div className="leave-modal-heading"><div><p className="leave-kicker">NEW REQUEST · STEP {step} OF 3</p><h2 id="wizard-title">Apply for leave</h2></div><button className="leave-close" type="button" onClick={onClose} aria-label="Close">×</button></div>
      {error && <div className="leave-alert error" role="alert">{error}</div>}
      <form onSubmit={submit}>
        {step === 1 && <fieldset className="leave-fieldset"><legend>Leave details</legend><label>Leave type<select value={form.leave_type_id} onChange={(event) => update('leave_type_id', event.target.value)} required><option value="">Select leave type</option>{leaveTypes.map((type) => <option value={type.id} key={type.id}>{type.name}</option>)}</select></label><div className="leave-form-row"><label>First day<input type="date" value={form.start_date} onChange={(event) => update('start_date', event.target.value)} required /></label><label>Last day<input type="date" value={form.end_date} onChange={(event) => update('end_date', event.target.value)} required /></label><div className="days-preview"><span>Number of days</span><strong>{days}</strong></div></div><label>Reason<textarea value={form.reason} onChange={(event) => update('reason', event.target.value)} required /></label><label className="checkbox-row"><input type="checkbox" checked={form.declaration} onChange={(event) => update('declaration', event.target.checked)} /> {declaration}</label><div className="leave-form-row"><label>Typed signature<input value={form.employee_signature} onChange={(event) => update('employee_signature', event.target.value)} required /></label><label>Declaration date<input type="date" value={form.declaration_date} onChange={(event) => update('declaration_date', event.target.value)} required /></label></div></fieldset>}
        {step === 2 && <fieldset className="leave-fieldset"><legend>Handover requirement</legend><p className="leave-muted">{handoverRequired ? 'Handover required for leaves longer than 2 days.' : 'No handover is required for leaves of 2 working days or fewer.'}</p>{handoverRequired && <><label>Handover person<select value={form.handover_user_id} onChange={(event) => update('handover_user_id', event.target.value)} required><option value="">Select colleague</option>{colleagues.map((person) => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label><label>Handover notes<textarea value={form.handover_notes} onChange={(event) => update('handover_notes', event.target.value)} required /></label><label>Supporting information<textarea value={form.supporting_info} onChange={(event) => update('supporting_info', event.target.value)} /></label></>}{reportRequired && <label>Full handover report <span className="field-counter">{wordCount(form.full_handover_report)} words</span><textarea value={form.full_handover_report} onChange={(event) => update('full_handover_report', event.target.value)} placeholder="Describe active work, next actions, deadlines, risks, and escalation contacts." required /></label>}</fieldset>}
        {step === 3 && <fieldset className="leave-fieldset"><legend>Review and submit</legend><dl className="review-list"><div><dt>Leave type</dt><dd>{selectedType?.name || '-'}</dd></div><div><dt>Dates</dt><dd>{form.start_date || '-'} to {form.end_date || '-'}</dd></div><div><dt>Number of days</dt><dd>{days}</dd></div><div><dt>Handover</dt><dd>{handoverRequired ? `${colleagues.find((item) => String(item.id) === String(form.handover_user_id))?.name || 'Not selected'} · pending acceptance` : 'Not required'}</dd></div><div><dt>Full report</dt><dd>{reportRequired ? (form.full_handover_report ? 'Ready to submit' : 'Missing') : 'Not required'}</dd></div></dl><label>Contact phone<input value={form.contact_phone} onChange={(event) => update('contact_phone', event.target.value)} required /></label><label>Contact email<input type="email" value={form.contact_email} onChange={(event) => update('contact_email', event.target.value)} required /></label></fieldset>}
        <div className="leave-modal-actions">{step > 1 && <button type="button" className="leave-secondary-button" onClick={() => { setError(''); setStep((current) => current - 1); }}>Back</button>}{step < 3 ? <button type="button" className="leave-primary-button" onClick={next}>Next</button> : <><button type="button" className="leave-secondary-button" onClick={saveDraft}>Save as draft</button><button type="submit" className="leave-primary-button" disabled={saving}>{saving ? 'Submitting…' : 'Submit leave request'}</button></>}</div>
      </form>
    </div></div>
  );
}
