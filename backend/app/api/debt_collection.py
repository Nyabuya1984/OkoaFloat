import csv
import io
import re
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import pandas as pd
from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import contains_eager

from app.extensions import db
from app.models import (
    DebtCollectionAssignment,
    DebtCollectionAuditLog,
    DebtCollectionCallLog,
    DebtCollectionCreditRating,
    DebtCollectionDebtor,
    DebtCollectionDutyAssignment,
    DebtCollectionFollowUpSchedule,
    DebtCollectionImportIssue,
    DebtCollectionImportJob,
    DebtCollectionLoan,
    DebtCollectionLoanStatusHistory,
    DebtCollectionPayment,
    Role,
    User,
    UserRole,
)
from app.utils.rbac import can, enforce_permission
from app.utils.organization import (
    get_active_assignment,
    infer_organizational_role,
    is_group_leader_substitute,
)


debt_collection_bp = Blueprint("debt_collection", __name__, url_prefix="/api/debt-collection")
collector_bp = Blueprint("collector", __name__, url_prefix="/api/collector")

ACTIVE_STATUSES = {"active", "overdue", "in_negotiation", "promise_to_pay", "legal"}
LOAN_STATUSES = ACTIVE_STATUSES | {"settled", "written_off"}
DEBTOR_FIELDS = {
    "first_name", "other_names", "agent_msisdn", "owner_msisdn", "operator_msisdn",
    "agent_no", "store_number", "business_name", "location",
}
REQUIRED_DEBTOR_FIELDS = {"first_name", "agent_msisdn", "agent_no", "business_name"}
REQUIRED_IMPORT_FIELDS = REQUIRED_DEBTOR_FIELDS | {"loan_amount"}
EXPORT_FIELDS = [
    "first_name", "other_names", "agent_msisdn", "owner_msisdn", "operator_msisdn",
    "agent_no", "store_number", "business_name", "location", "loan_amount",
    "amount_paid", "loan_balance", "loan_date", "last_interest_calc_date",
    "no_of_days", "days_outstanding", "status", "collector_name", "created_at",
    "record_created_at",
]


def _user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _collector_is_assignable(viewer, collector):
        return _can_manage(viewer) or (
            _is_team_leader(viewer) and collector.id in _team_member_ids(viewer)
        )


def _available_collectors(viewer):
        candidates = User.query.filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
            User.account_status == "approved",
            User.id.in_(_debt_collection_user_ids()),
        ).order_by(User.full_name.asc()).all()
        team_member_ids = _team_member_ids(viewer)
        return [
            user for user in candidates
            if _is_debt_collector(user)
            and (_can_view_all_debt_collection(viewer) or user.id in team_member_ids)
        ]


def _debt_collection_user_ids():
    return db.session.query(UserRole.user_id).join(
        Role, Role.id == UserRole.role_id
    ).filter(Role.name == "debt_collection")


def _is_general_manager(viewer):
    assignment = get_active_assignment(viewer.id) if viewer else None
    return bool(assignment and assignment.organizational_role == "general_manager")


def _is_hr_or_system_admin(viewer):
    if not viewer:
        return False
    role = str(viewer.role or "").strip().lower().replace("-", "_")
    return bool(
        viewer.is_superuser
        or role in {"hr_admin", "system_admin", "super_admin"}
    )


def _has_debt_collection_duty(viewer, *duties):
    if not viewer:
        return False
    return DebtCollectionDutyAssignment.query.filter(
        DebtCollectionDutyAssignment.user_id == viewer.id,
        DebtCollectionDutyAssignment.duty.in_(duties),
    ).first() is not None


def _is_departmental_manager(viewer):
    if not viewer or not can(viewer, "debt_collection.*"):
        return False
    assignment = get_active_assignment(viewer.id)
    if assignment and assignment.organizational_role == "department_manager":
        return assignment.role_name == "debt_collection" or "debt" in (
            assignment.department_name or ""
        ).lower()
    return _has_debt_collection_duty(
        viewer, "departmental_manager", "department_manager"
    )


def _is_team_leader(viewer):
    if not viewer or not can(viewer, "debt_collection.*"):
        return False
    assignment = get_active_assignment(viewer.id)
    if _has_debt_collection_duty(viewer, "group_leader", "team_leader"):
        return True
    return bool(
        (assignment and assignment.organizational_role == "team_leader")
        or is_group_leader_substitute(
            viewer, assignment.department_id if assignment else None
        )
        or infer_organizational_role(viewer.job_position_title) == "team_leader"
    )


def _is_debt_collector(viewer):
    if (
        not viewer
        or not can(viewer, "debt_collection.*")
        or _is_departmental_manager(viewer)
        or _is_team_leader(viewer)
    ):
        return False
    assignment = get_active_assignment(viewer.id)
    if assignment and assignment.organizational_role == "field_agent":
        return assignment.role_name == "debt_collection"
    return _has_debt_collection_duty(viewer, "debt_collector_agent")


def _team_member_ids(viewer):
    """Return the debt-collection agents directly reporting to a team leader."""
    if not _is_team_leader(viewer):
        return set()
    assignment = get_active_assignment(viewer.id)
    is_substitute = is_group_leader_substitute(
        viewer, assignment.department_id if assignment else None
    )
    if is_substitute:
        query = User.query.filter(User.department_id == assignment.department_id)
    else:
        query = User.query.filter(User.manager_id == viewer.id)
    query = query.filter(
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
        User.account_status == "approved",
    )
    if assignment and assignment.department_id:
        query = query.filter(User.department_id == assignment.department_id)
    debt_collection_duty_ids = db.session.query(
        DebtCollectionDutyAssignment.user_id
    ).filter(
        DebtCollectionDutyAssignment.duty == "debt_collector_agent"
    )
    query = query.filter(or_(
        User.id.in_(_debt_collection_user_ids()),
        User.id.in_(debt_collection_duty_ids),
    ))
    return {user_id for (user_id,) in query.with_entities(User.id).all()}


def _team_collector_ids(viewer):
    if not _is_team_leader(viewer):
        return {viewer.id} if viewer else set()
    return {viewer.id, *_team_member_ids(viewer)}


def _can_view_all_debt_collection(viewer):
    return (
        _can_manage(viewer)
        or _is_general_manager(viewer)
        or _is_hr_or_system_admin(viewer)
    )


def _can_view_all_debtors(viewer):
    return _can_view_all_debt_collection(viewer) or _is_team_leader(viewer)


def _is_super_admin(viewer):
    if not viewer:
        return False
    role = str(viewer.role or "").strip().lower().replace("-", "_")
    return bool(viewer.is_superuser or role in {"system_admin", "super_admin"})


def _can_permanently_delete(viewer):
    return bool(
        viewer
        and viewer.is_currently_active()
        and viewer.account_status == "approved"
        and (_is_general_manager(viewer) or _is_super_admin(viewer))
    )


def _error(message, status=400):
    return jsonify({"data": None, "error": {"message": message}}), status


def _json_object():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


@debt_collection_bp.before_request
def enforce_dashboard_feature_access():
    verify_jwt_in_request()
    viewer = _user()
    if (
        viewer
        and viewer.is_currently_active()
        and viewer.account_status == "approved"
        and _is_general_manager(viewer)
    ):
        return None
    if (
        request.method == "DELETE"
        and viewer
        and viewer.is_currently_active()
        and viewer.account_status == "approved"
        and _is_super_admin(viewer)
        and request.endpoint in {
            "debt_collection.permanently_delete_loan",
            "debt_collection.permanently_delete_debtor",
            "debt_collection.permanently_delete_loans_bulk",
        }
    ):
        return None
    if (
        request.method == "PATCH"
        and viewer
        and _can_permanently_delete(viewer)
        and request.endpoint in {
            "debt_collection.update_debtor",
            "debt_collection.update_loan",
        }
    ):
        return None
    if request.method == "GET" and viewer and _is_hr_or_system_admin(viewer):
        return None
    return enforce_permission("debt_collection.*")


@collector_bp.before_request
def enforce_collector_dashboard_access():
    return enforce_permission("debt_collection.related.*")


def _can_manage(viewer):
    if _is_general_manager(viewer):
        return True
    if not can(viewer, "debt_collection.*"):
        return False
    if viewer.is_superuser or str(viewer.role or "").strip().lower() in {
        "system_admin", "super_admin"
    }:
        return True
    return _is_departmental_manager(viewer)


def _can_view_team(viewer):
    return _is_team_leader(viewer)


def _can_allocate(viewer):
    return _can_manage(viewer)


def _allocation_required(viewer):
    if request.method == "GET" and (_can_allocate(viewer) or _is_team_leader(viewer)):
        return None
    if not _can_allocate(viewer):
        return _error("Only managers and administrators can allocate debt collection accounts", 403)
    return None


def _visible_loans(
    viewer, archived=False, include_unassigned=False, include_all_debtors=False
):
    query = DebtCollectionLoan.query.join(DebtCollectionLoan.debtor).filter(
        DebtCollectionLoan.is_deleted.is_(False),
        DebtCollectionLoan.is_archived.is_(archived),
        DebtCollectionDebtor.is_deleted.is_(False),
    )
    if not _can_view_all_debtors(viewer) or (
        not _can_view_all_debt_collection(viewer) and not include_all_debtors
    ):
        collector_ids = _team_collector_ids(viewer)
        assigned_to_team = DebtCollectionLoan.assignments.any(and_(
            DebtCollectionAssignment.collector_id.in_(collector_ids),
            DebtCollectionAssignment.is_active.is_(True),
        ))
        if include_unassigned and _is_team_leader(viewer):
            query = query.filter(or_(
                assigned_to_team,
                ~DebtCollectionLoan.assignments.any(
                    DebtCollectionAssignment.is_active.is_(True)
                ),
            ))
        else:
            query = query.filter(assigned_to_team)
    return query


def _visible_debtors(viewer, include_all_debtors=False):
    query = DebtCollectionDebtor.query.filter(DebtCollectionDebtor.is_deleted.is_(False))
    if not _can_view_all_debtors(viewer) or (
        not _can_view_all_debt_collection(viewer) and not include_all_debtors
    ):
        collector_ids = _team_collector_ids(viewer)
        query = query.filter(
            DebtCollectionDebtor.assignments.any(
                and_(
                    DebtCollectionAssignment.collector_id.in_(collector_ids),
                    DebtCollectionAssignment.is_active.is_(True),
                )
            )
        )
    return query


def _money(value, field, *, positive=False):
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError(f"{field} must be a valid amount")
    try:
        normalized = re.sub(r"(?i)\b(?:KES|KSH)\b", "", str(value))
        normalized = normalized.replace(",", "").replace(" ", "").strip()
        amount = Decimal(normalized)
        rounded = amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid amount")
    if not amount.is_finite() or amount != rounded or amount < 0 or (positive and amount == 0):
        constraint = "greater than zero" if positive else "a non-negative amount with at most two decimals"
        raise ValueError(f"{field} must be {constraint}")
    return amount


def _date(value, field):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must use YYYY-MM-DD format")


def _import_date(value, field):
    if value in (None, ""):
        return None
    try:
        return _import_timestamp(value, field).date()
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field} must be a valid Excel or calendar date")


def _import_timestamp(value, field):
    try:
        numeric_value = Decimal(str(value).strip())
        if numeric_value.is_finite() and 0 < numeric_value < 100000:
            return pd.to_datetime(
                float(numeric_value),
                unit="D",
                origin="1899-12-30",
                errors="raise",
            )
    except (InvalidOperation, TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(value, errors="raise")
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field} must be a valid Excel or calendar date")


def _import_datetime(value, field):
    if value in (None, ""):
        return None
    timestamp = _import_timestamp(value, field)
    return _datetime(timestamp.to_pydatetime(), field)


def _import_days(value):
    if value in (None, ""):
        return 0
    try:
        days = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("no_of_days must be a non-negative whole number")
    if not days.is_finite() or days < 0 or days != days.to_integral_value():
        raise ValueError("no_of_days must be a non-negative whole number")
    return int(days)


def _datetime(value, field):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{field} must be a valid ISO datetime")
    else:
        raise ValueError(f"{field} must be a valid ISO datetime")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _time(value, field):
    try:
        return time.fromisoformat(str(value)).strftime("%H:%M")
    except (TypeError, ValueError):
        raise ValueError(f"{field} must use HH:MM format")


def _status(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _debtor_dict(debtor):
    return {
        "id": debtor.id,
        "first_name": debtor.first_name,
        "other_names": debtor.other_names,
        "agent_name": " ".join(part for part in (debtor.first_name, debtor.other_names) if part),
        "agent_msisdn": debtor.agent_msisdn,
        "agent_number": debtor.agent_msisdn,
        "owner_msisdn": debtor.owner_msisdn,
        "operator_msisdn": debtor.operator_msisdn,
        "agent_no": debtor.agent_no,
        "store_number": debtor.store_number,
        "business_name": debtor.business_name,
        "location": debtor.location,
        "business_location": debtor.location,
        "created_at": debtor.created_at.isoformat() if debtor.created_at else None,
        "updated_at": debtor.updated_at.isoformat() if debtor.updated_at else None,
    }


def _loan_dict(loan, related=None):
    if related is None:
        last_call = loan.call_logs.order_by(
            db.desc("created_at"), db.desc("id")
        ).first()
        rating = loan.ratings.order_by(
            db.desc("computed_at"), db.desc("id")
        ).first()
        assignment = loan.assignments.filter_by(is_active=True).order_by(
            DebtCollectionAssignment.assigned_at.desc(), DebtCollectionAssignment.id.desc()
        ).first()
        next_payment = loan.follow_ups.filter_by(
            status="Pending", follow_up_type="PTP"
        ).order_by(DebtCollectionFollowUpSchedule.due_at.asc()).first()
        loans_borrowed = loan.debtor.loans.filter_by(is_deleted=False).count()
        collector_name = assignment.collector.full_name if assignment else None
        next_payment_amount = (
            next_payment.source_call.promised_amount
            if next_payment and next_payment.source_call
            else None
        )
    else:
        last_call = related["last_calls"].get(loan.id)
        rating = related["ratings"].get(loan.id)
        assignment = related["assignments"].get(loan.id)
        next_payment = related["next_payments"].get(loan.id)
        loans_borrowed = related["loan_counts"].get(loan.debtor_id, 0)
        collector_name = related["collector_names"].get(loan.id)
        next_payment_amount = related["next_payment_amounts"].get(loan.id)

    return {
        "id": loan.id,
        "debtor_id": loan.debtor_id,
        "loan_amount": str(loan.loan_amount),
        "amount_paid": str(loan.amount_paid),
        "loan_balance": str(max(Decimal("0.00"), loan.loan_balance)),
        "loans_borrowed": loans_borrowed,
        "loan_date": loan.loan_date.isoformat() if loan.loan_date else None,
        "last_interest_calc_date": loan.last_interest_calc_date.isoformat() if loan.last_interest_calc_date else None,
        "no_of_days": loan.no_of_days if loan.no_of_days is not None else (
            max(0, (date.today() - loan.loan_date).days) if loan.loan_date else 0
        ),
        "days_outstanding": max(0, (date.today() - loan.loan_date).days) if loan.loan_date else loan.no_of_days,
        "status": _status(loan.status),
        "is_archived": loan.is_archived,
        "first_name": loan.debtor.first_name,
        "other_names": loan.debtor.other_names,
        "agent_name": " ".join(part for part in (loan.debtor.first_name, loan.debtor.other_names) if part),
        "agent_number": loan.debtor.agent_msisdn,
        "agent_no": loan.debtor.agent_no,
        "store_number": loan.debtor.store_number,
        "business_name": loan.debtor.business_name,
        "business_location": loan.debtor.location,
        "owner_msisdn": loan.debtor.owner_msisdn,
        "operator_msisdn": loan.debtor.operator_msisdn,
        "record_created_at": loan.debtor.created_at.isoformat() if loan.debtor.created_at else None,
        "credit_rating": rating.grade if rating else None,
        "credit_score": rating.score if rating else None,
        "collector_id": assignment.collector_id if assignment else None,
        "collector_name": collector_name,
        "assignment_reason": assignment.reason if assignment else None,
        "assigned_at": assignment.assigned_at.isoformat() if assignment else None,
        "next_payment_date": next_payment.due_at.date().isoformat() if next_payment else None,
        "next_payment_time": next_payment.due_at.strftime("%H:%M") if next_payment else None,
        "next_payment_amount": str(next_payment_amount)
        if next_payment_amount is not None
        else None,
        "last_contact": last_call.created_at.date().isoformat() if last_call else None,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "updated_at": loan.updated_at.isoformat() if loan.updated_at else None,
    }


def _loan_dicts(loans):
    loans = list(loans)
    if not loans:
        return []

    loan_ids = [loan.id for loan in loans]
    debtor_ids = {loan.debtor_id for loan in loans}
    last_calls = {}
    for call in DebtCollectionCallLog.query.filter(
        DebtCollectionCallLog.loan_id.in_(loan_ids)
    ).order_by(
        DebtCollectionCallLog.loan_id,
        DebtCollectionCallLog.created_at.desc(),
        DebtCollectionCallLog.id.desc(),
    ).all():
        last_calls.setdefault(call.loan_id, call)

    ratings = {}
    for rating in DebtCollectionCreditRating.query.filter(
        DebtCollectionCreditRating.loan_id.in_(loan_ids)
    ).order_by(
        DebtCollectionCreditRating.loan_id,
        DebtCollectionCreditRating.computed_at.desc(),
        DebtCollectionCreditRating.id.desc(),
    ).all():
        ratings.setdefault(rating.loan_id, rating)

    assignments = {}
    collector_names = {}
    assignment_rows = db.session.query(
        DebtCollectionAssignment,
        User.full_name,
    ).join(
        User, User.id == DebtCollectionAssignment.collector_id
    ).filter(
        DebtCollectionAssignment.loan_id.in_(loan_ids),
        DebtCollectionAssignment.is_active.is_(True),
    ).order_by(
        DebtCollectionAssignment.loan_id,
        DebtCollectionAssignment.assigned_at.desc(),
        DebtCollectionAssignment.id.desc(),
    ).all()
    for assignment, collector_name in assignment_rows:
        assignments.setdefault(assignment.loan_id, assignment)
        collector_names.setdefault(assignment.loan_id, collector_name)

    next_payments = {}
    next_payment_amounts = {}
    follow_up_rows = db.session.query(
        DebtCollectionFollowUpSchedule,
        DebtCollectionCallLog.promised_amount,
    ).outerjoin(
        DebtCollectionCallLog,
        DebtCollectionCallLog.id == DebtCollectionFollowUpSchedule.source_call_log_id,
    ).filter(
        DebtCollectionFollowUpSchedule.loan_id.in_(loan_ids),
        DebtCollectionFollowUpSchedule.status == "Pending",
        DebtCollectionFollowUpSchedule.follow_up_type == "PTP",
    ).order_by(
        DebtCollectionFollowUpSchedule.loan_id,
        DebtCollectionFollowUpSchedule.due_at.asc(),
        DebtCollectionFollowUpSchedule.id.asc(),
    ).all()
    for follow_up, promised_amount in follow_up_rows:
        next_payments.setdefault(follow_up.loan_id, follow_up)
        next_payment_amounts.setdefault(follow_up.loan_id, promised_amount)

    loan_counts = dict(db.session.query(
        DebtCollectionLoan.debtor_id,
        func.count(DebtCollectionLoan.id),
    ).filter(
        DebtCollectionLoan.debtor_id.in_(debtor_ids),
        DebtCollectionLoan.is_deleted.is_(False),
    ).group_by(DebtCollectionLoan.debtor_id).all())

    related = {
        "last_calls": last_calls,
        "ratings": ratings,
        "assignments": assignments,
        "collector_names": collector_names,
        "next_payments": next_payments,
        "next_payment_amounts": next_payment_amounts,
        "loan_counts": loan_counts,
    }
    return [_loan_dict(loan, related) for loan in loans]


def _duplicate_loan_ids(loans):
    debtor_ids = {loan.debtor_id for loan in loans}
    if not debtor_ids:
        return set()
    rows = db.session.query(
        DebtCollectionLoan.id,
        DebtCollectionDebtor.agent_no,
        DebtCollectionDebtor.agent_msisdn,
        DebtCollectionDebtor.business_name,
    ).join(
        DebtCollectionDebtor, DebtCollectionLoan.debtor_id == DebtCollectionDebtor.id
    ).filter(
        DebtCollectionDebtor.id.in_(debtor_ids),
        DebtCollectionDebtor.is_deleted.is_(False),
        DebtCollectionLoan.is_deleted.is_(False),
        DebtCollectionLoan.is_archived.is_(False),
    ).all()
    groups = {}
    for loan_id, agent_no, agent_msisdn, business_name in rows:
        key = (
            " ".join((agent_no or "").split()).casefold(),
            re.sub(r"\D", "", agent_msisdn or ""),
            " ".join((business_name or "").split()).casefold(),
        )
        groups.setdefault(key, []).append(loan_id)
    return {
        loan_id
        for matching_ids in groups.values()
        if len(matching_ids) > 1
        for loan_id in matching_ids
    }


def _call_dict(call):
    return {
        "id": call.id,
        "debtor_id": call.debtor_id,
        "loan_id": call.loan_id,
        "debtor_name": " ".join(
            part for part in (call.debtor.first_name, call.debtor.other_names) if part
        ),
        "agent_number": call.debtor.agent_msisdn,
        "business_name": call.debtor.business_name,
        "collector_id": call.collector_id,
        "collector_name": call.collector.full_name,
        "outcome": call.outcome,
        "notes": call.notes,
        "promised_date": call.promised_date.isoformat() if call.promised_date else None,
        "promised_time": call.promised_time,
        "promised_amount": str(call.promised_amount) if call.promised_amount is not None else None,
        "callback_date": call.callback_date.isoformat() if call.callback_date else None,
        "callback_time": call.callback_time,
        "amount_paid": str(call.amount_paid or Decimal("0.00")),
        "loan_amount": str(call.loan.loan_amount) if call.loan else None,
        "amount_paid_to_date": str(call.loan.amount_paid) if call.loan else None,
        "loan_balance": str(max(Decimal("0.00"), call.loan.loan_balance)) if call.loan else None,
        "loan_status": _status(call.loan.status) if call.loan else None,
        "contact_date": call.created_at.date().isoformat() if call.created_at else None,
        "contact_time": call.created_at.strftime("%H:%M:%S") if call.created_at else None,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


def _xlsx_bytes(rows, headers):
    values = [headers] + [[row.get(header, "") for header in headers] for row in rows]
    sheet_rows = []
    for row_index, row in enumerate(values, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            column = ""
            number = column_index
            while number:
                number, remainder = divmod(number - 1, 26)
                column = chr(65 + remainder) + column
            text = escape(str(value if value is not None else ""))
            cells.append(f'<c r="{column}{row_index}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    workbook = '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Debt Portfolio" sheetId="1" r:id="rId1"/></sheets></workbook>'
    relationships = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook_relationships = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _xlsx_rows(stream):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(stream) as workbook:
        shared = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared = ["".join(text.text or "" for text in item.iter(f"{namespace}t")) for item in shared_root.findall(f"{namespace}si")]
        worksheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    matrix = []
    for row in worksheet.iter(f"{namespace}row"):
        values = {}
        for cell in row.findall(f"{namespace}c"):
            reference = cell.get("r", "")
            letters = re.match(r"[A-Z]+", reference)
            if not letters:
                continue
            column = 0
            for letter in letters.group(0):
                column = column * 26 + ord(letter) - 64
            kind = cell.get("t")
            raw = cell.findtext(f"{namespace}v", default="")
            if kind == "s" and raw:
                raw = shared[int(raw)]
            elif kind == "inlineStr":
                inline = cell.find(f"{namespace}is")
                raw = "".join(text.text or "" for text in inline.iter(f"{namespace}t")) if inline is not None else ""
            values[column - 1] = raw
        if values:
            matrix.append([values.get(index, "") for index in range(max(values) + 1)])
    if not matrix:
        return []
    headers = [str(value).strip() for value in matrix[0]]
    return [dict(zip(headers, row)) for row in matrix[1:] if any(value != "" for value in row)]


def _normalize_import_header(value):
    header = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value).strip().lower().lstrip("\ufeff"),
    ).strip("_")
    return {
        "wner_msisdn": "owner_msisdn",
        "operator_msid": "operator_msisdn",
        "operator_msisd": "operator_msisdn",
        "amount_p": "amount_paid",
        "mount_paid": "amount_paid",
        "a_mount_paid": "amount_paid",
        "last_interest_calc_da": "last_interest_calc_date",
        "loan_balance_a": "loan_balance",
    }.get(header, header)


def _import_records_from_frame(frame):
    header_index = None
    headers = None
    for index, values in frame.iterrows():
        normalized = [_normalize_import_header(value) for value in values]
        if REQUIRED_IMPORT_FIELDS.issubset(normalized):
            header_index = index
            headers = normalized
            break
    if header_index is None or headers is None:
        required = ", ".join(sorted(REQUIRED_IMPORT_FIELDS))
        raise ValueError(f"The file is missing required columns: {required}")

    records = []
    for values in frame.iloc[header_index + 1 :].itertuples(index=False, name=None):
        row = {
            header: "" if pd.isna(value) else str(value).strip()
            for header, value in zip(headers, values)
            if header
        }
        if any(value != "" for value in row.values()):
            records.append(row)
    return records


def _import_rows(upload):
    filename = (upload.filename or "").lower()
    if filename.endswith(".csv"):
        raw_csv = upload.stream.read()
        try:
            csv_text = raw_csv.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                csv_text = raw_csv.decode("utf-16")
            except UnicodeDecodeError:
                csv_text = raw_csv.decode("cp1252")

        lines = csv_text.splitlines(keepends=True)
        for line_index, line in enumerate(lines[:50]):
            for delimiter in (",", ";", "\t", "|"):
                headers = next(csv.reader([line], delimiter=delimiter), [])
                if REQUIRED_IMPORT_FIELDS.issubset(
                    [_normalize_import_header(header) for header in headers]
                ):
                    try:
                        frame = pd.read_csv(
                            io.StringIO("".join(lines[line_index:])),
                            dtype=str,
                            keep_default_na=False,
                            header=None,
                            sep=delimiter,
                            engine="python",
                        )
                        return _import_records_from_frame(frame)
                    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError):
                        break

        for delimiter in (",", ";", "\t", "|"):
            try:
                frame = pd.read_csv(
                    io.StringIO(csv_text),
                    dtype=str,
                    keep_default_na=False,
                    header=None,
                    sep=delimiter,
                    engine="python",
                )
                return _import_records_from_frame(frame)
            except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError):
                continue
        required = ", ".join(sorted(REQUIRED_IMPORT_FIELDS))
        raise ValueError(f"The CSV file could not be read or is missing required columns: {required}")
    elif filename.endswith(".xlsx"):
        try:
            workbook = pd.ExcelFile(upload.stream)
            frame = None
            for sheet_name in workbook.sheet_names:
                sheet = workbook.parse(
                    sheet_name=sheet_name,
                    dtype=str,
                    keep_default_na=False,
                    header=None,
                )
                if any(
                    REQUIRED_IMPORT_FIELDS.issubset(
                        [_normalize_import_header(value) for value in row]
                    )
                    for _, row in sheet.iterrows()
                ):
                    frame = sheet
                    break
            if frame is None:
                raise ValueError("The Excel workbook does not contain a debt portfolio sheet")
        except ValueError:
            raise
        except (ImportError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            raise ValueError("The Excel file could not be read")
    else:
        raise ValueError("Upload a CSV or .xlsx file")
    return _import_records_from_frame(frame)


def _audit(viewer, entity, entity_id, action, before=None, after=None):
    db.session.add(
        DebtCollectionAuditLog(
            user_id=viewer.id,
            entity=entity,
            action=action,
            before=before,
            after=after,
        )
    )


def _management_required(viewer):
    if request.method == "GET" and _can_view_all_debt_collection(viewer):
        return None
    if not _can_manage(viewer):
        return _error("Only managers and administrators can manage debtors and loans", 403)
    return None


def _record_management_required(viewer, loan):
    if _can_manage(viewer) or _can_permanently_delete(viewer):
        return None
    return _error("Only managers and administrators can update debt collection records", 403)


def _can_manage_debtor_record(viewer, debtor):
    return _can_manage(viewer) or _can_permanently_delete(viewer)


def _record_creation_required(viewer):
    if _can_manage(viewer):
        return None
    return _error("Only team leaders and managers can create debt collection records", 403)


def _loan_for_viewer(viewer, loan_id):
    return _visible_loans(viewer).filter(DebtCollectionLoan.id == loan_id).first()


def _filtered_loans(
    viewer, archived=False, include_unassigned=False, include_all_debtors=False
):
    query = _visible_loans(
        viewer,
        archived=archived,
        include_unassigned=include_unassigned,
        include_all_debtors=include_all_debtors,
    ).options(contains_eager(DebtCollectionLoan.debtor))
    requested_status = request.args.get("status")
    if requested_status:
        query = query.filter(DebtCollectionLoan.status.ilike(_status(requested_status)))
    store_number = request.args.get("store_number", "").strip()
    location = request.args.get("location", "").strip()
    if store_number:
        query = query.filter(DebtCollectionDebtor.store_number.ilike(f"%{store_number}%"))
    if location:
        query = query.filter(DebtCollectionDebtor.location.ilike(f"%{location}%"))
    business_name = request.args.get("business_name", "").strip()
    if business_name:
        query = query.filter(DebtCollectionDebtor.business_name.ilike(f"%{business_name}%"))
    agent_name = request.args.get("agent_name", "").strip()
    if agent_name:
        name_term = f"%{agent_name}%"
        query = query.filter(or_(
            DebtCollectionDebtor.first_name.ilike(name_term),
            DebtCollectionDebtor.other_names.ilike(name_term),
            func.concat(
                DebtCollectionDebtor.first_name, " ", DebtCollectionDebtor.other_names
            ).ilike(name_term),
        ))
    agent_number = request.args.get("agent_number", "").strip()
    if agent_number:
        query = query.filter(DebtCollectionDebtor.agent_msisdn.ilike(f"%{agent_number}%"))
    collector_name = request.args.get("collector_name", "").strip()
    collector_number = request.args.get("collector_number", "").strip()
    if collector_name or collector_number:
        collector_match = []
        if collector_name:
            collector_match.extend((
                User.full_name.ilike(f"%{collector_name}%"),
                User.employee_id.ilike(f"%{collector_name}%"),
            ))
        if collector_number:
            collector_match.append(User.phone_number.ilike(f"%{collector_number}%"))
        query = query.filter(DebtCollectionLoan.assignments.any(and_(
            DebtCollectionAssignment.is_active.is_(True),
            DebtCollectionAssignment.collector.has(or_(*collector_match)),
        )))
    search = request.args.get("q", "").strip()
    if search:
        term = f"%{search}%"
        query = query.filter(db.or_(
            DebtCollectionDebtor.first_name.ilike(term),
            DebtCollectionDebtor.other_names.ilike(term),
            DebtCollectionDebtor.agent_no.ilike(term),
            DebtCollectionDebtor.business_name.ilike(term),
            DebtCollectionDebtor.agent_msisdn.ilike(term),
            DebtCollectionDebtor.store_number.ilike(term),
            DebtCollectionLoan.assignments.any(and_(
                DebtCollectionAssignment.is_active.is_(True),
                DebtCollectionAssignment.collector.has(or_(
                    User.full_name.ilike(term),
                    User.employee_id.ilike(term),
                    User.phone_number.ilike(term),
                )),
            )),
        ))
    collector_id = request.args.get("collector_id")
    if collector_id:
        try:
            collector_id = int(collector_id)
        except ValueError:
            raise ValueError("collector_id must be an integer")
        query = query.filter(DebtCollectionLoan.assignments.any(and_(
            DebtCollectionAssignment.collector_id == collector_id,
            DebtCollectionAssignment.is_active.is_(True),
        )))

    collector_capacity = request.args.get("collector_capacity")
    if collector_capacity not in (None, ""):
        try:
            maximum_active_accounts = int(collector_capacity)
        except ValueError:
            raise ValueError("collector_capacity must be a whole number")
        if maximum_active_accounts < 0:
            raise ValueError("collector_capacity must be a non-negative whole number")
        active_loads = dict(db.session.query(
            DebtCollectionAssignment.collector_id,
            func.count(DebtCollectionAssignment.id).label("active_accounts"),
        ).join(DebtCollectionLoan).join(DebtCollectionDebtor).filter(
            DebtCollectionAssignment.is_active.is_(True),
            DebtCollectionLoan.is_deleted.is_(False),
            DebtCollectionLoan.is_archived.is_(False),
            DebtCollectionDebtor.is_deleted.is_(False),
        ).group_by(DebtCollectionAssignment.collector_id).all())
        active_collector_ids = [
            collector_id for (collector_id,) in User.query.filter(
                User.is_active.is_(True),
                User.is_archived.is_(False),
                User.is_deleted.is_(False),
                User.account_status == "approved",
                User.id.in_(_debt_collection_user_ids()),
            ).with_entities(User.id).all()
        ]
        eligible_collector_ids = [
            collector_id for collector_id in active_collector_ids
            if active_loads.get(collector_id, 0) <= maximum_active_accounts
        ]
        if eligible_collector_ids:
            query = query.filter(or_(
                ~DebtCollectionLoan.assignments.any(
                    DebtCollectionAssignment.is_active.is_(True)
                ),
                DebtCollectionLoan.assignments.any(and_(
                    DebtCollectionAssignment.collector_id.in_(eligible_collector_ids),
                    DebtCollectionAssignment.is_active.is_(True),
                )),
            ))
        else:
            query = query.filter(db.false())

    loans = query.order_by(DebtCollectionLoan.created_at.desc(), DebtCollectionLoan.id.desc()).all()
    for parameter, comparison in (("min_balance", lambda balance, value: balance >= value),
                                  ("max_balance", lambda balance, value: balance <= value)):
        raw_value = request.args.get(parameter)
        if raw_value not in (None, ""):
            amount = _money(raw_value, parameter)
            loans = [
                loan for loan in loans
                if comparison(max(Decimal("0.00"), loan.loan_balance), amount)
            ]
    overdue_days = request.args.get("overdue_days")
    if overdue_days not in (None, ""):
        try:
            minimum_days = int(overdue_days)
        except ValueError:
            raise ValueError("overdue_days must be a whole number")
        if minimum_days < 0:
            raise ValueError("overdue_days must be a non-negative whole number")
        loans = [
            loan for loan in loans
            if _status(loan.status) == "overdue"
            and (date.today() - loan.loan_date).days >= minimum_days
        ]
    return loans


def _parse_debtor(payload, debtor=None):
    values = {}
    fields = DEBTOR_FIELDS if debtor is None else DEBTOR_FIELDS.intersection(payload)
    for field in fields:
        if field not in payload:
            continue
        value = payload[field]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        value = value.strip() if isinstance(value, str) else None
        if field in REQUIRED_DEBTOR_FIELDS and not value and (debtor is None or field in payload):
            raise ValueError(f"{field} is required")
        values[field] = value or None
    if debtor is None and REQUIRED_DEBTOR_FIELDS - values.keys():
        raise ValueError("first_name, agent_msisdn, agent_no, and business_name are required")
    return values


def _parse_loan(payload, loan=None):
    current_amount = loan.loan_amount if loan else Decimal("0.00")
    current_paid = loan.amount_paid if loan else Decimal("0.00")
    amount = _money(payload.get("loan_amount", current_amount), "loan_amount", positive=True)
    paid = _money(payload.get("amount_paid", current_paid), "amount_paid")
    if paid > amount:
        raise ValueError("amount_paid cannot exceed loan_amount")
    status = _status(payload.get("status", loan.status if loan else "active"))
    if status not in LOAN_STATUSES:
        raise ValueError("status must be active, overdue, in_negotiation, promise_to_pay, settled, written_off, or legal")
    if paid == amount:
        status = "settled"
    elif status == "settled":
        raise ValueError("status can be settled only when amount_paid equals loan_amount")
    loan_date = _date(payload.get("loan_date", loan.loan_date if loan else None), "loan_date")
    last_interest_calc_date = payload.get(
        "last_interest_calc_date",
        loan.last_interest_calc_date if loan else None,
    )
    if last_interest_calc_date not in (None, ""):
        last_interest_calc_date = _date(last_interest_calc_date, "last_interest_calc_date")
    else:
        last_interest_calc_date = None
    no_of_days = payload.get("no_of_days", loan.no_of_days if loan else 0)
    try:
        no_of_days = int(no_of_days or 0)
    except (TypeError, ValueError):
        raise ValueError("no_of_days must be a non-negative whole number")
    if no_of_days < 0:
        raise ValueError("no_of_days must be a non-negative whole number")
    return {
        "loan_amount": amount,
        "amount_paid": paid,
        "loan_date": loan_date,
        "last_interest_calc_date": last_interest_calc_date,
        "no_of_days": no_of_days,
        "status": status,
    }


@debt_collection_bp.get("/summary")
def debt_collection_summary():
    viewer = _user()
    include_records = request.args.get("include_records", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    loans_query = _visible_loans(viewer)
    duties = [
        assignment.duty
        for assignment in DebtCollectionDutyAssignment.query.filter_by(user_id=viewer.id).order_by( DebtCollectionDutyAssignment.duty).all()
    ]
    if include_records:
        loans = loans_query.options(contains_eager(DebtCollectionLoan.debtor)).all()
        total_outstanding = sum(
            (max(Decimal("0.00"), loan.loan_balance) for loan in loans),
            Decimal("0.00"),
        )
        active_count = sum(1 for loan in loans if _status(loan.status) in ACTIVE_STATUSES)
        overdue_count = sum(1 for loan in loans if _status(loan.status) == "overdue")
        recovered_to_date = sum((loan.amount_paid for loan in loans), Decimal("0.00"))
        duplicate_ids = _duplicate_loan_ids(loans)
        loan_records = _loan_dicts(loans)
    else:
        loan_balance = func.coalesce(
            DebtCollectionLoan.imported_balance,
            DebtCollectionLoan.loan_amount - DebtCollectionLoan.amount_paid,
        )
        nonnegative_balance = case(
            (loan_balance < 0, 0),
            else_=loan_balance,
        )
        normalized_status = func.replace(
            func.lower(func.trim(DebtCollectionLoan.status)),
            " ",
            "_",
        )
        (
            total_outstanding,
            active_count,
            overdue_count,
            recovered_to_date,
        ) = loans_query.with_entities(
            func.coalesce(func.sum(nonnegative_balance), 0),
            func.coalesce(func.sum(case((normalized_status.in_(ACTIVE_STATUSES), 1), else_=0)), 0),
            func.coalesce(func.sum(case((normalized_status == "overdue", 1), else_=0)), 0),
            func.coalesce(func.sum(DebtCollectionLoan.amount_paid), 0),
        ).one()
        loans = []
        duplicate_ids = set()
        loan_records = []
    total_outstanding = Decimal(str(total_outstanding or 0)).quantize(Decimal("0.01"))
    recovered_to_date = Decimal(str(recovered_to_date or 0)).quantize(Decimal("0.01"))
    return jsonify({
        "data": {
            "total_outstanding": str(total_outstanding),
            "active_accounts": int(active_count),
            "overdue_accounts": int(overdue_count),
            "recovered_to_date": str(recovered_to_date),
            "records": [
                {**record, "is_duplicate": loan.id in duplicate_ids}
                for loan, record in zip(loans, loan_records)
            ],
            "permissions": {
                "duties": duties,
                "can_manage": _can_manage(viewer),
                "can_allocate": _can_allocate(viewer),
                "can_view_all": _can_view_all_debt_collection(viewer),
                "can_view_all_debtors": _can_view_all_debtors(viewer),
                "can_view_team": _can_view_team(viewer),
                "is_general_manager": _is_general_manager(viewer),
                "can_permanently_delete": _can_permanently_delete(viewer),
                "can_collect": can(viewer, "debt_collection.related.*"),
            },
        },
        "error": None,
    })


@debt_collection_bp.get("/records")
@debt_collection_bp.get("/loans")
def list_loans():
    viewer = _user()
    archived = request.args.get("archived", "false").lower()
    if archived not in {"true", "false"}:
        return _error("archived must be true or false", 422)
    is_archived = archived == "true"
    include_unassigned = request.args.get("include_unassigned", "false").lower()
    if include_unassigned not in {"true", "false"}:
        return _error("include_unassigned must be true or false", 422)
    if include_unassigned == "true" and not _can_allocate(viewer):
        return _error("Only team leaders and managers can view unassigned accounts", 403)
    if is_archived:
        if not _is_general_manager(viewer):
            denied = _management_required(viewer)
            if denied:
                return denied
    try:
        loans = _filtered_loans(
            viewer,
            archived=is_archived,
            include_unassigned=include_unassigned == "true",
            include_all_debtors=_is_team_leader(viewer),
        )
    except ValueError as error:
        return _error(str(error), 422)
    duplicate_ids = _duplicate_loan_ids(loans)
    records = _loan_dicts(loans)
    return jsonify({"data": [
        {**record, "is_duplicate": loan.id in duplicate_ids}
        for loan, record in zip(loans, records)
    ], "error": None})


@debt_collection_bp.get("/loans/archived")
def list_archived_loans():
    viewer = _user()
    if not _is_general_manager(viewer):
        denied = _management_required(viewer)
        if denied:
            return denied
    try:
        loans = _filtered_loans(viewer, archived=True)
    except ValueError as error:
        return _error(str(error), 422)
    duplicate_ids = _duplicate_loan_ids(loans)
    records = _loan_dicts(loans)
    return jsonify({"data": [
        {**record, "is_duplicate": loan.id in duplicate_ids}
        for loan, record in zip(loans, records)
    ], "error": None})


@debt_collection_bp.get("/debtors")
def list_debtors():
    viewer = _user()
    debtors = _visible_debtors(
        viewer, include_all_debtors=_is_team_leader(viewer)
    ).order_by(DebtCollectionDebtor.created_at.desc()).all()
    return jsonify({"data": [_debtor_dict(debtor) for debtor in debtors], "error": None})


@debt_collection_bp.post("/debtors")
def create_debtor():
    viewer = _user()
    denied = _record_creation_required(viewer)
    if denied:
        return denied
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    try:
        debtor = DebtCollectionDebtor(**_parse_debtor(payload))
    except ValueError as error:
        return _error(str(error), 422)
    db.session.add(debtor)
    try:
        db.session.flush()
        _audit(viewer, "DebtCollectionDebtor", debtor.id, "created", after=_debtor_dict(debtor))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("A debtor with this agent number already exists", 409)
    return jsonify({"data": _debtor_dict(debtor), "error": None}), 201


@debt_collection_bp.get("/debtors/<int:debtor_id>")
def get_debtor(debtor_id):
    debtor = _visible_debtors(_user()).filter_by(id=debtor_id).first()
    if not debtor:
        return _error("Debtor not found", 404)
    return jsonify({"data": _debtor_dict(debtor), "error": None})


@debt_collection_bp.patch("/debtors/<int:debtor_id>")
def update_debtor(debtor_id):
    viewer = _user()
    debtor = DebtCollectionDebtor.query.filter_by(id=debtor_id, is_deleted=False).first()
    if not debtor:
        return _error("Debtor not found", 404)
    if not _can_manage_debtor_record(viewer, debtor):
        return _error("You can only manage debtors whose accounts are unassigned or assigned within your team", 403)
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    if not isinstance(payload, dict) or set(payload) - DEBTOR_FIELDS:
        return _error("Request contains unsupported debtor fields", 422)
    before = _debtor_dict(debtor)
    try:
        for field, value in _parse_debtor(payload, debtor).items():
            setattr(debtor, field, value)
    except ValueError as error:
        return _error(str(error), 422)
    _audit(viewer, "DebtCollectionDebtor", debtor.id, "updated", before=before, after=_debtor_dict(debtor))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("A debtor with this agent number already exists", 409)
    return jsonify({"data": _debtor_dict(debtor), "error": None})


@debt_collection_bp.delete("/debtors/<int:debtor_id>")
def delete_debtor(debtor_id):
    viewer = _user()
    debtor = DebtCollectionDebtor.query.filter_by(id=debtor_id, is_deleted=False).first()
    if not debtor:
        return _error("Debtor not found", 404)
    if not _can_manage_debtor_record(viewer, debtor):
        return _error("You can only manage debtors whose accounts are unassigned or assigned within your team", 403)
    before = _debtor_dict(debtor)
    debtor.is_deleted = True
    for loan in debtor.loans.filter_by(is_deleted=False):
        loan.is_deleted = True
    _audit(viewer, "DebtCollectionDebtor", debtor.id, "deleted", before=before)
    db.session.commit()
    return jsonify({"data": {"id": debtor.id, "deleted": True}, "error": None})


@debt_collection_bp.post("/loans")
def create_loan():
    viewer = _user()
    denied = _record_creation_required(viewer)
    if denied:
        return denied
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    try:
        debtor_id = int(payload.get("debtor_id"))
        values = _parse_loan(payload)
    except (TypeError, ValueError) as error:
        return _error(str(error) or "debtor_id must be an integer", 422)
    if values["status"] == "written_off":
        return _error("Use the write-off approval action to record a loan write-off", 422)
    debtor = DebtCollectionDebtor.query.filter_by(id=debtor_id, is_deleted=False).first()
    if not debtor:
        return _error("Debtor not found", 404)
    if not _can_manage_debtor_record(viewer, debtor):
        return _error("You can only add loans to debtors whose accounts are unassigned or assigned within your team", 403)
    loan = DebtCollectionLoan(debtor_id=debtor.id, **values)
    db.session.add(loan)
    db.session.flush()
    if loan.status != "active":
        db.session.add(DebtCollectionLoanStatusHistory(
            loan_id=loan.id, old_status=None, new_status=loan.status,
            changed_by=viewer.id, reason="Initial status",
        ))
    _audit(viewer, "DebtCollectionLoan", loan.id, "created", after=_loan_dict(loan))
    db.session.commit()
    return jsonify({"data": _loan_dict(loan), "error": None}), 201


@debt_collection_bp.get("/loans/<int:loan_id>")
def get_loan(loan_id):
    viewer = _user()
    loan = _loan_for_viewer(viewer, loan_id)
    if not loan and _can_manage(viewer):
        loan = DebtCollectionLoan.query.join(DebtCollectionLoan.debtor).filter(
            DebtCollectionLoan.id == loan_id,
            DebtCollectionLoan.is_deleted.is_(False),
            DebtCollectionLoan.is_archived.is_(True),
            DebtCollectionDebtor.is_deleted.is_(False),
        ).first()
    if not loan:
        return _error("Loan not found", 404)
    return jsonify({"data": _loan_dict(loan), "error": None})


@debt_collection_bp.patch("/loans/<int:loan_id>")
def update_loan(loan_id):
    viewer = _user()
    query = (
        DebtCollectionLoan.query
        if _can_manage(viewer) or _can_permanently_delete(viewer)
        else _visible_loans(viewer, include_unassigned=True)
    )
    loan = query.filter(
        DebtCollectionLoan.id == loan_id,
        DebtCollectionLoan.is_deleted.is_(False),
        DebtCollectionLoan.is_archived.is_(False),
    ).first()
    if not loan or loan.debtor.is_deleted:
        return _error("Loan not found", 404)
    denied = _record_management_required(viewer, loan)
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    loan_fields = {"loan_amount", "amount_paid", "loan_date", "last_interest_calc_date", "no_of_days", "status"}
    allowed = loan_fields | DEBTOR_FIELDS
    if not isinstance(payload, dict) or set(payload) - allowed:
        return _error("Request contains unsupported loan fields", 422)
    if _status(payload.get("status")) == "written_off":
        return _error("Use the write-off approval action to record a loan write-off", 422)
    before_loan = _loan_dict(loan)
    before_debtor = _debtor_dict(loan.debtor)
    try:
        debtor_values = _parse_debtor(payload, loan.debtor)
        loan_values = _parse_loan(
            {field: value for field, value in payload.items() if field in loan_fields},
            loan,
        )
    except ValueError as error:
        return _error(str(error), 422)
    old_status = _status(loan.status)
    for field, value in debtor_values.items():
        setattr(loan.debtor, field, value)
    for field, value in loan_values.items():
        setattr(loan, field, value)
    if {"loan_amount", "amount_paid"}.intersection(payload):
        loan.imported_balance = None
    if old_status != loan.status:
        db.session.add(DebtCollectionLoanStatusHistory(
            loan_id=loan.id, old_status=old_status, new_status=loan.status,
            changed_by=viewer.id, reason="Loan updated",
        ))
    if debtor_values:
        _audit(viewer, "DebtCollectionDebtor", loan.debtor_id, "updated", before=before_debtor, after=_debtor_dict(loan.debtor))
    _audit(viewer, "DebtCollectionLoan", loan.id, "updated", before=before_loan, after=_loan_dict(loan))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("A debtor with this agent number already exists", 409)
    return jsonify({"data": _loan_dict(loan), "error": None})


@debt_collection_bp.delete("/loans/<int:loan_id>")
def delete_loan(loan_id):
    viewer = _user()
    query = (
        DebtCollectionLoan.query
        if _can_manage(viewer)
        else _visible_loans(viewer, include_unassigned=True)
    )
    loan = query.filter(
        DebtCollectionLoan.id == loan_id,
        DebtCollectionLoan.is_deleted.is_(False),
        DebtCollectionLoan.is_archived.is_(False),
    ).first()
    if not loan or loan.debtor.is_deleted:
        return _error("Loan not found", 404)
    denied = _record_management_required(viewer, loan)
    if denied:
        return denied
    before = _loan_dict(loan)
    loan.is_deleted = True
    _audit(viewer, "DebtCollectionLoan", loan.id, "deleted", before=before)
    db.session.commit()
    return jsonify({"data": {"id": loan.id, "deleted": True}, "error": None})


def _delete_loan_record_permanently(loan):
    loan_id = loan.id
    DebtCollectionAssignment.query.filter_by(loan_id=loan_id).delete(
        synchronize_session=False
    )
    DebtCollectionPayment.query.filter_by(loan_id=loan_id).delete(
        synchronize_session=False
    )
    DebtCollectionLoanStatusHistory.query.filter_by(loan_id=loan_id).delete(
        synchronize_session=False
    )
    DebtCollectionCreditRating.query.filter_by(loan_id=loan_id).update(
        {"loan_id": None}, synchronize_session=False
    )
    DebtCollectionFollowUpSchedule.query.filter_by(loan_id=loan_id).update(
        {"loan_id": None}, synchronize_session=False
    )
    DebtCollectionCallLog.query.filter_by(loan_id=loan_id).update(
        {"loan_id": None}, synchronize_session=False
    )
    db.session.delete(loan)


@debt_collection_bp.delete("/loans/<int:loan_id>/permanent")
def permanently_delete_loan(loan_id):
    viewer = _user()
    loan = DebtCollectionLoan.query.join(DebtCollectionDebtor).filter(
        DebtCollectionLoan.id == loan_id,
        DebtCollectionDebtor.is_deleted.is_(False),
    ).first()
    if not loan:
        return _error("Loan not found", 404)

    if not _can_permanently_delete(viewer):
        if not _is_departmental_manager(viewer):
            return _error(
                "Only super admins and general managers can permanently delete any loan; "
                "department managers can delete duplicates",
                403,
            )
        if loan.is_deleted or loan.is_archived:
            return _error(
                "Department managers can permanently delete active duplicate loans only",
                403,
            )
        if loan.id not in _duplicate_loan_ids([loan]):
            return _error("Department managers can permanently delete duplicate loans only", 403)
        denied = _record_management_required(viewer, loan)
        if denied:
            return denied

    _audit(
        viewer,
        "DebtCollectionLoan",
        loan.id,
        "permanently_deleted",
        before={"id": loan.id, "debtor_id": loan.debtor_id},
        after={"permanently_deleted": True},
    )
    _delete_loan_record_permanently(loan)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("This loan has related records that could not be permanently deleted", 409)
    return jsonify({"data": {
        "id": loan_id,
        "permanently_deleted": True,
    }, "error": None})


@debt_collection_bp.delete("/loans/permanent/bulk")
def permanently_delete_loans_bulk():
    viewer = _user()
    if not _can_permanently_delete(viewer):
        return _error("Only super admins and general managers can permanently delete selected loans", 403)
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    try:
        loan_ids = _archive_loan_ids(payload)
    except ValueError as error:
        return _error(str(error), 422)

    loans = DebtCollectionLoan.query.join(DebtCollectionDebtor).filter(
        DebtCollectionLoan.id.in_(loan_ids),
        DebtCollectionDebtor.is_deleted.is_(False),
    ).order_by(DebtCollectionLoan.id.asc()).with_for_update().all()
    if len(loans) != len(loan_ids):
        db.session.rollback()
        return _error("One or more selected loan entries were not found", 404)

    for loan in loans:
        _audit(
            viewer,
            "DebtCollectionLoan",
            loan.id,
            "permanently_deleted",
            before={"id": loan.id, "debtor_id": loan.debtor_id},
            after={"permanently_deleted": True},
        )
        _delete_loan_record_permanently(loan)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("One or more selected loans have related records that could not be permanently deleted", 409)
    return jsonify({"data": {
        "deleted_ids": loan_ids,
        "permanently_deleted": len(loan_ids),
    }, "error": None})


@debt_collection_bp.delete("/debtors/<int:debtor_id>/permanent")
def permanently_delete_debtor(debtor_id):
    viewer = _user()
    if not _can_permanently_delete(viewer):
        return _error("Only super admins and general managers can permanently delete client records", 403)
    debtor = DebtCollectionDebtor.query.filter_by(id=debtor_id).first()
    if not debtor:
        return _error("Client record not found", 404)

    loans = debtor.loans.all()
    loan_ids = [loan.id for loan in loans]
    call_ids = [
        call_id
        for (call_id,) in DebtCollectionCallLog.query.filter_by(
            debtor_id=debtor.id
        ).with_entities(DebtCollectionCallLog.id).all()
    ]
    before = {
        "id": debtor.id,
        "loan_count": len(loans),
        "call_count": len(call_ids),
    }

    DebtCollectionFollowUpSchedule.query.filter(
        or_(
            DebtCollectionFollowUpSchedule.debtor_id == debtor.id,
            DebtCollectionFollowUpSchedule.loan_id.in_(loan_ids) if loan_ids else False,
            DebtCollectionFollowUpSchedule.source_call_log_id.in_(call_ids) if call_ids else False,
        )
    ).delete(synchronize_session=False)
    if call_ids:
        DebtCollectionCallLog.query.filter(
            DebtCollectionCallLog.parent_call_log_id.in_(call_ids)
        ).update({"parent_call_log_id": None}, synchronize_session=False)
    if loan_ids:
        DebtCollectionAssignment.query.filter(
            DebtCollectionAssignment.loan_id.in_(loan_ids)
        ).delete(synchronize_session=False)
        DebtCollectionPayment.query.filter(
            DebtCollectionPayment.loan_id.in_(loan_ids)
        ).delete(synchronize_session=False)
        DebtCollectionLoanStatusHistory.query.filter(
            DebtCollectionLoanStatusHistory.loan_id.in_(loan_ids)
        ).delete(synchronize_session=False)
    DebtCollectionAssignment.query.filter_by(debtor_id=debtor.id).delete(
        synchronize_session=False
    )
    DebtCollectionCreditRating.query.filter_by(debtor_id=debtor.id).delete(
        synchronize_session=False
    )
    DebtCollectionCallLog.query.filter_by(debtor_id=debtor.id).delete(
        synchronize_session=False
    )
    for loan in loans:
        db.session.delete(loan)

    _audit(
        viewer,
        "DebtCollectionDebtor",
        debtor.id,
        "permanently_deleted",
        before=before,
        after={"permanently_deleted": True},
    )
    db.session.delete(debtor)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("This client has related records that could not be permanently deleted", 409)
    return jsonify({"data": {
        "id": debtor_id,
        "permanently_deleted": True,
    }, "error": None})


def _archive_loan_ids(payload):
    if not isinstance(payload, dict) or set(payload) != {"loan_ids"}:
        raise ValueError("Request body must contain only loan_ids")
    raw_ids = payload["loan_ids"]
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("loan_ids must be a non-empty list of integers")
    if any(isinstance(value, bool) for value in raw_ids):
        raise ValueError("loan_ids must contain integers")
    try:
        loan_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        raise ValueError("loan_ids must contain integers")
    if any(value <= 0 for value in loan_ids) or len(set(loan_ids)) != len(loan_ids):
        raise ValueError("loan_ids must contain unique positive integers")
    return loan_ids


def _set_loans_archived(viewer, loan_ids, archived, *, bulk):
    # Lock and validate the complete selection before changing any row, so a
    # malformed/stale bulk operation cannot leave only part of the selection changed.
    loans = DebtCollectionLoan.query.join(DebtCollectionLoan.debtor).filter(
        DebtCollectionLoan.id.in_(loan_ids),
        DebtCollectionLoan.is_deleted.is_(False),
        DebtCollectionLoan.is_archived.is_(not archived),
        DebtCollectionDebtor.is_deleted.is_(False),
    ).order_by(DebtCollectionLoan.id.asc()).with_for_update().all()
    if len(loans) != len(loan_ids):
        db.session.rollback()
        state = "active" if archived else "archived"
        return _error(f"One or more loans were not found or are not {state}", 404)

    action = "archived" if archived else "restored"
    try:
        results = []
        for loan in loans:
            before = _loan_dict(loan)
            loan.is_archived = archived
            after = _loan_dict(loan)
            _audit(
                viewer,
                "DebtCollectionLoan",
                loan.id,
                action,
                before=before,
                after=after,
            )
            results.append((loan, after))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if bulk:
        data = [after for _, after in results]
    else:
        data = results[0][1]
    return jsonify({"data": data, "error": None})


@debt_collection_bp.post("/loans/<int:loan_id>/archive")
def archive_loan(loan_id):
    viewer = _user()
    denied = _management_required(viewer)
    if denied:
        return denied
    return _set_loans_archived(viewer, [loan_id], archived=True, bulk=False)


@debt_collection_bp.post("/loans/<int:loan_id>/restore")
def restore_loan(loan_id):
    viewer = _user()
    denied = _management_required(viewer)
    if denied:
        return denied
    return _set_loans_archived(viewer, [loan_id], archived=False, bulk=False)


@debt_collection_bp.post("/loans/archive/bulk")
def bulk_archive_loans():
    viewer = _user()
    denied = _management_required(viewer)
    if denied:
        return denied
    try:
        loan_ids = _archive_loan_ids(_json_object())
    except ValueError as error:
        return _error(str(error), 422)
    return _set_loans_archived(viewer, loan_ids, archived=True, bulk=True)


@debt_collection_bp.post("/loans/restore/bulk")
def bulk_restore_loans():
    viewer = _user()
    denied = _management_required(viewer)
    if denied:
        return denied
    try:
        loan_ids = _archive_loan_ids(_json_object())
    except ValueError as error:
        return _error(str(error), 422)
    return _set_loans_archived(viewer, loan_ids, archived=False, bulk=True)


@debt_collection_bp.post("/loans/<int:loan_id>/assignments")
def assign_loan(loan_id):
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    loan = _visible_loans(
        viewer, include_unassigned=_is_team_leader(viewer)
    ).filter(DebtCollectionLoan.id == loan_id).first()
    if not loan or loan.debtor.is_deleted:
        return _error("Loan not found", 404)
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    try:
        collector_id = int(payload.get("collector_id"))
    except (TypeError, ValueError):
        return _error("collector_id must be an integer", 422)
    collector = User.query.filter_by(id=collector_id).first()
    if not collector or not collector.is_currently_active() or collector.account_status != "approved":
        return _error("Active collector not found", 404)
    if not _is_debt_collector(collector):
        return _error("Accounts can only be allocated to debt collection agents", 422)
    if not _collector_is_assignable(viewer, collector):
        return _error("You can only allocate accounts to your direct reports", 403)
    current_assignments = loan.assignments.filter_by(is_active=True).all()
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _error("reason must be text", 422)
    reason = (reason or "").strip()
    if len(reason) > 255:
        return _error("reason must be at most 255 characters", 422)
    if current_assignments and not reason:
        return _error("A reason is required when reassigning an account", 422)
    before = [{"collector_id": item.collector_id, "reason": item.reason} for item in current_assignments]
    for assignment in current_assignments:
        assignment.is_active = False
        assignment.unassigned_at = datetime.utcnow()
    assignment = DebtCollectionAssignment(
        debtor_id=loan.debtor_id,
        loan_id=loan.id,
        collector_id=collector.id,
        assigned_by=viewer.id,
        reason=reason or None,
    )
    db.session.add(assignment)
    _audit(
        viewer, "DebtCollectionLoan", loan.id, "assigned",
        before=before or None,
        after={"collector_id": collector.id, "reason": assignment.reason},
    )
    db.session.commit()
    return jsonify({"data": {
        "id": assignment.id,
        "loan_id": loan.id,
        "collector_id": collector.id,
        "assigned_by": viewer.id,
        "is_active": assignment.is_active,
    }, "error": None}), 201


@debt_collection_bp.get("/collectors")
def list_collectors():
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    collectors = _available_collectors(viewer)
    return jsonify({"data": [{
        "id": collector.id,
        "full_name": collector.full_name,
        "department": collector.department,
        "active_accounts": DebtCollectionAssignment.query.join(
            DebtCollectionLoan
        ).join(DebtCollectionDebtor).filter(
            DebtCollectionAssignment.collector_id == collector.id,
            DebtCollectionAssignment.is_active.is_(True),
            DebtCollectionLoan.is_deleted.is_(False),
            DebtCollectionLoan.is_archived.is_(False),
            DebtCollectionDebtor.is_deleted.is_(False),
        ).count(),
    } for collector in collectors], "error": None})


@debt_collection_bp.get("/assignments")
def list_assignments():
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    assignments = DebtCollectionAssignment.query.join(DebtCollectionLoan).join(
        DebtCollectionDebtor
    ).filter(
        DebtCollectionAssignment.is_active.is_(True),
        DebtCollectionLoan.is_deleted.is_(False),
        DebtCollectionLoan.is_archived.is_(False),
        DebtCollectionDebtor.is_deleted.is_(False),
    )
    if _is_team_leader(viewer):
        assignments = assignments.filter(
            DebtCollectionAssignment.collector_id.in_(_team_collector_ids(viewer))
        )
    assignments = assignments.order_by(DebtCollectionAssignment.assigned_at.desc()).all()
    return jsonify({"data": [{
        "id": assignment.id,
        "loan_id": assignment.loan_id,
        "debtor_id": assignment.debtor_id,
        "collector_id": assignment.collector_id,
        "collector_name": assignment.collector.full_name,
        "assigned_at": assignment.assigned_at.isoformat(),
        "reason": assignment.reason,
        "loan": _loan_dict(assignment.loan),
    } for assignment in assignments], "error": None})


@debt_collection_bp.post("/assignments/bulk")
def bulk_assign_loans():
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    payload = _json_object()
    if payload is None or not isinstance(payload.get("loan_ids"), list):
        return _error("loan_ids must be a list and collector_id is required", 422)
    try:
        collector_id = int(payload.get("collector_id"))
        loan_ids = {int(value) for value in payload["loan_ids"]}
    except (TypeError, ValueError):
        return _error("loan_ids and collector_id must contain integers", 422)
    if not loan_ids:
        return _error("Select at least one loan to assign", 422)
    collector = User.query.filter_by(id=collector_id).first()
    if not collector or not collector.is_currently_active() or collector.account_status != "approved":
        return _error("Active collector not found", 404)
    if not _is_debt_collector(collector):
        return _error("Accounts can only be allocated to debt collection agents", 422)
    if not _collector_is_assignable(viewer, collector):
        return _error("You can only allocate accounts to your direct reports", 403)
    loans = _visible_loans(
        viewer, include_unassigned=_is_team_leader(viewer)
    ).filter(DebtCollectionLoan.id.in_(loan_ids)).all()
    if len(loans) != len(loan_ids):
        return _error("One or more selected loans could not be found", 404)
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _error("reason must be text", 422)
    reason = (reason or "").strip()
    if len(reason) > 255:
        return _error("reason must be at most 255 characters", 422)
    if any(loan.assignments.filter_by(is_active=True).first() for loan in loans) and not reason:
        return _error("A reason is required when reassigning accounts", 422)
    for loan in loans:
        current_assignments = loan.assignments.filter_by(is_active=True).all()
        before = [{"collector_id": item.collector_id, "reason": item.reason} for item in current_assignments]
        for current in current_assignments:
            current.is_active = False
            current.unassigned_at = datetime.utcnow()
        db.session.add(DebtCollectionAssignment(
            debtor_id=loan.debtor_id,
            loan_id=loan.id,
            collector_id=collector.id,
            assigned_by=viewer.id,
            reason=reason or None,
        ))
        _audit(
            viewer, "DebtCollectionLoan", loan.id, "assigned",
            before=before or None,
            after={"collector_id": collector.id, "reason": reason or None},
        )
    db.session.commit()
    return jsonify({"data": {"assigned": len(loans), "collector_id": collector.id}, "error": None}), 201


@debt_collection_bp.get("/loans/<int:loan_id>/calls")
def list_call_logs(loan_id):
    loan = _loan_for_viewer(_user(), loan_id)
    if not loan:
        return _error("Loan not found", 404)
    calls = loan.call_logs.order_by(DebtCollectionCallLog.created_at.desc()).all()
    return jsonify({"data": [_call_dict(call) for call in calls], "error": None})


@debt_collection_bp.post("/loans/<int:loan_id>/calls")
def create_call_log(loan_id):
    viewer = _user()
    loan = _loan_for_viewer(viewer, loan_id)
    if not loan:
        return _error("Loan not found", 404)
    if not _can_manage(viewer) and not loan.assignments.filter_by(collector_id=viewer.id, is_active=True).first():
        return _error("Loan is not assigned to you", 403)
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    outcomes = {
        "phone_off", "no_answer", "negotiation", "wrong_number",
        "promise_to_pay", "callback_requested", "full_payment", "partial_payment",
    }
    outcome = str(payload.get("outcome", "")).strip().lower()
    if outcome not in outcomes:
        return _error("Choose a valid call outcome", 422)
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        return _error("notes must be text", 422)
    try:
        promised_date = _date(payload.get("promised_date"), "promised_date") if payload.get("promised_date") else None
        callback_date = _date(payload.get("callback_date"), "callback_date") if payload.get("callback_date") else None
        promised_time = _time(payload.get("promised_time"), "promised_time") if payload.get("promised_time") else None
        callback_time = _time(payload.get("callback_time"), "callback_time") if payload.get("callback_time") else None
        promised_amount = _money(payload.get("promised_amount"), "promised_amount") if payload.get("promised_amount") not in (None, "") else None
    except ValueError as error:
        return _error(str(error), 422)
    if outcome == "promise_to_pay" and (not promised_date or not promised_time):
        return _error("A promise to pay requires promised_date and promised_time", 422)
    if outcome == "callback_requested" and (not callback_date or not callback_time):
        return _error("A callback request requires callback_date and callback_time", 422)
    if outcome == "partial_payment" and (not promised_date or not promised_time):
        return _error("A partial payment requires the next payment date and time", 422)
    amount_paid = Decimal("0.00")
    if outcome in {"full_payment", "partial_payment"}:
        balance = max(Decimal("0.00"), loan.loan_balance)
        try:
            amount_paid = balance if outcome == "full_payment" and payload.get("amount_paid") in (None, "") else _money(payload.get("amount_paid"), "amount_paid", positive=True)
        except ValueError as error:
            return _error(str(error), 422)
        if amount_paid > balance:
            return _error("amount_paid cannot exceed the outstanding balance", 422)
        if outcome == "full_payment" and amount_paid != balance:
            return _error("full_payment must clear the outstanding balance", 422)
        if outcome == "partial_payment" and amount_paid >= balance:
            return _error("Use full_payment when the outstanding balance is cleared", 422)
    if promised_amount is not None:
        next_balance = max(Decimal("0.00"), loan.loan_balance - amount_paid)
        if promised_amount <= 0 or promised_amount > next_balance:
            return _error("promised_amount must be greater than zero and no more than the remaining balance", 422)

    call = DebtCollectionCallLog(
        debtor_id=loan.debtor_id,
        loan_id=loan.id,
        collector_id=viewer.id,
        outcome=outcome,
        notes=notes.strip() if notes else None,
        promised_date=promised_date,
        promised_time=promised_time,
        promised_amount=promised_amount,
        callback_date=callback_date,
        callback_time=callback_time,
        amount_paid=amount_paid,
    )
    old_status = _status(loan.status)
    if outcome == "negotiation":
        loan.status = "in_negotiation"
    elif outcome == "promise_to_pay":
        loan.status = "promise_to_pay"
    elif outcome in {"full_payment", "partial_payment"}:
        loan.amount_paid += amount_paid
        if loan.imported_balance is not None:
            loan.imported_balance = max(Decimal("0.00"), loan.imported_balance - amount_paid)
        loan.status = "settled" if loan.loan_balance <= 0 else "active"
        db.session.add(DebtCollectionPayment(
            loan_id=loan.id,
            collector_id=viewer.id,
            amount=amount_paid,
            payment_date=date.today(),
            payment_type="full" if outcome == "full_payment" else "partial",
            notes=notes.strip() if notes else None,
        ))
    db.session.add(call)
    db.session.flush()
    if promised_date and promised_time:
        due_date, due_time, follow_up_type = promised_date, promised_time, "PTP"
    elif callback_date and callback_time:
        due_date, due_time, follow_up_type = callback_date, callback_time, "Callback"
    else:
        due_date = due_time = follow_up_type = None
    if due_date and due_time:
        db.session.add(DebtCollectionFollowUpSchedule(
            debtor_id=loan.debtor_id,
            loan_id=loan.id,
            collector_id=viewer.id,
            follow_up_type=follow_up_type,
            due_at=datetime.combine(due_date, time.fromisoformat(due_time)),
            source_call_log_id=call.id,
        ))
    if old_status != loan.status:
        db.session.add(DebtCollectionLoanStatusHistory(
            loan_id=loan.id,
            old_status=old_status,
            new_status=loan.status,
            changed_by=viewer.id,
            reason=f"Call outcome: {outcome}",
        ))
    _audit(viewer, "DebtCollectionCallLog", call.id, "recorded", after=_call_dict(call))
    db.session.commit()
    return jsonify({"data": {"call": _call_dict(call), "loan": _loan_dict(loan)}, "error": None}), 201


@debt_collection_bp.post("/loans/<int:loan_id>/payments")
def record_payment(loan_id):
    viewer = _user()
    loan = _loan_for_viewer(viewer, loan_id)
    if not loan:
        return _error("Loan not found", 404)
    if not _can_manage(viewer) and not loan.assignments.filter_by(collector_id=viewer.id, is_active=True).first():
        return _error("Loan is not assigned to you", 403)
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    try:
        amount = _money(payload.get("amount"), "amount", positive=True)
        payment_date = _date(payload.get("payment_date") or date.today(), "payment_date")
    except ValueError as error:
        return _error(str(error), 422)
    payment_type = payload.get("payment_type", "partial")
    notes = payload.get("notes")
    if not isinstance(payment_type, str) or len(payment_type.strip()) > 40:
        return _error("payment_type must be text of at most 40 characters", 422)
    if notes is not None and not isinstance(notes, str):
        return _error("notes must be text", 422)
    balance = max(Decimal("0.00"), loan.loan_balance)
    if amount > balance:
        return _error("Payment cannot exceed the outstanding loan balance", 422)
    payment = DebtCollectionPayment(
        loan_id=loan.id,
        collector_id=viewer.id,
        amount=amount,
        payment_date=payment_date,
        payment_type=payment_type.strip() or "partial",
        notes=(notes or "").strip() or None,
    )
    old_status = _status(loan.status)
    loan.amount_paid += amount
    if loan.imported_balance is not None:
        loan.imported_balance = max(Decimal("0.00"), loan.imported_balance - amount)
    if loan.loan_balance <= 0:
        loan.status = "settled"
    else:
        loan.status = "active"
    db.session.add(payment)
    if old_status != loan.status:
        db.session.add(DebtCollectionLoanStatusHistory(
            loan_id=loan.id, old_status=old_status, new_status=loan.status,
            changed_by=viewer.id,
            reason="Loan paid in full" if loan.status == "settled" else "Partial payment; follow-up remains active",
        ))
    _audit(viewer, "DebtCollectionPayment", loan.id, "recorded", after={
        "amount": str(amount), "payment_date": payment_date.isoformat(),
    })
    db.session.commit()
    return jsonify({"data": {
        "id": payment.id,
        "loan_id": loan.id,
        "amount": str(payment.amount),
        "payment_date": payment.payment_date.isoformat(),
        "loan": _loan_dict(loan),
    }, "error": None}), 201


@debt_collection_bp.get("/follow-ups")
def list_follow_ups():
    viewer = _user()
    query = DebtCollectionFollowUpSchedule.query
    if not _can_view_all_debt_collection(viewer):
        query = query.filter(
            DebtCollectionFollowUpSchedule.collector_id.in_(
                _team_collector_ids(viewer)
            )
        )
    status = request.args.get("status", "Pending")
    if status:
        query = query.filter(DebtCollectionFollowUpSchedule.status.ilike(status))
    schedules = query.order_by(DebtCollectionFollowUpSchedule.due_at.asc()).all()
    return jsonify({"data": [{
        "id": item.id,
        "debtor_id": item.debtor_id,
        "loan_id": item.loan_id,
        "collector_id": item.collector_id,
        "collector_name": item.collector.full_name,
        "follow_up_type": item.follow_up_type,
        "due_at": item.due_at.isoformat(),
        "status": item.status,
        "debtor": _debtor_dict(item.debtor),
    } for item in schedules], "error": None})


@debt_collection_bp.patch("/follow-ups/<int:follow_up_id>")
def update_follow_up(follow_up_id):
    viewer = _user()
    follow_up = db.session.get(DebtCollectionFollowUpSchedule, follow_up_id)
    if not follow_up or (
        not _can_manage(viewer)
        and follow_up.collector_id not in _team_collector_ids(viewer)
    ):
        return _error("Follow-up not found", 404)
    payload = _json_object()
    status = payload.get("status") if payload else None
    if status not in {"Pending", "Completed", "Cancelled"}:
        return _error("status must be Pending, Completed, or Cancelled", 422)
    before = {"status": follow_up.status}
    follow_up.status = status
    _audit(viewer, "DebtCollectionFollowUpSchedule", follow_up.id, "status_updated", before=before, after={"status": status})
    db.session.commit()
    return jsonify({"data": {"id": follow_up.id, "status": follow_up.status}, "error": None})


@debt_collection_bp.get("/analytics")
def debt_collection_analytics():
    viewer = _user()
    if not _can_view_all_debt_collection(viewer) and not _can_view_team(viewer):
        denied = _management_required(viewer)
        if denied:
            return denied
    loans = _visible_loans(viewer).all()
    loan_ids = [loan.id for loan in loans]
    from_value = request.args.get("from")
    to_value = request.args.get("to")
    try:
        from_date = _date(from_value, "from") if from_value else None
        to_date = _date(to_value, "to") if to_value else None
    except ValueError as error:
        return _error(str(error), 422)
    if from_date and to_date and from_date > to_date:
        return _error("from must be on or before to", 422)
    payments_query = DebtCollectionPayment.query.filter(DebtCollectionPayment.loan_id.in_(loan_ids)) if loan_ids else DebtCollectionPayment.query.filter(db.false())
    calls_query = DebtCollectionCallLog.query.filter(DebtCollectionCallLog.loan_id.in_(loan_ids)) if loan_ids else DebtCollectionCallLog.query.filter(db.false())
    if from_date:
        payments_query = payments_query.filter(DebtCollectionPayment.payment_date >= from_date)
        calls_query = calls_query.filter(DebtCollectionCallLog.created_at >= datetime.combine(from_date, time.min))
    if to_date:
        payments_query = payments_query.filter(DebtCollectionPayment.payment_date <= to_date)
        calls_query = calls_query.filter(
            DebtCollectionCallLog.created_at < datetime.combine(to_date + timedelta(days=1), time.min)
        )
    collector_filter = request.args.get("collector_id")
    if collector_filter:
        try:
            collector_filter = int(collector_filter)
        except ValueError:
            return _error("collector_id must be an integer", 422)
        assignments = DebtCollectionAssignment.query.filter_by(collector_id=collector_filter, is_active=True).all()
        assigned_ids = {assignment.loan_id for assignment in assignments} & set(loan_ids)
        loans = [loan for loan in loans if loan.id in assigned_ids]
        loan_ids = [loan.id for loan in loans]
        payments_query = payments_query.filter(
            DebtCollectionPayment.collector_id == collector_filter
        )
        calls_query = calls_query.filter(
            DebtCollectionCallLog.collector_id == collector_filter
        )
    payments = payments_query.all()
    calls = calls_query.all()
    recovered_by_day = {}
    for payment in payments:
        day = payment.payment_date.isoformat()
        recovered_by_day[day] = recovered_by_day.get(day, Decimal("0.00")) + payment.amount
    collector_stats = {
        collector.id: {
            "collector_id": collector.id,
            "collector_name": collector.full_name,
            "recovered": Decimal("0.00"),
            "payments": 0,
            "calls": 0,
            "assigned_accounts": 0,
            "contacted_accounts": 0,
        }
        for collector in _available_collectors(viewer)
    }
    if collector_filter:
        collector_stats = {
            collector_filter: collector_stats[collector_filter]
        } if collector_filter in collector_stats else {}
    active_assignments = DebtCollectionAssignment.query.filter(
        DebtCollectionAssignment.is_active.is_(True),
        DebtCollectionAssignment.loan_id.in_(loan_ids),
    ).all() if loan_ids else []
    contacted_accounts = {
        (loan_id, collector_id)
        for loan_id, collector_id in db.session.query(
            DebtCollectionCallLog.loan_id,
            DebtCollectionCallLog.collector_id,
        ).filter(
            DebtCollectionCallLog.loan_id.in_(loan_ids)
        ).distinct().all()
    } if loan_ids else set()
    for assignment in active_assignments:
        row = collector_stats.setdefault(
            assignment.collector_id,
            {
                "collector_id": assignment.collector_id,
                "collector_name": assignment.collector.full_name,
                "recovered": Decimal("0.00"),
                "payments": 0,
                "calls": 0,
                "assigned_accounts": 0,
                "contacted_accounts": 0,
            },
        )
        row["assigned_accounts"] += 1
        if (assignment.loan_id, assignment.collector_id) in contacted_accounts:
            row["contacted_accounts"] += 1
    for item in payments:
        row = collector_stats.setdefault(item.collector_id, {
            "collector_id": item.collector_id, "collector_name": item.collector.full_name,
            "recovered": Decimal("0.00"), "payments": 0, "calls": 0,
            "assigned_accounts": 0, "contacted_accounts": 0,
        })
        row["recovered"] += item.amount
        row["payments"] += 1
    for call in calls:
        row = collector_stats.setdefault(call.collector_id, {
            "collector_id": call.collector_id, "collector_name": call.collector.full_name,
            "recovered": Decimal("0.00"), "payments": 0, "calls": 0,
            "assigned_accounts": 0, "contacted_accounts": 0,
        })
        row["calls"] += 1
    return jsonify({"data": {
        "portfolio": {
            "accounts": len(loans),
            "outstanding": str(sum((max(Decimal("0.00"), loan.loan_balance) for loan in loans), Decimal("0.00"))),
            "overdue_accounts": sum(1 for loan in loans if _status(loan.status) == "overdue"),
        },
        "period": {"from": from_date.isoformat() if from_date else None, "to": to_date.isoformat() if to_date else None},
        "collector_id": collector_filter,
        "period_recovered": str(sum((payment.amount for payment in payments), Decimal("0.00"))),
        "period_calls": len(calls),
        "recovery_trends": [
            {"date": day, "recovered": str(recovered_by_day[day])}
            for day in sorted(recovered_by_day)
        ],
        "interactions": [_call_dict(call) for call in calls],
        "collectors": [{
            **row,
            "recovered": str(row["recovered"]),
            "pending_accounts": max(0, row["assigned_accounts"] - row["contacted_accounts"]),
        } for row in sorted(collector_stats.values(), key=lambda item: item["collector_name"].lower())],
    }, "error": None})


@debt_collection_bp.post("/loans/<int:loan_id>/ratings")
def approve_credit_rating(loan_id):
    viewer = _user()
    denied = _management_required(viewer)
    if denied:
        return denied
    loan = DebtCollectionLoan.query.filter_by(id=loan_id, is_deleted=False, is_archived=False).first()
    if not loan or loan.debtor.is_deleted:
        return _error("Loan not found", 404)
    payload = _json_object()
    if payload is None:
        return _error("Request body must be a JSON object", 422)
    grade = str(payload.get("grade", "")).strip().upper()
    reason = payload.get("reason")
    try:
        score = int(payload.get("score"))
    except (TypeError, ValueError):
        return _error("score must be a whole number from 0 to 100", 422)
    if grade not in {"A", "B", "C", "D", "E"} or not 0 <= score <= 100:
        return _error("grade must be A-E and score must be from 0 to 100", 422)
    if not isinstance(reason, str) or not reason.strip():
        return _error("reason is required for an approved credit rating", 422)
    rating = DebtCollectionCreditRating(
        debtor_id=loan.debtor_id,
        loan_id=loan.id,
        grade=grade,
        score=score,
        reason=reason.strip(),
        approved_by=viewer.id,
        approved_at=datetime.utcnow(),
    )
    db.session.add(rating)
    db.session.flush()
    _audit(viewer, "DebtCollectionCreditRating", rating.id, "approved", after={"grade": grade, "score": score, "reason": reason.strip()})
    db.session.commit()
    return jsonify({"data": {"id": rating.id, "loan_id": loan.id, "grade": grade, "score": score, "approved_at": rating.approved_at.isoformat()}, "error": None}), 201


@debt_collection_bp.post("/loans/<int:loan_id>/write-off")
def approve_loan_write_off(loan_id):
    viewer = _user()
    denied = _management_required(viewer)
    if denied:
        return denied
    loan = DebtCollectionLoan.query.filter_by(id=loan_id, is_deleted=False, is_archived=False).first()
    if not loan or loan.debtor.is_deleted:
        return _error("Loan not found", 404)
    payload = _json_object()
    reason = payload.get("reason") if payload else None
    if not isinstance(reason, str) or not reason.strip():
        return _error("A reason is required to approve a write-off", 422)
    before = _loan_dict(loan)
    old_status = _status(loan.status)
    loan.status = "written_off"
    db.session.add(DebtCollectionLoanStatusHistory(loan_id=loan.id, old_status=old_status, new_status="written_off", changed_by=viewer.id, reason=reason.strip()))
    _audit(viewer, "DebtCollectionLoan", loan.id, "write_off_approved", before=before, after={"status": "written_off", "reason": reason.strip()})
    db.session.commit()
    return jsonify({"data": _loan_dict(loan), "error": None})


@debt_collection_bp.get("/export.csv")
def export_portfolio_csv():
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    try:
        loans = _filtered_loans(viewer)
    except ValueError as error:
        return _error(str(error), 422)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for loan in loans:
        debtor = loan.debtor
        row = {
            **_loan_dict(loan),
            "first_name": debtor.first_name,
            "other_names": debtor.other_names,
            "agent_msisdn": debtor.agent_msisdn,
            "owner_msisdn": debtor.owner_msisdn,
            "operator_msisdn": debtor.operator_msisdn,
            "location": debtor.location,
            "record_created_at": debtor.created_at.isoformat() if debtor.created_at else None,
        }
        writer.writerow({field: row.get(field, "") for field in EXPORT_FIELDS})
    return Response("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=debt-portfolio.csv"})


@debt_collection_bp.get("/export.xlsx")
def export_portfolio_xlsx():
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    try:
        loans = _filtered_loans(viewer)
    except ValueError as error:
        return _error(str(error), 422)
    rows = []
    for loan in loans:
        debtor = loan.debtor
        rows.append({
            **_loan_dict(loan),
            "first_name": debtor.first_name,
            "other_names": debtor.other_names,
            "agent_msisdn": debtor.agent_msisdn,
            "owner_msisdn": debtor.owner_msisdn,
            "operator_msisdn": debtor.operator_msisdn,
            "location": debtor.location,
            "record_created_at": debtor.created_at.isoformat() if debtor.created_at else None,
        })
    return Response(_xlsx_bytes(rows, EXPORT_FIELDS), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=debt-portfolio.xlsx"})


@debt_collection_bp.post("/import")
def import_portfolio():
    viewer = _user()
    denied = _allocation_required(viewer)
    if denied:
        return denied
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return _error("Upload a CSV or .xlsx file", 422)
    try:
        rows = _import_rows(upload)
    except ValueError as error:
        return _error(str(error), 422)
    job = DebtCollectionImportJob(uploaded_by=viewer.id, file_name=upload.filename, total_rows=len(rows))
    db.session.add(job)
    db.session.flush()
    accepted = 0
    for row_number, raw in enumerate(rows, start=2):
        row = {str(key or "").strip().lower(): value for key, value in raw.items()}
        try:
            debtor_data = _parse_debtor(row)
            debtor = DebtCollectionDebtor.query.filter_by(agent_no=debtor_data["agent_no"], is_deleted=False).first()
            if debtor and _is_team_leader(viewer):
                assigned_outside_team = DebtCollectionAssignment.query.filter(
                    DebtCollectionAssignment.debtor_id == debtor.id,
                    DebtCollectionAssignment.is_active.is_(True),
                    ~DebtCollectionAssignment.collector_id.in_(_team_collector_ids(viewer)),
                ).first()
                if assigned_outside_team:
                    raise ValueError("This debtor is already assigned outside your team")
            loan_amount = row.get("loan_amount")
            loan_values = None
            loan_created_at = None
            imported_balance = None
            if loan_amount not in (None, ""):
                amount_paid = row.get("amount_paid")
                if row.get("loan_balance") not in (None, ""):
                    imported_balance = _money(row["loan_balance"], "loan_balance")
                    if not amount_paid:
                        imported_amount = _money(loan_amount, "loan_amount", positive=True)
                        amount_paid = str(max(Decimal("0.00"), imported_amount - imported_balance))
                imported_status = _status(row.get("status") or "active")
                try:
                    legacy_status = Decimal(imported_status)
                    if legacy_status.is_finite() and legacy_status in {
                        Decimal("0"),
                        Decimal("1"),
                    }:
                        imported_status = "active"
                except InvalidOperation:
                    pass
                loan_payload = {
                    "loan_amount": loan_amount,
                    "amount_paid": amount_paid or "0",
                    "loan_date": _import_date(
                        row.get("loan_date") or row.get("created_at") or date.today(),
                        "created_at",
                    ),
                    "last_interest_calc_date": _import_date(
                        row.get("last_interest_calc_date"), "last_interest_calc_date"
                    ),
                    "no_of_days": _import_days(row.get("no_of_days")),
                    "status": imported_status,
                }
                reported_amount_paid = _money(
                    loan_payload["amount_paid"], "amount_paid"
                )
                if (
                    imported_balance is not None
                    and reported_amount_paid
                    > _money(loan_amount, "loan_amount", positive=True)
                ):
                    loan_payload["amount_paid"] = str(
                        _money(loan_amount, "loan_amount", positive=True)
                    )
                loan_values = _parse_loan(loan_payload)
                if reported_amount_paid != loan_values["amount_paid"]:
                    loan_values["amount_paid"] = reported_amount_paid
                if loan_values["status"] == "written_off":
                    raise ValueError("Write-offs require the manager approval action")
                if imported_balance is not None:
                    if imported_balance == 0:
                        loan_values["status"] = "settled"
                    elif loan_values["status"] == "settled":
                        loan_values["status"] = "active"
                if row.get("created_at"):
                    loan_created_at = _import_datetime(row["created_at"], "created_at")
            if not debtor:
                debtor = DebtCollectionDebtor(**debtor_data)
                db.session.add(debtor)
                db.session.flush()
            if loan_values:
                loan = DebtCollectionLoan(debtor_id=debtor.id, **loan_values)
                loan.imported_balance = imported_balance
                if loan_created_at:
                    loan.created_at = loan_created_at
                db.session.add(loan)
                db.session.flush()
                if loan.status != "active":
                    db.session.add(DebtCollectionLoanStatusHistory(loan_id=loan.id, old_status=None, new_status=loan.status, changed_by=viewer.id, reason="Imported loan"))
            accepted += 1
        except (ValueError, TypeError) as error:
            db.session.add(DebtCollectionImportIssue(job_id=job.id, row_number=row_number, message=str(error)))
    job.accepted_rows = accepted
    job.rejected_rows = len(rows) - accepted
    _audit(viewer, "DebtCollectionImportJob", job.id, "imported", after={"accepted_rows": accepted, "rejected_rows": job.rejected_rows})
    db.session.commit()
    return jsonify({"data": {
        "job_id": job.id,
        "total_rows": job.total_rows,
        "accepted_rows": job.accepted_rows,
        "rejected_rows": job.rejected_rows,
        "issues": [{"row_number": issue.row_number, "message": issue.message} for issue in job.issues.all()],
    }, "error": None}), 201


@debt_collection_bp.get("/analytics/performance")
def collector_performance():
    viewer = _user()
    if _can_manage(viewer) or _can_view_team(viewer):
        return debt_collection_analytics()
    loans = _visible_loans(viewer).all()
    loan_ids = [loan.id for loan in loans]
    today = date.today()
    starts = {
        "daily": today,
        "weekly": today - timedelta(days=today.weekday()),
        "monthly": today.replace(day=1),
    }
    periods = {}
    for name, start in starts.items():
        payments = DebtCollectionPayment.query.filter(
            DebtCollectionPayment.collector_id == viewer.id,
            DebtCollectionPayment.payment_date >= start,
            DebtCollectionPayment.payment_date <= today,
        ).all()
        calls = DebtCollectionCallLog.query.filter(
            DebtCollectionCallLog.collector_id == viewer.id,
            DebtCollectionCallLog.created_at >= datetime.combine(start, time.min),
            DebtCollectionCallLog.created_at <= datetime.combine(today, time.max),
        ).all()
        periods[name] = {
            "recovered": str(sum((payment.amount for payment in payments), Decimal("0.00"))),
            "payments": len(payments),
            "calls": len(calls),
        }
    periods["daily"]["promises_to_pay"] = DebtCollectionFollowUpSchedule.query.filter(
        DebtCollectionFollowUpSchedule.collector_id == viewer.id,
        DebtCollectionFollowUpSchedule.follow_up_type == "PTP",
        DebtCollectionFollowUpSchedule.status == "Pending",
        DebtCollectionFollowUpSchedule.due_at >= datetime.combine(today, time.min),
        DebtCollectionFollowUpSchedule.due_at < datetime.combine(today + timedelta(days=1), time.min),
    ).count()
    month = periods["monthly"]
    return jsonify({"data": {
        "period": "month_to_date",
        "assigned_accounts": len(loans),
        "recovered": month["recovered"],
        "payments": month["payments"],
        "calls": month["calls"],
        "periods": periods,
    }, "error": None})


def _collector_dashboard_loans(viewer):
    return _visible_loans(viewer).order_by(DebtCollectionLoan.id.asc()).all()


@collector_bp.get("/my-portfolio")
def collector_my_portfolio():
    viewer = _user()
    loans = _collector_dashboard_loans(viewer)

    loan_ids = [loan.id for loan in loans]
    last_interactions = {}
    if loan_ids:
        calls = DebtCollectionCallLog.query.filter(
            DebtCollectionCallLog.loan_id.in_(loan_ids)
        ).order_by(
            DebtCollectionCallLog.created_at.desc(),
            DebtCollectionCallLog.id.desc(),
        ).all()
        for call in calls:
            last_interactions.setdefault(call.loan_id, _call_dict(call))

    records = []
    for loan in loans:
        record = _loan_dict(loan)
        record["is_assigned_to_me"] = bool(
            loan.assignments.filter_by(
                collector_id=viewer.id, is_active=True
            ).first()
        )
        record["last_interaction"] = last_interactions.get(loan.id)
        record["interactions"] = [
            _call_dict(call)
            for call in loan.call_logs.order_by(
                DebtCollectionCallLog.created_at.desc(), DebtCollectionCallLog.id.desc()
            ).all()
        ]
        records.append(record)
    return jsonify({"data": records, "error": None})


@collector_bp.get("/analytics")
def collector_dashboard_analytics():
    viewer = _user()
    loans = _collector_dashboard_loans(viewer)
    loan_ids = [loan.id for loan in loans]
    all_calls = DebtCollectionCallLog.query.filter(
        DebtCollectionCallLog.loan_id.in_(loan_ids)
    ).all() if loan_ids else []
    contacted_loan_ids = {call.loan_id for call in all_calls}
    calls_query = DebtCollectionCallLog.query.filter(
        DebtCollectionCallLog.loan_id.in_(loan_ids)
    ) if loan_ids else DebtCollectionCallLog.query.filter(db.false())
    from_value = request.args.get("from")
    to_value = request.args.get("to")
    outcome = request.args.get("outcome", "").strip().lower()
    supported_outcomes = {
        "phone_off", "no_answer", "negotiation", "wrong_number",
        "promise_to_pay", "callback_requested", "full_payment", "partial_payment",
    }
    if outcome and outcome not in supported_outcomes:
        return _error("Choose a valid call outcome", 422)
    try:
        from_date = _date(from_value, "from") if from_value else None
        to_date = _date(to_value, "to") if to_value else None
    except ValueError as error:
        return _error(str(error), 422)
    if from_date and to_date and from_date > to_date:
        return _error("from must be on or before to", 422)
    if from_date:
        calls_query = calls_query.filter(
            DebtCollectionCallLog.created_at >= datetime.combine(from_date, time.min)
        )
    if to_date:
        calls_query = calls_query.filter(
            DebtCollectionCallLog.created_at < datetime.combine(to_date + timedelta(days=1), time.min)
        )
    if outcome:
        calls_query = calls_query.filter(DebtCollectionCallLog.outcome == outcome)
    calls = calls_query.order_by(
        DebtCollectionCallLog.created_at.desc(), DebtCollectionCallLog.id.desc()
    ).all()
    interaction_types = (
        "phone_off", "no_answer", "negotiation", "wrong_number",
        "promise_to_pay", "callback_requested", "full_payment", "partial_payment",
    )
    interaction_breakdown = {outcome: 0 for outcome in interaction_types}
    for call in calls:
        interaction_breakdown[call.outcome] = interaction_breakdown.get(call.outcome, 0) + 1

    today = date.today()
    start_date = today - timedelta(days=6)
    payments = DebtCollectionPayment.query.filter(
        DebtCollectionPayment.collector_id.in_(_team_collector_ids(viewer)),
        DebtCollectionPayment.loan_id.in_(loan_ids),
        DebtCollectionPayment.payment_date >= start_date,
        DebtCollectionPayment.payment_date <= today,
    ).all() if loan_ids else []
    recovered_by_day = { (start_date + timedelta(days=offset)).isoformat(): Decimal("0.00") for offset in range(7) }
    recovered_today = Decimal("0.00")
    for payment in payments:
        day = payment.payment_date.isoformat()
        recovered_by_day[day] += payment.amount
        if payment.payment_date == today:
            recovered_today += payment.amount

    return jsonify({"data": {
        "total_assigned": len(loan_ids),
        "total_contacted": len(contacted_loan_ids),
        "total_pending": max(0, len(loan_ids) - len(contacted_loan_ids)),
        "recovered_today": str(recovered_today),
        "interaction_breakdown": interaction_breakdown,
        "daily_recovery_trend": [
            {"date": day, "amount": str(amount)}
            for day, amount in recovered_by_day.items()
        ],
        "interactions": [_call_dict(call) for call in calls],
        "interaction_period": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
            "outcome": outcome or None,
        },
    }, "error": None})
