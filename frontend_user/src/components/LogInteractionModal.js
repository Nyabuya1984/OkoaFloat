import React, { useState } from 'react';
import { useForm } from 'react-hook-form';

const interactionTypes = [
  ['phone_off', 'Phone off / client unreachable'],
  ['no_answer', 'Phone ringing / nobody answered'],
  ['negotiation', 'Negotiation'],
  ['wrong_number', 'Wrong Number'],
  ['promise_to_pay', 'Promise to Pay'],
  ['callback_requested', 'Client requested a callback'],
  ['full_payment', 'Full Payment'],
  ['partial_payment', 'Partial Payment'],
];

const formatMoney = (value) => new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 2,
}).format(Number(value) || 0);

export default function LogInteractionModal({ loan, onClose, onSave }) {
  const [submitError, setSubmitError] = useState('');
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm({
    defaultValues: { outcome: '', follow_up_at: '', amount_paid: '', promised_amount: '', notes: '' },
  });
  const outcome = watch('outcome');
  const amountPaid = Number(watch('amount_paid') || 0);
  const remainingBalance = Math.max(0, Number(loan.loan_balance || 0) - amountPaid);
  const needsFollowUp = ['promise_to_pay', 'callback_requested', 'partial_payment'].includes(outcome);
  const followUpDateTime = watch('follow_up_at');
  const followUpDay = followUpDateTime
    ? new Intl.DateTimeFormat('en-KE', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(followUpDateTime))
    : '';

  const submit = async (values) => {
    setSubmitError('');
    const payload = { outcome: values.outcome, notes: values.notes.trim() };
    if (needsFollowUp) {
      const [followUpDate, followUpTime] = values.follow_up_at.split('T');
      if (outcome === 'promise_to_pay') {
        payload.promised_date = followUpDate;
        payload.promised_time = followUpTime;
        if (values.promised_amount !== '') payload.promised_amount = values.promised_amount;
      } else if (outcome === 'callback_requested') {
        payload.callback_date = followUpDate;
        payload.callback_time = followUpTime;
      } else {
        payload.promised_date = followUpDate;
        payload.promised_time = followUpTime;
        if (values.promised_amount !== '') payload.promised_amount = values.promised_amount;
      }
    }
    if (outcome === 'partial_payment') payload.amount_paid = values.amount_paid;

    try {
      await onSave(payload);
      onClose();
    } catch (error) {
      setSubmitError(error.message || 'Unable to save this interaction.');
    }
  };

  return (
    <div className="debt-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !isSubmitting) onClose();
    }}>
      <section className="debt-interaction-modal" role="dialog" aria-modal="true" aria-labelledby="log-interaction-title">
        <div className="debt-modal-heading">
          <div>
            <p className="leave-kicker">COLLECTOR WORKSPACE</p>
            <h2 id="log-interaction-title">Log interaction</h2>
            <p className="leave-muted">{loan.business_name} · {loan.agent_name}</p>
          </div>
          <button type="button" className="leave-text-button" onClick={onClose} disabled={isSubmitting} aria-label="Close interaction dialog">Close</button>
        </div>

        <div className="debt-current-balance">
          <span>Outstanding balance</span>
          <strong>{formatMoney(loan.loan_balance)}</strong>
        </div>

        {submitError && <div className="leave-alert error" role="alert">{submitError}</div>}
        <form className="debt-modal-form" onSubmit={handleSubmit(submit)} noValidate>
          <fieldset className="debt-interaction-options">
            <legend>How did the call go?</legend>
            <input type="hidden" {...register('outcome', { required: 'Choose an interaction type.' })} />
            {interactionTypes.map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`debt-interaction-option ${outcome === value ? 'selected' : ''}`}
                aria-pressed={outcome === value}
                onClick={() => setValue('outcome', value, { shouldValidate: true, shouldDirty: true, shouldTouch: true })}
              >
                <span>{label}</span>
                {outcome === value && <span className="debt-option-selected-mark" aria-hidden="true">✓</span>}
              </button>
            ))}
            {errors.outcome && <span className="debt-field-error">{errors.outcome.message}</span>}
          </fieldset>

          {needsFollowUp && (
            <>
              <label>
                {outcome === 'promise_to_pay'
                  ? 'Promised payment date and time'
                  : outcome === 'callback_requested'
                    ? 'Preferred callback date and time'
                    : 'Next payment date and time'}
              <input
                type="datetime-local"
                {...register('follow_up_at', { required: 'Choose a follow-up date and time.' })}
                aria-invalid={Boolean(errors.follow_up_at)}
              />
              {errors.follow_up_at && <span className="debt-field-error">{errors.follow_up_at.message}</span>}
              {followUpDay && <span className="debt-follow-up-preview">Scheduled for {followUpDay}</span>}
              </label>
              {outcome !== 'callback_requested' && (
                <label>
                  {outcome === 'partial_payment' ? 'Agreed next payment amount (optional)' : 'Promised payment amount (optional)'}
                  <input
                    type="number"
                    min="0"
                    max={loan.loan_balance}
                    step="0.01"
                    {...register('promised_amount', {
                      min: { value: 0, message: 'Amount cannot be negative.' },
                      max: { value: Number(loan.loan_balance), message: 'Amount cannot exceed the outstanding balance.' },
                    })}
                    aria-invalid={Boolean(errors.promised_amount)}
                  />
                  {errors.promised_amount && <span className="debt-field-error">{errors.promised_amount.message}</span>}
                </label>
              )}
            </>
          )}

          {outcome === 'partial_payment' && (
            <label>
              Payment amount
              <input
                type="number"
                min="0.01"
                max={loan.loan_balance}
                step="0.01"
                {...register('amount_paid', {
                  required: 'Enter the amount received.',
                  valueAsNumber: true,
                  min: { value: 0.01, message: 'Payment must be greater than zero.' },
                  max: { value: Number(loan.loan_balance), message: 'Payment cannot exceed the outstanding balance.' },
                })}
                aria-invalid={Boolean(errors.amount_paid)}
              />
              {errors.amount_paid && <span className="debt-field-error">{errors.amount_paid.message}</span>}
              <span className="debt-remaining-balance">Remaining balance: {formatMoney(remainingBalance)}</span>
            </label>
          )}

          {outcome === 'full_payment' && (
            <p className="debt-full-payment-note">
              Confirm receipt of {formatMoney(loan.loan_balance)}. Saving this response will clear the outstanding balance.
            </p>
          )}

          <label>
            Notes
            <textarea rows="4" {...register('notes', { maxLength: { value: 2000, message: 'Notes must be 2,000 characters or fewer.' } })} />
            {errors.notes && <span className="debt-field-error">{errors.notes.message}</span>}
          </label>

          <div className="debt-modal-actions">
            <button type="button" className="leave-secondary-button" onClick={onClose} disabled={isSubmitting}>Cancel</button>
            <button type="submit" className="leave-primary-button" disabled={isSubmitting}>{isSubmitting ? 'Saving…' : 'Save interaction'}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
