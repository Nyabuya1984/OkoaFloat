"""Server-side leave workflow transitions and handover gates."""

from datetime import datetime

from app.extensions import db
from app.models import AuditLog, HandoverReport

WORKFLOW_STATES = {
    "draft",
    "submitted",
    "handover_pending",
    "supervisor_pending",
    "hr_verification",
    "approved",
    "deferred",
    "rejected",
    "completed",
}

TRANSITIONS = {
    "draft": {"submit": "submitted"},
    "submitted": {"require_handover": "handover_pending", "send_to_supervisor": "supervisor_pending", "approve": "hr_verification", "defer": "deferred", "reject": "rejected"},
    "handover_pending": {"handover_complete": "supervisor_pending", "defer": "deferred", "reject": "rejected"},
    "supervisor_pending": {"approve": "hr_verification", "defer": "deferred", "reject": "rejected"},
    "hr_verification": {"verify": "completed", "defer": "deferred", "reject": "rejected"},
    "deferred": {"resubmit": "supervisor_pending"},
    "approved": {"verify": "completed"},
    "rejected": {},
    "completed": {},
}


def handover_gate(request):
    days = float(request.days_requested or 0)
    report = HandoverReport.query.filter_by(leave_request_id=request.id).first()
    return {
        "required": days > 2,
        "assigned": bool(request.handover_user_id),
        "accepted": bool(request.handover_agreed_at and request.handover_statement and not request.handover_statement.startswith("DECLINED:")),
        "report_submitted": bool(request.handover_report or (report and report.submitted_at)),
        "report_required": days > 3,
    }


def require_handover_gate(request):
    gate = handover_gate(request)
    missing = []
    if gate["required"] and not gate["assigned"]:
        missing.append("handover person")
    if gate["required"] and not gate["accepted"]:
        missing.append("handover acceptance")
    if gate["report_required"] and not gate["report_submitted"]:
        missing.append("full handover report")
    return missing


def transition(request, action, actor, metadata=None):
    current = request.workflow_state or "submitted"
    next_state = TRANSITIONS.get(current, {}).get(action)
    if not next_state:
        raise ValueError(f"Invalid workflow transition: {current} -> {action}")
    if action == "approve":
        missing = require_handover_gate(request)
        if missing:
            raise ValueError(f"Handover incomplete: {', '.join(missing)}")
    before = current
    request.workflow_state = next_state
    db.session.add(AuditLog(
        actor_id=actor.id if actor else None,
        action=f"leave_workflow_{action}",
        entity="LeaveRequest",
        entity_id=str(request.id),
        event_metadata={"before": before, "after": next_state, **(metadata or {})},
    ))
    return next_state


def decision_metadata(actor, payload):
    return {
        "actor_name": actor.full_name,
        "signature": (payload.get("signature") or actor.full_name).strip(),
        "decision_date": datetime.utcnow().isoformat(),
        "reason": (payload.get("reason") or payload.get("decision_comment") or "").strip(),
    }