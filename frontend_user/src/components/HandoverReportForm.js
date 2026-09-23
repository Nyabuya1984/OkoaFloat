import React, { useEffect, useMemo, useRef, useState } from 'react';
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

const emptyReport = () => ({
  summary: '',
  tasks: [emptyTask()],
  recurring: [],
  escalations: [],
  access: [],
  risks: [],
  attachments: [],
});

const apiUrl = (requestId) => `/api/leave/requests/${requestId}/handover`;

function Field({ label, value, onChange, type = 'text', required = false }) {
  return (
    <label className="handover-field">
      <span>{label}{required ? ' *' : ''}</span>
      <input type={type} value={value || ''} onChange={(event) => onChange(event.target.value)} />
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

export default function HandoverReportForm({ requestId, readOnly = false, onSubmitted }) {
  const [report, setReport] = useState(emptyReport);
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState('Loading report...');
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const saveTimer = useRef(null);
  const draftKey = useMemo(() => `okoa-handover-draft-${requestId}`, [requestId]);

  useEffect(() => {
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
  }, [draftKey, requestId]);

  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  const updateReport = (nextReport) => {
    setReport(nextReport);
    window.sessionStorage.setItem(draftKey, JSON.stringify(nextReport));
    if (readOnly) return;
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
    event.preventDefault();
    setSubmitting(true);
    setErrors({});
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

  return (
    <form className="handover-report-form" onSubmit={submit}>
      {savedNotice && <div className="save-success-modal" role="status" aria-live="polite"><span aria-hidden="true">✓</span><strong>Customer Record added successfully</strong></div>}
      {submitted && <div className="handover-success" role="status"><span className="handover-success-icon" aria-hidden="true">✓</span><div><strong>Report submitted successfully</strong><p>Your work handover report has been sent for review.</p></div></div>}
      <div className="handover-report-header">
        <div>
          <h2>Work handover report</h2>
          <p className={`handover-status ${message.toLowerCase().includes('failed') || message.toLowerCase().includes('unable') ? 'is-error' : ''} ${message.toLowerCase().includes('submitted') ? 'is-success' : ''}`}>{message}</p>
        </div>
        {!readOnly && <button type="submit" disabled={submitting || saving}>{submitting ? 'Submitting…' : 'Submit report'}</button>}
      </div>
      {errors._ && <div role="alert" className="handover-error">{errors._}</div>}

      <Section title="1. Handover summary">
        <label className="handover-field">
          <span>Summary ({report.summary.length}/500 characters, {wordCount(report.summary)} words) *</span>
          <textarea
            value={report.summary}
            minLength={50}
            maxLength={500}
            readOnly={readOnly}
            onChange={(event) => updateReport({ ...report, summary: event.target.value })}
          />
        </label>
        {errors.summary && <small className="handover-error">{errors.summary}</small>}
      </Section>

      <Section title="2. Active tasks">
        {report.tasks.map((task, index) => (
          <div className="handover-row" key={`task-${index}`}>
            <Field label="Task" value={task.task_name} required onChange={(value) => updateTask(index, 'task_name', value)} />
            <Field label="Next action" value={task.next_action} required onChange={(value) => updateTask(index, 'next_action', value)} />
            <Field label="Deadline" type="date" value={task.deadline} required onChange={(value) => updateTask(index, 'deadline', value)} />
            <label className="handover-field"><span>Priority</span><select value={task.priority} disabled={readOnly} onChange={(event) => updateTask(index, 'priority', event.target.value)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            {!readOnly && report.tasks.length > 1 && (
              <button type="button" onClick={() => updateReport({ ...report, tasks: report.tasks.filter((_, taskIndex) => taskIndex !== index) })}>Remove</button>
            )}
            {errors[`tasks.${index}.next_action`] && <small className="handover-error">{errors[`tasks.${index}.next_action`]}</small>}
          </div>
        ))}
        {!readOnly && <button type="button" onClick={() => updateReport({ ...report, tasks: [...report.tasks, emptyTask()] })}>Add task</button>}
      </Section>

      <Section title="3. Recurring responsibilities">
        {report.recurring.map((item, index) => (
          <div className="handover-row" key={`recurring-${index}`}>
            <Field label="Task" value={item.task} onChange={(value) => {
              const recurring = report.recurring.map((entry, entryIndex) => entryIndex === index ? { ...entry, task: value } : entry);
              updateReport({ ...report, recurring });
            }} />
            <Field label="Cadence" value={item.cadence} onChange={(value) => {
              const recurring = report.recurring.map((entry, entryIndex) => entryIndex === index ? { ...entry, cadence: value } : entry);
              updateReport({ ...report, recurring });
            }} />
            {!readOnly && <button type="button" onClick={() => updateReport({ ...report, recurring: report.recurring.filter((_, itemIndex) => itemIndex !== index) })}>Remove</button>}
          </div>
        ))}
        {!readOnly && <button type="button" onClick={() => updateReport({ ...report, recurring: [...report.recurring, { task: '', cadence: 'weekly', where_link: '', definition_of_done: '' }] })}>Add recurring responsibility</button>}
      </Section>

      <Section title="4. Escalations, access and risks">
        <p>Record operational contacts and escalation instructions. Never enter passwords, PINs, secrets, or API keys.</p>
        <Field label="Escalation contact email" value={report.escalations[0]?.contact_email} onChange={(value) => updateReport({ ...report, escalations: [{ ...(report.escalations[0] || {}), contact_email: value }] })} />
        <label className="handover-field"><span>System access instructions</span><textarea value={report.access[0]?.how_to_request || ''} readOnly={readOnly} onChange={(event) => updateReport({ ...report, access: [{ ...(report.access[0] || {}), how_to_request: event.target.value }] })} /></label>
        <label className="handover-field"><span>Primary risk</span><textarea value={report.risks[0]?.risk || ''} readOnly={readOnly} onChange={(event) => updateReport({ ...report, risks: [{ ...(report.risks[0] || {}), risk: event.target.value }] })} /></label>
      </Section>

      <Section title="5. Supporting attachment">
        <HandoverAttachment
          requestId={requestId}
          attachments={report.attachments || []}
          readOnly={readOnly}
          onBeforeUpload={() => saveDraft(report)}
          onChange={(attachments) => updateReport({ ...report, attachments })}
        />
      </Section>

    </form>
  );
}
