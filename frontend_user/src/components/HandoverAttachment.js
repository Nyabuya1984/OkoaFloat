import React, { useRef, useState } from 'react';
import { getAuthToken } from '../services/authStorage';

const ACCEPTED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];
const MAX_SIZE = 10 * 1024 * 1024;

export default function HandoverAttachment({ requestId, attachments = [], readOnly = false, onChange, onBeforeUpload }) {
  const inputRef = useRef(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const token = getAuthToken();

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setMessage('Only PDF and DOCX files are allowed.');
      return;
    }
    if (file.size > MAX_SIZE) {
      setMessage('The attachment must be 10 MB or smaller.');
      return;
    }

    setBusy(true);
    setMessage('');
    const formData = new FormData();
    formData.append('file', file);
    try {
      if (onBeforeUpload) await onBeforeUpload();
      const response = await fetch(`/api/leave/requests/${requestId}/handover/attachment`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Upload failed.');
      onChange([...attachments, payload.data]);
      setMessage('Attachment uploaded.');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (attachmentId) => {
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch(
        `/api/leave/requests/${requestId}/handover/attachment/${attachmentId}`,
        { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to remove attachment.');
      onChange(attachments.filter((attachment) => attachment.id !== attachmentId));
      setMessage('Attachment removed.');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const download = async (attachment) => {
    try {
      const response = await fetch(`/api/leave/requests/${requestId}/handover/attachment/${attachment.id}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error('Unable to download attachment.');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = attachment.file_url.split('/').pop();
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) { setMessage(error.message); }
  };

  return (
    <div className="handover-attachments">
      <div className="handover-attachment-heading">
        <strong>Supporting document</strong>
        {!readOnly && (
          <>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              hidden
              onChange={upload}
            />
            <button type="button" disabled={busy} onClick={() => inputRef.current?.click()}>
              {busy ? 'Working…' : 'Upload PDF/DOCX'}
            </button>
          </>
        )}
      </div>
      {attachments.length === 0 ? (
        <p>No attachment uploaded.</p>
      ) : (
        <ul>
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              <button type="button" className="leave-text-button" onClick={() => download(attachment)}>
                {attachment.file_url.split('/').pop()}
              </button>
              <span>{Math.ceil(attachment.size_bytes / 1024)} KB</span>
              {!readOnly && (
                <button type="button" disabled={busy} onClick={() => remove(attachment.id)}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  );
}
