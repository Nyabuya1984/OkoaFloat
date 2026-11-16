"""Okoa Float extensions to the established customer-care API."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    CallLog,
    ConcernCategory,
    Customer,
    DebtCollectionCallLog,
    DebtCollectionLoan,
    DepartmentAssignmentHistory,
    Escalation,
    SalesDailyReport,
    ShiftDefinition,
    User,
)
from app.utils.okia_business import (
    INBOUND_CONCERNS,
    OUTBOUND_REASONS,
    compute_shift,
    generate_reference_number,
    should_escalate,
    validate_caller_fields,
)
from app.utils.rbac import can, enforce_permission


okoa_customer_care_bp = Blueprint("okoa_customer_care", __name__, url_prefix="/api")

GM_READ_ENDPOINTS = {
    "okoa_customer_care.concern_volume_report",
    "okoa_customer_care.current_shift",
    "okoa_customer_care.escalation_summary",
    "okoa_customer_care.escalation_volume_report",
    "okoa_customer_care.get_escalation",
    "okoa_customer_care.gm_agent_shift_matrix",
    "okoa_customer_care.gm_attention_report",
    "okoa_customer_care.gm_escalation_report",
    "okoa_customer_care.gm_resolution_report",
    "okoa_customer_care.gm_shift_overview",
    "okoa_customer_care.list_escalations",
    "okoa_customer_care.list_shifts",
    "okoa_customer_care.shift_coverage",
}
GM_ACTION_ENDPOINTS = {
    "okoa_customer_care.resolve_call_escalation",
    "okoa_customer_care.resolve_escalation",
}


@okoa_customer_care_bp.before_request
def enforce_okoa_customer_care_access():
    permission_error = enforce_permission("customer_care.*")
    if not permission_error:
        return permission_error

    staff = _staff()
    if not staff or not _has_active_general_manager_assignment(staff):
        return permission_error
    if request.endpoint in GM_READ_ENDPOINTS and request.method == "GET":
        return None
    if request.endpoint in GM_ACTION_ENDPOINTS and request.method == "PATCH":
        return None
    return permission_error


def _error(message, status=400):
    return jsonify({"data": None, "error": {"message": message}}), status


def _staff():
    try:
        staff_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    staff = db.session.get(User, staff_id)
    if not staff or not staff.is_currently_active() or staff.account_status != "approved":
        return None
    return staff


def _utc_datetime(value, field_name):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    else:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _date_bounds():
    start_value = request.args.get("from")
    end_value = request.args.get("to")
    try:
        start = date.fromisoformat(start_value) if start_value else None
        end = date.fromisoformat(end_value) if end_value else None
    except ValueError:
        raise ValueError("from and to must be ISO dates (YYYY-MM-DD)")
    if start and end and start > end:
        raise ValueError("from must not be after to")
    return start, end


def _filtered_calls(start=None, end=None):
    query = CallLog.query
    if start:
        query = query.filter(CallLog.call_started_at >= datetime.combine(start, time.min))
    if end:
        query = query.filter(CallLog.call_started_at < datetime.combine(end + timedelta(days=1), time.min))
    return query


def _escalation_dict(row):
    call = row.call_log
    return {
        "id": row.id,
        "call_id": row.call_id,
        "to_dept": row.to_dept,
        "reason": row.reason,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "resolved_at": _iso(row.resolved_at),
        "resolved_by": row.resolved_by,
        "reference_number": call.reference_number,
        "concern_category": call.concern_category,
        "priority": call.priority,
        "summary": call.summary,
        "handling_agent": call.staff.full_name if call.staff else None,
        "staff_id": call.staff.employee_id if call.staff else None,
        "shift_code": call.shift_code,
        "call_started_at": _iso(call.call_started_at or call.created_at),
        "customer": {
            "id": call.customer.id,
            "name": call.customer.name,
            "phone_number": call.customer.phone_number,
        },
    }


def _call_dict(call):
    return {
        "id": call.id,
        "customer_id": call.customer_id,
        "customer": {
            "id": call.customer.id,
            "name": call.customer.name,
            "phone_number": call.customer.phone_number,
            "caller_type": call.customer.caller_type,
            "location": call.customer.location,
            "agent_name": call.customer.agent_name,
            "agent_number": call.customer.agent_number,
            "store_number": call.customer.store_number,
        },
        "staff_id": call.staff_id,
        "staff_name": call.staff.full_name,
        "call_type": call.call_type,
        "category": call.category,
        "concern_category": call.concern_category,
        "outbound_reason": call.outbound_reason,
        "priority": call.priority,
        "summary": call.summary,
        "outcome": call.outcome,
        "status": call.status,
        "call_started_at": _iso(call.call_started_at),
        "created_at": _iso(call.created_at),
        "shift_code": call.shift_code,
        "reference_number": call.reference_number,
        "requires_escalation": call.requires_escalation,
        "escalated_to": call.escalated_to,
        "escalation_reason": call.escalation_reason,
        "escalated_at": _iso(call.escalated_at),
        "escalation_resolved": call.escalation_resolved,
    }


def _call_query():
    return CallLog.query.options(joinedload(CallLog.customer), joinedload(CallLog.staff))


def _record_escalation(call, department, reason):
    call.requires_escalation = True
    call.escalated_to = department
    call.escalation_reason = reason
    call.escalated_at = datetime.utcnow()
    call.escalation_resolved = False
    call.status = "Escalated"
    if not any(row.status == "open" for row in call.escalations):
        db.session.add(Escalation(call_id=call.id, to_dept=department, reason=reason))


@okoa_customer_care_bp.get("/calls")
@jwt_required()
def list_okoa_calls():
    if not _staff():
        return _error("Active staff account not found", 403)
    query = _call_query()
    shift = request.args.get("shift")
    concern = request.args.get("concern")
    if shift:
        if shift not in {"A", "B", "C"}:
            return _error("shift must be A, B, or C")
        query = query.filter(CallLog.shift_code == shift)
    if concern:
        query = query.filter(CallLog.concern_category == concern)
    escalated = request.args.get("escalated")
    if escalated is not None:
        if escalated.lower() not in {"true", "false"}:
            return _error("escalated must be true or false")
        query = query.filter(CallLog.requires_escalation.is_(escalated.lower() == "true"))
    try:
        start, end = _date_bounds()
        query = _filtered_calls(start, end).options(joinedload(CallLog.customer), joinedload(CallLog.staff))
    except ValueError as exc:
        return _error(str(exc))
    if shift:
        query = query.filter(CallLog.shift_code == shift)
    if concern:
        query = query.filter(CallLog.concern_category == concern)
    if escalated is not None:
        query = query.filter(CallLog.requires_escalation.is_(escalated.lower() == "true"))
    calls = query.order_by(CallLog.call_started_at.desc(), CallLog.id.desc()).limit(500).all()
    return jsonify({"data": [_call_dict(call) for call in calls]})


@okoa_customer_care_bp.post("/calls")
@jwt_required()
def create_okoa_call():
    staff = _staff()
    if not staff:
        return _error("Active staff account not found", 403)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required")

    call_type = str(payload.get("call_type", "")).strip().lower()
    if call_type in {"incoming", "inbound"}:
        call_type = "Incoming"
    elif call_type in {"outgoing", "outbound"}:
        call_type = "Outgoing"
    else:
        return _error("call_type must be inbound/incoming or outbound/outgoing")

    caller_type = payload.get("caller_type")
    try:
        validate_caller_fields(caller_type, payload)
    except ValueError as exc:
        return _error(str(exc))
    concern = payload.get("concern_category")
    outbound = payload.get("outbound_reason")
    if call_type == "Incoming":
        if concern not in INBOUND_CONCERNS:
            return _error("A valid concern_category is required for inbound calls")
        if outbound:
            return _error("outbound_reason is only valid for outbound calls")
    else:
        if outbound not in OUTBOUND_REASONS:
            return _error("A valid outbound_reason is required for outbound calls")
        if concern:
            return _error("concern_category is only valid for inbound calls")

    name = payload.get("customer_name")
    phone = payload.get("phone_number")
    customer_id = payload.get("customer_id")
    if customer_id is not None:
        customer = db.session.get(Customer, customer_id)
        if not customer:
            return _error("Customer not found", 404)
    else:
        if not isinstance(name, str) or not name.strip() or not isinstance(phone, str) or not phone.strip():
            return _error("customer_name and phone_number are required")
        customer = Customer.query.filter_by(phone_number=phone.strip()).first()
        if customer is None:
            customer = Customer(
                name=name.strip(),
                phone_number=phone.strip(),
                caller_type=caller_type,
                location=payload.get("location"),
                agent_name=payload.get("agent_name"),
                agent_number=payload.get("agent_number"),
                store_number=payload.get("store_number"),
                email=payload.get("email"),
                company=payload.get("company"),
            )
            db.session.add(customer)
            db.session.flush()
        elif caller_type:
            for field in ("caller_type", "location", "agent_name", "agent_number", "store_number"):
                if payload.get(field) is not None:
                    setattr(customer, field, payload[field])

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return _error("summary is required")
    try:
        started = _utc_datetime(payload.get("call_started_at", datetime.now(timezone.utc).isoformat()), "call_started_at")
    except ValueError as exc:
        return _error(str(exc))
    priority = payload.get("priority", "Normal")
    if priority not in {"Low", "Normal", "Urgent"}:
        return _error("priority must be Low, Normal, or Urgent")
    outcome = payload.get("outcome")
    if outcome is not None and not isinstance(outcome, str):
        return _error("outcome must be text")
    call = CallLog(
        customer_id=customer.id,
        staff_id=staff.id,
        call_type=call_type,
        category=concern or outbound,
        concern_category=concern,
        outbound_reason=outbound,
        priority=priority,
        summary=summary.strip(),
        status=payload.get("status", "Pending Follow-up"),
        outcome=outcome.strip() if outcome else None,
        call_started_at=started,
        shift_code=compute_shift(started.replace(tzinfo=timezone.utc)),
    )
    if call.status not in {"Resolved", "Pending Follow-up", "Escalated"}:
        return _error("status must be Resolved, Pending Follow-up, or Escalated")
    try:
        db.session.add(call)
        db.session.flush()
        call.reference_number = generate_reference_number(call.id)
        escalate, department = should_escalate(concern or outbound, priority, outcome or summary)
        if escalate:
            _record_escalation(call, department, summary.strip())
        db.session.commit()
        return jsonify({"data": _call_dict(call)}), 201
    except (IntegrityError, SQLAlchemyError):
        db.session.rollback()
        current_app.logger.exception("Okoa customer-care call creation failed")
        return _error("Unable to create call right now", 500)


def _get_call(call_id):
    return _call_query().filter(CallLog.id == call_id).first()


@okoa_customer_care_bp.patch("/calls/<int:call_id>/escalate")
@jwt_required()
def escalate_call(call_id):
    if not _staff():
        return _error("Active staff account not found", 403)
    call = _get_call(call_id)
    if not call:
        return _error("Call not found", 404)
    payload = request.get_json(silent=True) or {}
    department = payload.get("to_dept")
    reason = payload.get("reason")
    if department not in {"general_manager", "it_support", "supervisor"} or not isinstance(reason, str) or not reason.strip():
        return _error("to_dept and a non-empty reason are required")
    _record_escalation(call, department, reason.strip())
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Unable to escalate call", 500)
    return jsonify({"data": _call_dict(call)})


@okoa_customer_care_bp.patch("/calls/<int:call_id>/resolve-escalation")
@jwt_required()
def resolve_call_escalation(call_id):
    staff = _staff()
    if not staff:
        return _error("Active staff account not found", 403)
    call = _get_call(call_id)
    if not call:
        return _error("Call not found", 404)
    open_rows = Escalation.query.filter_by(call_id=call.id, status="open").all()
    if not open_rows:
        return _error("No open escalation exists", 404)
    now = datetime.utcnow()
    for row in open_rows:
        row.status = "resolved"
        row.resolved_at = now
        row.resolved_by = staff.id
    call.escalation_resolved = True
    call.status = "Resolved"
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Unable to resolve escalation", 500)
    return jsonify({"data": _call_dict(call)})


@okoa_customer_care_bp.patch("/calls/<int:call_id>/outcome")
@jwt_required()
def update_call_outcome(call_id):
    staff = _staff()
    if not staff:
        return _error("Active staff account not found", 403)
    call = _get_call(call_id)
    if not call:
        return _error("Call not found", 404)
    payload = request.get_json(silent=True)
    outcome = payload.get("outcome") if isinstance(payload, dict) else None
    if not isinstance(outcome, str) or not outcome.strip():
        return _error("outcome must be non-empty text")
    call.outcome = outcome.strip()
    if call.outcome.lower() in {"resolved", "completed"}:
        call.status = "Resolved"
        unresolved = Escalation.query.filter_by(call_id=call.id, status="open").all()
        now = datetime.utcnow()
        for row in unresolved:
            row.status = "resolved"
            row.resolved_at = now
            row.resolved_by = staff.id
        if unresolved:
            call.escalation_resolved = True
    elif call.outcome.lower() in {"unresolved", "pending"}:
        call.status = "Pending Follow-up"
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Unable to update call outcome", 500)
    return jsonify({"data": _call_dict(call)})


@okoa_customer_care_bp.get("/customers")
@jwt_required()
def list_okoa_customers():
    if not _staff():
        return _error("Active staff account not found", 403)
    query = Customer.query
    for key in ("caller_type", "store_number"):
        value = request.args.get(key)
        if value:
            query = query.filter(getattr(Customer, key) == value)
    return jsonify({"data": [{
        "id": customer.id, "name": customer.name, "phone_number": customer.phone_number,
        "caller_type": customer.caller_type, "location": customer.location,
        "agent_name": customer.agent_name, "agent_number": customer.agent_number,
        "store_number": customer.store_number,
    } for customer in query.order_by(Customer.name).limit(500).all()]})


@okoa_customer_care_bp.get("/escalations")
@jwt_required()
def list_escalations():
    if not _staff():
        return _error("Active staff account not found", 403)
    query = Escalation.query.options(
        joinedload(Escalation.call_log).joinedload(CallLog.customer)
    )
    status = request.args.get("status")
    department = request.args.get("to_dept")
    reason = request.args.get("reason")
    if status:
        query = query.filter(Escalation.status == status)
    if department:
        query = query.filter(Escalation.to_dept == department)
    if reason:
        query = query.filter(Escalation.reason.ilike(f"%{reason}%"))
    return jsonify({"data": [_escalation_dict(row) for row in query.order_by(Escalation.created_at).limit(500).all()]})


@okoa_customer_care_bp.get("/escalations/<int:escalation_id>")
@jwt_required()
def get_escalation(escalation_id):
    if not _staff():
        return _error("Active staff account not found", 403)
    row = Escalation.query.options(
        joinedload(Escalation.call_log).joinedload(CallLog.customer)
    ).filter_by(id=escalation_id).first()
    return (jsonify({"data": _escalation_dict(row)}), 200) if row else _error("Escalation not found", 404)


@okoa_customer_care_bp.patch("/escalations/<int:escalation_id>/resolve")
@jwt_required()
def resolve_escalation(escalation_id):
    staff = _staff()
    if not staff:
        return _error("Active staff account not found", 403)
    row = Escalation.query.filter_by(id=escalation_id, status="open").first()
    if not row:
        return _error("Open escalation not found", 404)
    row.status = "resolved"
    row.resolved_at = datetime.utcnow()
    row.resolved_by = staff.id
    if not Escalation.query.filter(
        Escalation.call_id == row.call_id, Escalation.status == "open", Escalation.id != row.id
    ).first():
        row.call_log.escalation_resolved = True
        row.call_log.status = "Resolved"
    db.session.commit()
    return jsonify({"data": {"id": row.id, "status": row.status, "resolved_at": _iso(row.resolved_at)}})


@okoa_customer_care_bp.get("/escalations/summary")
@jwt_required()
def escalation_summary():
    if not _staff():
        return _error("Active staff account not found", 403)
    open_rows = Escalation.query.filter_by(status="open")
    by_dept = dict(db.session.query(Escalation.to_dept, func.count(Escalation.id))
                   .filter(Escalation.status == "open").group_by(Escalation.to_dept).all())
    by_reason = dict(db.session.query(Escalation.reason, func.count(Escalation.id))
                     .filter(Escalation.status == "open").group_by(Escalation.reason).all())
    oldest = open_rows.order_by(Escalation.created_at.asc()).first()
    age = (datetime.utcnow() - oldest.created_at).total_seconds() / 60 if oldest else None
    return jsonify({"data": {"open": open_rows.count(), "by_dept": by_dept,
                             "by_reason": by_reason, "oldest_open_minutes": age}})


@okoa_customer_care_bp.get("/shifts")
@jwt_required()
def list_shifts():
    if not _staff():
        return _error("Active staff account not found", 403)
    return jsonify({"data": [{
        "code": shift.code, "start_weekday": shift.start_weekday,
        "start_time": shift.start_time.isoformat(), "end_weekday": shift.end_weekday,
        "end_time": shift.end_time.isoformat(),
    } for shift in ShiftDefinition.query.order_by(ShiftDefinition.code).all()]})


@okoa_customer_care_bp.get("/shifts/current")
@jwt_required()
def current_shift():
    if not _staff():
        return _error("Active staff account not found", 403)
    now = datetime.now(timezone.utc)
    return jsonify({"data": {"shift_code": compute_shift(now), "at": now.isoformat().replace("+00:00", "Z")}})


@okoa_customer_care_bp.get("/shifts/coverage")
@jwt_required()
def shift_coverage():
    if not _staff():
        return _error("Active staff account not found", 403)
    try:
        start, end = _date_bounds()
    except ValueError as exc:
        return _error(str(exc))
    query = _filtered_calls(start, end)
    result = []
    for code in ("A", "B", "C"):
        calls = query.filter(CallLog.shift_code == code)
        total = calls.count()
        resolved = calls.filter(CallLog.status == "Resolved").count()
        escalated = calls.filter(CallLog.requires_escalation.is_(True)).count()
        agents = [{
            "id": staff_id,
            "name": db.session.get(User, staff_id).full_name,
        } for (staff_id,) in calls.with_entities(CallLog.staff_id).distinct().all()]
        result.append({"shift": code, "total_calls": total, "resolved": resolved,
                       "escalated": escalated, "agents_on_duty": agents})
    return jsonify({"data": result})


@okoa_customer_care_bp.get("/concerns")
@jwt_required()
def concern_categories():
    if not _staff():
        return _error("Active staff account not found", 403)
    return jsonify({"data": [{
        "code": row.code, "label": row.label, "direction": row.direction,
        "is_escalation_trigger": row.is_escalation_trigger,
    } for row in ConcernCategory.query.order_by(ConcernCategory.direction, ConcernCategory.code).all()]})


def _gm_report_access():
    staff = _staff()
    if not staff:
        return None, _error("Active staff account not found", 403)
    if not can(staff, "customer_care.*") and not _has_active_general_manager_assignment(staff):
        return None, _error("Insufficient permissions", 403)
    return staff, None


def _has_active_general_manager_assignment(staff):
    return DepartmentAssignmentHistory.query.filter_by(
        user_id=staff.id,
        organizational_role="general_manager",
        ended_at=None,
    ).first() is not None


@okoa_customer_care_bp.get("/reports/gm/resolution")
@jwt_required()
def gm_resolution_report():
    _, error = _gm_report_access()
    if error:
        return error
    try:
        start, end = _date_bounds()
    except ValueError as exc:
        return _error(str(exc))
    query = _filtered_calls(start, end)
    total = query.count()
    resolved = query.filter(CallLog.status == "Resolved").count()
    by_concern = db.session.query(
        CallLog.concern_category, func.count(CallLog.id),
        func.sum(case((CallLog.status == "Resolved", 1), else_=0)),
    ).filter(CallLog.concern_category.isnot(None))
    by_shift = db.session.query(
        CallLog.shift_code, func.count(CallLog.id),
        func.sum(case((CallLog.status == "Resolved", 1), else_=0)),
    )
    if start:
        bound = datetime.combine(start, time.min)
        by_concern = by_concern.filter(CallLog.call_started_at >= bound)
        by_shift = by_shift.filter(CallLog.call_started_at >= bound)
    if end:
        bound = datetime.combine(end + timedelta(days=1), time.min)
        by_concern = by_concern.filter(CallLog.call_started_at < bound)
        by_shift = by_shift.filter(CallLog.call_started_at < bound)
    return jsonify({"data": {
        "total": total, "resolved": resolved,
        "resolution_rate": resolved / total if total else 0,
        "by_concern": [{"concern_category": category, "total": count, "resolved": done or 0}
                       for category, count, done in by_concern.group_by(CallLog.concern_category).all()],
        "by_shift": [{"shift": shift, "total": count, "resolved": done or 0}
                     for shift, count, done in by_shift.group_by(CallLog.shift_code).all()],
    }})


@okoa_customer_care_bp.get("/reports/gm/attention")
@jwt_required()
def gm_attention_report():
    _, error = _gm_report_access()
    if error:
        return error
    rows = Escalation.query.filter_by(status="open").order_by(Escalation.created_at.asc()).all()
    now = datetime.utcnow()
    grouped = {}
    for row in rows:
        entry = grouped.setdefault(row.reason, {"reason": row.reason, "count": 0, "oldest_age_minutes": 0})
        entry["count"] += 1
        entry["oldest_age_minutes"] = max(entry["oldest_age_minutes"], (now - row.created_at).total_seconds() / 60)
    return jsonify({"data": {"open_escalations": [_escalation_dict(row) for row in rows],
                             "by_reason": list(grouped.values())}})


def _assignment_at(user_id, occurred_at):
    return DepartmentAssignmentHistory.query.filter(
        DepartmentAssignmentHistory.user_id == user_id,
        DepartmentAssignmentHistory.started_at <= occurred_at,
        or_(
            DepartmentAssignmentHistory.ended_at.is_(None),
            DepartmentAssignmentHistory.ended_at >= occurred_at,
        ),
    ).order_by(DepartmentAssignmentHistory.started_at.desc()).first()


def _manager_roster(occurred_at, department_id):
    assignments = DepartmentAssignmentHistory.query.filter(
        DepartmentAssignmentHistory.organizational_role.in_(
            {"general_manager", "department_manager", "team_leader"}
        ),
        DepartmentAssignmentHistory.started_at <= occurred_at,
        or_(
            DepartmentAssignmentHistory.ended_at.is_(None),
            DepartmentAssignmentHistory.ended_at >= occurred_at,
        ),
    ).order_by(DepartmentAssignmentHistory.started_at.desc()).all()
    roster = {
        "general_manager": [],
        "department_manager": [],
        "team_leader": [],
    }
    seen = set()
    for assignment in assignments:
        role = assignment.organizational_role
        if (
            department_id is not None
            and role != "general_manager"
            and assignment.department_id != department_id
        ):
            continue
        if assignment.user_id in seen:
            continue
        user = db.session.get(User, assignment.user_id)
        if not user or not user.is_currently_active() or user.account_status != "approved":
            continue
        seen.add(user.id)
        roster[role].append(
            {
                "staff_id": user.employee_id,
                "user_id": user.id,
                "name": user.full_name,
                "department": assignment.department_name,
                "assignment_basis": "Organizational assignment active when the call was opened",
            }
        )
    return roster


@okoa_customer_care_bp.get("/reports/gm/shift-overview")
@jwt_required()
def gm_shift_overview():
    _, error = _gm_report_access()
    if error:
        return error

    configured_timezone = ZoneInfo(current_app.config.get("TIMEZONE", "Africa/Nairobi"))
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(configured_timezone)
    shift_code = compute_shift(now)
    day_start = datetime.combine(local_now.date(), time.min).replace(
        tzinfo=configured_timezone
    ).astimezone(timezone.utc).replace(tzinfo=None)
    day_end = datetime.combine(
        local_now.date() + timedelta(days=1), time.min
    ).replace(tzinfo=configured_timezone).astimezone(timezone.utc).replace(tzinfo=None)
    calls = CallLog.query.options(joinedload(CallLog.staff), joinedload(CallLog.customer)).filter(
        CallLog.shift_code == shift_code,
        CallLog.call_started_at >= day_start,
        CallLog.call_started_at < day_end,
    ).order_by(CallLog.call_started_at.asc(), CallLog.id.asc()).all()

    unique_clients = {}
    active_agents = {}
    for call in calls:
        unique_clients.setdefault(call.customer_id, call)
        if call.staff:
            active_agents[call.staff_id] = {
                "name": call.staff.full_name,
                "staff_id": call.staff.employee_id,
            }
    first_contact_resolved = sum(
        call.status == "Resolved" for call in unique_clients.values()
    )
    open_escalations = Escalation.query.options(
        joinedload(Escalation.call_log).joinedload(CallLog.customer),
        joinedload(Escalation.call_log).joinedload(CallLog.staff),
    ).join(CallLog).filter(
        Escalation.status == "open",
        CallLog.shift_code == shift_code,
        CallLog.call_started_at >= day_start,
        CallLog.call_started_at < day_end,
    ).order_by(Escalation.created_at.asc()).all()

    sales_reports = SalesDailyReport.query.filter(
        SalesDailyReport.date_visited == local_now.date()
    ).all()
    sales_metrics = {
        "new_registrations": sum(
            row.outcome == "registered"
            or (
                row.outcome == "ready_to_register"
                and (row.report_data or {}).get("registration_status") == "COMPLETE"
            )
            for row in sales_reports
        ),
        "appointments": sum(row.outcome == "appointment" for row in sales_reports),
        "pending_documents": sum(
            row.outcome == "ready_to_register"
            and (row.report_data or {}).get("registration_status") != "COMPLETE"
            for row in sales_reports
        ),
        "basis": (
            "Sales reports recorded today. A ready-to-register report counts as "
            "registered only when its required document checklist is complete."
        ),
    }
    debt_calls = DebtCollectionCallLog.query.filter(
        DebtCollectionCallLog.created_at >= day_start,
        DebtCollectionCallLog.created_at < day_end,
    ).all()
    debt_metrics = {
        "calls_made": len(debt_calls),
        "promises_to_pay": sum(row.outcome == "promise_to_pay" for row in debt_calls),
        "default_escalations": DebtCollectionLoan.query.filter(
            DebtCollectionLoan.is_deleted.is_(False),
            DebtCollectionLoan.is_archived.is_(False),
            func.lower(DebtCollectionLoan.status) == "legal",
        ).count(),
        "default_escalations_basis": (
            "Legal-status loans are shown as a proxy; no separate default-escalation "
            "event is stored."
        ),
    }

    manager_roster = _manager_roster(now.replace(tzinfo=None), None)
    hierarchy = {
        "agents": list(active_agents.values()),
        "team_leaders": manager_roster["team_leader"],
        "department_managers": manager_roster["department_manager"],
        "general_managers": manager_roster["general_manager"],
    }
    exceptions = []
    for escalation in open_escalations:
        case = escalation.call_log
        tags = ["OPEN"]
        if (case.priority or "").strip().upper() in {"URGENT", "HIGH"}:
            tags.append((case.priority or "").strip().upper())
        exceptions.append({
            "escalation_id": escalation.id,
            "reference_number": case.reference_number,
            "tags": tags,
        })

    return jsonify({"data": {
        "date": local_now.date().isoformat(),
        "shift_code": shift_code,
        "timezone": str(configured_timezone),
        "as_of": local_now.isoformat(),
        "manager": manager_roster["department_manager"],
        "team_leader": manager_roster["team_leader"],
        "clients_served": len(unique_clients),
        "first_contact_resolution": {
            "resolved_clients": first_contact_resolved,
            "clients_served": len(unique_clients),
            "rate": first_contact_resolved / len(unique_clients) if unique_clients else None,
            "basis": "First recorded call per client in this shift/date; based on logged call status.",
        },
        "pending_escalations": len(open_escalations),
        "active_agents": len(active_agents),
        "workload": {
            "calls_handled": len(calls),
            "resolved_calls": sum(call.status == "Resolved" for call in calls),
            "open_escalations": len(open_escalations),
        },
        "hierarchy": hierarchy,
        "exceptions": exceptions,
        "department_snapshots": {
            "sales_marketing": sales_metrics,
            "debt_collection": debt_metrics,
            "customer_care": {
                "calls_handled": len(calls),
                "first_contact_resolution_rate": (
                    first_contact_resolved / len(unique_clients)
                    if unique_clients else None
                ),
                "open_tickets": Escalation.query.filter_by(status="open").count(),
                "basis": (
                    "Customer Care calls are limited to the current shift and local "
                    "date; FCR uses the first recorded call for each client."
                ),
            },
        },
        "roster_note": (
            "Agents are staff with calls recorded in this shift/date. Manager roles "
            "come from active organizational assignments; they are not a shift-duty roster."
        ),
    }})


def _call_history_item(call):
    return {
        "id": call.id,
        "reference_number": call.reference_number,
        "customer_name": call.customer.name if call.customer else None,
        "date_time": _iso(call.call_started_at or call.created_at),
        "direction": call.call_type,
        "category": call.concern_category or call.category,
        "priority": call.priority,
        "status": call.status,
        "outcome": call.outcome,
        "remarks": call.summary,
        "handling_agent": call.staff.full_name if call.staff else "Unknown staff",
        "staff_id": call.staff.employee_id if call.staff else None,
        "shift_id": call.shift_code,
        "escalated": call.requires_escalation,
        "escalation_resolved": call.escalation_resolved,
    }


@okoa_customer_care_bp.get("/reports/gm/escalations/<int:escalation_id>")
@jwt_required()
def gm_escalation_report(escalation_id):
    _, error = _gm_report_access()
    if error:
        return error
    escalation = Escalation.query.options(
        joinedload(Escalation.call_log).joinedload(CallLog.customer),
        joinedload(Escalation.call_log).joinedload(CallLog.staff),
    ).filter_by(id=escalation_id).first()
    if not escalation:
        return _error("Escalation not found", 404)

    call = escalation.call_log
    if not call:
        return _error("Escalation call details are unavailable", 404)
    call_time = call.call_started_at or call.created_at
    if not call_time:
        return _error("Escalation has no call timestamp for shift reporting", 422)
    configured_timezone = ZoneInfo(current_app.config.get("TIMEZONE", "Africa/Nairobi"))
    local_call_time = call_time.replace(tzinfo=timezone.utc).astimezone(configured_timezone)
    shift_date = local_call_time.date()
    day_start = datetime.combine(shift_date, time.min).replace(
        tzinfo=configured_timezone
    ).astimezone(timezone.utc).replace(tzinfo=None)
    day_end = datetime.combine(
        shift_date + timedelta(days=1), time.min
    ).replace(tzinfo=configured_timezone).astimezone(timezone.utc).replace(tzinfo=None)
    shift_id = call.shift_code or "unknown"
    shift_definition = ShiftDefinition.query.filter_by(code=shift_id).first()
    shift_query = CallLog.query.options(joinedload(CallLog.staff)).filter(
        CallLog.shift_code == shift_id,
        CallLog.call_started_at >= day_start,
        CallLog.call_started_at < day_end,
    )
    shift_calls = shift_query.order_by(CallLog.call_started_at.asc()).all()
    agent_calls = [row for row in shift_calls if row.staff_id == call.staff_id]
    same_customer_calls = CallLog.query.options(joinedload(CallLog.staff)).filter_by(
        customer_id=call.customer_id
    ).order_by(CallLog.call_started_at.asc(), CallLog.id.asc()).all()

    agent_assignment = _assignment_at(call.staff_id, call_time)
    department_id = agent_assignment.department_id if agent_assignment else None
    department_name = agent_assignment.department_name if agent_assignment else None
    client = call.customer
    sales_matches = []
    if client and (client.agent_number or client.store_number or client.agent_name):
        identity_filters = []
        if client.agent_number:
            identity_filters.append(
                SalesDailyReport.agent_number == client.agent_number
            )
        if client.store_number:
            identity_filters.append(
                SalesDailyReport.store_number == client.store_number
            )
        if client.agent_name:
            identity_filters.append(SalesDailyReport.agent_name == client.agent_name)
        sales_matches = (
            SalesDailyReport.query.filter(or_(*identity_filters))
            .order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc())
            .limit(20)
            .all()
        )
    latest_sales_match = sales_matches[0] if sales_matches else None
    registration_documents = []
    submitted_files = []
    if latest_sales_match:
        required_fields = (
            {
                "business_permit": "Business Permit",
                "individual_kra_pin": "Individual KRA PIN",
                "six_months_commission": "6-Month Commission Statement",
                "subagent_agent_contract": "Sub-Agent Contract",
                "owner_national_id": "Owner National ID",
                "sign_contract": "Signed Contract",
            }
            if latest_sales_match.customer_type == "sub_agent"
            else {
                "certificate_of_incorporation": "Certificate of Incorporation / Registration",
                "company_kra_pin": "Company / Individual KRA PIN",
                "six_months_commission": "6-Month Commission Statement",
                "owners_directors_national_ids": "Owner / Director National IDs",
                "cr12_directors": "CR12 for Directors",
            }
        )
        documents = latest_sales_match.documents or {}
        registration_documents = [
            {"name": label, "submitted": bool(documents.get(field))}
            for field, label in required_fields.items()
        ]
        submitted_files = [
            item.get("name") or item.get("filename")
            for item in (latest_sales_match.uploaded_files or [])
            if item.get("name") or item.get("filename")
        ]
    agent_roster = {}
    for shift_call in shift_calls:
        staff_member = shift_call.staff
        if not staff_member:
            continue
        entry = agent_roster.setdefault(
            staff_member.id,
            {
                "staff_id": staff_member.employee_id,
                "user_id": staff_member.id,
                "name": staff_member.full_name,
                "calls_handled": 0,
            },
        )
        entry["calls_handled"] += 1
    on_duty = _manager_roster(call_time, department_id)
    shift_open_escalations = Escalation.query.join(CallLog).filter(
        Escalation.status == "open",
        CallLog.shift_code == shift_id,
        CallLog.call_started_at >= day_start,
        CallLog.call_started_at < day_end,
    ).count()
    shift_clients = {row.customer_id for row in shift_calls}
    department_manager = on_duty["department_manager"]
    team_leader = on_duty["team_leader"]
    general_manager = on_duty["general_manager"]
    agent_clients = {row.customer_id for row in agent_calls}
    agent_resolved = sum(row.status == "Resolved" for row in agent_calls)
    agent_escalated = sum(
        row.requires_escalation or row.status != "Resolved"
        for row in agent_calls
    )
    recommended_action = (
        "Decide whether to resolve this escalation or assign a follow-up action. "
        "No more specific approval request was recorded."
    )

    report = {
        "escalation": {
            "id": escalation.id,
            "status": escalation.status,
            "department": escalation.to_dept,
            "reason": escalation.reason,
            "priority": call.priority,
            "client": call.customer.name if call.customer else None,
            "agent_number": call.customer.agent_number if call.customer else None,
            "store_number": call.customer.store_number if call.customer else None,
            "handling_agent": call.staff.full_name if call.staff else "Unknown staff",
            "handling_agent_staff_id": call.staff.employee_id if call.staff else None,
            "department": department_name or escalation.to_dept,
            "shift_manager": department_manager[0] if department_manager else None,
            "team_leader": team_leader[0] if team_leader else None,
            "issue_summary": call.summary,
            "root_cause": escalation.reason or call.escalation_reason or call.summary,
            "impact": (
                "Open escalation requires GM intervention; no quantified business "
                "impact was recorded."
                if escalation.status == "open"
                else "No separate business-impact assessment was recorded."
            ),
            "opened_at": _iso(escalation.created_at),
            "resolved_at": _iso(escalation.resolved_at),
            "recommended_action": recommended_action,
            "exception_tags": [
                tag for tag, active in (
                    ("OPEN", escalation.status == "open"),
                    ("URGENT", (call.priority or "").strip().upper() == "URGENT"),
                    ("HIGH PRIORITY", (call.priority or "").strip().upper() == "HIGH"),
                ) if active
            ],
            "workload": {
                "calls_handled": len(shift_calls),
                "clients_served": len(shift_clients),
                "active_agents": len(agent_roster),
                "pending_escalations": shift_open_escalations,
            },
            "agent_workload": {
                "clients_served": len(agent_clients),
                "resolved": agent_resolved,
                "escalated": agent_escalated,
            },
        },
        "sections": [
            {
                "id": "client",
                "title": "Client overview & call history",
                "client": {
                    "name": call.customer.name if call.customer else None,
                    "phone_number": call.customer.phone_number if call.customer else None,
                    "agent_name": call.customer.agent_name if call.customer else None,
                    "agent_number": call.customer.agent_number if call.customer else None,
                    "store_number": call.customer.store_number if call.customer else None,
                    "category": call.customer.caller_type if call.customer else None,
                    "business_location": call.customer.location if call.customer else None,
                },
                "evidence_checklist": {
                    "client_name_recorded": bool(call.customer and call.customer.name),
                    "callback_number_recorded": bool(call.customer and call.customer.phone_number),
                    "issue_summary_recorded": bool(call.summary),
                    "attachments_tracked": False,
                    "attachments_note": "Document attachments are not tracked on Customer Care calls.",
                },
                "document_checklist": {
                    "available": bool(latest_sales_match),
                    "category": latest_sales_match.customer_type if latest_sales_match else None,
                    "registration_status": (
                        (latest_sales_match.report_data or {}).get("registration_status")
                        if latest_sales_match else None
                    ),
                    "documents": registration_documents,
                    "submitted_files": submitted_files,
                },
                "call_history": [_call_history_item(row) for row in same_customer_calls],
            },
            {
                "id": "shift",
                "title": "Shift context & roster",
                "shift": {
                    "shift_id": shift_id,
                    "date": shift_date.isoformat(),
                    "call_time": local_call_time.isoformat(),
                    "timezone": str(configured_timezone),
                    "configured_start_time": (
                        shift_definition.start_time.isoformat()
                        if shift_definition else None
                    ),
                    "configured_end_time": (
                        shift_definition.end_time.isoformat()
                        if shift_definition else None
                    ),
                },
                "on_duty_personnel": on_duty,
                "hierarchy": {
                    "handling_agent": {
                        "name": call.staff.full_name if call.staff else "Unknown staff",
                        "staff_id": call.staff.employee_id if call.staff else None,
                        "department": department_name,
                    },
                    "team_leader": team_leader,
                    "department_manager": department_manager,
                    "general_manager": general_manager,
                },
                "workload": {
                    "calls_handled": len(shift_calls),
                    "clients_served": len({row.customer_id for row in shift_calls}),
                    "active_agents": len(agent_roster),
                    "pending_escalations": shift_open_escalations,
                },
                "customer_care_agents": list(agent_roster.values()),
                "roster_note": (
                    "The system has no separate shift-duty roster. Manager roles reflect "
                    "organizational assignments active at the call time; Customer Care "
                    "agents are those with recorded calls in this shift and date."
                ),
            },
            {
                "id": "agent_activity",
                "title": "Primary agent work history & shift snapshot",
                "agent": {
                    "name": call.staff.full_name if call.staff else "Unknown staff",
                    "staff_id": call.staff.employee_id if call.staff else None,
                    "department": department_name,
                },
                "shift_activity": {
                    "clients_served": len({row.customer_id for row in agent_calls}),
                    "total_calls": len(agent_calls),
                    "resolved_on_spot": sum(
                        row.status == "Resolved" for row in agent_calls
                    ),
                    "escalated_or_pending": sum(
                        row.status != "Resolved"
                        or (row.requires_escalation and not row.escalation_resolved)
                        for row in agent_calls
                    ),
                },
                "call_log": [_call_history_item(row) for row in agent_calls],
            },
            {
                "id": "escalation",
                "title": "Escalation details",
                "reason": escalation.reason,
                "customer_care_agent_remarks": call.summary,
                "recommended_action": recommended_action,
            },
        ],
    }
    return jsonify({"data": report, "error": None})


@okoa_customer_care_bp.get("/reports/gm/agent-shift-matrix")
@jwt_required()
def gm_agent_shift_matrix():
    _, error = _gm_report_access()
    if error:
        return error
    try:
        start, end = _date_bounds()
    except ValueError as exc:
        return _error(str(exc))
    calls = _filtered_calls(start, end).options(joinedload(CallLog.customer), joinedload(CallLog.staff)).order_by(
        CallLog.call_started_at.asc()
    ).all()
    matrix = {}
    for call in calls:
        key = (call.staff_id, call.staff.full_name, call.shift_code or "unknown")
        row = matrix.setdefault(key, {"agent_id": call.staff_id, "agent_name": call.staff.full_name,
                                     "shift": call.shift_code, "count": 0, "first_call_at": None,
                                     "last_call_at": None, "customers": []})
        row["count"] += 1
        row["first_call_at"] = row["first_call_at"] or _iso(call.call_started_at)
        row["last_call_at"] = _iso(call.call_started_at)
        row["customers"].append({"customer_id": call.customer_id, "name": call.customer.name,
                                 "reference_number": call.reference_number})
    return jsonify({"data": list(matrix.values())})


@okoa_customer_care_bp.get("/reports/concerns")
@jwt_required()
def concern_volume_report():
    if not _staff():
        return _error("Active staff account not found", 403)
    try:
        start, end = _date_bounds()
    except ValueError as exc:
        return _error(str(exc))
    query = _filtered_calls(start, end)
    rows = query.with_entities(CallLog.concern_category, func.count(CallLog.id)).group_by(CallLog.concern_category).all()
    return jsonify({"data": [{"concern_category": code, "count": count} for code, count in rows]})


@okoa_customer_care_bp.get("/reports/escalations")
@jwt_required()
def escalation_volume_report():
    if not _staff():
        return _error("Active staff account not found", 403)
    rows = Escalation.query.order_by(Escalation.reason).all()
    totals = {}
    for row in rows:
        item = totals.setdefault(row.reason, {"reason": row.reason, "count": 0, "_durations": []})
        item["count"] += 1
        if row.resolved_at:
            item["_durations"].append((row.resolved_at - row.created_at).total_seconds())
    result = []
    for item in totals.values():
        durations = item.pop("_durations")
        item["average_resolution_seconds"] = sum(durations) / len(durations) if durations else None
        result.append(item)
    return jsonify({"data": result})
