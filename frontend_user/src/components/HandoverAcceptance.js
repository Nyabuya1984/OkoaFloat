import React, { useState } from 'react';
import { acceptHandover, declineHandover } from '../services/leaveApi';

const ACKNOWLEDGMENT_TEXT =
  'I have been hereby briefed on work to be undertaken and hereby agree to take responsibility of work to be executed.';

export default function HandoverAcceptance({ requestId, onComplete }) {
  const [fullName, setFullName] = useState('');
  const [signature, setSignature] = useState('');
  const [signatureDate, setSignatureDate] = useState(new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const accept = async () => {
    if (!fullName.trim() || !signature.trim() || !signatureDate) {
      setError('Enter your full name, signature, and date.');
      return;
    }
    if (fullName.trim() !== signature.trim()) {
      setError('Your signature must match your full name.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await acceptHandover(requestId, ACKNOWLEDGMENT_TEXT, fullName.trim(), signature.trim(), signatureDate);
      onComplete();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const decline = async () => {
    if (!reason.trim()) {
      setError('A reason is required when declining.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await declineHandover(requestId, reason.trim());
      onComplete();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="handover-acceptance" aria-label="Delegate acknowledgment">
      <p className="handover-acceptance-title">Delegate acknowledgment</p>
      <p>{ACKNOWLEDGMENT_TEXT}</p>
      <label>
        Full Names
        <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
      </label>
      <label>
        Signature
        <input value={signature} onChange={(event) => setSignature(event.target.value)} required />
      </label>
      <label>
        Date
        <input type="date" max={new Date().toISOString().slice(0, 10)} value={signatureDate} onChange={(event) => setSignatureDate(event.target.value)} />
      </label>
      <div className="handover-acceptance-actions">
        <button type="button" disabled={busy} onClick={accept}>Accept handover</button>
        <input
          aria-label="Reason for declining handover"
          placeholder="Reason if declining"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <button type="button" disabled={busy} onClick={decline}>Decline</button>
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
