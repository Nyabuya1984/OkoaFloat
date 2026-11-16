import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import HandoverAttachment from './HandoverAttachment';
import { getAuthToken } from '../services/authStorage';

const emptyTask = () => ({
  task_name: '',
  description: '',
  status: 'not_started',
  percent_complete: 0,
  next_action: '',
  deadline: '',
  priority: 'medium',
  stakeholder: '',
  location: '',
});

export const emptyReport = () => ({
  summary: '',
  tasks: [emptyTask()],
  recurring: [],
  escalations: [],
  access: [],
  risks: [],
  attachments: [],
});

const apiUrl = (requestId) => `/api/leave/requests/${requestId}/handover`;

function Field({ label, value, onChange, type = 'text', required = false, readOnly = false }) {
  return (
    <label className="handover-field">
      <span>{label}{required ? ' *' : ''}</span>
      <input type={type} value={value || ''} required={required} readOnly={readOnly} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

const wordCount = (value = '') => value.trim() ? value.trim().split(/\s+/).length : 0;

function Section({ title, children }) {
  return (
    <section className="handover-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export default function HandoverReportForm({ requestId, readOnly = false, onSubmitted, preSubmit = false, initialReport, onChange, onClose }) {
  const [report, setReport] = useState(() => initialReport || emptyReport());
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState('Loading report...');
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const saveTimer = useRef(null);
  const draftKey = useMemo(() => `okoa-handover-draft-${requestId}`, [requestId]);
  const contentReadOnly = readOnly || (submitted && !preSubmit);

  useEffect(() => {
    if (preSubmit) {
      setMessage('Complete and submit the report before submitting this leave request.');
      return undefined;
    }
    let cancelled = false;
    const draft = window.sessionStorage.getItem(draftKey);
    if (draft) {
      try {
        setReport(JSON.parse(draft));
        setMessage('Draft restored locally.');
      } catch {
        window.sessionStorage.removeItem(draftKey);
      }
    }

    fetch(apiUrl(requestId), {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error?.message || 'Unable to load report.');
        if (!cancelled && payload.data) {
          setReport(payload.data);
          setSubmitted(Boolean(payload.data.submitted_at));
          window.sessionStorage.setItem(draftKey, JSON.stringify(payload.data));
          setMessage('Report loaded.');
        } else if (!cancelled) {
          setMessage('Start your handover report below.');
        }
      })
      .catch((error) => {
        if (!cancelled) setMessage(error.message);
      });

    return () => { cancelled = true; };
  }, [draftKey, preSubmit, requestId]);

  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  const updateReport = (nextReport) => {
    setReport(nextReport);
    if (preSubmit) {
      setSubmitted(false);
      setErrors({});
      setMessage('Changes made. Submit the report again before continuing.');
      if (onChange) onChange(nextReport);
      return;
    }
    window.sessionStorage.setItem(draftKey, JSON.stringify(nextReport));
    if (contentReadOnly) return;
    setSubmitted(false);
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => saveDraft(nextReport), 800);
  };

  const saveDraft = async (nextReport) => {
    setSaving(true);
    try {
      const response = await fetch(apiUrl(requestId), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getAuthToken()}`,
        },
        body: JSON.stringify(nextReport),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Autosave failed.');
      setMessage('Customer Record added successfully.');
      setSavedNotice(true);
      window.setTimeout(() => setSavedNotice(false), 1500);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  };

  const submit = async (event) => {
    if (event?.preventDefault) event.preventDefault();
    setSubmitting(true);
    setErrors({});
    if (preSubmit) {
      const validationErrors = {};
      if (report.summary.trim().length < 50 || report.summary.trim().length > 500) {
        validationErrors.summary = 'Summary must be between 50 and 500 characters';
      }
      if (!report.tasks.length) validationErrors.tasks = 'Add at least one active task.';
      report.tasks.forEach((task, index) => {
        if (!task.task_name.trim()) validationErrors[`tasks.${index}.task_name`] = 'Task name is required.';
        if (!task.next_action.trim()) validationErrors[`tasks.${index}.next_action`] = 'Next action is required.';
        if (!task.deadline) validationErrors[`tasks.${index}.deadline`] = 'Deadline is required.';
      });
      if (Object.keys(validationErrors).length) {
        setErrors(validationErrors);
        setSubmitting(false);
        return;
      }
      if (onChange) onChange(report);
      setMessage('Report complete. You can now submit your leave request.');
      setSubmitted(true);
      if (onSubmitted) onSubmitted(report);
      setSubmitting(false);
      return;
    }
    try {
      const response = await fetch(`${apiUrl(requestId)}/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getAuthToken()}`,
        },
        body: JSON.stringify(report),
      });
      const payload = await response.json();
      if (!response.ok) {
        setErrors(payload.error?.fields || { _: payload.error?.message || 'Unable to submit report.' });
        return;
      }
      window.sessionStorage.removeItem(draftKey);
      setReport(payload.data || report);
      setMessage('Handover report submitted.');
      setSubmitted(true);
      if (onSubmitted) onSubmitted(payload.data);
    } catch (error) {
      setErrors({ _: error.message });
    } finally {
      setSubmitting(false);
    }
  };

  const updateTask = (index, field, value) => {
    const tasks = report.tasks.map((task, taskIndex) => (
      taskIndex === index ? { ...task, [field]: value } : task
    ));
    updateReport({ ...report, tasks });
  };

  const ReportContainer = preSubmit ? 'div' : 'form';

  return (
    <ReportContainer className="handover-report-form" onSubmit={preSubmit ? undefined : submit}>
      {savedNotice && <div className="save-success-modal" role="status" aria-live="polite"><span aria-hidden="true">✓</span><strong>Customer Record added successfully</strong></div>}
      {submitted && <div className="handover-success" role="status"><span className="handover-success-icon" aria-hidden="true">✓</span><div><strong>Report submitted successfully</strong><p>Your work handover report has been sent for review.</p></div></div>}
      <div className="handover-report-header">
        <div>
          <h2>Work handover report</h2>
          <p className={`handover-status ${message.toLowerCase().includes('failed') || message.toLowerCase().includes('unable') ? 'is-error' : ''} ${message.toLowerCase().includes('submitted') || message.toLowerCase().includes('complete') ? 'is-success' : ''}`}>{message}</p>
        </div>
        <div className="handover-report-actions">
          {!readOnly && (!submitted || preSubmit) && <button type={preSubmit ? 'button' : 'submit'} onClick={preSubmit ? submit : undefined} disabled={submitting || saving}>{submitting ? 'Submitting…' : submitted ? 'Update report' : 'Submit report'}</button>}
          {onClose && <button type="button" className="leave-close" aria-label="Close handover report" onClick={onClose}>×</button>}
        </div>
      </div>
      {errors._ && <div role="alert" className="handover-error">{errors._}</div>}

      <Section title="1. Handover summary">
        <label className="handover-field">
          <span>Summary ({report.summary.length}/500 characters, {wordCount(report.summary)} words) *</span>
          <textarea
            value={report.summary}
            minLength={50}
            maxLength={500}
            readOnly={contentReadOnly}
            onChange={(event) => updateReport({ ...report, summary: event.target.value })}
          />
        </label>
        {errors.summary && <small className="handover-error">{errors.summary}</small>}
      </Section>

      <Section title="2. Active tasks">
        {report.tasks.map((task, index) => (
          <div className="handover-row" key={`task-${index}`}>
            <Field label="Task" value={task.task_name} required readOnly={contentReadOnly} onChange={(value) => updateTask(index, 'task_name', value)} />
            <Field label="Next action" value={task.next_action} required readOnly={contentReadOnly} onChange={(value) => updateTask(index, 'next_action', value)} />
            <Field label="Deadline" type="date" value={task.deadline} required readOnly={contentReadOnly} onChange={(value) => updateTask(index, 'deadline', value)} />
            <label className="handover-field"><span>Priority</span><select value={task.priority} disabled={contentReadOnly} onChange={(event) => updateTask(index, 'priority', event.target.value)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            {!contentReadOnly && report.tasks.length > 1 && (
              <button className="handover-remove-task" type="button" aria-label={`Remove active task ${index + 1}`} title="Remove active task" onClick={() => updateReport({ ...report, tasks: report.tasks.filter((_, taskIndex) => taskIndex !== index) })}><X size={16} aria-hidden="true" /></button>
            )}
            {errors[`tasks.${index}.next_action`] && <small className="handover-error">{errors[`tasks.${index}.next_action`]}</small>}
          </div>
        ))}
        {!contentReadOnly && <button type="button" onClick={() => updateReport({ ...report, tasks: [...report.tasks, emptyTask()] })}>Add active task</button>}
      </Section>

      <Section title="3. Recurring responsibilities">
        {report.recurring.map((item, index) => (
          <div className="handover-row" key={`recurring-${index}`}>
            <Field label="Task" value={item.task} readOnly={contentReadOnly} onChange={(value) => {
              const recurring = report.recurring.map((entry, entryIndex) => entryIndex === index ? { ...entry, task: value } : entry);
              updateReport({ ...report, recurring });
            }} />
            <Field label="Cadence" value={item.cadence} readOnly={contentReadOnly} onChange={(value) => {
              const recurring = report.recurring.map((entry, entryIndex) => entryIndex === index ? { ...entry, cadence: value } : entry);
              updateReport({ ...report, recurring });
            }} />
            {!contentReadOnly && <button type="button" onClick={() => updateReport({ ...report, recurring: report.recurring.filter((_, itemIndex) => itemIndex !== index) })}>Remove</button>}
          </div>
        ))}
        {!contentReadOnly && <button type="button" onClick={() => updateReport({ ...report, recurring: [...report.recurring, { task: '', cadence: 'weekly', where_link: '', definition_of_done: '' }] })}>Add recurring responsibility</button>}
      </Section>

      <Section title="4. Escalations, access and risks">
        <p>Record operational contacts and escalation instructions. Never enter passwords, PINs, secrets, or API keys.</p>
        <Field label="Escalation contact email" value={report.escalations[0]?.contact_email} readOnly={contentReadOnly} onChange={(value) => updateReport({ ...report, escalations: [{ ...(report.escalations[0] || {}), contact_email: value }] })} />
        <label className="handover-field"><span>System access instructions</span><textarea value={report.access[0]?.how_to_request || ''} readOnly={contentReadOnly} onChange={(event) => updateReport({ ...report, access: [{ ...(report.access[0] || {}), how_to_request: event.target.value }] })} /></label>
        <label className="handover-field"><span>Primary risk</span><textarea value={report.risks[0]?.risk || ''} readOnly={contentReadOnly} onChange={(event) => updateReport({ ...report, risks: [{ ...(report.risks[0] || {}), risk: event.target.value }] })} /></label>
      </Section>

      {!preSubmit && <Section title="5. Supporting attachment">
        {
          <HandoverAttachment
            requestId={requestId}
            attachments={report.attachments || []}
            readOnly={readOnly}
            onBeforeUpload={() => (submitted ? Promise.resolve() : saveDraft(report))}
            onChange={(attachments) => updateReport({ ...report, attachments })}
          />
        }
      </Section>}

    </ReportContainer>
  );
}
