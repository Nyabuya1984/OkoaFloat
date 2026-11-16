from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
import re
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, make_response, render_template, request, send_file
from flask_jwt_extended import (
    get_jwt,
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    AuditLog,
    CompanyHoliday,
    DepartmentAssignmentHistory,
    HandoverAccess,
    HandoverAttachment,
    HandoverEscalation,
    HandoverRecurring,
    HandoverReport,
    HandoverRisk,
    HandoverTask,
    LeaveBalance,
    LeaveApprovalStep,
    LeavePolicy,
    LeaveRequest,
    LeaveType,
    Notification,
    User,
)
from app.utils.handover_validation import validate_handover_submission
from app.utils.organization import (
    get_active_assignment,
    is_group_leader_substitute,
)
from app.utils.rbac import normalize_role
from app.utils.workflow import handover_gate, transition


leave_bp = Blueprint("leave", __name__, url_prefix="/api/leave")


@leave_bp.before_request
def enforce_leave_application_permission():
    if request.endpoint == "leave.create_request" and request.method == "POST":
        verify_jwt_in_request()
        if not _current_user():
            return _error("User not found or inactive", 403)
    return None


def _error(message, status=400):
    return jsonify({"error": message}), status


def _current_user():
    user = db.session.get(User, int(get_jwt_identity()))
    return (
        user
        if user and user.is_currently_active() and user.account_status == "approved"
        else None
    )


def _leave_reporting_chain(employee):
    def active_assignment(user_id, expected_role, department_id):
        manager = db.session.get(User, user_id) if user_id else None
        assignment = get_active_assignment(user_id) if user_id else None
        if (
            not manager
            or not manager.is_currently_active()
            or manager.account_status != "approved"
            or not assignment
            or assignment.started_at > datetime.utcnow()
            or assignment.organizational_role != expected_role
            or (
                expected_role != "general_manager"
                and (
                    assignment.department_id != manager.department_id
                    or manager.department_id != department_id
                )
            )
        ):
            return None
        return manager

    def active_department_role(role):
        return DepartmentAssignmentHistory.query.filter_by(
            department_id=department_id,
            organizational_role=role,
            ended_at=None,
        ).filter(DepartmentAssignmentHistory.user_id != employee.id).first() is not None

    employee_assignment = get_active_assignment(employee.id)
    department_id = employee.department_id
    requester_role = (
        employee_assignment.organizational_role if employee_assignment else None
    )
    if (
        not employee_assignment
        or not employee.is_currently_active()
        or employee.account_status != "approved"
        or employee_assignment.started_at > datetime.utcnow()
        or requester_role not in {
            "general_manager",
            "department_manager",
            "team_leader",
            "field_agent",
        }
    ):
        return None
    chain = {}
    if requester_role == "general_manager":
        return chain if employee.manager_id is None else None
    if (
        department_id is None
        or employee_assignment.department_id != department_id
    ):
        return None
    if requester_role == "field_agent":
        team_leader = active_assignment(
            employee.manager_id, "team_leader", department_id
        )
        if team_leader:
            chain["team_leader"] = team_leader
            next_manager_id = team_leader.manager_id
            direct_general_manager = active_assignment(
                next_manager_id, "general_manager", None
            )
            if direct_general_manager and not active_department_role("department_manager"):
                chain["general_manager"] = direct_general_manager
                return chain
        else:
            direct_general_manager = active_assignment(
                employee.manager_id, "general_manager", None
            )
            if (
                direct_general_manager
                and not active_department_role("department_manager")
                and not active_department_role("team_leader")
            ):
                chain["general_manager"] = direct_general_manager
                return chain
            inactive_leader = (
                db.session.get(User, employee.manager_id)
                if employee.manager_id
                else None
            )
            inactive_assignment = (
                get_active_assignment(inactive_leader.id)
                if inactive_leader
                else None
            )
            if (
                not inactive_leader
                or inactive_leader.is_currently_active()
                or not inactive_assignment
                or inactive_assignment.organizational_role != "team_leader"
                or inactive_assignment.department_id != department_id
            ):
                return None
            department_manager = active_assignment(
                inactive_leader.manager_id,
                "department_manager",
                department_id,
            )
            if (
                not department_manager
                or not is_group_leader_substitute(
                    department_manager, department_id
                )
            ):
                return None
            # The department manager temporarily fulfills both approval stages;
            # the normal department-manager approval remains in the workflow.
            chain["team_leader"] = department_manager
            next_manager_id = inactive_leader.manager_id
    elif requester_role == "team_leader":
        next_manager_id = employee.manager_id
    elif requester_role == "department_manager":
        next_manager_id = employee.manager_id
    else:
        if employee.manager_id is not None:
            return None
        return chain

    if requester_role in {"field_agent", "team_leader"}:
        if requester_role == "team_leader":
            direct_general_manager = active_assignment(
                next_manager_id, "general_manager", None
            )
            if direct_general_manager and not active_department_role("department_manager"):
                chain["general_manager"] = direct_general_manager
                return chain
        department_manager = active_assignment(
            next_manager_id, "department_manager", department_id
        )
        if not department_manager:
            return None
        chain["department_manager"] = department_manager
        next_manager_id = department_manager.manager_id

    general_manager = active_assignment(
        next_manager_id, "general_manager", None
    )
    if not general_manager or general_manager.manager_id is not None:
        return None
    chain["general_manager"] = general_manager
    return chain


def _leave_approval_actor_matches(item, actor, stage_role):
    chain = _leave_reporting_chain(item.user)
    return bool(
        chain
        and stage_role in chain
        and actor.id == chain[stage_role].id
    )


_LEAVE_STAGE_BY_STATE = {
    "team_leader_pending": "team_leader",
    "department_manager_pending": "department_manager",
    "general_manager_pending": "general_manager",
}


def _initial_leave_workflow_state(chain):
    for stage, state in (
        ("team_leader", "team_leader_pending"),
        ("department_manager", "department_manager_pending"),
        ("general_manager", "general_manager_pending"),
    ):
        if stage in chain:
            return state
    return "hr_verification"


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
    annual_days = _annual_entitlement(leave_type)
    return {
        "id": leave_type.id,
        "name": leave_type.name,
        "code": leave_type.code,
        "is_paid": leave_type.is_paid,
        "requires_document": leave_type.requires_document,
        "default_days_per_year": _number(annual_days),
        "annual_entitlement_days": _number(annual_days),
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
        "total_allocated_days": _number(_decimal(balance.entitled_days) + _decimal(balance.carried_over)),
        "used_days": _number(balance.used_days),
        "pending_days": _number(balance.pending_days),
        "carried_over": _number(balance.carried_over),
        "available_days": float(available),
        "remaining_days": float(available),
        "is_manual_override": bool(balance.is_manual_override),
    }


def _annual_entitlement(leave_type):
    policy = LeavePolicy.query.filter_by(leave_type_id=leave_type.id).first()
    if policy and policy.annual_entitlement_days is not None:
        configured_days = _decimal(policy.annual_entitlement_days)
        if configured_days != 0 or _decimal(leave_type.default_days_per_year) == 0:
            return configured_days
    return _decimal(leave_type.default_days_per_year)


def _can_manage_leave_settings(user):
    role = normalize_role(getattr(user, "role", None))
    return bool(
        user
        and user.is_active
        and getattr(user, "account_status", None) == "approved"
        and (
            role in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
            or getattr(user, "is_superuser", False) is True
        )
    )


def _hr_leave_summary(leave_request):
    summary = []
    for code in ("ANNUAL", "SICK"):
        leave_type = LeaveType.query.filter_by(code=code).first()
        if leave_type is None:
            continue
        balance = _balance_for(leave_request.user_id, leave_type.id, leave_request.start_date.year)
        entitlement = _decimal(balance.entitled_days if balance else leave_type.default_days_per_year)
        taken = _decimal(balance.used_days if balance else 0)
        carried_over = _decimal(balance.carried_over if balance else 0)
        summary.append({
            "code": code,
            "name": leave_type.name,
            "entitlement": _number(entitlement),
            "requested": _number(leave_request.days_requested) if leave_request.leave_type_id == leave_type.id else 0,
            "taken": _number(taken),
            "balance": float(entitlement + carried_over - taken),
        })
    return summary


def _request_dict(leave_request, include_names=False, include_hr_details=False):
    requester = leave_request.user
    department_record = getattr(requester, "department_record", None)
    stage_role = _LEAVE_STAGE_BY_STATE.get(leave_request.workflow_state)
    reporting_chain = _leave_reporting_chain(requester) if stage_role else {}
    pending_approver = reporting_chain.get(stage_role) if reporting_chain else None
    data = {
        "id": leave_request.id,
        "user_id": leave_request.user_id,
        "manager_id": getattr(requester, "manager_id", None),
        "manager_name": getattr(getattr(requester, "manager", None), "full_name", None),
        "department_name": (
            getattr(department_record, "name", None)
            or getattr(requester, "department", None)
            or "Unassigned"
        ),
        "department_id": getattr(requester, "department_id", None),
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
        "pending_approver_id": pending_approver.id if pending_approver else None,
        "pending_approver_name": pending_approver.full_name if pending_approver else None,
        "approval_steps": [
            {
                "stage_role": step.stage_role,
                "actor_id": step.actor_id,
                "actor_name": step.actor.full_name if step.actor else None,
                "decision": step.decision,
                "decision_comment": step.decision_comment,
                "signature": step.signature,
                "decided_at": step.decided_at.isoformat() if step.decided_at else None,
            }
            for step in LeaveApprovalStep.query
            .filter_by(leave_request_id=leave_request.id)
            .order_by(LeaveApprovalStep.id.asc())
            .all()
        ],
        "handover_gate": handover_gate(leave_request),
        "declaration_accepted": leave_request.declaration_accepted,
        "employee_signature": leave_request.employee_signature,
        "declaration_date": leave_request.declaration_date.isoformat() if leave_request.declaration_date else None,
        "manual_days_override": _number(leave_request.manual_days_override),
        "manual_days_reason": leave_request.manual_days_reason,
        "supervisor_name": leave_request.supervisor_name,
        "supervisor_signature": leave_request.supervisor_signature,
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
        data["requester_name"] = requester.full_name
        data["type_name"] = leave_request.leave_type.name
    if include_hr_details:
        data["hr_leave_summary"] = _hr_leave_summary(leave_request)
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
    role = normalize_role(getattr(user, "role", None))
    if role in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
        return True
    chain = _leave_reporting_chain(leave_request.user)
    return bool(chain and any(manager.id == user.id for manager in chain.values()))


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
    report = HandoverReport.query.filter_by(leave_request_id=leave_request.id).first()
    return not bool(report and report.submitted_at)


def _notify_approvers(user, leave_request):
    chain = _leave_reporting_chain(user)
    if chain is None:
        recipient_ids = []
    elif chain:
        first_stage = next(iter(chain))
        recipient_ids = [chain[first_stage].id]
    else:
        recipient_ids = [
            admin.id
            for admin in User.query.filter(
                db.func.upper(User.role).in_(("HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN")),
                User.is_active.is_(True),
                User.account_status == "approved",
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
            entitled_days=_annual_entitlement(leave_type),
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


@leave_bp.get("/admin/policies")
@jwt_required()
def get_admin_leave_policies():
    actor = _current_user()
    if not _can_manage_leave_settings(actor):
        return _error("You are not authorized to manage leave policies", 403)
    policies = []
    for leave_type in LeaveType.query.order_by(LeaveType.name.asc()).all():
        if leave_type.code.upper() == "UNPAID":
            continue
        policy = LeavePolicy.query.filter_by(leave_type_id=leave_type.id).first()
        policies.append({
            "leave_type_id": leave_type.id,
            "name": leave_type.name,
            "code": leave_type.code,
            "annual_entitlement_days": _number(_annual_entitlement(leave_type)),
            "max_carryover": _number(policy.max_carryover) if policy else 0,
            "notice_days_required": policy.notice_days_required if policy else 0,
            "min_service_months": policy.min_service_months if policy else 0,
            "gender_restriction": policy.gender_restriction if policy else None,
        })
    return jsonify({"data": policies, "message": "Leave policies retrieved"})


@leave_bp.patch("/admin/policies/<int:leave_type_id>")
@jwt_required()
def update_admin_leave_policy(leave_type_id):
    actor = _current_user()
    if not _can_manage_leave_settings(actor):
        return _error("You are not authorized to manage leave policies", 403)
    leave_type = db.session.get(LeaveType, leave_type_id)
    if not leave_type or leave_type.code.upper() == "UNPAID":
        return _error("Paid leave type not found", 404)
    payload = request.get_json(silent=True) or {}
    try:
        annual_days = Decimal(str(payload.get("annual_entitlement_days")))
        if not annual_days.is_finite() or annual_days < 0 or annual_days > 366:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        return _error("annual_entitlement_days must be between 0 and 366", 422)
    try:
        carryover_days = Decimal(str(payload.get("max_carryover", 0)))
        notice_days = int(payload.get("notice_days_required", 0))
        service_months = int(payload.get("min_service_months", 0))
        if not carryover_days.is_finite() or carryover_days < 0 or carryover_days > 366:
            raise ValueError
        if not 0 <= notice_days <= 365 or not 0 <= service_months <= 1200:
            raise ValueError
    except (InvalidOperation, TypeError, ValueError):
        return _error("Carryover, notice days, or service months are invalid", 422)
    gender_restriction = payload.get("gender_restriction") or None
    if gender_restriction not in {None, "Male", "Female"}:
        return _error("gender_restriction must be Male, Female, or blank", 422)

    policy = LeavePolicy.query.filter_by(leave_type_id=leave_type.id).first()
    if not policy:
        policy = LeavePolicy(leave_type_id=leave_type.id)
        db.session.add(policy)
    old_days = _annual_entitlement(leave_type)
    policy.annual_entitlement_days = annual_days
    policy.accrual_rate = annual_days
    policy.max_carryover = carryover_days
    policy.notice_days_required = notice_days
    policy.min_service_months = service_months
    policy.gender_restriction = gender_restriction
    leave_type.default_days_per_year = annual_days
    current_year = date.today().year
    LeaveBalance.query.filter_by(
        leave_type_id=leave_type.id,
        year=current_year,
        is_manual_override=False,
    ).update({"entitled_days": annual_days}, synchronize_session=False)
    db.session.add(AuditLog(
        actor_id=actor.id,
        action="leave_policy_updated",
        entity="LeavePolicy",
        entity_id=str(leave_type.id),
        event_metadata={
            "leave_type": leave_type.name,
            "previous_annual_entitlement_days": _number(old_days),
            "annual_entitlement_days": _number(annual_days),
        },
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update annual leave allocation")
        return _error("Unable to update the leave policy", 500)
    return jsonify({
        "data": {
            "leave_type_id": leave_type.id,
            "name": leave_type.name,
            "code": leave_type.code,
            "annual_entitlement_days": _number(annual_days),
            "max_carryover": _number(carryover_days),
            "notice_days_required": notice_days,
            "min_service_months": service_months,
            "gender_restriction": gender_restriction,
        },
        "message": "Leave policy updated",
    })


@leave_bp.get("/admin/requests")
@jwt_required()
def get_admin_leave_requests():
    actor = _current_user()
    if not _can_manage_leave_settings(actor):
        return _error("You are not authorized to view employee leave history", 403)
    try:
        page_number = max(1, int(request.args.get("page", 1)))
        page_size = min(100, max(1, int(request.args.get("per_page", 50))))
    except (TypeError, ValueError):
        return _error("page and per_page must be integers", 422)

    query = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id)
    query = query.filter(db.func.lower(User.role).in_(("employee", "manager")))
    employee_search = (request.args.get("employee") or "").strip()
    if employee_search:
        pattern = f"%{employee_search}%"
        query = query.filter(
            (User.full_name.ilike(pattern))
            | (User.employee_id.ilike(pattern))
        )
    leave_type_id = request.args.get("leave_type_id", type=int)
    if leave_type_id:
        query = query.filter(LeaveRequest.leave_type_id == leave_type_id)
    status = (request.args.get("status") or "").strip().lower()
    if status:
        if status not in {"pending", "approved", "rejected", "cancelled"}:
            return _error("status must be pending, approved, rejected, or cancelled", 422)
        query = query.filter(LeaveRequest.status == status)
    year_value = (request.args.get("year") or "").strip()
    if year_value:
        try:
            year = int(year_value)
            if year < 2000 or year > 9998:
                raise ValueError
        except ValueError:
            return _error("year must be a valid four-digit year", 422)
        query = query.filter(
            LeaveRequest.end_date >= date(year, 1, 1),
            LeaveRequest.start_date < date(year + 1, 1, 1),
        )

    total = query.count()
    rows = query.order_by(LeaveRequest.applied_at.desc()).offset(
        (page_number - 1) * page_size
    ).limit(page_size).all()
    requests_data = []
    for leave_request in rows:
        row = _request_dict(leave_request, include_names=True)
        requests_data.append({
            key: row.get(key)
            for key in (
                "id", "user_id", "requester_name", "department_name",
                "leave_type_id", "type_name", "start_date", "end_date",
                "days_requested", "reason", "status", "workflow_state",
                "decision_comment", "applied_at", "decided_at",
            )
        })
    return jsonify({
        "data": requests_data,
        "pagination": {
            "page": page_number,
            "per_page": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
        "message": "Employee leave history retrieved",
    })


@leave_bp.get("/admin/balances")
@jwt_required()
def get_admin_leave_balances():
    actor = _current_user()
    if not _can_manage_leave_settings(actor):
        return _error("You are not authorized to view employee leave balances", 403)
    try:
        year = int(request.args.get("year", date.today().year))
        if year < 2000 or year > 9999:
            raise ValueError
    except (TypeError, ValueError):
        return _error("year must be a valid four-digit year", 422)

    employees = [
        employee for employee in User.query.filter_by(is_active=True, account_status="approved").all()
        if normalize_role(employee.role) in {"EMPLOYEE", "MANAGER"}
    ]
    employee_ids = {employee.id for employee in employees}
    leave_types = [
        leave_type for leave_type in LeaveType.query.order_by(LeaveType.name.asc()).all()
        if leave_type.code.upper() != "UNPAID"
    ]
    balances = {
        (balance.user_id, balance.leave_type_id): balance
        for balance in LeaveBalance.query.filter(
            LeaveBalance.year == year,
            LeaveBalance.user_id.in_(employee_ids),
        ).all()
    }
    added_balances = False
    for employee in employees:
        for leave_type in leave_types:
            key = (employee.id, leave_type.id)
            if key not in balances:
                balance = LeaveBalance(
                    user_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=year,
                    entitled_days=_annual_entitlement(leave_type),
                    used_days=Decimal("0.00"),
                    pending_days=Decimal("0.00"),
                    carried_over=Decimal("0.00"),
                )
                db.session.add(balance)
                db.session.flush()
                balances[key] = balance
                added_balances = True
    if added_balances:
        db.session.commit()

    rows = []
    for employee in employees:
        for leave_type in leave_types:
            balance = balances[(employee.id, leave_type.id)]
            rows.append({
                "user_id": employee.id,
                "employee_name": employee.full_name,
                "employee_id": employee.employee_id,
                "department": employee.department_record.name if employee.department_record else employee.department,
                "year": year,
                **_balance_dict(balance),
            })
    return jsonify({"data": rows, "message": "Employee leave balances retrieved"})


@leave_bp.patch("/admin/balances/<int:user_id>/<int:leave_type_id>")
@jwt_required()
def update_admin_leave_balance(user_id, leave_type_id):
    actor = _current_user()
    if not _can_manage_leave_settings(actor):
        return _error("You are not authorized to adjust leave balances", 403)
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 3 or len(reason) > 500:
        return _error("A reason between 3 and 500 characters is required", 422)
    employee = db.session.get(User, user_id)
    leave_type = db.session.get(LeaveType, leave_type_id)
    if (
        not employee
        or not employee.is_active
        or employee.account_status != "approved"
        or normalize_role(employee.role) not in {"EMPLOYEE", "MANAGER"}
        or not leave_type
        or leave_type.code.upper() == "UNPAID"
    ):
        return _error("Employee or paid leave type not found", 404)
    try:
        year = int(payload.get("year", date.today().year))
        if year < 2000 or year > 9999:
            raise ValueError
    except (TypeError, ValueError):
        return _error("year must be a valid four-digit year", 422)
    balance = _balance_for(employee.id, leave_type.id, year)
    if not balance:
        balance = LeaveBalance(
            user_id=employee.id,
            leave_type_id=leave_type.id,
            year=year,
            entitled_days=_annual_entitlement(leave_type),
            used_days=Decimal("0.00"),
            pending_days=Decimal("0.00"),
            carried_over=Decimal("0.00"),
        )
        db.session.add(balance)
        db.session.flush()

    before = {
        "entitled_days": _number(balance.entitled_days),
        "used_days": _number(balance.used_days),
        "carried_over": _number(balance.carried_over),
    }
    fields = {
        "entitled_days": "entitled_days",
        "used_days": "used_days",
        "carried_over": "carried_over",
    }
    try:
        for field, model_field in fields.items():
            if field not in payload:
                continue
            value = Decimal(str(payload[field]))
            if not value.is_finite() or value < 0 or value > 366:
                raise InvalidOperation
            setattr(balance, model_field, value)
    except (InvalidOperation, TypeError, ValueError):
        db.session.rollback()
        return _error("Balance values must be between 0 and 366", 422)

    if not any(field in payload for field in fields):
        db.session.rollback()
        return _error("At least one balance value is required", 422)
    if "entitled_days" in payload or "carried_over" in payload:
        balance.is_manual_override = True
    after = {
        "entitled_days": _number(balance.entitled_days),
        "used_days": _number(balance.used_days),
        "carried_over": _number(balance.carried_over),
    }
    db.session.add(AuditLog(
        actor_id=actor.id,
        action="employee_leave_balance_adjusted",
        entity="LeaveBalance",
        entity_id=str(balance.id),
        event_metadata={
            "employee_id": employee.id,
            "leave_type_id": leave_type.id,
            "year": year,
            "reason": reason.strip(),
            "before": before,
            "after": after,
        },
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to adjust employee leave balance")
        return _error("Unable to save the leave balance adjustment", 500)
    return jsonify({"data": {**_balance_dict(balance), "user_id": employee.id, "year": year}, "message": "Leave balance adjusted"})


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
        reporting_chain = _leave_reporting_chain(user)
        if reporting_chain is None:
            return _error(
                "Your active department assignment must have a complete, valid reporting chain before leave can be requested",
                409,
            )
        policy = LeavePolicy.query.filter_by(leave_type_id=leave_type.id).first()
        if not policy:
            policy = LeavePolicy(
                leave_type_id=leave_type.id,
                accrual_rate=leave_type.default_days_per_year or 0,
                annual_entitlement_days=leave_type.default_days_per_year or 0,
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
        balance = None
        if leave_type.code != "UNPAID":
            balance = _balance_for(user.id, leave_type.id, today.year)
            if not balance:
                balance = LeaveBalance(
                    user_id=user.id,
                    leave_type_id=leave_type.id,
                    year=today.year,
                    entitled_days=_annual_entitlement(leave_type),
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
            workflow_state=(
                "handover_pending"
                if working_days > 2
                else _initial_leave_workflow_state(reporting_chain)
            ),
            declaration_accepted=bool(payload.get("declaration", payload.get("declaration_accepted", False))),
            employee_signature=(payload.get("employee_signature") or "").strip() or None,
            declaration_date=_parse_date(payload.get("declaration_date"), "declaration_date") if payload.get("declaration_date") else None,
            manual_days_override=payload.get("number_of_days_override"),
            manual_days_reason=(payload.get("number_of_days_reason") or "").strip() or None,
        )
        db.session.add(leave_request)
        db.session.flush()
        report_payload = payload.get("handover_report_details")
        report_required = working_days > 3 and leave_type.code.upper() not in {"SICK", "UNPAID"}
        if report_required:
            report_errors = validate_handover_submission(leave_request, report_payload)
            if report_errors:
                db.session.rollback()
                return jsonify({
                    "data": None,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "A complete handover report is required before leave submission",
                        "fields": report_errors,
                    },
                }), 422
            report = HandoverReport(
                leave_request_id=leave_request.id,
                version="v1",
                summary=(report_payload.get("summary") or "").strip(),
                submitted_at=datetime.utcnow(),
            )
            db.session.add(report)
            db.session.flush()
            _apply_handover_payload(report, report_payload)
            report.submitted_at = datetime.utcnow()
        elif payload.get("supporting_attachments_expected"):
            db.session.add(HandoverReport(
                leave_request_id=leave_request.id,
                version="v1",
                summary=(leave_request.handover_report or payload.get("supporting_info") or "Supporting documents for leave request").strip(),
            ))
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
    full_name = (payload.get("full_name") or "").strip()
    signature_date = payload.get("signature_date")
    if not full_name or not signature or not signature_date:
        return _error("full_name, signature, and signature_date are required", 422)
    if full_name != user.full_name or signature != user.full_name:
        return _error("The delegate signature must match your full name", 422)
    try:
        signature_date = _parse_date(signature_date, "signature_date")
    except ValueError as error:
        return _error(str(error), 422)
    if signature_date > date.today():
        return _error("signature_date cannot be in the future", 422)

    leave_request.handover_name = full_name
    leave_request.handover_statement = statement
    leave_request.handover_agreed_at = datetime.utcnow()
    leave_request.handover_signature = signature
    leave_request.handover_signature_date = signature_date
    if leave_request.workflow_state == "handover_pending":
        reporting_chain = _leave_reporting_chain(leave_request.user)
        if reporting_chain is None:
            db.session.rollback()
            return _error(
                "The employee's reporting chain is no longer valid; contact an administrator",
                409,
            )
        transition(leave_request, "handover_complete", user, {"signature": signature})
        leave_request.workflow_state = _initial_leave_workflow_state(reporting_chain)
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
    role = normalize_role(getattr(user, "role", None))
    requests = LeaveRequest.query.filter_by(handover_user_id=user.id).order_by(
        LeaveRequest.applied_at.desc()
    ).all()
    return jsonify({
        "data": [_request_dict(item, include_names=True, include_hr_details=role in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}) for item in requests],
        "message": "Delegations retrieved",
    })


@leave_bp.get("/requests/pending")
@jwt_required()
def get_pending_requests():
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    role = normalize_role(getattr(user, "role", None))
    assignment = get_active_assignment(user.id)
    is_org_approver = bool(
        assignment
        and assignment.organizational_role
        in {"general_manager", "department_manager", "team_leader"}
    )
    is_hr = role in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
    if not is_org_approver and not is_hr:
        return _error("Manager or HR administrator access is required", 403)
    query = LeaveRequest.query.filter(LeaveRequest.status == "pending")
    allowed_states = set()
    if is_hr:
        allowed_states.add("hr_verification")
    if is_org_approver:
        expected_stage = {
            "team_leader": "team_leader_pending",
            "department_manager": "department_manager_pending",
            "general_manager": "general_manager_pending",
        }[assignment.organizational_role]
        allowed_states.add(expected_stage)
        if (
            assignment.organizational_role == "department_manager"
            and is_group_leader_substitute(user, assignment.department_id)
        ):
            allowed_states.add("team_leader_pending")
    query = query.filter(LeaveRequest.workflow_state.in_(allowed_states))
    requests = [
        item
        for item in query.order_by(LeaveRequest.applied_at.asc()).all()
        if (
            (is_hr and item.workflow_state == "hr_verification")
            or (
                item.workflow_state in _LEAVE_STAGE_BY_STATE
                and _leave_approval_actor_matches(
                    item, user, _LEAVE_STAGE_BY_STATE[item.workflow_state]
                )
            )
        )
    ]
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
    role = normalize_role(getattr(user, "role", None))
    assignment = get_active_assignment(user.id)
    is_hr = role in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
    if not is_hr and not (
        assignment
        and assignment.organizational_role
        in {"general_manager", "department_manager", "team_leader"}
    ):
        return _error("Manager or HR administrator access is required", 403)
    query = LeaveRequest.query.filter(
        LeaveRequest.status.in_(("pending", "approved"))
    )
    if not is_hr and assignment.organizational_role == "department_manager":
        query = query.join(User, LeaveRequest.user_id == User.id).filter(
            User.department_id == assignment.department_id
        )
    elif not is_hr and assignment.organizational_role == "team_leader":
        query = query.join(User, LeaveRequest.user_id == User.id).filter(
            User.manager_id == user.id
        )
    requests = query.order_by(LeaveRequest.start_date.asc(), LeaveRequest.applied_at.asc()).all()
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
    role = normalize_role(getattr(user, "role", None))
    is_hr = role in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
    chain = _leave_reporting_chain(item.user)
    can_view_as_manager = bool(chain and any(
        manager.id == user.id for manager in chain.values()
    ))
    if item.user_id != user.id and not is_hr and not can_view_as_manager:
        return _error("You are not allowed to view this request", 403)
    return jsonify({
        "data": _request_dict(item, include_hr_details=is_hr),
        "message": "Leave request retrieved",
    })


@leave_bp.post("/requests/<int:request_id>/cancel")
@jwt_required()
def cancel_request(request_id):
    user = _current_user()
    if not user:
        return _error("User not found or inactive", 404)
    try:
        item = LeaveRequest.query.filter_by(id=request_id).with_for_update().first()
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
        item = LeaveRequest.query.filter_by(id=request_id).with_for_update().first()
        if not item:
            return _error("Leave request not found", 404)
        if item.status != "pending":
            return _error(f"Only pending requests can be {action}d", 409)
        stage_role = _LEAVE_STAGE_BY_STATE.get(item.workflow_state)
        if not stage_role:
            return _error("This request is not awaiting organizational approval", 409)
        if not _leave_approval_actor_matches(item, user, stage_role):
            return _error(
                f"Only the assigned {stage_role.replace('_', ' ')} can decide this request",
                403,
            )

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

        db.session.add(LeaveApprovalStep(
            leave_request_id=item.id,
            stage_role=stage_role,
            actor_id=user.id,
            decision=action,
            decision_comment=comment or None,
            signature=(payload.get("signature") or user.full_name).strip(),
        ))
        if action == "reject":
            leave_type = db.session.get(LeaveType, item.leave_type_id)
            balance = _balance_for(item.user_id, item.leave_type_id, item.start_date.year)
            if leave_type and leave_type.code != "UNPAID" and not balance:
                db.session.rollback()
                return _error("Leave balance not found", 409)
            if balance:
                balance.pending_days = max(
                    Decimal("0.00"),
                    _decimal(balance.pending_days) - _decimal(item.days_requested),
                )
            item.status = "rejected"
            item.decided_at = datetime.utcnow()
            title = "Leave request rejected"
            message = "Leave request rejected"
        elif next_state == "deferred":
            item.status = "pending"
            item.decided_at = None
            title = "Leave request deferred"
            message = "Your leave request was deferred with a reason"
        else:
            item.status = "pending"
            item.decided_at = None
            if next_state == "hr_verification":
                title = "Leave request sent to HR"
                message = "General Manager approval completed; HR verification is next"
            else:
                next_stage = _LEAVE_STAGE_BY_STATE[next_state]
                title = "Leave request forwarded"
                message = (
                    f"Leave request approved by {stage_role.replace('_', ' ')} "
                    f"and forwarded to {next_stage.replace('_', ' ')}"
                )
        item.supervisor_decision = action
        item.approver_id = user.id
        item.decision_comment = comment
        item.supervisor_name = user.full_name
        item.supervisor_signature = (payload.get("signature") or user.full_name).strip()
        item.supervisor_decision_date = datetime.utcnow()
        db.session.add(Notification(
            user_id=item.user_id,
            title=title,
            body=message,
            is_read=False,
        ))
        if next_state == "hr_verification":
            hr_verifiers = User.query.filter(
                db.func.upper(User.role).in_(("HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN")),
                User.is_active.is_(True),
                User.account_status == "approved",
            ).all()
            for verifier in hr_verifiers:
                db.session.add(Notification(
                    user_id=verifier.id,
                    title="Leave request requires HR verification",
                    body=f"{item.user.full_name}'s leave request #{item.id} completed organizational approval.",
                    is_read=False,
                ))
        db.session.add(_audit(
            user.id,
            f"leave_request_{action}",
            item.id,
            {
                "stage_role": stage_role,
                "decision_comment": comment,
                "workflow_state": next_state,
                "signature": item.supervisor_signature,
            },
        ))
        db.session.commit()
        return jsonify({
            "data": _request_dict(item),
            "message": message,
        })
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to record leave approval decision")
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
    role = normalize_role(getattr(user, "role", None)) if user else None
    if not user or role not in {"HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
        return _error("HR administrator access is required", 403)
    item = LeaveRequest.query.filter_by(id=request_id).with_for_update().first()
    if not item:
        return _error("Leave request not found", 404)
    if item.workflow_state != "hr_verification" or item.status != "pending":
        return jsonify({"data": None, "error": {"code": "INVALID_TRANSITION", "message": "Request is not ready for HR verification"}}), 409
    chain = _leave_reporting_chain(item.user)
    if chain is None:
        return jsonify({
            "data": None,
            "error": {
                "code": "VERIFICATION_INCOMPLETE",
                "message": "The requester no longer has a valid reporting chain",
            },
        }), 409
    approval_steps = {
        step.stage_role: step
        for step in LeaveApprovalStep.query.filter_by(
            leave_request_id=item.id
        ).all()
    }
    missing = [
        stage.replace("_", " ")
        for stage in chain
        if stage not in approval_steps or approval_steps[stage].decision != "approve"
    ]
    if missing:
        return jsonify({
            "data": None,
            "error": {
                "code": "VERIFICATION_INCOMPLETE",
                "message": ", ".join(missing) + " approval is required",
            },
        }), 409
    try:
        leave_type = db.session.get(LeaveType, item.leave_type_id)
        balance = _balance_for(item.user_id, item.leave_type_id, item.start_date.year)
        if leave_type and leave_type.code != "UNPAID" and not balance:
            db.session.rollback()
            return _error("Leave balance not found", 409)
        transition(item, "verify", user, {"verification_status": "verified"})
        if balance:
            days = _decimal(item.days_requested)
            balance.pending_days = max(
                Decimal("0.00"), _decimal(balance.pending_days) - days
            )
            balance.used_days = _decimal(balance.used_days) + days
        item.status = "approved"
        item.decided_at = datetime.utcnow()
        item.hr_manager = user.full_name
        item.hr_verification_date = datetime.utcnow()
        item.hr_verification_status = "verified"
        db.session.add(Notification(user_id=item.user_id, title="Leave completed", body="Your leave request has been verified by HR.", is_read=False))
        db.session.commit()
        return jsonify({"data": _request_dict(item), "message": "Leave request verified and completed"})
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to complete HR leave verification")
        return _error("Unable to complete HR verification", 500)