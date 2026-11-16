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
  onChat,
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
          <p>{request.department_name || 'Unassigned'} · {formatDate(request.start_date)} - {formatDate(request.end_date)} · {request.days_requested} days</p>
        </div>
        <span className={workflowStatusClass(request)}>{workflowLabel(request)}</span>
      </div>
      <div className="approval-request-gate">
        <strong>Handover</strong>
        <span>{gateText}</span>
      </div>
      {request.approval_steps?.length > 0 && (
        <div className="approval-request-signoffs">
          <strong>Approval history</strong>
          {request.approval_steps.map((step) => (
            <p key={`${step.stage_role}-${step.decided_at}`}>
              <strong>{step.stage_role.replaceAll('_', ' ')}</strong>
              {' · '}{step.actor_name || 'Former approver'}
              {' · '}{step.decision}
              {step.signature ? ` · ${step.signature}` : ''}
              {step.decided_at ? ` · ${step.decided_at.slice(0, 10)}` : ''}
              {step.decision_comment ? ` · ${step.decision_comment}` : ''}
            </p>
          ))}
        </div>
      )}
      {(request.employee_signature || request.handover_signature || request.supervisor_signature || request.hr_manager) && (
        <div className="approval-request-signoffs">
          {request.employee_signature && <p><strong>Employee signature</strong> {request.employee_signature} · {request.declaration_date || 'Date not recorded'}</p>}
          {request.handover_signature && <p><strong>Delegate</strong> {request.handover_name} · {request.handover_signature} · {request.handover_signature_date}</p>}
          {request.supervisor_signature && <p><strong>Immediate supervisor</strong> {request.supervisor_name} · {request.supervisor_signature} · {request.supervisor_decision_date?.slice(0, 10)}</p>}
          {request.hr_manager && <p><strong>HR Manager</strong> {request.hr_manager} · {request.hr_verification_date?.slice(0, 10)}</p>}
        </div>
      )}
      {request.hr_leave_summary?.length > 0 && (
        <div className="approval-hr-summary">
          <h4>HR official use only</h4>
          <div className="leave-table-wrap">
            <table className="leave-table">
              <thead><tr><th>Leave type</th><th>Entitlement</th><th>Requested</th><th>Leave taken</th><th>Leave balance</th></tr></thead>
              <tbody>{request.hr_leave_summary.map((balance) => (
                <tr key={balance.code}>
                  <td>{balance.name}</td>
                  <td>{balance.entitlement}</td>
                  <td>{balance.requested}</td>
                  <td>{balance.taken}</td>
                  <td>{balance.balance}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
      <div className="approval-request-actions">
        <button type="button" className="leave-secondary-button action-view" onClick={() => onView(request, 'request')}>View leave details</button>
        <button type="button" className="leave-secondary-button action-view" onClick={() => onView(request, 'handover')}>View Handover report</button>
        <button type="button" className="leave-secondary-button action-view" onClick={() => onChat(request)}>Chat employee</button>
        {!handoverReady && request.workflow_state === 'handover_pending' && <button type="button" className="leave-secondary-button action-navigation" onClick={() => onChase(request)}>Chase Delegate</button>}
        {canVerify && <button type="button" className="leave-primary-button" onClick={() => onVerify(request.id)}>Verify &amp; Complete</button>}
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
