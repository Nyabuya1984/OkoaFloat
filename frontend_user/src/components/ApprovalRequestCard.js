import React from 'react';

export default function ApprovalRequestCard({
  request,
  leaveType,
  formatDate,
  workflowLabel,
  workflowStatusClass,
  handoverReady,
  canVerify,
  waitingForDelegate,
  waitingForManager,
  onView,
  onDecide,
  onChase,
  onVerify,
}) {
  const gate = request.handover_gate || {};
  const gateText = gate.required
    ? `${gate.assigned ? '✓' : '⚠'} person assigned${request.handover_name ? ` (${request.handover_name})` : ''} · ${gate.accepted ? '✓ accepted' : '⚠ acceptance pending'} · ${gate.report_required ? (gate.report_submitted ? '✓ report submitted' : '⚠ report pending') : 'report not required'}`
    : 'Not required';

  return (
    <article className="approval-request-card">
      <div className="approval-request-heading">
        <div>
          <h3>{request.requester_name} <span>· {leaveType}</span></h3>
          <p>{formatDate(request.start_date)} - {formatDate(request.end_date)} · {request.days_requested} days</p>
        </div>
        <span className={workflowStatusClass(request)}>{workflowLabel(request)}</span>
      </div>
      <div className="approval-request-gate">
        <strong>Handover</strong>
        <span>{gateText}</span>
      </div>
      <div className="approval-request-actions">
        <button type="button" className="leave-secondary-button action-view" onClick={() => onView(request, 'request')}>View leave details</button>
        <button type="button" className="leave-secondary-button action-view" onClick={() => onView(request, 'handover')}>View Handover report</button>
        {!handoverReady && request.workflow_state === 'handover_pending' && <button type="button" className="leave-secondary-button action-navigation" onClick={() => onChase(request)}>Chase Delegate</button>}
        {canVerify && <button type="button" className="leave-primary-button" onClick={() => onVerify(request)}>Verify &amp; Complete</button>}
        {!canVerify && !waitingForDelegate && !waitingForManager && <>
          <button type="button" className="leave-primary-button" disabled={!handoverReady} title={handoverReady ? 'Approve leave request' : 'Approval is locked until handover is accepted and any required report is submitted'} onClick={() => onDecide(request, 'approve')}>Approve</button>
          <button type="button" className="leave-secondary-button action-defer" onClick={() => onDecide(request, 'defer')}>Defer</button>
          <button type="button" className="leave-danger-button" onClick={() => onDecide(request, 'reject')}>Reject</button>
        </>}
        {(waitingForDelegate || waitingForManager) && <span className="approval-waiting">{waitingForDelegate ? 'Waiting for delegate' : 'Waiting for manager'}</span>}
        <button type="button" className="leave-text-button" onClick={() => onView(request, 'more')}>More</button>
      </div>
    </article>
  );
}
