from datetime import date, datetime, timedelta
from decimal import Decimal
import os
import re
from uuid import uuid4

from flask import Blueprint, jsonify, make_response, render_template, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    AuditLog,
    CompanyHoliday,
    HandoverAccess,
    HandoverAttachment,
    HandoverEscalation,
    HandoverRecurring,
    HandoverReport,
    HandoverRisk,
    HandoverTask,
    LeaveBalance,
    LeavePolicy,
    LeaveRequest,
    LeaveType,
    Notification,
    User,
)
from app.utils.handover_validation import validate_handover_submission
from app.utils.workflow import handover_gate, transition


leave_bp = Blueprint("leave", __name__, url_prefix="/api/leave")


def _error(message, status=400):
    return jsonify({"error": message}), status


def _current_user():
    user = db.session.get(User, int(get_jwt_identity()))
    return user if user and user.is_active else None


def _decimal(value):
    return Decimal(value or 0)


def _number(value):
    return float(_decimal(value))


def _parse_date(value, name):
    if not value:
        raise ValueError(f"{name} is required")
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must use YYYY-MM-DD format")


def _working_days(start_date, end_date):
    holidays = {
        holiday.date
        for holiday in CompanyHoliday.query.filter(
            CompanyHoliday.country == "Kenya",
            CompanyHoliday.date >= start_date,
            CompanyHoliday.date <= end_date,
        ).all()
    }
    total = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holidays:
            total += 1
        current += timedelta(days=1)
    return total


def _validate_contact(contact):
    if not re.fullmatch(r"\+?[0-9 ()-]{7,30}", contact["contact_phone"]):
        return "contact_phone must be a valid phone number"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact["contact_email"]):
        return "contact_email must be a valid email address"
    return None


def _type_dict(leave_type):
    return {
        "id": leave_type.id,
        "name": leave_type.name,
        "code": leave_type.code,
        "is_paid": leave_type.is_paid,
        "requires_document": leave_type.requires_document,
        "default_days_per_year": _number(leave_type.default_days_per_year),
    }


def _balance_dict(balance):
    leave_type = getattr(balance, "leave_type", None) or db.session.get(LeaveType, getattr(balance, "leave_type_id", None))
    available = (
        _decimal(balance.entitled_days)
        + _decimal(balance.carried_over)
        - _decimal(balance.used_days)
        - _decimal(balance.pending_days)
    )
    return {
        "leave_type_id": balance.leave_type_id,
        "code": getattr(leave_type, "code", "UNKNOWN"),
        "name": getattr(leave_type, "name", "Unknown leave type"),
        "entitled_days": _number(balance.entitled_days),
        "used_days": _number(balance.used_days),
        "pending_days": _number(balance.pending_days),
        "carried_over": _number(balance.carried_over),
        "available_days": float(available),
    }


def _request_dict(leave_request, include_names=False):
    data = {
        "id": leave_request.id,
        "user_id": leave_request.user_id,
        "leave_type_id": leave_request.leave_type_id,
        "start_date": leave_request.start_date.isoformat(),
        "end_date": leave_request.end_date.isoformat(),
        "days_requested": _number(leave_request.days_requested),
        "reason": leave_request.reason,
        "contact_phone": leave_request.contact_phone,
        "contact_email": leave_request.contact_email,
        "address_line1": leave_request.address_line1,
        "address_line2": leave_request.address_line2,
        "city": leave_request.city,
        "country": leave_request.country,
        "postal_code": leave_request.postal_code,
        "handover_user_id": leave_request.handover_user_id,
        "handover_name": leave_request.handover_name,
        "handover_statement": leave_request.handover_statement,
        "handover_agreed_at": leave_request.handover_agreed_at.isoformat() if leave_request.handover_agreed_at else None,
        "handover_signature": leave_request.handover_signature,
        "handover_signature_date": leave_request.handover_signature_date.isoformat() if leave_request.handover_signature_date else None,
        "handover_report": leave_request.handover_report,
        "status": leave_request.status,
        "workflow_state": leave_request.workflow_state,
        "handover_gate": handover_gate(leave_request),
        "declaration_accepted": leave_request.declaration_accepted,
        "employee_signature": leave_request.employee_signature,
        "declaration_date": leave_request.declaration_date.isoformat() if leave_request.declaration_date else None,
        "manual_days_override": _number(leave_request.manual_days_override),
        "manual_days_reason": leave_request.manual_days_reason,
        "supervisor_name": leave_request.supervisor_name,
        "supervisor_decision": leave_request.supervisor_decision,
        "supervisor_decision_date": leave_request.supervisor_decision_date.isoformat() if leave_request.supervisor_decision_date else None,
        "hr_manager": leave_request.hr_manager,
        "hr_verification_date": leave_request.hr_verification_date.isoformat() if leave_request.hr_verification_date else None,
        "hr_verification_status": leave_request.hr_verification_status,
        "approver_id": leave_request.approver_id,
        "decision_comment": leave_request.decision_comment,
        "applied_at": leave_request.applied_at.isoformat() if leave_request.applied_at else None,
        "decided_at": leave_request.decided_at.isoformat() if leave_request.decided_at else None,
    }
    if include_names:
        data["requester_name"] = leave_request.user.full_name
        data["type_name"] = leave_request.leave_type.name
    return data


def _audit(actor_id, action, request_id, metadata=None):
    return AuditLog(
        actor_id=actor_id,
        action=action,
        entity="LeaveRequest",
        entity_id=str(request_id),
        event_metadata=metadata or {},
    )


def _balance_for(user_id, leave_type_id, year):
    return LeaveBalance.query.filter_by(
        user_id=user_id,
        leave_type_id=leave_type_id,
        year=year,
    ).first()


def _can_manage(user, leave_request):
    if bool(getattr(user, "is_superuser", False)) or user.role == "hr_admin":
        return True
    if user.role != "manager":
        return False
    if leave_request.user.manager_id == user.id:
        return True
    department = (leave_request.user.department or "").strip().lower()
    if not department:
        return False
    department_managers = User.query.filter(
        User.role == "manager",
        User.is_active.is_(True),
        db.func.lower(User.department) == department,
    ).all()
    return len(department_managers) == 1 and department_managers[0].id == user.id


def _is_handover_pending(leave_request):
    if leave_request is None:
        return False
    if float(_decimal(getattr(leave_request, "days_requested", 0) or 0)) <= 2:
        return False

    if not leave_request.handover_user_id:
        return True

    if not leave_request.handover_agreed_at:
        return True

    statement = (leave_request.handover_statement or "").strip()
    return bool(statement.startswith("DECLINED:")) or not statement


def _is_handover_report_missing(leave_request):
    if leave_request is None:
        return False
    days = float(_decimal(getattr(leave_request, "days_requested", 0) or 0))
    if days <= 3:
        return False
    leave_type = getattr(leave_request, "leave_type", None)
    if leave_type is None:
        leave_type = db.session.get(LeaveType, leave_request.leave_type_id)
    if leave_type is not None and leave_type.code.upper() in {"SICK", "UNPAID"}:
        return False
    report = getattr(leave_request, "handover_report", None)
    if not report and not HandoverReport.query.filter_by(leave_request_id=leave_request.id).first():
        return True
    return False


def _notify_approvers(user, leave_request):
    if user.manager_id:
        recipient_ids = [user.manager_id]
    else:
        recipient_ids = [
            admin.id
            for admin in User.query.filter_by(
                role="hr_admin", is_active=True
            ).all()
        ]

    body = (
        f"{user.full_name} requested {leave_request.days_requested} day(s) "
        f"of {leave_request.leave_type.name} leave from "
        f"{leave_request.start_date.isoformat()} to "
        f"{leave_request.end_date.isoformat()}."
    )
    for recipient_id in recipient_ids:
        db.session.add(
            Notification(
                user_id=recipient_id,
                title="New leave request",
                body=body,
                is_read=False,
            )
        )
    if leave_request.handover_user_id:
        db.session.add(Notification(
            user_id=leave_request.handover_user_id,
            title="Handover request",
            body=f"{user.full_name} asked you to handle work during their leave.",
            is_read=False,
        ))


def _handover_error(code, message, status=400):
    return jsonify({
        "data": None,
        "error": {"code": code, "message": message},
    }), status


def _handover_upload_dir(request_id):
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "handovers", str(request_id))
    )


def _attachment_dict(attachment):
    return {
        "id": attachment.id,
        "file_url": attachment.file_url,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "uploaded_by": attachment.uploaded_by,
        "uploaded_at": attachment.uploaded_at.isoformat() if attachment.uploaded_at else None,
    }


def _serialize_handover_task(task):
    return {
        "id": task.id,
        "task_name": task.task_name,
        "description": task.description,
        "status": task.status,
        "percent_complete": task.percent_complete,
        "next_action": task.next_action,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "priority": task.priority,
        "stakeholder": task.stakeholder,
        "location": task.location,
        "sort_order": task.sort_order,
    }


def _serialize_handover_report(report):
    if report is None:
        return None
    return {
        "id": report.id,
        "leave_request_id": report.leave_request_id,
        "version": report.version,
        "summary": report.summary,
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        "tasks": [
            _serialize_handover_task(task)
            for task in sorted(report.tasks, key=lambda item: (item.sort_order or 0, item.id))
        ],
        "recurring": [
            {
                "id": item.id,
                "task": item.task,
                "cadence": item.cadence,
                "where_link": item.where_link,
                "definition_of_done": item.definition_of_done,
            }
            for item in report.recurring
        ],
        "escalations": [
            {
                "id": item.id,
                "issue_type": item.issue_type,
                "contact_user_id": item.contact_user_id,
                "contact_name": item.contact_name,
                "contact_role": item.contact_role,
                "contact_phone": item.contact_phone,
                "contact_email": item.contact_email,
                "when_to_escalate": item.when_to_escalate,
            }
            for item in report.escalations
        ],
        "access": [
            {
                "id": item.id,
                "system_name": item.system_name,
                "access_level": item.access_level,
                "how_to_request": item.how_to_request,
                "ticket_raised": item.ticket_raised,
                "approved_by": item.approved_by,
            }
            for item in report.access_entries
        ],
        "risks": [
            {
                "id": item.id,
                "risk": item.risk,
                "impact": item.impact,
                "mitigation": item.mitigation,
                "owner_id": item.owner_id,
            }
            for item in report.risks
        ],
        "attachments": [_attachment_dict(item) for item in report.attachments],
    }


def _load_handover_report(report_id=None, request_id=None):
    if report_id is not None:
        return db.session.get(HandoverReport, report_id)
    if request_id is not None:
        return HandoverReport.query.filter_by(leave_request_id=request_id).first()
    return None


def _can_read_handover(user, leave_request):
    return (
        leave_request.user_id == user.id
        or leave_request.handover_user_id == user.id
        or user.role in ("manager", "hr_admin")
    )


def _apply_handover_payload(report, payload):
    if not isinstance(payload, dict):
        return report
    if "summary" in payload:
        report.summary = str(payload.get("summary") or "")
    if "version" in payload:
        report.version = str(payload.get("version") or "v1")
    if "submitted_at" in payload and payload.get("submitted_at") is not None:
        report.submitted_at = payload.get("submitted_at")

    for field_name, model_cls, serializer in (
        ("tasks", HandoverTask, lambda item: {
            "task_name": item.get("task_name"),
            "description": item.get("description"),
            "status": item.get("status"),
            "percent_complete": item.get("percent_complete"),
            "next_action": item.get("next_action") or "",
            "deadline": item.get("deadline") or date.today().isoformat(),
            "priority": item.get("priority"),
            "stakeholder": item.get("stakeholder"),
            "location": item.get("location"),
            "sort_order": item.get("sort_order", 0),
        }),
        ("recurring", HandoverRecurring, lambda item: {
            "task": item.get("task"),
            "cadence": item.get("cadence"),
            "where_link": item.get("where_link"),
            "definition_of_done": item.get("definition_of_done") or "",
        }),
        ("escalations", HandoverEscalation, lambda item: {
            "issue_type": item.get("issue_type"),
            "contact_user_id": item.get("contact_user_id"),
            "contact_name": item.get("contact_name"),
            "contact_role": item.get("contact_role"),
            "contact_phone": item.get("contact_phone"),
            "contact_email": item.get("contact_email"),
            "when_to_escalate": item.get("when_to_escalate") or "",
        }),
        ("access", HandoverAccess, lambda item: {
            "system_name": item.get("system_name"),
            "access_level": item.get("access_level"),
            "how_to_request": item.get("how_to_request") or "",
            "ticket_raised": bool(item.get("ticket_raised", False)),
            "approved_by": item.get("approved_by"),
        }),
        ("risks", HandoverRisk, lambda item: {
            "risk": item.get("risk"),
            "impact": item.get("impact"),
            "mitigation": item.get("mitigation"),
            "owner_id": item.get("owner_id"),
        }),
        ("attachments", HandoverAttachment, lambda item: {
            "file_url": item.get("file_url"),
            "mime_type": item.get("mime_type"),
            "size_bytes": item.get("size_bytes"),
            "uploaded_by": item.get("uploaded_by"),
            "uploaded_at": item.get("uploaded_at"),
        }),
    ):
        if field_name not in payload:
            continue
        values = payload.get(field_name) or []
        existing_map = {item.id: item for item in getattr(report, field_name.replace('access', 'access_entries') if field_name == 'access' else field_name, [])}
        for existing in list(getattr(report, field_name.replace('access', 'access_entries') if field_name == 'access' else field_name, [])):
            db.session.delete(existing)
        for order_index, item in enumerate(values):
            model_item = model_cls(**serializer(item))
            if field_name == "tasks":
                model_item.sort_order = item.get("sort_order", order_index)
                model_item.handover_report = report
            elif field_name == "recurring":
                model_item.handover_report = report
            elif field_name == "escalations":
                model_item.handover_report = report
            elif field_name == "access":
                model_item.handover_report = report
            elif field_name == "risks":
                model_item.handover_report = report
            elif field_name == "attachments":
                model_item.handover_report = report
            db.session.add(model_item)
    return report


@leave_bp.get("/types")
@jwt_required()
def get_types():
    leave_types = LeaveType.query.order_by(LeaveType.name.asc()).all()
    return jsonify({
        "data": [_type_dict(leave_type) for leave_type in leave_types],
        "message": "Leave types retrieved",
    })


@leave_bp.get("/balances")
@jwt_required()
def get_balances():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    balances = (
        LeaveBalance.query.join(LeaveType, LeaveBalance.leave_type_id == LeaveType.id)
        .filter(LeaveBalance.user_id == user.id, LeaveBalance.year == date.today().year)
        .all()
    )
    balances = [balance for balance in balances if getattr(balance, "leave_type", None) is not None or db.session.get(LeaveType, balance.leave_type_id) is not None]
    existing_type_ids = {balance.leave_type_id for balance in balances}
    for leave_type in LeaveType.query.order_by(LeaveType.id.asc()).all():
        if leave_type.id in existing_type_ids or leave_type.code.upper() == "UNPAID":
            continue
        balances.append(LeaveBalance(
            user_id=user.id,
            leave_type_id=leave_type.id,
            year=date.today().year,
            entitled_days=leave_type.default_days_per_year or 0,
            used_days=Decimal("0.00"),
            pending_days=Decimal("0.00"),
            carried_over=Decimal("0.00"),
        ))
    if len(balances) > len(existing_type_ids):
        db.session.commit()
    return jsonify({
        "data": [_balance_dict(balance) for balance in balances],
        "message": "Leave balances retrieved",
    })


@leave_bp.post("/requests")
@jwt_required()
def create_request():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    try:
        payload = request.get_json(silent=True) or {}
        leave_type_id = payload.get("leave_type_id")
        reason = payload.get("reason")
        if not leave_type_id:
            return _error("leave_type_id is required")
        if not reason:
            return _error("reason is required")

        start_date = _parse_date(payload.get("start_date"), "start_date")
        end_date = _parse_date(payload.get("end_date"), "end_date")
        today = date.today()
        if end_date < start_date:
            return _error("end_date must be on or after start_date")
        if start_date < today:
            return _error("start_date cannot be before today")

        leave_type = LeaveType.query.get(leave_type_id)
        if not leave_type:
            return _error("Leave type not found", 404)
        policy = LeavePolicy.query.filter_by(leave_type_id=leave_type.id).first()
        if not policy:
            policy = LeavePolicy(
                leave_type_id=leave_type.id,
                accrual_rate=leave_type.default_days_per_year or 0,
                max_carryover=0,
                notice_days_required=0,
            )
            db.session.add(policy)
            db.session.flush()
        if policy.min_service_months:
            if not user.hire_date:
                return _error("A hire date is required for this leave type", 403)
            if (today - user.hire_date).days // 30 < policy.min_service_months:
                return _error("The minimum service period has not been met", 403)
        if (start_date - today).days < policy.notice_days_required:
            return _error(
                f"This leave type requires at least {policy.notice_days_required} days notice"
            )

        working_days = _working_days(start_date, end_date)
        if working_days <= 0:
            return _error("The selected dates contain no working days")

        required_contact = {
            field: (payload.get(field) or "").strip()
            for field in ("contact_phone", "contact_email")
        }
        missing_contact = [field for field, value in required_contact.items() if not value]
        if missing_contact:
            return _error("Contact details are required: " + ", ".join(missing_contact))
        contact_error = _validate_contact(required_contact)
        if contact_error:
            return _error(contact_error, 422)
        handover_user = None
        handover_name = (payload.get("handover_name") or "").strip()
        if working_days > 2:
            handover_user_id = payload.get("handover_user_id")
            handover_user = db.session.get(User, handover_user_id) if handover_user_id else None
            if not handover_user or handover_user.id == user.id or not handover_user.is_active:
                return _error("A valid colleague must be assigned for absences longer than two days")
            handover_name = handover_user.full_name
        if working_days > 3 and not (payload.get("handover_report") or "").strip():
            return _error("A full handover report is required for absences longer than three days")

        balance = None
        if leave_type.code != "UNPAID":
            balance = _balance_for(user.id, leave_type.id, today.year)
            if not balance:
                balance = LeaveBalance(
                    user_id=user.id,
                    leave_type_id=leave_type.id,
                    year=today.year,
                    entitled_days=_decimal(leave_type.default_days_per_year),
                    used_days=Decimal("0.00"),
                    pending_days=Decimal("0.00"),
                    carried_over=Decimal("0.00"),
                )
                db.session.add(balance)
                db.session.flush()

            available = (
                _decimal(balance.entitled_days)
                + _decimal(balance.carried_over)
                - _decimal(balance.used_days)
                - _decimal(balance.pending_days)
            )
            if Decimal(working_days) > available:
                return _error("Insufficient leave balance", 409)
            balance.pending_days = _decimal(balance.pending_days) + working_days
        leave_request = LeaveRequest(
            user_id=user.id,
            leave_type_id=leave_type.id,
            start_date=start_date,
            end_date=end_date,
            days_requested=working_days,
            reason=reason,
            contact_phone=required_contact["contact_phone"],
            contact_email=required_contact["contact_email"],
            address_line1=None,
            address_line2=(payload.get("address_line2") or "").strip() or None,
            city=None,
            country=None,
            postal_code=None,
            handover_user_id=handover_user.id if handover_user else None,
            handover_name=handover_name or None,
            handover_report=(payload.get("handover_report") or "").strip() or None,
            status="pending",
            workflow_state="handover_pending" if working_days > 2 else "supervisor_pending",
            declaration_accepted=bool(payload.get("declaration", payload.get("declaration_accepted", False))),
            employee_signature=(payload.get("employee_signature") or "").strip() or None,
            declaration_date=_parse_date(payload.get("declaration_date"), "declaration_date") if payload.get("declaration_date") else None,
            manual_days_override=payload.get("number_of_days_override"),
            manual_days_reason=(payload.get("number_of_days_reason") or "").strip() or None,
        )
        db.session.add(leave_request)
        db.session.flush()
        _notify_approvers(user, leave_request)
        db.session.add(_audit(
            user.id,
            "leave_request_created",
            leave_request.id,
            {
                "leave_type_id": leave_type.id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days_requested": working_days,
                "workflow_state": leave_request.workflow_state,
            },
        ))
        db.session.commit()
        return jsonify({
            "data": _request_dict(leave_request),
            "message": "Leave request submitted",
        }), 201
    except ValueError as error:
        db.session.rollback()
        return _error(str(error))
    except Exception:
        db.session.rollback()
        return _error("Unable to create leave request", 500)


@leave_bp.post("/requests/<int:request_id>/handover-ack")
@jwt_required()
def acknowledge_handover(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request or leave_request.handover_user_id != user.id:
        return _error("Only the assigned colleague can acknowledge this handover", 403)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or user.full_name).strip()
    statement = (payload.get("statement") or "").strip()
    expected = "I have been briefed on the work to be undertaken and hereby agree to take responsibility of the work to be executed."
    if statement != expected:
        return _error("The handover acknowledgement must use the required statement")
    if not name:
        return _error("Name is required")
    leave_request.handover_name = name
    leave_request.handover_statement = expected
    leave_request.handover_agreed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"data": _request_dict(leave_request), "message": "Handover acknowledged"})


@leave_bp.get("/requests/<int:request_id>/handover")
@jwt_required()
def get_handover_details(request_id):
    user = _current_user()
    if not user:
        return _handover_error("NOT_FOUND", "User not found or inactive", 404)

    leave_request = db.session.get(LeaveRequest, request_id)
    if not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)

    if not _can_read_handover(user, leave_request):
        return _handover_error("FORBIDDEN", "You do not have access to this handover", 403)

    report = HandoverReport.query.filter_by(leave_request_id=leave_request.id).first()
    return jsonify({
        "data": _serialize_handover_report(report),
        "error": None,
    })


@leave_bp.put("/requests/<int:request_id>/handover")
@jwt_required()
def upsert_handover_report(request_id):
    user = _current_user()
    if not user:
        return _handover_error("NOT_FOUND", "User not found or inactive", 404)

    leave_request = db.session.get(LeaveRequest, request_id)
    if not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)

    if leave_request.user_id != user.id:
        return _handover_error("FORBIDDEN", "Only the requester can update this handover report", 403)

    report = HandoverReport.query.filter_by(leave_request_id=leave_request.id).first()
    if report is not None and report.submitted_at is not None:
        return _handover_error("HANDOVER_LOCKED", "Submitted handover reports cannot be edited", 409)

    payload = request.get_json(silent=True) or {}
    if report is None:
        report = HandoverReport(
            leave_request_id=leave_request.id,
            version=str(payload.get("version") or "v1"),
            summary=str(payload.get("summary") or ""),
        )
        db.session.add(report)
        db.session.flush()
    report = _apply_handover_payload(report, payload)
    db.session.commit()
    return jsonify({
        "data": _serialize_handover_report(report),
        "error": None,
    })


@leave_bp.patch("/requests/<int:request_id>/handover")
@jwt_required()
def patch_handover_report(request_id):
    user = _current_user()
    if not user:
        return _handover_error("NOT_FOUND", "User not found or inactive", 404)

    leave_request = db.session.get(LeaveRequest, request_id)
    if not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)

    if leave_request.user_id != user.id:
        return _handover_error("FORBIDDEN", "Only the requester can autosave this handover report", 403)

    report = HandoverReport.query.filter_by(leave_request_id=leave_request.id).first()
    if report is not None and report.submitted_at is not None:
        return _handover_error("HANDOVER_LOCKED", "Submitted handover reports cannot be edited", 409)

    payload = request.get_json(silent=True) or {}
    if report is None:
        report = HandoverReport(
            leave_request_id=leave_request.id,
            version=str(payload.get("version") or "v1"),
            summary=str(payload.get("summary") or ""),
        )
        db.session.add(report)
        db.session.flush()

    if "summary" in payload:
        report.summary = str(payload.get("summary") or "")
    if "version" in payload:
        report.version = str(payload.get("version") or "v1")
    if "submitted_at" in payload and payload.get("submitted_at") is not None:
        report.submitted_at = payload.get("submitted_at")

    report = _apply_handover_payload(report, payload)
    db.session.commit()
    return jsonify({
        "data": _serialize_handover_report(report),
        "error": None,
    })


@leave_bp.post("/requests/<int:request_id>/handover/submit")
@jwt_required()
def submit_handover_report(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)
    if leave_request.user_id != user.id:
        return _handover_error("FORBIDDEN", "Only the requester can submit this handover report", 403)

    payload = request.get_json(silent=True) or {}
    errors = validate_handover_submission(leave_request, payload)
    if errors:
        return jsonify({
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Validation failed",
                "fields": errors,
            },
        }), 422

    report = HandoverReport.query.filter_by(leave_request_id=leave_request.id).first()
    if report is None:
        report = HandoverReport(
            leave_request_id=leave_request.id,
            version="v1",
            summary=(payload.get("summary") or "").strip(),
        )
        db.session.add(report)
        db.session.flush()

    report.summary = (payload.get("summary") or "").strip()
    report.version = str(payload.get("version") or report.version or "v1")
    report.submitted_at = datetime.utcnow()
    report = _apply_handover_payload(report, payload)
    db.session.commit()
    return jsonify({
        "data": _serialize_handover_report(report),
        "error": None,
    })


@leave_bp.post("/requests/<int:request_id>/handover/attachment")
@jwt_required()
def upload_handover_attachment(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)
    if leave_request.user_id != user.id:
        return _handover_error("FORBIDDEN", "Only the requester can upload an attachment", 403)

    report = HandoverReport.query.filter_by(leave_request_id=request_id).first()
    if report is None:
        return _handover_error("NOT_FOUND", "Create a handover report before uploading an attachment", 404)
    if report.submitted_at is not None:
        return _handover_error("HANDOVER_LOCKED", "Submitted handover reports cannot be edited", 409)

    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return _handover_error("FILE_REQUIRED", "A PDF or DOCX file is required", 422)

    filename = secure_filename(uploaded_file.filename)
    extension = os.path.splitext(filename)[1].lower()
    allowed_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if extension not in allowed_types:
        return _handover_error("UNSUPPORTED_MEDIA_TYPE", "Only PDF and DOCX attachments are allowed", 415)

    content_type = (uploaded_file.mimetype or "").lower()
    if content_type and content_type != allowed_types[extension]:
        return _handover_error("UNSUPPORTED_MEDIA_TYPE", "Attachment MIME type does not match its extension", 415)

    uploaded_file.stream.seek(0, os.SEEK_END)
    size_bytes = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)
    max_size = 10 * 1024 * 1024
    if size_bytes > max_size:
        return _handover_error("FILE_TOO_LARGE", "Attachment must be 10 MB or less", 413)

    upload_dir = _handover_upload_dir(request_id)
    os.makedirs(upload_dir, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    stored_path = os.path.join(upload_dir, stored_name)
    uploaded_file.save(stored_path)

    attachment = HandoverAttachment(
        handover_report_id=report.id,
        file_url=f"/uploads/handovers/{request_id}/{stored_name}",
        mime_type=allowed_types[extension],
        size_bytes=size_bytes,
        uploaded_by=user.id,
    )
    db.session.add(attachment)
    db.session.add(_audit(user.id, "handover_attachment_uploaded", request_id, {
        "handover_report_id": report.id,
        "mime_type": attachment.mime_type,
        "size_bytes": size_bytes,
    }))
    db.session.commit()
    return jsonify({"data": _attachment_dict(attachment), "error": None}), 201


@leave_bp.get("/requests/<int:request_id>/handover/attachment/<int:attachment_id>")
@jwt_required()
def download_handover_attachment(request_id, attachment_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request or not _can_read_handover(user, leave_request):
        return _handover_error("FORBIDDEN", "You do not have access to this attachment", 403)
    report = HandoverReport.query.filter_by(leave_request_id=request_id).first()
    attachment = HandoverAttachment.query.filter_by(id=attachment_id, handover_report_id=report.id if report else None).first()
    if not attachment:
        return _handover_error("NOT_FOUND", "Attachment not found", 404)
    upload_dir = _handover_upload_dir(request_id)
    file_path = os.path.abspath(os.path.join(upload_dir, os.path.basename(attachment.file_url or "")))
    if os.path.commonpath([file_path, upload_dir]) != upload_dir or not os.path.isfile(file_path):
        return _handover_error("NOT_FOUND", "Attachment file not found", 404)
    return send_file(file_path, mimetype=attachment.mime_type, as_attachment=True, download_name=os.path.basename(file_path))


@leave_bp.delete("/requests/<int:request_id>/handover/attachment/<int:attachment_id>")
@jwt_required()
def delete_handover_attachment(request_id, attachment_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)
    if leave_request.user_id != user.id:
        return _handover_error("FORBIDDEN", "Only the requester can remove an attachment", 403)

    report = HandoverReport.query.filter_by(leave_request_id=request_id).first()
    attachment = (
        HandoverAttachment.query.filter_by(id=attachment_id, handover_report_id=report.id).first()
        if report is not None
        else None
    )
    if attachment is None:
        return _handover_error("NOT_FOUND", "Attachment not found", 404)
    if report.submitted_at is not None:
        return _handover_error("HANDOVER_LOCKED", "Submitted handover reports cannot be edited", 409)

    file_path = os.path.abspath(os.path.join(_handover_upload_dir(request_id), os.path.basename(attachment.file_url or "")))
    upload_dir = _handover_upload_dir(request_id)
    if os.path.commonpath([file_path, upload_dir]) == upload_dir and os.path.isfile(file_path):
        os.remove(file_path)

    db.session.delete(attachment)
    db.session.add(_audit(user.id, "handover_attachment_removed", request_id, {
        "attachment_id": attachment_id,
    }))
    db.session.commit()
    return jsonify({"data": {"id": attachment_id}, "error": None})


@leave_bp.get("/requests/<int:request_id>/handover/pdf")
@jwt_required()
def download_handover_pdf(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _handover_error("NOT_FOUND", "Leave request not found", 404)
    if not _can_read_handover(user, leave_request):
        return _handover_error("FORBIDDEN", "You do not have access to this handover", 403)

    report = HandoverReport.query.filter_by(leave_request_id=request_id).first()
    if report is None:
        return _handover_error("NOT_FOUND", "Handover report not found", 404)

    try:
        from weasyprint import HTML
        rendered_html = render_template(
            "handover_report.html",
            leave_request=leave_request,
            report=report,
            acknowledgment_text=(
                "I have been hereby briefed on work to be undertaken and hereby agree "
                "to take responsibility of work to be executed."
            ),
        )
        pdf_bytes = HTML(string=rendered_html).write_pdf()
    except ImportError:
        return _handover_error("PDF_UNAVAILABLE", "PDF export is not available", 503)

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="handover_{request_id}_{report.version}.pdf"'
    )
    return response


@leave_bp.post("/requests/<int:request_id>/handover/accept")
@jwt_required()
def accept_handover(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _error("Leave request not found", 404)
    if leave_request.handover_user_id != user.id:
        return _error("Only the assigned delegate can accept this handover", 403)

    payload = request.get_json(silent=True) or {}
    statement = (payload.get("statement") or "I have been hereby briefed on work to be undertaken and hereby agree to take responsibility of work to be executed.").strip()
    if statement != "I have been hereby briefed on work to be undertaken and hereby agree to take responsibility of work to be executed.":
        return _error("The handover acknowledgement must use the required statement", 422)
    signature = (payload.get("signature") or "").strip()
    signature_date = payload.get("signature_date")
    if not signature or not signature_date:
        return _error("signature and signature_date are required", 422)
    if signature != user.full_name:
        return _error("The delegate signature must match your full name", 422)
    try:
        signature_date = _parse_date(signature_date, "signature_date")
    except ValueError as error:
        return _error(str(error), 422)
    if signature_date > date.today():
        return _error("signature_date cannot be in the future", 422)

    leave_request.handover_name = user.full_name
    leave_request.handover_statement = statement
    leave_request.handover_agreed_at = datetime.utcnow()
    leave_request.handover_signature = signature
    leave_request.handover_signature_date = signature_date
    if leave_request.workflow_state == "handover_pending":
        transition(leave_request, "handover_complete", user, {"signature": signature})
    db.session.commit()
    return jsonify({"data": _request_dict(leave_request), "message": "Handover accepted"})


@leave_bp.post("/requests/<int:request_id>/handover/decline")
@jwt_required()
def decline_handover(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _error("Leave request not found", 404)
    if leave_request.handover_user_id != user.id:
        return _error("Only the assigned delegate can decline this handover", 403)

    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "Declined by assigned delegate").strip()
    if not reason:
        return _error("reason is required", 422)

    leave_request.handover_name = user.full_name
    leave_request.handover_statement = f"DECLINED: {reason}"
    leave_request.handover_agreed_at = None
    db.session.commit()
    return jsonify({"data": _request_dict(leave_request), "message": "Handover declined"})


@leave_bp.post("/requests/<int:request_id>/handover/request-changes")
@jwt_required()
def request_handover_changes(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _error("Leave request not found", 404)
    if leave_request.handover_user_id != user.id:
        return _error("Only the assigned delegate can request changes to this handover", 403)

    payload = request.get_json(silent=True) or {}
    comment = (payload.get("comment") or payload.get("reason") or "").strip()
    if not comment:
        return _error("comment is required", 422)

    leave_request.handover_name = user.full_name
    leave_request.handover_statement = f"CHANGES_REQUESTED: {comment}"
    leave_request.handover_agreed_at = None
    db.session.commit()
    return jsonify({"data": _request_dict(leave_request), "message": "Handover changes requested"})


@leave_bp.post("/requests/<int:request_id>/handover/remind")
@jwt_required()
def remind_handover_delegate(request_id):
    user = _current_user()
    leave_request = db.session.get(LeaveRequest, request_id)
    if not user or not leave_request:
        return _error("Leave request not found", 404)
    if not _can_manage(user, leave_request):
        return _error("You cannot remind the delegate for this request", 403)
    if not leave_request.handover_user_id:
        return _error("No delegate is assigned", 409)
    if leave_request.handover_agreed_at:
        return _error("The delegate has already accepted this handover", 409)
    db.session.add(Notification(
        user_id=leave_request.handover_user_id,
        title="Handover reminder",
        body=f"{leave_request.user.full_name} is waiting for you to accept the handover for request #{leave_request.id}.",
        is_read=False,
    ))
    db.session.add(_audit(user.id, "handover_delegate_reminded", leave_request.id))
    db.session.commit()
    return jsonify({"data": _request_dict(leave_request), "message": "Delegate reminder sent"})


@leave_bp.get("/requests")
@jwt_required()
def get_requests():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    requests = LeaveRequest.query.filter_by(user_id=user.id).order_by(
        LeaveRequest.applied_at.desc()
    ).all()
    return jsonify({
        "data": [_request_dict(item) for item in requests],
        "message": "Leave requests retrieved",
    })


@leave_bp.get("/requests/history")
@jwt_required()
def get_request_history():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    requests = LeaveRequest.query.filter_by(user_id=user.id).order_by(
        LeaveRequest.applied_at.desc()
    ).all()
    return jsonify({
        "data": [_request_dict(item) for item in requests],
        "message": "Leave history retrieved",
    })


@leave_bp.get("/requests/delegations")
@jwt_required()
def get_delegations():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    requests = LeaveRequest.query.filter_by(handover_user_id=user.id).order_by(
        LeaveRequest.applied_at.desc()
    ).all()
    return jsonify({
        "data": [_request_dict(item, include_names=True) for item in requests],
        "message": "Delegations retrieved",
    })


@leave_bp.get("/requests/pending")
@jwt_required()
def get_pending_requests():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    is_superuser = bool(getattr(user, "is_superuser", False))
    if user.role not in ("manager", "hr_admin") and not is_superuser:
        return _error("Manager or HR administrator access is required", 403)
    query = LeaveRequest.query.filter(
        (LeaveRequest.status == "pending")
        | LeaveRequest.workflow_state.in_(("hr_verification", "approved"))
    )
    requests = query.order_by(LeaveRequest.applied_at.asc()).all()
    return jsonify({
        "data": [_request_dict(item, include_names=True) for item in requests],
        "message": "Pending leave requests retrieved",
    })


@leave_bp.get("/team-calendar")
@jwt_required()
def get_team_calendar():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    is_superuser = bool(getattr(user, "is_superuser", False))
    if user.role not in ("manager", "hr_admin") and not is_superuser:
        return _error("Manager or HR administrator access is required", 403)
    requests = LeaveRequest.query.filter(
        LeaveRequest.status.in_(("pending", "approved"))
    ).order_by(LeaveRequest.start_date.asc(), LeaveRequest.applied_at.asc()).all()
    return jsonify({
        "data": [_request_dict(item, include_names=True) for item in requests],
        "message": "Team calendar retrieved",
    })


@leave_bp.get("/requests/<int:request_id>")
@jwt_required()
def get_request(request_id):
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    item = LeaveRequest.query.get(request_id)
    if not item:
        return _error("Leave request not found", 404)
    if item.user_id != user.id and get_jwt().get("role") not in (
        "manager", "hr_admin"
    ):
        return _error("You are not allowed to view this request", 403)
    return jsonify({
        "data": _request_dict(item),
        "message": "Leave request retrieved",
    })


@leave_bp.post("/requests/<int:request_id>/cancel")
@jwt_required()
def cancel_request(request_id):
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    try:
        item = LeaveRequest.query.get(request_id)
        if not item:
            return _error("Leave request not found", 404)
        if item.user_id != user.id:
            return _error("Only the owner can cancel this request", 403)
        if item.status != "pending":
            return _error("Only pending requests can be cancelled")
        leave_type = db.session.get(LeaveType, item.leave_type_id)
        balance = _balance_for(user.id, item.leave_type_id, item.start_date.year)
        if leave_type and leave_type.code != "UNPAID":
            if not balance:
                return _error("Leave balance not found", 409)
            balance.pending_days = max(
                Decimal("0.00"),
                _decimal(balance.pending_days) - _decimal(item.days_requested),
            )
        item.status = "cancelled"
        item.decided_at = datetime.utcnow()
        db.session.add(_audit(user.id, "leave_request_cancelled", item.id))
        db.session.commit()
        return jsonify({
            "data": _request_dict(item),
            "message": "Leave request cancelled",
        })
    except Exception:
        db.session.rollback()
        return _error("Unable to cancel leave request", 500)


def _decision(request_id, action):
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    try:
        if user.role not in ("manager", "hr_admin") and not getattr(user, "is_superuser", False):
            return _error("Manager or HR administrator access is required", 403)
        item = LeaveRequest.query.get(request_id)
        if not item:
            return _error("Leave request not found", 404)
        if item.status != "pending":
            return _error(f"Only pending requests can be {action}d")
        if user.role == "hr_admin" and not getattr(user, "is_superuser", False) and item.workflow_state == "supervisor_pending" and action == "approve":
            return _error("Manager approval is required before HR verification", 403)

        if action == "approve":
            if _is_handover_pending(item):
                return jsonify({
                    "data": None,
                    "error": {
                        "code": "HANDOVER_PENDING",
                        "message": "Handover pending acceptance",
                    },
                }), 409
            if _is_handover_report_missing(item):
                return jsonify({
                    "data": None,
                    "error": {
                        "code": "HANDOVER_REPORT_MISSING",
                        "message": "Handover report is required",
                    },
                }), 409

        payload = request.get_json(silent=True) or {}
        comment = (payload.get("decision_comment") or payload.get("reason") or "").strip()
        if action in ("reject", "defer") and len(comment) < 10:
            return _error("A reason of at least 10 characters is required", 422)

        try:
            next_state = transition(item, action, user, {
                "reason": comment,
                "signature": (payload.get("signature") or user.full_name).strip(),
            })
        except ValueError as error:
            return jsonify({"data": None, "error": {"code": "INVALID_TRANSITION", "message": str(error)}}), 409

        leave_type = db.session.get(LeaveType, item.leave_type_id)
        balance = _balance_for(item.user_id, item.leave_type_id, item.start_date.year)
        if leave_type and leave_type.code != "UNPAID" and not balance:
            return _error("Leave balance not found", 409)
        days = _decimal(item.days_requested)
        if balance:
            balance.pending_days = max(
                Decimal("0.00"), _decimal(balance.pending_days) - days
            )
        if action == "approve":
            if balance:
                balance.used_days = _decimal(balance.used_days) + days
            item.status = "approved"
            title = "Leave request approved"
            message = "Leave request approved"
            item.supervisor_decision = "approve"
        else:
            item.status = "rejected" if action == "reject" else "pending"
            title = f"Leave request {action}d"
            message = f"Leave request {action}d"
            item.supervisor_decision = action
        item.approver_id = user.id
        item.decided_at = datetime.utcnow()
        item.decision_comment = comment
        item.supervisor_name = user.full_name
        item.supervisor_signature = (payload.get("signature") or user.full_name).strip()
        item.supervisor_decision_date = datetime.utcnow()
        db.session.add(Notification(
            user_id=item.user_id,
            title=title,
            body=f"Your leave request was {item.status}.",
            is_read=False,
        ))
        db.session.add(_audit(
            user.id,
            f"leave_request_{action}d",
            item.id,
            {"decision_comment": comment, "workflow_state": next_state, "signature": item.supervisor_signature},
        ))
        db.session.commit()
        return jsonify({
            "data": _request_dict(item),
            "message": message,
        })
    except Exception:
        db.session.rollback()
        return _error(f"Unable to {action} leave request", 500)


@leave_bp.post("/requests/<int:request_id>/approve")
@jwt_required()
def approve_request(request_id):
    return _decision(request_id, "approve")


@leave_bp.post("/requests/<int:request_id>/reject")
@jwt_required()
def reject_request(request_id):
    return _decision(request_id, "reject")


@leave_bp.post("/requests/<int:request_id>/defer")
@jwt_required()
def defer_request(request_id):
    return _decision(request_id, "defer")


@leave_bp.post("/requests/<int:request_id>/verify-complete")
@jwt_required()
def verify_complete_request(request_id):
    user = _current_user()
    if not user or (user.role != "hr_admin" and not getattr(user, "is_superuser", False)):
        return _error("HR administrator access is required", 403)
    item = LeaveRequest.query.get(request_id)
    if not item:
        return _error("Leave request not found", 404)
    if item.workflow_state not in {"hr_verification", "approved"}:
        return jsonify({"data": None, "error": {"code": "INVALID_TRANSITION", "message": "Request is not ready for HR verification"}}), 409
    missing = []
    if not item.supervisor_decision and not user.is_superuser:
        missing.append("supervisor decision")
    if missing:
        return jsonify({"data": None, "error": {"code": "VERIFICATION_INCOMPLETE", "message": ", ".join(missing) + " required"}}), 409
    try:
        if item.workflow_state == "hr_verification":
            transition(item, "verify", user, {"verification_status": "verified"})
        else:
            item.workflow_state = "completed"
            db.session.add(_audit(user.id, "leave_workflow_verify", item.id, {"before": "approved", "after": "completed"}))
        item.status = "approved"
        item.hr_manager = user.full_name
        item.hr_verification_date = datetime.utcnow()
        item.hr_verification_status = "verified"
        db.session.add(Notification(user_id=item.user_id, title="Leave completed", body="Your leave request has been verified by HR.", is_read=False))
        db.session.commit()
        return jsonify({"data": _request_dict(item), "message": "Leave request verified and completed"})
    except Exception:
        db.session.rollback()
        return _error("Unable to complete HR verification", 500)