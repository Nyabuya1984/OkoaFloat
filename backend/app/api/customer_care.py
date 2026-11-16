from datetime import date, datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import CallFollowUp, CallLog, Customer, User
from app.models import Escalation
from app.utils.okia_business import (
    INBOUND_CONCERNS,
    OUTBOUND_REASONS,
    compute_shift,
    generate_reference_number,
    should_escalate,
    validate_caller_fields,
)
from app.utils.rbac import enforce_permission
from app.utils.organization import get_active_assignment


customer_care_bp = Blueprint(
    "customer_care",
    __name__,
    url_prefix="/api/customer-care",
)

CALL_TYPES = {"Incoming", "Outgoing"}
PRIORITIES = {"Low", "Normal", "Urgent"}
STATUSES = {"Resolved", "Pending Follow-up", "Escalated"}
MAX_PAGE_SIZE = 100
CALLER_TYPES = {"agent", "sub_agent", "sales_rep", "potential_client"}


def _parse_call_started_at(value):
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("call_started_at must be an ISO-8601 datetime") from exc
    else:
        raise ValueError("call_started_at must be an ISO-8601 datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _record_okoa_escalation(call_log, department, reason):
    call_log.requires_escalation = True
    call_log.escalated_to = department
    call_log.escalation_reason = reason
    call_log.escalated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    call_log.escalation_resolved = False
    call_log.status = "Escalated"
    db.session.add(Escalation(
        call_id=call_log.id,
        to_dept=department,
        reason=reason,
    ))


@customer_care_bp.before_request
def enforce_customer_care_access():
    permission_error = enforce_permission("customer_care.*")
    if not permission_error:
        return None
    if request.method == "GET":
        verify_jwt_in_request()
        staff = _current_staff()
        assignment = get_active_assignment(staff.id) if staff else None
        if assignment and assignment.organizational_role == "general_manager":
            return None
    return permission_error


def _current_staff():
    try:
        staff_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    staff = db.session.get(User, staff_id)
    if not staff or not staff.is_currently_active() or staff.account_status != "approved":
        return None
    return staff


def _error(message, status=400):
    return jsonify({"data": None, "error": {"message": message}}), status


def _payload():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else None


def _page_values():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "25"))
    except (TypeError, ValueError):
        raise ValueError("page and per_page must be whole numbers")
    if page < 1 or not 1 <= per_page <= MAX_PAGE_SIZE:
        raise ValueError(f"page must be positive and per_page must be between 1 and {MAX_PAGE_SIZE}")
    return page, per_page


def _customer_dict(customer, interaction_count=None):
    result = {
        "id": customer.id,
        "name": customer.name,
        "phone_number": customer.phone_number,
        "email": customer.email,
        "company": customer.company,
        "caller_type": customer.caller_type,
        "location": customer.location,
        "agent_name": customer.agent_name,
        "agent_number": customer.agent_number,
        "store_number": customer.store_number,
        "created_at": customer.created_at.isoformat(),
    }
    if interaction_count is not None:
        result["interaction_count"] = interaction_count
    return result


def _follow_up_dict(follow_up):
    return {
        "id": follow_up.id,
        "call_log_id": follow_up.call_log_id,
        "assigned_to": follow_up.assigned_to,
        "assigned_to_name": follow_up.assignee.full_name,
        "due_date": follow_up.due_date.isoformat(),
        "notes": follow_up.notes,
        "is_completed": follow_up.is_completed,
        "created_at": follow_up.created_at.isoformat(),
    }


def _call_log_dict(call_log, include_follow_ups=False):
    result = {
        "id": call_log.id,
        "customer_id": call_log.customer_id,
        "customer": _customer_dict(call_log.customer),
        "staff_id": call_log.staff_id,
        "staff_name": call_log.staff.full_name,
        "call_type": call_log.call_type,
        "category": call_log.category,
        "priority": call_log.priority,
        "summary": call_log.summary,
        "status": call_log.status,
        "concern_category": call_log.concern_category,
        "outbound_reason": call_log.outbound_reason,
        "call_started_at": _utc_iso(call_log.call_started_at),
        "shift_code": call_log.shift_code,
        "reference_number": call_log.reference_number,
        "requires_escalation": bool(call_log.requires_escalation),
        "escalated_to": call_log.escalated_to,
        "escalation_reason": call_log.escalation_reason,
        "escalated_at": _utc_iso(call_log.escalated_at),
        "escalation_resolved": bool(call_log.escalation_resolved),
        "escalation_id": call_log.escalations[0].id if call_log.escalations else None,
        "created_at": call_log.created_at.isoformat(),
    }
    if include_follow_ups:
        result["follow_ups"] = [_follow_up_dict(item) for item in call_log.follow_ups]
    return result


def _commit_or_error():
    try:
        db.session.commit()
        return None
    except IntegrityError:
        db.session.rollback()
        return _error("This record changed while you were saving. Refresh and try again.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Customer care database operation failed")
        return _error("Unable to save the customer care record right now.", 500)


def _loaded_call_log_query(include_follow_ups=False):
    query = CallLog.query.options(
        joinedload(CallLog.customer),
        joinedload(CallLog.staff),
    )
    if include_follow_ups:
        query = query.options(
            joinedload(CallLog.follow_ups).joinedload(CallFollowUp.assignee),
        )
    return query


@customer_care_bp.get("/logs")
@jwt_required()
def list_call_logs():
    if not _current_staff():
        return _error("Active staff account not found", 403)
    try:
        page, per_page = _page_values()
    except ValueError as exc:
        return _error(str(exc))

    query = CallLog.query.join(Customer).join(User, CallLog.staff_id == User.id)
    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Customer.name.ilike(pattern), Customer.phone_number.ilike(pattern)))
    status = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()
    concern = request.args.get("concern", "").strip()
    shift = request.args.get("shift", "").strip()
    escalated = request.args.get("escalated")
    if status:
        query = query.filter(CallLog.status == status)
    if category:
        query = query.filter(CallLog.category == category)
    if concern:
        query = query.filter(CallLog.concern_category == concern)
    if shift:
        if shift not in {"A", "B", "C"}:
            return _error("shift must be A, B, or C")
        query = query.filter(CallLog.shift_code == shift)
    if escalated is not None:
        if escalated.lower() not in {"true", "false"}:
            return _error("escalated must be true or false")
        query = query.filter(CallLog.requires_escalation.is_(escalated.lower() == "true"))

    pagination = query.order_by(CallLog.created_at.desc(), CallLog.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    logs = _loaded_call_log_query().filter(
        CallLog.id.in_([item.id for item in pagination.items])
    ).order_by(CallLog.created_at.desc(), CallLog.id.desc()).all()
    return jsonify({
        "data": [_call_log_dict(item) for item in logs],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    })


@customer_care_bp.post("/logs")
@jwt_required()
def create_call_log():
    staff = _current_staff()
    if not staff:
        return _error("Active staff account not found", 403)
    payload = _payload()
    if payload is None:
        return _error("A JSON request body is required")

    name = payload.get("customer_name")
    phone_number = payload.get("phone_number")
    call_type = payload.get("call_type")
    concern_category = payload.get("concern_category")
    outbound_reason = payload.get("outbound_reason")
    caller_type = payload.get("caller_type")
    category = payload.get("category") or concern_category or outbound_reason
    # The original customer-care form only submitted `category`. Recognize
    # Okoa enum values there too, while leaving legacy free-text categories intact.
    if call_type == "Incoming" and concern_category is None and isinstance(category, str) and category in INBOUND_CONCERNS:
        concern_category = category
    elif call_type == "Outgoing" and outbound_reason is None and isinstance(category, str) and category in OUTBOUND_REASONS:
        outbound_reason = category
    priority = payload.get("priority", "Normal")
    summary = payload.get("summary")
    status = payload.get("status", "Pending Follow-up")
    if not all(isinstance(value, str) for value in (name, phone_number, call_type, category, summary, status, priority)):
        return _error("Customer name, phone number, call details, priority, and status are required")

    name = name.strip()
    phone_number = phone_number.strip()
    category = category.strip()
    summary = summary.strip()
    if not name or len(name) > 160 or not phone_number or len(phone_number) > 40:
        return _error("Enter a customer name (up to 160 characters) and phone number (up to 40 characters)")
    if not category or len(category) > 80:
        return _error("Category must contain 1 to 80 characters")
    if not summary or len(summary) > 10000:
        return _error("Call summary must contain 1 to 10000 characters")
    if call_type not in CALL_TYPES:
        return _error("Call type must be Incoming or Outgoing")
    if caller_type is not None:
        try:
            validate_caller_fields(caller_type, payload)
        except ValueError as exc:
            return _error(str(exc))
    if concern_category is not None and (
        not isinstance(concern_category, str) or concern_category not in INBOUND_CONCERNS
    ):
        return _error("concern_category must be a valid inbound concern category")
    if outbound_reason is not None and (
        not isinstance(outbound_reason, str) or outbound_reason not in OUTBOUND_REASONS
    ):
        return _error("outbound_reason must be a valid outbound reason")
    if concern_category and call_type != "Incoming":
        return _error("concern_category is only valid for Incoming calls")
    if outbound_reason and call_type != "Outgoing":
        return _error("outbound_reason is only valid for Outgoing calls")
    if caller_type and call_type == "Incoming" and not concern_category:
        return _error("concern_category is required for Okoa inbound calls")
    if caller_type and call_type == "Outgoing" and not outbound_reason:
        return _error("outbound_reason is required for Okoa outbound calls")
    if priority not in PRIORITIES:
        return _error("Priority must be Low, Normal, or Urgent")
    if status not in STATUSES:
        return _error("Status must be Resolved, Pending Follow-up, or Escalated")

    follow_up_date = payload.get("follow_up_date")
    follow_up_notes = payload.get("follow_up_notes", "")
    if follow_up_notes is not None and not isinstance(follow_up_notes, str):
        return _error("Follow-up notes must be text")
    if follow_up_notes and len(follow_up_notes) > 5000:
        return _error("Follow-up notes must not exceed 5000 characters")
    email = payload.get("email")
    company = payload.get("company")
    if email is not None and not isinstance(email, str):
        return _error("Customer email must be text")
    if company is not None and not isinstance(company, str):
        return _error("Customer company must be text")
    if (email and len(email) > 255) or (company and len(company) > 160):
        return _error("Customer email or company exceeds the supported length")
    due_date = None
    if follow_up_date:
        try:
            due_date = date.fromisoformat(follow_up_date)
        except (TypeError, ValueError):
            return _error("Follow-up date must be a valid ISO date")
    try:
        call_started_at = _parse_call_started_at(payload.get("call_started_at"))
    except ValueError as exc:
        return _error(str(exc))

    try:
        customer = Customer.query.filter_by(phone_number=phone_number).first()
        if customer is None:
            customer = Customer(
                name=name,
                phone_number=phone_number,
                email=email.strip() if email else None,
                company=company.strip() if company else None,
                caller_type=caller_type,
                location=payload.get("location"),
                agent_name=payload.get("agent_name"),
                agent_number=payload.get("agent_number"),
                store_number=payload.get("store_number"),
            )
            db.session.add(customer)
            db.session.flush()
        else:
            customer_fields = {
                "caller_type": caller_type,
                "location": payload.get("location"),
                "agent_name": payload.get("agent_name"),
                "agent_number": payload.get("agent_number"),
                "store_number": payload.get("store_number"),
            }
            for field, value in customer_fields.items():
                if value is not None:
                    setattr(customer, field, value)

        call_log = CallLog(
            customer_id=customer.id,
            staff_id=staff.id,
            call_type=call_type,
            category=category,
            priority=priority,
            summary=summary,
            status=status,
            concern_category=concern_category,
            outbound_reason=outbound_reason,
            call_started_at=call_started_at,
            shift_code=compute_shift(call_started_at.replace(tzinfo=timezone.utc)),
        )
        db.session.add(call_log)
        db.session.flush()
        call_log.reference_number = generate_reference_number(call_log.id)
        # Preserve legacy call behavior unless the caller submits Okoa category
        # metadata; new Okoa calls are automatically escalated per business rules.
        if concern_category or outbound_reason:
            escalate, department = should_escalate(
                concern_category or outbound_reason, priority, payload.get("outcome") or summary
            )
            if escalate:
                _record_okoa_escalation(call_log, department, summary)
        if due_date:
            db.session.add(CallFollowUp(
                call_log_id=call_log.id,
                assigned_to=staff.id,
                due_date=due_date,
                notes=follow_up_notes.strip() or None if follow_up_notes else summary,
            ))
        db.session.commit()
        return jsonify({"data": _call_log_dict(call_log, include_follow_ups=True)}), 201
    except IntegrityError:
        db.session.rollback()
        return _error("Unable to create the call log because the customer record changed. Please retry.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Customer care call log creation failed")
        return _error("Unable to create the call log right now.", 500)


@customer_care_bp.get("/logs/<int:log_id>")
@jwt_required()
def get_call_log(log_id):
    if not _current_staff():
        return _error("Active staff account not found", 403)
    call_log = _loaded_call_log_query(include_follow_ups=True).filter_by(id=log_id).first()
    if not call_log:
        return _error("Call log not found", 404)
    return jsonify({"data": _call_log_dict(call_log, include_follow_ups=True)})


@customer_care_bp.patch("/logs/<int:log_id>")
@jwt_required()
def update_call_log(log_id):
    staff = _current_staff()
    if not staff:
        return _error("Active staff account not found", 403)
    payload = _payload()
    if payload is None:
        return _error("A JSON request body is required")
    allowed_fields = {"summary", "category", "status"}
    if not payload or set(payload) - allowed_fields:
        return _error("Only summary, category, and status can be updated")
    call_log = _loaded_call_log_query(include_follow_ups=True).filter_by(id=log_id).first()
    if not call_log:
        return _error("Call log not found", 404)
    for field in allowed_fields.intersection(payload):
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            return _error(f"{field.replace('_', ' ').capitalize()} must be non-empty text")
        value = value.strip()
        if field == "status" and value not in STATUSES:
            return _error("Status must be Resolved, Pending Follow-up, or Escalated")
        if field == "category" and len(value) > 80:
            return _error("Category must not exceed 80 characters")
        if field == "summary" and len(value) > 10000:
            return _error("Summary must not exceed 10000 characters")
        setattr(call_log, field, value)
    if call_log.status == "Resolved" and call_log.requires_escalation:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for escalation in Escalation.query.filter_by(call_id=call_log.id, status="open").all():
            escalation.status = "resolved"
            escalation.resolved_at = now
            escalation.resolved_by = staff.id
        call_log.escalation_resolved = True
    error_response = _commit_or_error()
    if error_response:
        return error_response
    return jsonify({"data": _call_log_dict(call_log, include_follow_ups=True)})


@customer_care_bp.get("/customers")
@jwt_required()
def list_customers():
    if not _current_staff():
        return _error("Active staff account not found", 403)
    try:
        page, per_page = _page_values()
    except ValueError as exc:
        return _error(str(exc))

    query = Customer.query
    caller_type = request.args.get("caller_type", "").strip()
    store_number = request.args.get("store_number", "").strip()
    if caller_type:
        if caller_type not in CALLER_TYPES:
            return _error("caller_type must be agent, sub_agent, sales_rep, or potential_client")
        query = query.filter(Customer.caller_type == caller_type)
    if store_number:
        query = query.filter(Customer.store_number == store_number)
    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Customer.name.ilike(pattern), Customer.phone_number.ilike(pattern)))
    pagination = query.order_by(Customer.name.asc(), Customer.id.asc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    customers = pagination.items
    counts = dict(
        db.session.query(CallLog.customer_id, func.count(CallLog.id))
        .filter(CallLog.customer_id.in_([customer.id for customer in customers]))
        .group_by(CallLog.customer_id)
        .all()
    ) if customers else {}
    return jsonify({
        "data": [_customer_dict(customer, counts.get(customer.id, 0)) for customer in customers],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    })


@customer_care_bp.get("/customers/<int:customer_id>")
@jwt_required()
def get_customer(customer_id):
    if not _current_staff():
        return _error("Active staff account not found", 403)
    customer = Customer.query.filter_by(id=customer_id).first()
    if not customer:
        return _error("Customer not found", 404)
    call_logs = _loaded_call_log_query(include_follow_ups=True).filter_by(customer_id=customer.id).order_by(
        CallLog.created_at.desc(), CallLog.id.desc()
    ).all()
    return jsonify({
        "data": {
            **_customer_dict(customer, len(call_logs)),
            "call_logs": [_call_log_dict(item, include_follow_ups=True) for item in call_logs],
        }
    })


@customer_care_bp.get("/follow-ups")
@jwt_required()
def list_follow_ups():
    staff = _current_staff()
    if not staff:
        return _error("Active staff account not found", 403)
    follow_ups = CallFollowUp.query.join(CallLog).options(
        joinedload(CallFollowUp.call_log).joinedload(CallLog.customer),
        joinedload(CallFollowUp.call_log).joinedload(CallLog.staff),
        joinedload(CallFollowUp.assignee),
    ).filter(
        CallFollowUp.assigned_to == staff.id,
        CallFollowUp.is_completed.is_(False),
    ).order_by(CallFollowUp.due_date.asc(), CallFollowUp.id.asc()).all()
    return jsonify({
        "data": [
            {
                **_follow_up_dict(item),
                "call_log": _call_log_dict(item.call_log),
            }
            for item in follow_ups
        ]
    })


@customer_care_bp.patch("/follow-ups/<int:follow_up_id>")
@jwt_required()
def complete_follow_up(follow_up_id):
    staff = _current_staff()
    if not staff:
        return _error("Active staff account not found", 403)
    payload = _payload()
    if payload is None or payload != {"is_completed": True}:
        return _error("Set is_completed to true to complete this follow-up")
    follow_up = CallFollowUp.query.filter_by(
        id=follow_up_id,
        assigned_to=staff.id,
    ).first()
    if not follow_up:
        return _error("Follow-up not found", 404)
    follow_up.is_completed = True
    error_response = _commit_or_error()
    if error_response:
        return error_response
    return jsonify({"data": _follow_up_dict(follow_up)})
