import csv
import io
import zipfile
from html import escape
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_from_directory, Response
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from sqlalchemy import extract, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    AuditLog,
    Client,
    Customer,
    DebtCollectionDebtor,
    DepartmentAssignmentHistory,
    Notification,
    Role,
    SalesDailyReport,
    SalesCallLog,
    SalesFollowUp,
    SalesLead,
    SalesRegistration,
    User,
    UserRole,
)
from app.services.sales_reports_v2 import compliance, daily_submissions, document_gaps, funnel, integrity, locations, regions, registrations, summary, top_performers
from app.services.registration_analytics import (
    DOCUMENT_ALIASES as REGISTRATION_DOCUMENT_ALIASES,
    DOCUMENT_LABELS as REGISTRATION_DOCUMENT_LABELS,
    DOCUMENT_REQUIREMENTS as REGISTRATION_DOCUMENT_REQUIREMENTS,
    as_bool as _analytics_bool,
    calculate_registration_analytics,
    calculate_employee_performance,
    category_of as _analytics_category,
    date_value as _analytics_date,
    document_submitted as _analytics_document_submitted,
    is_eligible as _analytics_eligible,
    is_outstanding_followup as _analytics_outstanding_followup,
    missing_requirements as _analytics_missing_requirements,
    registration_started as _analytics_started,
    registration_status as _analytics_status,
    report_data as _analytics_report_data,
)
from app.utils.rbac import can, enforce_permission, is_hr_admin, is_system_admin, require_scope
from app.utils.organization import get_active_assignment, require_active_department_write

sales_bp = Blueprint("sales", __name__, url_prefix="/api/sales")
DOCUMENT_FIELDS = {"business_permit", "individual_kra_pin", "six_months_commission", "subagent_agent_contract", "owner_national_id", "sign_contract", "certificate_of_incorporation", "company_kra_pin", "owners_directors_national_ids", "cr12_directors", "commission_statement", "kra_pin", "national_id", "contract", "cr12"}
CUSTOMER_TYPES = {"agent", "sub_agent"}
OUTCOMES = {"existing", "interested", "not_interested", "registered", "ready_to_register", "appointment", "undecided", "promised", "declined"}
DOCUMENT_REQUIREMENTS = {
    "sub_agent": {"business_permit", "individual_kra_pin", "six_months_commission", "subagent_agent_contract", "owner_national_id", "sign_contract"},
    "agent": {"certificate_of_incorporation", "company_kra_pin", "six_months_commission", "owners_directors_national_ids", "cr12_directors"},
}
DOCUMENT_ALIASES = {"individual_kra_pin": "kra_pin", "six_months_commission": "commission_statement", "subagent_agent_contract": "contract", "owner_national_id": "national_id", "certificate_of_incorporation": "incorporation_certificate", "owners_directors_national_ids": "national_id", "cr12_directors": "cr12"}
CLIENT_LOOKUP_FIELDS = {
    "agent_name": "agent_name",
    "agent_number": "agent_number",
    "store_number": "store_number",
}
REPORT_DATA_FIELDS = {
    "new_client", "heard_about_okoa", "interested_in_okoa", "already_uses_okoa", "customers_visited",
    "registered_count", "appointment_count", "undecided_count", "not_interested_count", "referral_count",
    "referral_name", "referral_details", "referral_agreed", "referral_contact_number", "appointment_date", "appointment_time", "follow_up_details", "contract_status", "registration_status", "client_type",
    "mpesa_admin_id_number", "mpesa_admin_phone",
}
CSV_FIELDS = [
    "employee_id", "employee_name",
    "agent_name", "agent_number", "store_number", "business_owner_name", "contact_phone", "id_number",
    "business_location", "date_visited", "registration_date", "customer_type", "outcome", "visit_mode",
    "admin_name", "witness_name", "witness_id_number", "witness_phone",
    "new_client", "heard_about_okoa", "interested_in_okoa", "already_uses_okoa", "customers_visited",
    "registered_count", "appointment_count", "undecided_count", "not_interested_count", "referral_count",
    "referral_agreed", "referral_name", "referral_details", "referral_contact_number",
    "appointment_date", "appointment_time", "follow_up_details", "contract_status",
    "mpesa_admin_id_number", "mpesa_admin_phone", "notes",
    *sorted(DOCUMENT_FIELDS),
]


def _user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


@sales_bp.before_request
def enforce_dashboard_feature_access():
    if request.method == "GET" and request.endpoint == "sales.lookup_clients":
        verify_jwt_in_request()
        viewer = _user()
        if viewer and viewer.is_active and viewer.account_status == "approved":
            if can(viewer, "customer_care.*") or can(viewer, "debt_collection.*"):
                return None
    if request.method == "GET":
        verify_jwt_in_request()
        viewer = _user()
        assignment = get_active_assignment(viewer.id) if viewer else None
        if (
            viewer
            and viewer.is_currently_active()
            and viewer.account_status == "approved"
            and is_system_admin(viewer)
        ):
            return None
        if (
            viewer
            and viewer.is_currently_active()
            and viewer.account_status == "approved"
            and assignment
            and assignment.organizational_role == "general_manager"
        ):
            return None
        if (
            viewer
            and request.endpoint in {
                "sales.list_reports",
                "sales.registration_analytics",
                "sales.registration_analytics_records",
                "sales.employee_registration_performance",
                "sales.field_agent_analytics",
                "sales.export_field_agent_analytics",
                "sales.list_report_recovery_follow_ups",
                "sales.export_reports",
                "sales.download_document",
                "sales.v2_team_reports",
                "sales.v2_team_compliance",
                "sales.v2_team_performance",
                "sales.v2_team_registrations",
                "sales.v2_team_locations",
                "sales.v2_appointments",
                "sales.v2_export_csv",
                "sales.v2_export_xlsx",
            }
            and _sales_management_assignment(viewer, assignment)
        ):
            return None
    if (
        request.method == "POST"
        and request.endpoint == "sales.create_report"
        and request.form.get("outcome") == "ready_to_register"
        and _as_bool(request.form.get("new_client"))
    ):
        verify_jwt_in_request()
        caller = _user()
        if (
            caller
            and caller.is_currently_active()
            and caller.account_status == "approved"
            and can(caller, "customer_care.*")
            and not request.files
        ):
            # Customer Care may persist only a new-client registration from this
            # endpoint. The route still runs the shared Sales validation below.
            return None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        access_response = require_active_department_write("sales")(lambda: None)()
        if access_response is not None:
            return access_response
    permission = (
        "sales_reports.write"
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}
        else "sales_reports.view"
    )
    return enforce_permission(permission)


def _date(value):
    return date.fromisoformat(value) if value else None


def _error(message, status=400):
    return jsonify({"data": None, "error": {"message": message}}), status


def _sales_reports():
    sales_user_ids = db.session.query(UserRole.user_id).join(
        Role, Role.id == UserRole.role_id
    ).filter(Role.name == "sales")
    return SalesDailyReport.query.filter(SalesDailyReport.employee_id.in_(sales_user_ids))


def _sales_management_assignment(viewer, assignment=None):
    assignment = assignment or get_active_assignment(viewer.id)
    if not assignment:
        return None
    if assignment.organizational_role == "general_manager":
        return assignment
    if (
        assignment.organizational_role in {"team_leader", "department_manager"}
        and _is_sales_department(assignment.department_name)
    ):
        return assignment
    return None


def _sales_employee_query():
    return (
        User.query.join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.name == "sales", User.account_status == "approved")
    )


def _sales_employee_ids_for_manager(viewer, assignment):
    employees = _sales_employee_query()
    if assignment.organizational_role == "general_manager":
        return employees.with_entities(User.id)
    employees = employees.filter(
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
    )
    if assignment.organizational_role == "team_leader":
        return employees.filter(User.manager_id == viewer.id).with_entities(User.id)
    if assignment.organizational_role == "department_manager":
        if assignment.department_id:
            assigned_user_ids = db.session.query(
                DepartmentAssignmentHistory.user_id
            ).filter(
                DepartmentAssignmentHistory.department_id == assignment.department_id,
                DepartmentAssignmentHistory.ended_at.is_(None),
            )
            employees = employees.filter(
                or_(
                    User.department_id == assignment.department_id,
                    User.id.in_(assigned_user_ids),
                )
            )
        else:
            employees = employees.filter(
                func.lower(User.department) == assignment.department_name.strip().lower()
            )
        return employees.with_entities(User.id)
    return db.session.query(User.id).filter(User.id == -1)


def _scope_sales_reports(query, viewer):
    assignment = _sales_management_assignment(viewer)
    if assignment and assignment.organizational_role == "general_manager":
        return query
    if assignment:
        employee_ids = _sales_employee_ids_for_manager(viewer, assignment)
        return query.filter(SalesDailyReport.employee_id.in_(employee_ids))
    if is_system_admin(viewer) or (
        can(viewer, "sales_reports.view") and is_hr_admin(viewer)
    ):
        return query
    return query.filter(SalesDailyReport.employee_id == viewer.id)


def _is_sales_department(value):
    normalized = (value or "").strip().lower().replace("&", " and ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return "sales" in normalized or "marketing" in normalized


def _as_bool(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _report_data(payload):
    data = {field: payload.get(field) for field in REPORT_DATA_FIELDS if field in payload}
    for field in {"new_client"}:
        if field in data:
            data[field] = _as_bool(data[field])
    for field in {"customers_visited", "registered_count", "appointment_count", "undecided_count", "not_interested_count", "referral_count"}:
        if field in data and data[field] not in (None, ""):
            try:
                data[field] = int(data[field])
            except (TypeError, ValueError):
                raise ValueError(f"{field} must be a whole number")
            if data[field] < 0:
                raise ValueError(f"{field} cannot be negative")
    return data


def _validate_documents(payload, customer_type, outcome):
    documents = {field: _as_bool(payload.get(field) or payload.get(DOCUMENT_ALIASES.get(field, ""))) for field in set(DOCUMENT_REQUIREMENTS[customer_type]) | DOCUMENT_FIELDS}
    if outcome == "registered":
        missing = sorted(field.replace("_", " ") for field in DOCUMENT_REQUIREMENTS[customer_type] if not documents.get(field))
        if missing:
            return None, f"Registered {customer_type.replace('_', ' ')} reports require: {', '.join(missing)}"
    return documents, None


def _create_report(employee, payload, uploaded_files=None):
    try:
        date_visited = _date(payload.get("date_visited"))
        registration_date = _date(payload.get("registration_date"))
        report_data = _report_data(payload)
    except ValueError as error:
        return None, str(error), 422
    if not payload.get("agent_name") or not date_visited:
        return None, "Agent name and date visited are required", 422
    if payload.get("customer_type") not in CUSTOMER_TYPES or payload.get("outcome") not in OUTCOMES:
        return None, "Choose a valid customer type and visit outcome", 422
    documents, document_error = _validate_documents(payload, payload["customer_type"], payload["outcome"])
    if document_error:
        return None, document_error, 422
    if "new_client" in report_data:
        is_new_client = report_data["new_client"]
        report_data["client_type"] = "new" if is_new_client else "existing"
        if is_new_client and payload["outcome"] not in {"interested", "not_interested", "appointment", "ready_to_register"}:
            return None, "Choose a valid new-client outcome", 422
        if not is_new_client and payload["outcome"] != "existing":
            return None, "Existing-client reports must use the existing outcome", 422

        required_fields = ["agent_name", "agent_number", "store_number", "business_location"]
        if not is_new_client or payload["outcome"] in {"interested", "not_interested", "appointment"}:
            required_fields.append("notes")
        if payload["outcome"] == "appointment":
            required_fields.extend(["appointment_date", "appointment_time"])
            try:
                appointment_date = _date(payload.get("appointment_date"))
                time.fromisoformat(payload.get("appointment_time", ""))
            except (TypeError, ValueError):
                return None, "Appointment date and time must be valid", 422
            if not appointment_date:
                return None, "Appointment date and time must be valid", 422
        if not is_new_client:
            if payload.get("referral_agreed") not in {"yes", "no"}:
                return None, "Choose whether the existing client agreed to a referral", 422
            report_data["referral_agreed"] = payload["referral_agreed"]
            if payload["referral_agreed"] == "yes":
                if not (payload.get("referral_name") or "").strip():
                    return None, "A referral name is required when a referral is agreed", 422
                if not (payload.get("referral_contact_number") or "").strip():
                    return None, "A referral contact number is required when a referral is agreed", 422
        if payload["outcome"] == "ready_to_register":
            required_fields.extend(
                ["registration_date", "witness_name", "witness_id_number", "witness_phone"]
            )
        missing_fields = [field for field in required_fields if not str(payload.get(field) or "").strip()]
        if missing_fields:
            return None, f"Required report fields are missing: {', '.join(missing_fields)}", 422

    if payload["outcome"] in {"ready_to_register", "registered"}:
        required_documents = DOCUMENT_REQUIREMENTS[payload["customer_type"]]
        registration_complete = (
            all(documents.get(field) for field in required_documents)
            and all(str(payload.get(field) or "").strip() for field in (
                "witness_name", "witness_id_number", "witness_phone"
            ))
        )
        report_data["registration_status"] = "COMPLETE" if registration_complete else "INCOMPLETE"
    else:
        # Clients cannot set a quality grade directly; it is derived from the
        # registration evidence and requirements by the backend.
        report_data.pop("registration_status", None)
    completion_date = date.today() if report_data.get("registration_status") == "COMPLETE" else None
    report = SalesDailyReport(
        employee_id=employee.id,
        created_by_id=employee.id,
        department=employee.department or "Sales and Marketing",
        agent_name=payload["agent_name"].strip(),
        agent_number=payload.get("agent_number", "").strip() or None,
        store_number=payload.get("store_number", "").strip() or None,
        business_owner_name=payload.get("business_owner_name", "").strip() or None,
        contact_phone=payload.get("contact_phone", "").strip() or None,
        id_number=payload.get("id_number", "").strip() or None,
        business_location=payload.get("business_location", "").strip() or None,
        date_visited=date_visited,
        registration_date=registration_date,
        completion_date=completion_date,
        admin_name=payload.get("admin_name", "").strip() or None,
        witness_name=payload.get("witness_name", "").strip() or None,
        witness_id_number=payload.get("witness_id_number", "").strip() or None,
        witness_phone=payload.get("witness_phone", "").strip() or None,
        customer_type=payload["customer_type"],
        outcome=payload["outcome"],
        visit_mode=(payload.get("visit_mode") or "field_visit").strip().lower(),
        notes=payload.get("notes", "").strip() or None,
        documents=documents,
        uploaded_files=uploaded_files or [],
        report_data=report_data,
    )
    if report.visit_mode not in {"field_visit", "telesales"}:
        return None, "visit_mode must be field_visit or telesales", 422
    if _analytics_status(report) == "incomplete":
        report.report_data = {
            **(report.report_data or {}),
            "recovery_follow_up": {
                "status": "open",
                "due_date": (date.today() + timedelta(days=7)).isoformat(),
                "notes": "",
            },
        }
    return report, None, 201


def _client_category(value):
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "mpesa_sub_agent" if normalized in {"sub_agent", "subagent", "mpesa_sub_agent"} else (
        "mpesa_agent" if normalized in {
            "agent", "mpesa_agent", "mpesa_agent_dealer", "dealer"
        } else ""
    )


def _lookup_result(
    *,
    source,
    agent_name=None,
    agent_number=None,
    store_number=None,
    business_location=None,
    category=None,
    documents=None,
    owner_name=None,
    owner_id_number=None,
    owner_phone_number=None,
    phone_number=None,
):
    return {
        "source": source,
        "agent_name": agent_name or "",
        "agent_number": agent_number or "",
        "store_number": store_number or "",
        "business_location": business_location or "",
        "category": _client_category(category),
        "documents": documents if isinstance(documents, dict) else {},
        "owner_name": owner_name or "",
        "owner_id_number": owner_id_number or "",
        "owner_phone_number": owner_phone_number or "",
        "phone_number": phone_number or "",
    }


@sales_bp.get("/clients/lookup")
@jwt_required()
def lookup_clients():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)

    field = request.args.get("field", "")
    query_text = request.args.get("q", "").strip()
    if field not in CLIENT_LOOKUP_FIELDS:
        return _error("field must be agent_name, agent_number, or store_number", 422)
    if not query_text:
        return _error("Enter a client name, agent number, or store number", 422)

    matches = []
    report_column = getattr(SalesDailyReport, CLIENT_LOOKUP_FIELDS[field])
    if field == "agent_name":
        reports = _sales_reports().filter(
            report_column.ilike(f"%{query_text}%")
        ).order_by(SalesDailyReport.created_at.desc()).limit(25).all()
    else:
        reports = _sales_reports().filter(
            func.lower(report_column) == query_text.lower()
        ).order_by(SalesDailyReport.created_at.desc()).limit(25).all()
    for report in reports:
        matches.append(
            _lookup_result(
                source="Sales report",
                agent_name=report.agent_name,
                agent_number=report.agent_number,
                store_number=report.store_number,
                business_location=report.business_location,
                category=report.customer_type,
                documents=report.documents,
                owner_name=report.business_owner_name,
                owner_id_number=report.id_number,
                owner_phone_number=report.contact_phone,
                phone_number=report.contact_phone,
            )
        )

    if can(viewer, "customer_care.*"):
        customer_column = {
            "agent_name": Customer.agent_name,
            "agent_number": Customer.agent_number,
            "store_number": Customer.store_number,
        }[field]
        customers_query = Customer.query
        if field == "agent_name":
            customers_query = customers_query.filter(
                customer_column.ilike(f"%{query_text}%")
            )
        else:
            customers_query = customers_query.filter(
                func.lower(customer_column) == query_text.lower()
            )
        for customer in customers_query.order_by(
            Customer.created_at.desc()
        ).limit(25).all():
            matches.append(
                _lookup_result(
                    source="Customer Care",
                    agent_name=customer.agent_name or customer.name,
                    agent_number=customer.agent_number,
                    store_number=customer.store_number,
                    business_location=customer.location,
                    category=customer.caller_type,
                    phone_number=customer.phone_number,
                )
            )

    if field == "agent_name":
        client_query = Client.query.filter(
            or_(
                Client.name.ilike(f"%{query_text}%"),
                Client.business_name.ilike(f"%{query_text}%"),
            )
        )
        for client in client_query.order_by(Client.created_at.desc()).limit(25).all():
            matches.append(
                _lookup_result(
                    source="Client directory",
                    agent_name=client.name,
                    business_location=client.business_location,
                    category=client.client_type,
                    owner_phone_number=client.phone_number,
                    phone_number=client.phone_number,
                )
            )

    if can(viewer, "debt_collection.*"):
        debtor_column = {
            "agent_name": DebtCollectionDebtor.first_name,
            "agent_number": DebtCollectionDebtor.agent_no,
            "store_number": DebtCollectionDebtor.store_number,
        }[field]
        if field == "agent_name":
            debtors_query = DebtCollectionDebtor.query.filter(
                or_(
                    DebtCollectionDebtor.first_name.ilike(f"%{query_text}%"),
                    DebtCollectionDebtor.other_names.ilike(f"%{query_text}%"),
                    DebtCollectionDebtor.business_name.ilike(f"%{query_text}%"),
                )
            )
        else:
            debtors_query = DebtCollectionDebtor.query.filter(
                func.lower(debtor_column) == query_text.lower()
            )
        for debtor in debtors_query.filter_by(is_deleted=False).order_by(
            DebtCollectionDebtor.created_at.desc()
        ).limit(25).all():
            matches.append(
                _lookup_result(
                    source="Debt Collection",
                    agent_name=" ".join(
                        filter(None, (debtor.first_name, debtor.other_names))
                    ),
                    agent_number=debtor.agent_no,
                    store_number=debtor.store_number,
                    business_location=debtor.location,
                    category="agent",
                    owner_phone_number=debtor.owner_msisdn,
                    phone_number=debtor.agent_msisdn,
                )
            )

    merged = {}
    for match in matches:
        identity = (
            (match["agent_number"] or "").strip().lower()
            or (match["store_number"] or "").strip().lower()
            or (match["agent_name"] or "").strip().lower()
        )
        if identity not in merged:
            merged[identity] = match
            continue
        current = merged[identity]
        for key, value in match.items():
            if key == "documents":
                current[key] = {**value, **current[key]}
            elif key == "source":
                if value not in current[key]:
                    current[key] = f"{current[key]}, {value}"
            elif not current[key] and value:
                current[key] = value
    return jsonify({"data": {"matches": list(merged.values())}, "error": None})


@sales_bp.post("/reports")
@jwt_required()
def create_report():
    employee = _user()
    if not employee or not employee.is_active:
        return _error("Active user not found", 403)

    payload = request.form.to_dict()
    upload_dir = Path(current_app.config.get("UPLOAD_FOLDER", Path(current_app.root_path).parent / "uploads")) / "sales_reports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    uploaded_files = []
    for uploaded in request.files.getlist("documents"):
        if not uploaded or not uploaded.filename:
            continue
        filename = f"{uuid4().hex}_{secure_filename(uploaded.filename)}"
        uploaded.save(upload_dir / filename)
        uploaded_files.append({"name": uploaded.filename, "filename": filename})

    report, error, status = _create_report(employee, payload, uploaded_files)
    if error:
        return _error(error, status)
    db.session.add(report)
    db.session.flush()
    db.session.add(AuditLog(
        actor_id=employee.id,
        action="sales_report_created",
        entity="SalesDailyReport",
        entity_id=str(report.id),
        event_metadata={"visit_mode": report.visit_mode, "outcome": report.outcome},
    ))
    db.session.commit()
    return jsonify({"data": report.to_dict(), "error": None, "message": "Daily sales report submitted."}), 201


@sales_bp.get("/reports")
@jwt_required()
def list_reports():
    viewer = _user()
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved":
        return _error("Active user not found", 403)
    query = _scope_sales_reports(_sales_reports(), viewer)
    if request.args.get("from"):
        query = query.filter(SalesDailyReport.date_visited >= _date(request.args["from"]))
    if request.args.get("to"):
        query = query.filter(SalesDailyReport.date_visited <= _date(request.args["to"]))
    if request.args.get("employee_id"):
        query = query.filter_by(employee_id=int(request.args["employee_id"]))
    employee_name = (request.args.get("employee_name") or "").strip()
    if employee_name:
        query = query.filter(
            SalesDailyReport.employee.has(
                User.full_name.ilike(f"%{employee_name}%")
            )
        )
    reports = query.order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.created_at.desc()).all()
    return jsonify({"data": [report.to_dict() for report in reports], "error": None})


@sales_bp.patch("/reports/<int:report_id>")
@jwt_required()
def update_report(report_id):
    viewer = _user()
    report = _sales_reports().filter_by(id=report_id).first()
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)
    if not report:
        return _error("Sales report not found", 404)
    previous_registration_status = _analytics_status(report)
    active_assignment = get_active_assignment(viewer.id)
    if (
        not active_assignment
        or (report.department or "").strip().lower()
        != active_assignment.department_name.strip().lower()
    ):
        return _error("Reports outside your active department are read-only", 403)
    payload = request.get_json(silent=True) or {}
    field_types = {
        "agent_name": str, "agent_number": str, "store_number": str,
        "business_owner_name": str, "contact_phone": str, "id_number": str,
        "business_location": str, "admin_name": str, "witness_name": str,
        "witness_id_number": str, "witness_phone": str, "customer_type": str,
        "outcome": str, "visit_mode": str, "notes": str,
    }
    for field, field_type in field_types.items():
        if field in payload:
            value = payload[field]
            if value is not None and not isinstance(value, field_type):
                return _error(f"{field} must be text", 422)
            setattr(report, field, value.strip() if isinstance(value, str) else value)
    for field in ("date_visited", "registration_date"):
        if field in payload:
            try:
                setattr(report, field, _date(payload[field]))
            except (TypeError, ValueError):
                return _error(f"{field} must use YYYY-MM-DD format", 422)
    if report.customer_type not in CUSTOMER_TYPES or report.outcome not in OUTCOMES:
        return _error("Choose a valid customer type and visit outcome", 422)
    if report.visit_mode not in {"field_visit", "telesales"}:
        return _error("visit_mode must be field_visit or telesales", 422)
    if "report_data" in payload:
        if not isinstance(payload["report_data"], dict):
            return _error("report_data must be an object", 422)
        safe_report_data = dict(payload["report_data"])
        safe_report_data.pop("registration_status", None)
        report.report_data = {**(report.report_data or {}), **safe_report_data}
    registration_quality = _analytics_status(report)
    if registration_quality in {"complete", "incomplete"}:
        report.report_data = {
            **(report.report_data or {}),
            "registration_status": registration_quality.upper(),
        }
    else:
        (report.report_data or {}).pop("registration_status", None)
    report.updated_by_id = viewer.id
    current_registration_status = _analytics_status(report)
    if current_registration_status == "complete":
        if previous_registration_status != "complete":
            report.completion_date = date.today()
    else:
        report.completion_date = None
    db.session.add(AuditLog(actor_id=viewer.id, action="sales_report_updated", entity="SalesDailyReport", entity_id=str(report.id), event_metadata={"report_id": report.id}))
    db.session.commit()
    return jsonify({"data": report.to_dict(), "error": None, "message": "Sales report updated."})


@sales_bp.get("/reports/template")
@jwt_required()
def report_template():
    return Response(",".join(CSV_FIELDS) + "\n", mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=sales-report-template.csv"})


@sales_bp.get("/reports/template.xlsx")
@jwt_required()
def report_template_xlsx():
    rows = [{field: "" for field in CSV_FIELDS}]
    return Response(
        _xlsx_bytes(rows, headers=CSV_FIELDS),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sales-report-template.xlsx"},
    )


@sales_bp.get("/reports/export")
@jwt_required()
def export_reports():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)
    query = _scope_sales_reports(_sales_reports(), viewer)
    try:
        for key, column, comparison in (
            ("from", SalesDailyReport.date_visited, ">="),
            ("to", SalesDailyReport.date_visited, "<="),
        ):
            value = request.args.get(key)
            if value:
                parsed = date.fromisoformat(value)
                query = query.filter(column >= parsed if comparison == ">=" else column <= parsed)
        if request.args.get("employee_id"):
            employee_id = int(request.args["employee_id"])
            if employee_id < 1:
                raise ValueError
            query = query.filter(SalesDailyReport.employee_id == employee_id)
    except (TypeError, ValueError):
        return _error("Use ISO dates and a positive employee_id for export filters", 422)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for report in query.order_by(SalesDailyReport.date_visited.desc()).all():
        row = report.to_dict()
        exported = {field: row.get(field, "") for field in CSV_FIELDS}
        exported.update({
            field: (report.documents or {}).get(field, "")
            for field in DOCUMENT_FIELDS
        })
        writer.writerow(exported)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=sales-reports.csv"})


@sales_bp.get("/reports/export.xlsx")
@jwt_required()
def export_reports_xlsx():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)
    query = _scope_sales_reports(_sales_reports(), viewer)
    try:
        for key, column, comparison in (
            ("from", SalesDailyReport.date_visited, ">="),
            ("to", SalesDailyReport.date_visited, "<="),
        ):
            value = request.args.get(key)
            if value:
                parsed = date.fromisoformat(value)
                query = query.filter(column >= parsed if comparison == ">=" else column <= parsed)
        if request.args.get("employee_id"):
            employee_id = int(request.args["employee_id"])
            if employee_id < 1:
                raise ValueError
            query = query.filter(SalesDailyReport.employee_id == employee_id)
    except (TypeError, ValueError):
        return _error("Use ISO dates and a positive employee_id for export filters", 422)
    rows = []
    for report in query.order_by(SalesDailyReport.date_visited.desc()).all():
        serialized = report.to_dict()
        row = {field: serialized.get(field, "") for field in CSV_FIELDS}
        row.update({field: (report.documents or {}).get(field, "") for field in DOCUMENT_FIELDS})
        rows.append(row)
    return Response(
        _xlsx_bytes(rows, headers=CSV_FIELDS),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sales-reports.xlsx"},
    )


def _read_report_upload(uploaded):
    """Read bounded, tabular CSV/XLSX report imports without partially saving rows."""
    try:
        uploaded.stream.seek(0, 2)
        size = uploaded.stream.tell()
        uploaded.stream.seek(0)
    except (AttributeError, OSError):
        size = 0
    if size > 10 * 1024 * 1024:
        raise ValueError("Uploads are limited to 10 MB")
    filename = (uploaded.filename or "").lower()
    if filename.endswith(".csv"):
        return list(csv.DictReader(io.TextIOWrapper(
            uploaded.stream, encoding="utf-8-sig", newline=""
        )))
    if filename.endswith(".xlsx"):
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException

        try:
            workbook = load_workbook(uploaded.stream, read_only=True, data_only=True)
        except (InvalidFileException, OSError, zipfile.BadZipFile) as error:
            raise ValueError("The Excel workbook is invalid") from error
        try:
            worksheet = workbook.active
            rows = worksheet.iter_rows(values_only=True)
            header_row = next(rows, None)
            if not header_row:
                return []
            headers = [str(value or "").strip() for value in header_row]
            if (
                not any(headers)
                or len(headers) != len(set(headers))
                or len(headers) > len(CSV_FIELDS) * 2
            ):
                raise ValueError("The first worksheet row must contain unique column headings")
            result = []
            for row in rows:
                if any(value is not None and str(value).strip() for value in row):
                    values = []
                    for value in row:
                        if isinstance(value, datetime):
                            values.append(value.date().isoformat())
                        elif isinstance(value, date):
                            values.append(value.isoformat())
                        elif isinstance(value, time):
                            values.append(value.isoformat())
                        else:
                            values.append(value)
                    result.append(dict(zip(headers, values)))
                    if len(result) > 500:
                        break
            return result
        finally:
            workbook.close()
    raise ValueError("Upload a CSV or Excel .xlsx file")


def _report_import_owner(importer, row):
    raw_employee_id = row.get("employee_id")
    assignment = _sales_management_assignment(importer)
    if raw_employee_id in (None, ""):
        if assignment:
            raise ValueError("employee_id is required when a manager imports field-agent reports")
        is_sales_employee = _sales_employee_query().filter(
            User.id == importer.id,
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        ).first()
        if is_sales_employee:
            return importer
        raise ValueError("employee_id is required to assign the imported report to a Sales employee")
    try:
        employee_id = int(raw_employee_id)
    except (TypeError, ValueError):
        raise ValueError("employee_id must be a positive Sales employee ID")
    if employee_id < 1:
        raise ValueError("employee_id must be a positive Sales employee ID")

    query = _sales_employee_query().filter(
        User.id == employee_id,
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
    )
    if assignment and assignment.organizational_role != "general_manager":
        query = query.filter(User.id.in_(_sales_employee_ids_for_manager(importer, assignment)))
    elif not assignment and not (
        is_system_admin(importer)
        or (is_hr_admin(importer) and can(importer, "sales_reports.write"))
    ):
        query = query.filter(User.id == importer.id)
    target = query.first()
    if not target:
        raise ValueError("employee_id is outside your permitted active Sales scope")
    return target


@sales_bp.post("/reports/import")
@jwt_required()
def import_reports():
    employee = _user()
    if not employee or not employee.is_active or not can(employee, "sales_reports.write"):
        return _error("Active employee not found", 403)
    uploaded = request.files.get("file")
    if not uploaded:
        return _error("Upload a CSV or Excel .xlsx file", 422)
    try:
        rows = _read_report_upload(uploaded)
    except ValueError as error:
        return _error(str(error), 422)
    except (UnicodeDecodeError, csv.Error, zipfile.BadZipFile):
        return _error("The CSV or Excel file could not be read. Use the supplied template.", 422)
    if len(rows) > 500:
        return _error("Uploads are limited to 500 rows", 422)
    created = []
    errors = []
    for index, row in enumerate(rows, start=2):
        try:
            owner = _report_import_owner(employee, row)
        except ValueError as error:
            errors.append({"row": index, "message": str(error)})
            continue
        report, error, _ = _create_report(owner, row)
        if error:
            errors.append({"row": index, "message": error})
        else:
            report.created_by_id = employee.id
            created.append(report)
    if errors:
        return jsonify({"data": {"created": 0, "errors": errors}, "error": {"message": "CSV validation failed"}}), 422
    db.session.add_all(created)
    db.session.flush()
    db.session.add_all([
        AuditLog(
            actor_id=employee.id,
            action="sales_report_imported",
            entity="SalesDailyReport",
            entity_id=str(report.id),
            event_metadata={"visit_mode": report.visit_mode, "outcome": report.outcome},
        )
        for report in created
    ])
    db.session.commit()
    return jsonify({"data": {"created": len(created), "errors": []}, "error": None, "message": f"Imported {len(created)} daily reports."}), 201


@sales_bp.get("/reports/recovery-follow-ups")
@jwt_required()
def list_report_recovery_follow_ups():
    viewer, error = _analytics_authorized_viewer()
    if error:
        return error
    reports = _scope_sales_reports(_sales_reports(), viewer).filter(
        SalesDailyReport.visit_mode == "field_visit"
    ).order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc()).all()
    tasks = []
    for report in reports:
        if _analytics_status(report) != "incomplete":
            continue
        data = report.report_data or {}
        follow_up = data.get("recovery_follow_up") or {
            "status": "open",
            "due_date": (
                (report.created_at.date() if report.created_at else date.today())
                + timedelta(days=7)
            ).isoformat(),
            "notes": "",
        }
        if follow_up.get("status") == "open":
            tasks.append({
                "report_id": report.id,
                "employee_id": report.employee_id,
                "employee_name": report.employee.full_name if report.employee else None,
                "client_name": report.business_owner_name or report.agent_name,
                "agent_name": report.agent_name,
                "customer_type": report.customer_type,
                "date_visited": report.date_visited.isoformat() if report.date_visited else None,
                "due_date": follow_up.get("due_date"),
                "notes": follow_up.get("notes", ""),
                "missing_requirements": _analytics_missing_requirements(report),
            })
    return jsonify({"data": tasks, "error": None})


@sales_bp.patch("/reports/<int:report_id>/recovery-follow-up")
@jwt_required()
def update_report_recovery_follow_up(report_id):
    viewer = _user()
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved":
        return _error("Active user not found", 403)
    report = _scope_sales_reports(_sales_reports(), viewer).filter_by(id=report_id).first()
    if not report:
        return _error("Sales report not found in your permitted scope", 404)
    if report.visit_mode != "field_visit":
        return _error("Recovery follow-up is only available for field visits", 422)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required")
    documents = payload.get("documents", {})
    if not isinstance(documents, dict):
        return _error("documents must be an object", 422)
    applicable = set(REGISTRATION_DOCUMENT_REQUIREMENTS.get(report.customer_type, ()))
    if set(documents) - applicable:
        return _error("Only applicable registration document fields may be updated", 422)
    for field in ("witness_name", "witness_id_number", "witness_phone"):
        if field in payload and not isinstance(payload[field], str):
            return _error(f"{field} must be text", 422)
    notes = payload.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 1000:
        return _error("notes must be text no longer than 1000 characters", 422)

    updated_documents = dict(report.documents or {})
    for key, value in documents.items():
        if not isinstance(value, (str, bool, int)):
            return _error(f"{key} must be a boolean value", 422)
        updated_documents[key] = _analytics_bool(value)
    report.documents = updated_documents
    for field in ("witness_name", "witness_id_number", "witness_phone"):
        if field in payload:
            setattr(report, field, payload[field].strip() or None)
    current_status = _analytics_status(report)
    existing_follow_up = (report.report_data or {}).get("recovery_follow_up") or {}
    follow_up = {
        **existing_follow_up,
        "status": "completed" if current_status == "complete" else "open",
        "due_date": existing_follow_up.get(
            "due_date", (date.today() + timedelta(days=7)).isoformat()
        ),
        "notes": notes.strip() or existing_follow_up.get("notes", ""),
        "updated_at": datetime.utcnow().isoformat(),
    }
    if current_status == "complete":
        report.completion_date = report.completion_date or date.today()
        report.report_data = {
            **(report.report_data or {}),
            "registration_status": "COMPLETE",
        }
        follow_up["completed_at"] = datetime.utcnow().isoformat()
    else:
        report.completion_date = None
        report.report_data = {
            **(report.report_data or {}),
            "registration_status": "INCOMPLETE",
        }
        follow_up.pop("completed_at", None)
    report.report_data = {**(report.report_data or {}), "recovery_follow_up": follow_up}
    report.updated_by_id = viewer.id
    db.session.add(AuditLog(
        actor_id=viewer.id,
        action="sales_registration_recovery_updated",
        entity="SalesDailyReport",
        entity_id=str(report.id),
        event_metadata={
            "registration_status": current_status.upper(),
            "missing_requirements": _analytics_missing_requirements(report),
        },
    ))
    if viewer.id != report.employee_id:
        db.session.add(Notification(
            user_id=report.employee_id,
            title="Registration recovery updated",
            body=(
                "Your field-visit registration is now complete."
                if current_status == "complete"
                else "A manager updated your registration recovery checklist."
            ),
        ))
    db.session.commit()
    return jsonify({
        "data": {
            "report": report.to_dict(),
            "status": current_status.upper(),
            "follow_up": follow_up,
            "missing_requirements": _analytics_missing_requirements(report),
        },
        "error": None,
    })


TELESALES_RESPONSES = {
    "new",
    "interested",
    "not_interested",
    "ready_to_register",
    "appointment",
    "registered",
    "unreachable",
    "wrong_number",
}
LEGACY_LEAD_STATUSES = {
    "new", "contacted", "no_answer", "callback_requested",
    "converted",
}
LEAD_STATUSES = TELESALES_RESPONSES | LEGACY_LEAD_STATUSES | {"new_or_existing"}
REGISTRATION_DOCUMENTS = {
    "director_id",
    "business_permit",
    "tax_certificate",
    "till_store_number",
}
REACHED_RESPONSES = TELESALES_RESPONSES - {"unreachable", "wrong_number"}
LEGACY_RESPONSE_MAP = {
    "new_or_existing": "new",
    "contacted": "interested",
    "no_answer": "unreachable",
    "callback_requested": "appointment",
    "converted": "registered",
}


def _normalize_telesales_response(value):
    if not isinstance(value, str):
        return None
    normalized = "_".join(value.strip().casefold().replace("&", "and").split())
    if normalized == "new_or_existing":
        return "new"
    return normalized if normalized in TELESALES_RESPONSES else None


def _lead_manager_scope(viewer):
    assignment = _sales_management_assignment(viewer)
    if assignment:
        return assignment
    if is_system_admin(viewer) or (is_hr_admin(viewer) and can(viewer, "sales_reports.view")):
        return "org"
    return None


def _lead_query_for(viewer, manager_scope):
    query = SalesLead.query
    if manager_scope == "org" or manager_scope.organizational_role == "general_manager":
        return query
    employee_ids = _sales_employee_ids_for_manager(viewer, manager_scope)
    return query.filter(
        SalesLead.department_id == manager_scope.department_id,
        or_(
            SalesLead.assigned_to_id.in_(employee_ids),
            SalesLead.created_by_id == viewer.id,
            SalesLead.assigned_to_id.is_(None),
        ),
    )


def _employee_lead_history_query(viewer):
    historically_contacted_ids = db.session.query(
        SalesCallLog.lead_id
    ).filter(
        SalesCallLog.contacted_by_user_id == viewer.id
    ).distinct()
    return SalesLead.query.filter(or_(
        SalesLead.assigned_to_id == viewer.id,
        SalesLead.id.in_(historically_contacted_ids),
    ))


def _filter_sales_leads(query):
    """Apply validated, scope-preserving filters to lead records."""
    parsed_dates = {}
    for key, operator in (("from", ">="), ("to", "<=")):
        value = request.args.get(key)
        if not value:
            continue
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an ISO date")
        parsed_dates[key] = parsed
        if operator == ">=":
            query = query.filter(SalesLead.created_at >= datetime.combine(parsed, time.min))
        else:
            query = query.filter(SalesLead.created_at <= datetime.combine(parsed, time.max))
    if parsed_dates.get("from") and parsed_dates.get("to") and parsed_dates["from"] > parsed_dates["to"]:
        raise ValueError("'from' must not be after 'to'")
    employee_id = request.args.get("employee_id")
    if employee_id:
        try:
            employee_id = int(employee_id)
        except (TypeError, ValueError):
            raise ValueError("employee_id must be a positive integer")
        if employee_id < 1:
            raise ValueError("employee_id must be a positive integer")
        query = query.filter(SalesLead.assigned_to_id == employee_id)
    status = (request.args.get("status") or "").strip().lower()
    if status:
        if status not in LEAD_STATUSES:
            raise ValueError("Choose a valid lead status")
        if status == "new":
            query = query.filter(SalesLead.status.in_({"new", "new_or_existing"}))
        else:
            query = query.filter(SalesLead.status == status)
    if request.args.get("include_archived", "").lower() not in {"true", "1"}:
        query = query.filter(SalesLead.is_archived.is_(False))
    return query


SALES_LEAD_EXPORT_FIELDS = [
    "Business Name", "Head Office Location", "Director's Name", "Phone Number",
    "M-Pesa Agent Name", "M-Pesa Agent Number", "M-Pesa Store Number",
    "Lead ID", "Lead Status", "Assigned Representative", "Call Attempts", "Last Response",
    "Last Contact Date", "Last Contact Day", "Last Contact Time",
    "Last Contacted By", "Last Call Notes", "Reason for Decline",
    "Appointment Date and Time", "Registration Status", "Missing Documents",
    "Reason for Incompleteness", "Open Escalations",
]


def _sales_lead_export_rows(leads):
    rows = []
    for lead in leads:
        latest = max(
            lead.call_logs,
            key=lambda row: (row.contact_datetime, row.id),
            default=None,
        )
        registration = lead.registration
        missing_documents = (
            ", ".join(
                key.replace("_", " ")
                for key, complete in (registration.documents or {}).items()
                if not complete
            )
            if registration and registration.status == "INCOMPLETE"
            else ""
        )
        rows.append({
            "Business Name": lead.company_name or lead.business_name or "",
            "Head Office Location": lead.head_office_location or "",
            "Director's Name": lead.director_name or lead.lead_name,
            "Phone Number": lead.phone_number,
            "M-Pesa Agent Name": lead.mpesa_agent_name or "",
            "M-Pesa Agent Number": lead.mpesa_agent_number or "",
            "M-Pesa Store Number": lead.mpesa_store_number or "",
            "Lead ID": lead.id,
            "Lead Status": (
                _normalize_telesales_response(lead.status) or lead.status
            ),
            "Assigned Representative": lead.assignee.full_name if lead.assignee else "",
            "Call Attempts": len(lead.call_logs),
            "Last Response": (
                _normalize_telesales_response(latest.response) or latest.response
                if latest else ""
            ),
            "Last Contact Date": (
                latest.contact_date.isoformat()
                if latest and latest.contact_date else ""
            ),
            "Last Contact Day": latest.contact_day if latest else "",
            "Last Contact Time": latest.contact_time if latest else "",
            "Last Contacted By": (
                latest.contacted_by.full_name if latest and latest.contacted_by else ""
            ),
            "Last Call Notes": latest.notes if latest and latest.notes else "",
            "Reason for Decline": (
                latest.reason_for_decline if latest and latest.reason_for_decline else ""
            ),
            "Appointment Date and Time": (
                latest.appointment_datetime.isoformat()
                if latest and latest.appointment_datetime else ""
            ),
            "Registration Status": registration.status if registration else "",
            "Missing Documents": missing_documents,
            "Reason for Incompleteness": (
                registration.reason_for_incompleteness if registration else ""
            ),
            "Open Escalations": sum(
                not task.is_completed and task.task_type == "manager_escalation"
                for task in lead.follow_ups
            ),
        })
    return rows


def _sales_lead_from_csv_row(row, employee):
    row = {
        "".join(character for character in str(key or "").strip().lower() if character.isalnum()):
        ("" if value is None else str(value).strip())
        for key, value in row.items()
    }

    def first(*keys):
        return next((row[key] for key in keys if row.get(key)), "")

    company = first("companyname", "businessname", "company", "business")
    lead_name = first(
        "leadname", "directorname", "directorsname", "primarycontactperson",
        "contactname", "name",
    ) or company
    phone = first("phonenumber", "phone", "contact", "primarycontactnumber")
    if not lead_name or not phone:
        raise ValueError("A director/contact name (or company name) and phone number are required")
    if len(lead_name) > 160 or len(phone) > 40:
        raise ValueError("lead name or phone number exceeds the allowed length")
    return SalesLead(
        lead_name=lead_name,
        business_name=company[:160] or None,
        company_name=company[:160] or None,
        director_name=first(
            "directorname", "directorsname", "primarycontactperson", "contactname"
        )[:160] or None,
        phone_number=phone,
        email=first("email", "emailaddress")[:160] or None,
        location=first("businesslocation", "location", "headofficelocation")[:240] or None,
        head_office_location=first("headofficelocation", "headquarterslocation")[:240] or None,
        business_location=first("businesslocation", "businessphysicaladdress")[:240] or None,
        mpesa_agent_name=first("mpesaagentname", "agentname")[:160] or None,
        mpesa_agent_number=first("mpesaagentnumber", "agentnumber")[:80] or None,
        mpesa_store_number=first("mpesastorenumber", "storenumber", "tillnumber")[:80] or None,
        source=first("source", "campaign", "leadsource")[:120] or None,
        department_id=employee.department_id,
        created_by_id=employee.id,
    )


def _read_sales_lead_upload(uploaded):
    filename = (uploaded.filename or "").lower()
    if filename.endswith(".csv"):
        return list(csv.DictReader(io.TextIOWrapper(
            uploaded.stream, encoding="utf-8-sig", newline=""
        )))
    if filename.endswith(".xlsx"):
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException

        try:
            workbook = load_workbook(uploaded.stream, read_only=True, data_only=True)
        except (InvalidFileException, OSError, zipfile.BadZipFile) as error:
            raise ValueError("The Excel workbook is invalid") from error
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers:
            return []
        keys = [str(value or "").strip() for value in headers]
        return [
            dict(zip(keys, row))
            for row in rows
            if any(value is not None and str(value).strip() for value in row)
        ]
    raise ValueError("Upload a CSV or Excel .xlsx file")


@sales_bp.post("/leads/import")
@jwt_required()
def import_sales_leads():
    uploader = _user()
    if (
        not uploader or not uploader.is_currently_active()
        or uploader.account_status != "approved"
        or not _lead_manager_scope(uploader)
    ):
        return _error("Lead uploads are available to Sales & Marketing managers.", 403)
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return _error("Select a CSV or Excel .xlsx lead list", 422)
    try:
        rows = _read_sales_lead_upload(uploaded)
    except (UnicodeDecodeError, csv.Error, ValueError):
        return _error("The lead file could not be read. Upload a valid CSV or Excel .xlsx file.", 422)
    if not rows or len(rows) > 500:
        return _error("Lead uploads must contain between 1 and 500 data rows", 422)
    leads, errors = [], []
    for row_number, row in enumerate(rows, start=2):
        try:
            leads.append(_sales_lead_from_csv_row(row, uploader))
        except ValueError as error:
            errors.append({"row": row_number, "message": str(error)})
    if errors:
        return jsonify({"data": {"created": 0, "errors": errors}, "error": {"message": "Lead-list validation failed"}}), 422

    distribution_requested = str(request.form.get("distribute_evenly", "")).lower() in {"true", "1", "yes"}
    manager_scope = _lead_manager_scope(uploader)
    allowed_ids = (
        _sales_employee_query().filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        ).with_entities(User.id)
        if manager_scope == "org" or manager_scope.organizational_role == "general_manager"
        else _sales_employee_ids_for_manager(uploader, manager_scope)
    )
    employees = _sales_employee_query().filter(User.id.in_(allowed_ids)).order_by(
        User.full_name, User.id
    ).all()
    if distribution_requested and not employees:
        return _error("No active Sales representatives are available for lead distribution.", 422)

    db.session.add_all(leads)
    db.session.flush()
    if distribution_requested:
        for index, lead in enumerate(leads):
            assignee = employees[index % len(employees)]
            lead.assigned_to_id = assignee.id
            lead.allocated_by_id = uploader.id
            lead.allocated_at = datetime.utcnow()
            lead.updated_by_id = uploader.id
            db.session.add(AuditLog(
                actor_id=uploader.id,
                action="sales_lead_allocated",
                entity="SalesLead",
                entity_id=str(lead.id),
                event_metadata={"assignee_id": assignee.id, "distribution": "even"},
            ))
    db.session.add_all([
        AuditLog(
            actor_id=uploader.id,
            action="sales_lead_imported",
            entity="SalesLead",
            entity_id=str(lead.id),
            event_metadata={"status": lead.status, "source": lead.source},
        )
        for lead in leads
    ])
    db.session.commit()
    return jsonify({
        "data": {"created": len(leads), "assigned": len(leads) if distribution_requested else 0, "errors": []},
        "error": None,
        "message": f"Imported {len(leads)} leads" + (" and distributed them evenly." if distribution_requested else "."),
    }), 201


@sales_bp.get("/leads")
@jwt_required()
def list_sales_leads():
    viewer = _user()
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved":
        return _error("Active user not found", 403)
    manager_scope = _lead_manager_scope(viewer)
    include_archived = request.args.get("include_archived", "").lower() in {"true", "1"}
    if include_archived and not manager_scope:
        return _error("Only managers can view archived leads.", 403)
    query = _lead_query_for(viewer, manager_scope) if manager_scope else _employee_lead_history_query(viewer)
    query = query.options(
        selectinload(SalesLead.call_logs).joinedload(SalesCallLog.contacted_by),
        selectinload(SalesLead.registration).joinedload(SalesRegistration.registered_by),
        selectinload(SalesLead.follow_ups),
    )
    try:
        query = _filter_sales_leads(query)
    except ValueError as error:
        return _error(str(error), 422)
    leads = query.order_by(SalesLead.created_at.desc(), SalesLead.id.desc()).limit(1000).all()
    return jsonify({"data": [lead.to_dict() for lead in leads], "error": None})


@sales_bp.get("/leads/export.csv")
@jwt_required()
def export_sales_lead_sheet():
    viewer = _user()
    manager_scope = _lead_manager_scope(viewer) if viewer else None
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved" or not manager_scope:
        return _error("Lead-sheet exports are available to Sales & Marketing managers.", 403)
    try:
        query = _filter_sales_leads(_lead_query_for(viewer, manager_scope))
    except ValueError as error:
        return _error(str(error), 422)
    leads = query.options(
        joinedload(SalesLead.assignee),
        joinedload(SalesLead.registration),
        selectinload(SalesLead.call_logs).joinedload(SalesCallLog.contacted_by),
        selectinload(SalesLead.follow_ups),
    ).order_by(SalesLead.created_at.desc(), SalesLead.id.desc()).limit(10000).all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SALES_LEAD_EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(_sales_lead_export_rows(leads))
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=okoa-telesales-lead-sheet.csv"},
    )


@sales_bp.get("/leads/export.xlsx")
@jwt_required()
def export_sales_lead_sheet_xlsx():
    viewer = _user()
    manager_scope = _lead_manager_scope(viewer) if viewer else None
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved" or not manager_scope:
        return _error("Lead-sheet exports are available to Sales & Marketing managers.", 403)
    try:
        query = _filter_sales_leads(_lead_query_for(viewer, manager_scope))
    except ValueError as error:
        return _error(str(error), 422)
    leads = query.options(
        joinedload(SalesLead.assignee),
        joinedload(SalesLead.registration),
        selectinload(SalesLead.call_logs).joinedload(SalesCallLog.contacted_by),
        selectinload(SalesLead.follow_ups),
    ).order_by(SalesLead.created_at.desc(), SalesLead.id.desc()).limit(10000).all()
    return Response(
        _xlsx_bytes(_sales_lead_export_rows(leads), headers=SALES_LEAD_EXPORT_FIELDS),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=okoa-telesales-lead-sheet.xlsx"},
    )


@sales_bp.get("/leads/export.pdf")
@jwt_required()
def export_sales_lead_sheet_pdf():
    viewer = _user()
    manager_scope = _lead_manager_scope(viewer) if viewer else None
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved" or not manager_scope:
        return _error("Lead-sheet exports are available to Sales & Marketing managers.", 403)
    try:
        query = _filter_sales_leads(_lead_query_for(viewer, manager_scope))
    except ValueError as error:
        return _error(str(error), 422)
    leads = query.options(
        joinedload(SalesLead.assignee),
        joinedload(SalesLead.registration),
        selectinload(SalesLead.call_logs).joinedload(SalesCallLog.contacted_by),
        selectinload(SalesLead.follow_ups),
    ).order_by(SalesLead.created_at.desc(), SalesLead.id.desc()).limit(10000).all()
    rows = _sales_lead_export_rows(leads)
    return Response(
        _pdf_bytes(rows, SALES_LEAD_EXPORT_FIELDS, "Telesales Lead Report"),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=okoa-telesales-lead-sheet.pdf"},
    )


@sales_bp.get("/leads/assignees")
@jwt_required()
def sales_lead_assignees():
    viewer = _user()
    manager_scope = _lead_manager_scope(viewer) if viewer else None
    if not manager_scope:
        return _error("Lead allocation is available to Sales & Marketing managers.", 403)
    ids = (
        _sales_employee_query()
        .filter(User.is_active.is_(True), User.is_archived.is_(False), User.is_deleted.is_(False))
        .with_entities(User.id)
        if manager_scope == "org" or manager_scope.organizational_role == "general_manager"
        else _sales_employee_ids_for_manager(viewer, manager_scope)
    )
    employees = _sales_employee_query().filter(User.id.in_(ids)).order_by(User.full_name, User.id).all()
    return jsonify({"data": [{"id": user.id, "full_name": user.full_name} for user in employees], "error": None})


@sales_bp.get("/leads/analytics")
@jwt_required()
def sales_lead_analytics():
    viewer = _user()
    manager_scope = _lead_manager_scope(viewer) if viewer else None
    if not viewer or (
        not manager_scope
        and not _sales_employee_query().filter(User.id == viewer.id).first()
    ):
        return _error("Lead analytics are available to Sales & Marketing employees and managers.", 403)
    try:
        from_value = request.args.get("from")
        to_value = request.args.get("to")
        from_date = date.fromisoformat(from_value) if from_value else None
        to_date = date.fromisoformat(to_value) if to_value else None
        if (from_value and not from_date) or (to_value and not to_date):
            raise ValueError
        if from_date and to_date and from_date > to_date:
            return _error("'from' must not be after 'to'", 422)
        employee_value = request.args.get("employee_id")
        employee_id = int(employee_value) if employee_value else None
        if employee_id is not None and employee_id < 1:
            raise ValueError
        if employee_id is not None and not manager_scope and employee_id != viewer.id:
            return _error("You may only view your own telesales analytics.", 403)
    except (TypeError, ValueError):
        return _error("Use ISO dates and a positive employee_id for analytics filters", 422)

    scope_query = (
        _lead_query_for(viewer, manager_scope)
        if manager_scope
        else _employee_lead_history_query(viewer)
    )
    scoped_ids = scope_query.with_entities(SalesLead.id)
    lead_query = SalesLead.query.filter(SalesLead.id.in_(scoped_ids), SalesLead.is_archived.is_(False))
    if employee_id and manager_scope:
        lead_query = lead_query.filter(SalesLead.assigned_to_id == employee_id)
    elif not manager_scope:
        lead_query = lead_query.filter(SalesLead.assigned_to_id == viewer.id)
    if from_date:
        lead_query = lead_query.filter(SalesLead.created_at >= datetime.combine(from_date, time.min))
    if to_date:
        lead_query = lead_query.filter(SalesLead.created_at <= datetime.combine(to_date, time.max))
    leads = lead_query.options(selectinload(SalesLead.assignee)).all()

    call_query = SalesCallLog.query.join(SalesLead, SalesCallLog.lead_id == SalesLead.id).filter(
        SalesLead.id.in_(scoped_ids),
    )
    if from_date:
        call_query = call_query.filter(SalesCallLog.contact_date >= from_date)
    if to_date:
        call_query = call_query.filter(SalesCallLog.contact_date <= to_date)
    if employee_id and manager_scope:
        call_query = call_query.filter(SalesCallLog.contacted_by_user_id == employee_id)
    elif not manager_scope:
        call_query = call_query.filter(SalesCallLog.contacted_by_user_id == viewer.id)
    calls = call_query.options(
        joinedload(SalesCallLog.contacted_by),
    ).order_by(SalesCallLog.contact_datetime.desc()).all()

    statuses = {status: 0 for status in sorted(TELESALES_RESPONSES)}
    by_employee = {}
    reached_lead_ids = set()
    interested_responses = {"interested", "ready_to_register", "appointment"}
    for call in calls:
        response = _normalize_telesales_response(call.response) or call.response
        statuses[response] = statuses.get(response, 0) + 1
        if call.reached:
            reached_lead_ids.add(call.lead_id)
        employee = by_employee.setdefault(call.contacted_by_user_id, {
            "employee_id": call.contacted_by_user_id,
            "employee_name": call.contacted_by.full_name if call.contacted_by else "Inactive employee",
            "call_attempts": 0,
            "reached_calls": 0,
            "registered": 0,
            "complete_registrations": 0,
            "incomplete_registrations": 0,
            "responses": {response: 0 for response in sorted(TELESALES_RESPONSES)},
        })
        employee["call_attempts"] += 1
        employee["reached_calls"] += int(call.reached)
        employee["responses"][response] = employee["responses"].get(response, 0) + 1

    for row in by_employee.values():
        row["reachability_rate"] = (
            round(row["reached_calls"] * 100 / row["call_attempts"], 1)
            if row["call_attempts"] else 0
        )

    registrations_query = SalesRegistration.query.join(
        SalesLead, SalesRegistration.lead_id == SalesLead.id
    ).filter(SalesLead.id.in_(scoped_ids))
    if from_date:
        registrations_query = registrations_query.filter(
            SalesRegistration.created_at >= datetime.combine(from_date, time.min)
        )
    if to_date:
        registrations_query = registrations_query.filter(
            SalesRegistration.created_at <= datetime.combine(to_date, time.max)
        )
    if employee_id and manager_scope:
        registrations_query = registrations_query.filter(
            SalesRegistration.registered_by_user_id == employee_id
        )
    elif not manager_scope:
        registrations_query = registrations_query.filter(
            SalesRegistration.registered_by_user_id == viewer.id
        )
    registrations = registrations_query.options(
        joinedload(SalesRegistration.registered_by)
    ).all()
    registration_counts = {"COMPLETE": 0, "INCOMPLETE": 0}
    for registration in registrations:
        registration_counts[registration.status] = registration_counts.get(registration.status, 0) + 1
        employee = by_employee.setdefault(registration.registered_by_user_id, {
            "employee_id": registration.registered_by_user_id,
            "employee_name": (
                registration.registered_by.full_name
                if registration.registered_by else "Inactive employee"
            ),
            "call_attempts": 0,
            "reached_calls": 0,
            "registered": 0,
            "complete_registrations": 0,
            "incomplete_registrations": 0,
            "responses": {response: 0 for response in sorted(TELESALES_RESPONSES)},
        })
        employee["registered"] += 1
        if registration.status == "COMPLETE":
            employee["complete_registrations"] += 1
        elif registration.status == "INCOMPLETE":
            employee["incomplete_registrations"] += 1

    bottleneck_query = registrations_query.filter(SalesRegistration.status == "INCOMPLETE")
    bottlenecks = {}
    for registration in bottleneck_query.all():
        reason = registration.reason_for_incompleteness or "Reason not recorded"
        bottlenecks[reason] = bottlenecks.get(reason, 0) + 1

    total_calls = len(calls)
    reached_calls = sum(call.reached for call in calls)
    assigned_leads = sum(lead.assigned_to_id is not None for lead in leads)
    attempted_lead_ids = {call.lead_id for call in calls}
    interested_lead_ids = {
        call.lead_id for call in calls
        if (_normalize_telesales_response(call.response) or call.response) in interested_responses
    }
    return jsonify({
        "data": {
            "total": len(leads),
            "statuses": statuses,
            "employees": sorted(by_employee.values(), key=lambda row: row["employee_name"].casefold()),
            "call_attempts": total_calls,
            "reached_calls": reached_calls,
            "reachability_rate": round(reached_calls * 100 / total_calls, 1) if total_calls else 0,
            "registration_counts": registration_counts,
            "incomplete_bottlenecks": [
                {"reason": reason, "count": count}
                for reason, count in sorted(bottlenecks.items(), key=lambda item: (-item[1], item[0].casefold()))
            ],
            "funnel": {
                "assigned": assigned_leads,
                "attempted": len(attempted_lead_ids),
                "reached": len(reached_lead_ids),
                "interested_or_appointment": len(interested_lead_ids),
                "registered": registration_counts["COMPLETE"] + registration_counts["INCOMPLETE"],
            },
            "period": {"from": from_value or "", "to": to_value or ""},
        },
        "error": None,
    })


@sales_bp.get("/leads/call-history/export.csv")
@jwt_required()
def export_sales_lead_call_history():
    viewer = _user()
    manager_scope = _lead_manager_scope(viewer) if viewer else None
    if (
        not viewer or not viewer.is_currently_active()
        or viewer.account_status != "approved"
        or (
            not manager_scope
            and not _sales_employee_query().filter(User.id == viewer.id).first()
        )
    ):
        return _error("Call-history exports are available to Sales & Marketing employees and managers.", 403)

    try:
        from_value = request.args.get("from")
        to_value = request.args.get("to")
        from_date = date.fromisoformat(from_value) if from_value else None
        to_date = date.fromisoformat(to_value) if to_value else None
        if from_value and not from_date:
            raise ValueError
        if to_value and not to_date:
            raise ValueError
        if from_date and to_date and from_date > to_date:
            return _error("'from' must not be after 'to'", 422)
        employee_value = request.args.get("employee_id")
        employee_id = int(employee_value) if employee_value else None
        if employee_id is not None and employee_id < 1:
            raise ValueError
    except (TypeError, ValueError):
        return _error("Use ISO dates and a positive employee_id for call-history export", 422)

    scoped_leads = (
        _lead_query_for(viewer, manager_scope)
        if manager_scope
        else _employee_lead_history_query(viewer)
    )
    scoped_ids = scoped_leads.with_entities(SalesLead.id)
    events = SalesCallLog.query.join(
        SalesLead, SalesCallLog.lead_id == SalesLead.id
    ).filter(
        SalesLead.id.in_(scoped_ids),
    ).options(
        joinedload(SalesCallLog.lead).joinedload(SalesLead.assignee),
        joinedload(SalesCallLog.contacted_by),
    )
    if from_date:
        events = events.filter(SalesCallLog.contact_date >= from_date)
    if to_date:
        events = events.filter(SalesCallLog.contact_date <= to_date)
    if employee_id and manager_scope:
        events = events.filter(SalesCallLog.contacted_by_user_id == employee_id)
    elif not manager_scope:
        if employee_id and employee_id != viewer.id:
            return _error("You may only export your own telesales activity.", 403)
        events = events.filter(SalesCallLog.contacted_by_user_id == viewer.id)
    status = request.args.get("status", "").strip().lower()
    if status:
        if status not in TELESALES_RESPONSES:
            return _error("Choose a valid telesales response for call-history export.", 422)
        events = events.filter(SalesCallLog.response == status)

    fields = [
        "event_id", "contact_date", "contact_day", "contact_time", "lead_id",
        "company_name", "director_name", "business_name", "phone_number",
        "head_office_location", "business_location", "mpesa_agent_name",
        "mpesa_agent_number", "mpesa_store_number", "assigned_rep",
        "contacted_by_user_id", "contacted_by", "response", "reached",
        "appointment_datetime", "reason_for_decline", "notes",
    ]
    rows = []
    for event in events.order_by(SalesCallLog.contact_datetime.desc(), SalesCallLog.id.desc()).limit(10000).all():
        lead = event.lead
        rows.append({
            "event_id": event.id,
            "contact_date": event.contact_date.isoformat() if event.contact_date else "",
            "contact_day": event.contact_day,
            "contact_time": event.contact_time,
            "lead_id": lead.id,
            "company_name": lead.company_name or "",
            "director_name": lead.director_name or lead.lead_name,
            "business_name": lead.business_name or "",
            "phone_number": lead.phone_number,
            "head_office_location": lead.head_office_location or "",
            "business_location": lead.business_location or lead.location or "",
            "mpesa_agent_name": lead.mpesa_agent_name or "",
            "mpesa_agent_number": lead.mpesa_agent_number or "",
            "mpesa_store_number": lead.mpesa_store_number or "",
            "assigned_rep": lead.assignee.full_name if lead.assignee else "",
            "contacted_by_user_id": event.contacted_by_user_id,
            "contacted_by": event.contacted_by.full_name if event.contacted_by else "",
            "response": _normalize_telesales_response(event.response) or event.response,
            "reached": event.reached,
            "appointment_datetime": event.appointment_datetime.isoformat() if event.appointment_datetime else "",
            "reason_for_decline": event.reason_for_decline or "",
            "notes": event.notes or "",
        })
    export_format = request.args.get("format", "csv").lower()
    if export_format == "xlsx":
        return Response(
            _xlsx_bytes(rows, headers=fields),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=sales-call-history.xlsx"},
        )
    if export_format == "pdf":
        return Response(
            _pdf_bytes(rows, fields, "Telesales Call History"),
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=sales-call-history.pdf"},
        )
    if export_format != "csv":
        return _error("format must be csv, xlsx, or pdf.", 422)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales-call-history.csv"},
    )


@sales_bp.patch("/leads/<int:lead_id>/allocation")
@jwt_required()
def allocate_sales_lead(lead_id):
    manager = _user()
    manager_scope = _lead_manager_scope(manager) if manager else None
    if not manager_scope:
        return _error("Lead allocation is available to Sales & Marketing managers.", 403)
    lead = _lead_query_for(manager, manager_scope).filter_by(id=lead_id).first()
    if not lead:
        return _error("Lead not found", 404)
    payload = request.get_json(silent=True) or {}
    try:
        employee_id = int(payload.get("employee_id"))
    except (TypeError, ValueError):
        return _error("employee_id must identify an active Sales & Marketing employee", 422)
    allowed_ids = (
        _sales_employee_query().filter(
            User.is_active.is_(True), User.is_archived.is_(False), User.is_deleted.is_(False)
        ).with_entities(User.id)
        if manager_scope == "org" or manager_scope.organizational_role == "general_manager"
        else _sales_employee_ids_for_manager(manager, manager_scope)
    )
    assignee = _sales_employee_query().filter(
        User.id == employee_id,
        User.id.in_(allowed_ids),
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
    ).first()
    if not assignee:
        return _error("Lead can only be allocated to an active employee in your permitted Sales scope", 403)
    before = lead.assigned_to_id
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _error("reason must be text", 422)
    reason = (reason or "").strip()
    if len(reason) > 255:
        return _error("reason must be at most 255 characters", 422)
    if before is not None and not reason:
        return _error("A reason is required when reassigning a lead.", 422)
    lead.assigned_to_id = assignee.id
    lead.allocated_by_id = manager.id
    lead.allocated_at = datetime.utcnow()
    lead.updated_by_id = manager.id
    db.session.add(AuditLog(
        actor_id=manager.id,
        action="sales_lead_allocated",
        entity="SalesLead",
        entity_id=str(lead.id),
        event_metadata={
            "previous_assignee_id": before,
            "assignee_id": assignee.id,
            "reason": reason or None,
        },
    ))
    db.session.commit()
    return jsonify({"data": lead.to_dict(), "error": None})


@sales_bp.post("/leads/assignments/bulk")
@jwt_required()
def bulk_allocate_sales_leads():
    manager = _user()
    manager_scope = _lead_manager_scope(manager) if manager else None
    if not manager_scope:
        return _error("Lead allocation is available to Sales & Marketing managers.", 403)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("lead_ids"), list):
        return _error("lead_ids must be a list and employee_id is required.", 422)
    lead_ids = payload["lead_ids"]
    if (
        not lead_ids
        or len(lead_ids) > 1000
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in lead_ids)
        or len(set(lead_ids)) != len(lead_ids)
    ):
        return _error("lead_ids must contain up to 1000 unique positive integers.", 422)
    try:
        employee_id = int(payload.get("employee_id"))
    except (TypeError, ValueError):
        return _error("employee_id must identify an active Sales representative.", 422)

    allowed_ids = (
        _sales_employee_query().filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        ).with_entities(User.id)
        if manager_scope == "org" or manager_scope.organizational_role == "general_manager"
        else _sales_employee_ids_for_manager(manager, manager_scope)
    )
    assignee = _sales_employee_query().filter(
        User.id == employee_id,
        User.id.in_(allowed_ids),
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
    ).first()
    if not assignee:
        return _error("Leads can only be allocated to active Sales representatives in your permitted scope.", 403)

    leads = _lead_query_for(manager, manager_scope).filter(
        SalesLead.id.in_(lead_ids),
        SalesLead.is_archived.is_(False),
    ).all()
    if len(leads) != len(lead_ids):
        return _error("One or more selected leads could not be found in your permitted scope.", 404)
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _error("reason must be text", 422)
    reason = (reason or "").strip()
    if len(reason) > 255:
        return _error("reason must be at most 255 characters", 422)
    if any(lead.assigned_to_id is not None for lead in leads) and not reason:
        return _error("A reason is required when reassigning leads.", 422)

    now = datetime.utcnow()
    for lead in leads:
        previous_assignee = lead.assigned_to_id
        lead.assigned_to_id = assignee.id
        lead.allocated_by_id = manager.id
        lead.allocated_at = now
        lead.updated_by_id = manager.id
        db.session.add(AuditLog(
            actor_id=manager.id,
            action="sales_lead_allocated",
            entity="SalesLead",
            entity_id=str(lead.id),
            event_metadata={
                "previous_assignee_id": previous_assignee,
                "assignee_id": assignee.id,
                "reason": reason or None,
                "distribution": "bulk",
            },
        ))
    db.session.commit()
    return jsonify({
        "data": {"assigned": len(leads), "employee_id": assignee.id},
        "error": None,
    }), 201


@sales_bp.post("/leads/distribute")
@jwt_required()
def distribute_sales_leads():
    manager = _user()
    manager_scope = _lead_manager_scope(manager) if manager else None
    if not manager_scope:
        return _error("Lead distribution is available to Sales & Marketing managers.", 403)
    employee_query = _sales_employee_query().filter(
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
    )
    if manager_scope != "org" and manager_scope.organizational_role != "general_manager":
        employee_query = employee_query.filter(
            User.id.in_(_sales_employee_ids_for_manager(manager, manager_scope))
        )
    employees = employee_query.order_by(User.full_name, User.id).all()
    if not employees:
        return _error("No active Sales representatives are available for distribution.", 422)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required.", 422)
    lead_ids = payload.get("lead_ids")
    if lead_ids is not None:
        if (
            not isinstance(lead_ids, list)
            or not lead_ids
            or len(lead_ids) > 1000
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in lead_ids)
            or len(set(lead_ids)) != len(lead_ids)
        ):
            return _error("lead_ids must contain up to 1000 unique positive integers.", 422)
        query = _lead_query_for(manager, manager_scope).filter(
            SalesLead.id.in_(set(lead_ids)),
            SalesLead.is_archived.is_(False),
        )
    else:
        query = _lead_query_for(manager, manager_scope).filter(
            SalesLead.assigned_to_id.is_(None),
            SalesLead.is_archived.is_(False),
        )
    leads = query.order_by(SalesLead.created_at, SalesLead.id).limit(1000).all()
    if lead_ids is not None and len(leads) != len(lead_ids):
        return _error("One or more selected leads could not be found in your permitted scope.", 404)
    if not leads:
        return jsonify({"data": {"assigned": 0, "message": "No leads need distribution."}, "error": None})

    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _error("reason must be text", 422)
    reason = (reason or "").strip()
    if len(reason) > 255:
        return _error("reason must be at most 255 characters", 422)
    if any(lead.assigned_to_id is not None for lead in leads) and not reason:
        return _error("A reason is required when reassigning leads.", 422)

    now = datetime.utcnow()
    for index, lead in enumerate(leads):
        assignee = employees[index % len(employees)]
        previous_assignee = lead.assigned_to_id
        lead.assigned_to_id = assignee.id
        lead.allocated_by_id = manager.id
        lead.allocated_at = now
        lead.updated_by_id = manager.id
        db.session.add(AuditLog(
            actor_id=manager.id,
            action="sales_lead_allocated",
            entity="SalesLead",
            entity_id=str(lead.id),
            event_metadata={
                "previous_assignee_id": previous_assignee,
                "assignee_id": assignee.id,
                "reason": reason or None,
                "distribution": "even",
            },
        ))
    db.session.commit()
    return jsonify({
        "data": {"assigned": len(leads), "representatives": len(employees)},
        "error": None,
    })


def _create_sales_call(lead, actor, payload, response):
    response = _normalize_telesales_response(response)
    if not response:
        return _error("Choose one of the eight standard telesales responses.", 422)

    reason = payload.get("reason_for_decline")
    if response == "not_interested" and not isinstance(reason, str):
        return _error("A decline reason is required when the prospect is not interested.", 422)
    reason = reason.strip() if isinstance(reason, str) else ""
    if response == "not_interested" and not reason:
        return _error("A decline reason is required when the prospect is not interested.", 422)
    if len(reason) > 500:
        return _error("Decline reason must not exceed 500 characters.", 422)

    appointment_datetime = None
    appointment_value = payload.get("appointment_datetime")
    if response == "appointment":
        if not isinstance(appointment_value, str) or not appointment_value.strip():
            return _error("Select an appointment date and time.", 422)
        try:
            appointment_datetime = datetime.fromisoformat(
                appointment_value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return _error("Appointment must be a valid ISO date and time.", 422)
        if appointment_datetime.tzinfo:
            appointment_datetime = appointment_datetime.astimezone(timezone.utc).replace(tzinfo=None)
        if appointment_datetime <= datetime.utcnow():
            return _error("Appointment date and time must be in the future.", 422)
    elif appointment_value:
        return _error("Appointment date and time are only valid for the Appointment response.", 422)

    notes = payload.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 5000:
        return _error("Call notes must be text of at most 5000 characters.", 422)

    registration = None
    follow_up = None
    document_values = payload.get("registration_documents")
    incompleteness_reason = payload.get("reason_for_incompleteness")
    if response == "registered":
        if document_values is None:
            document_values = {}
        if (
            not isinstance(document_values, dict)
            or set(document_values) - REGISTRATION_DOCUMENTS
            or any(not isinstance(value, bool) for value in document_values.values())
        ):
            return _error("Registration documents must use the supported document fields.", 422)
        documents = {
            key: document_values.get(key) is True
            for key in sorted(REGISTRATION_DOCUMENTS)
        }
        complete = all(documents.values())
        incompleteness_reason = (
            incompleteness_reason.strip()
            if isinstance(incompleteness_reason, str)
            else ""
        )
        if not complete and not incompleteness_reason:
            return _error("Describe which document or verification is still outstanding.", 422)
        if len(incompleteness_reason) > 500:
            return _error("Incomplete-registration reason must not exceed 500 characters.", 422)
        registration = lead.registration or SalesRegistration(
            lead_id=lead.id,
            registered_by_user_id=actor.id,
        )
        if registration.id:
            SalesFollowUp.query.filter_by(
                registration_id=registration.id,
                is_completed=False,
            ).update({"is_completed": True}, synchronize_session=False)
        registration.registered_by_user_id = actor.id
        registration.status = "COMPLETE" if complete else "INCOMPLETE"
        registration.documents = documents
        registration.reason_for_incompleteness = None if complete else incompleteness_reason
        registration.updated_at = datetime.utcnow()
        db.session.add(registration)
    elif document_values is not None or incompleteness_reason:
        return _error("Registration documents are only accepted for the Registered response.", 422)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    call = SalesCallLog(
        lead_id=lead.id,
        contacted_by_user_id=actor.id,
        contact_datetime=now,
        contact_date=now.date(),
        contact_day=now.strftime("%A"),
        contact_time=now.strftime("%H:%M:%S"),
        response=response,
        reason_for_decline=reason or None,
        appointment_datetime=appointment_datetime,
        notes=notes.strip() or None,
        reached=response not in {"unreachable", "wrong_number"},
        created_at=now,
    )
    db.session.add(call)
    db.session.flush()

    lead.status = response
    lead.updated_by_id = actor.id
    lead.updated_at = now
    lead.outcome_reason = reason or None
    lead.notes = notes.strip() or None
    lead.callback_date = appointment_datetime.date() if appointment_datetime else None
    lead.callback_time = appointment_datetime.strftime("%H:%M") if appointment_datetime else None
    if response == "wrong_number":
        lead.is_archived = True
        lead.archived_at = now
    elif response != "wrong_number":
        lead.is_archived = False
        lead.archived_at = None

    if response == "unreachable":
        follow_up = SalesFollowUp(
            lead_id=lead.id,
            call_log_id=call.id,
            assigned_to_user_id=lead.assigned_to_id or actor.id,
            due_at=now + timedelta(days=1),
            task_type="retry_call",
            notes="Retry unreachable prospect",
        )
    elif response == "appointment":
        follow_up = SalesFollowUp(
            lead_id=lead.id,
            call_log_id=call.id,
            assigned_to_user_id=lead.assigned_to_id or actor.id,
            due_at=appointment_datetime,
            task_type="appointment",
            notes=notes.strip() or "Complete the requested follow-up appointment",
        )
    elif registration and registration.status == "INCOMPLETE":
        follow_up = SalesFollowUp(
            lead_id=lead.id,
            call_log_id=call.id,
            registration=registration,
            assigned_to_user_id=lead.assigned_to_id or actor.id,
            due_at=now + timedelta(days=1),
            task_type="registration_documents",
            notes=incompleteness_reason,
        )
    if follow_up:
        db.session.add(follow_up)

    db.session.add(AuditLog(
        actor_id=actor.id,
        action="sales_call_logged",
        entity="SalesLead",
        entity_id=str(lead.id),
        event_metadata={
            "call_log_id": call.id,
            "response": response,
            "contact_date": call.contact_date.isoformat(),
            "contact_day": call.contact_day,
            "contact_time": call.contact_time,
            "reached": call.reached,
            "registration_status": registration.status if registration else None,
            "follow_up_id": follow_up.id if follow_up else None,
        },
    ))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Telesales call submission failed")
        return _error("Unable to save the call outcome right now.", 500)
    return jsonify({
        "data": {
            "call": call.to_dict(),
            "lead": lead.to_dict(),
            "registration": registration.to_dict() if registration else None,
            "follow_up": follow_up.to_dict() if follow_up else None,
        },
        "error": None,
    }), 201


@sales_bp.post("/leads/<int:lead_id>/calls")
@jwt_required()
def create_sales_call(lead_id):
    actor = _user()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active user not found", 403)
    manager_scope = _lead_manager_scope(actor)
    query = _lead_query_for(actor, manager_scope) if manager_scope else SalesLead.query.filter_by(
        assigned_to_id=actor.id
    )
    lead = query.filter_by(id=lead_id, is_archived=False).first()
    if not lead:
        return _error("Lead not found in your calling queue.", 404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required.", 422)
    response = _normalize_telesales_response(payload.get("response"))
    if not response:
        return _error("Choose one of the eight standard telesales responses.", 422)
    return _create_sales_call(lead, actor, payload, response)


@sales_bp.post("/leads/<int:lead_id>/escalations")
@jwt_required()
def escalate_sales_lead(lead_id):
    actor = _user()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active user not found", 403)
    manager_scope = _lead_manager_scope(actor)
    lead_query = (
        _lead_query_for(actor, manager_scope)
        if manager_scope
        else SalesLead.query.filter_by(assigned_to_id=actor.id)
    )
    lead = lead_query.filter_by(id=lead_id, is_archived=False).first()
    if not lead:
        return _error("Lead not found in your permitted Sales scope.", 404)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required.", 422)
    level = payload.get("level")
    if not isinstance(level, str):
        return _error("Choose a group leader, department manager, or general manager.", 422)
    role_by_level = {
        "group_leader": "team_leader",
        "department_manager": "department_manager",
        "general_manager": "general_manager",
    }
    target_role = role_by_level.get(level)
    reason = payload.get("reason")
    if not target_role:
        return _error("Choose a group leader, department manager, or general manager.", 422)
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 2000:
        return _error("Provide an escalation reason of up to 2000 characters.", 422)

    recipients_query = User.query.join(
        DepartmentAssignmentHistory,
        DepartmentAssignmentHistory.user_id == User.id,
    ).filter(
        DepartmentAssignmentHistory.organizational_role == target_role,
        DepartmentAssignmentHistory.ended_at.is_(None),
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
        User.account_status == "approved",
    ).distinct()
    if target_role != "general_manager":
        if not lead.department_id:
            return _error("This lead has no department assignment for escalation routing.", 422)
        recipients_query = recipients_query.filter(
            DepartmentAssignmentHistory.department_id == lead.department_id
        )
    recipients = recipients_query.order_by(User.id).all()
    if not recipients:
        return _error("No active manager is assigned at the selected escalation level.", 422)

    now = datetime.utcnow()
    task = SalesFollowUp(
        lead_id=lead.id,
        assigned_to_user_id=recipients[0].id,
        due_at=now,
        task_type="manager_escalation",
        notes=reason.strip(),
    )
    db.session.add(task)
    for recipient in recipients:
        db.session.add(Notification(
            user_id=recipient.id,
            title=f"Sales lead escalation: {lead.company_name or lead.business_name or lead.lead_name}",
            body=f"{actor.full_name} escalated this lead to {level.replace('_', ' ')}. Reason: {reason.strip()}",
        ))
    db.session.add(AuditLog(
        actor_id=actor.id,
        action="sales_lead_escalated",
        entity="SalesLead",
        entity_id=str(lead.id),
        event_metadata={
            "level": level,
            "recipient_ids": [recipient.id for recipient in recipients],
            "follow_up_id": task.id,
            "reason": reason.strip(),
        },
    ))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Sales lead escalation failed")
        return _error("Unable to submit the escalation right now.", 500)
    return jsonify({
        "data": {"follow_up": task.to_dict(), "notified_count": len(recipients)},
        "error": None,
    }), 201


@sales_bp.get("/leads/<int:lead_id>/calls")
@jwt_required()
def list_sales_calls(lead_id):
    viewer = _user()
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved":
        return _error("Active user not found", 403)
    manager_scope = _lead_manager_scope(viewer)
    lead_query = _lead_query_for(viewer, manager_scope) if manager_scope else _employee_lead_history_query(viewer)
    lead = lead_query.filter_by(id=lead_id).first()
    if not lead:
        return _error("Lead not found in your permitted Sales scope.", 404)
    logs = SalesCallLog.query.filter_by(lead_id=lead.id).options(
        joinedload(SalesCallLog.contacted_by)
    ).order_by(SalesCallLog.contact_datetime.desc(), SalesCallLog.id.desc()).all()
    return jsonify({"data": [item.to_dict() for item in logs], "error": None})


@sales_bp.patch("/leads/<int:lead_id>/details")
@jwt_required()
def edit_sales_lead_details(lead_id):
    manager = _user()
    manager_scope = _lead_manager_scope(manager) if manager else None
    if not manager_scope:
        return _error("Lead details can only be edited by Sales & Marketing managers.", 403)
    lead = _lead_query_for(manager, manager_scope).filter_by(
        id=lead_id,
        is_archived=False,
    ).first()
    if not lead:
        return _error("Active lead not found in your permitted Sales scope.", 404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return _error("A non-empty JSON object is required.", 422)

    field_map = {
        "business_name": ("business_name", 160),
        "head_office_location": ("head_office_location", 240),
        "director_name": ("director_name", 160),
        "phone_number": ("phone_number", 40),
        "mpesa_agent_name": ("mpesa_agent_name", 160),
        "mpesa_agent_number": ("mpesa_agent_number", 80),
        "mpesa_store_number": ("mpesa_store_number", 80),
        "business_location": ("business_location", 240),
    }
    if not set(payload).issubset(field_map):
        return _error("Only lead contact and business details can be edited.", 422)
    updates = {}
    for key, value in payload.items():
        if not isinstance(value, str):
            return _error(f"{key} must be text.", 422)
        value = value.strip()
        column, maximum_length = field_map[key]
        if len(value) > maximum_length:
            return _error(f"{key} must not exceed {maximum_length} characters.", 422)
        if key == "phone_number" and not value:
            return _error("Phone number is required.", 422)
        updates[column] = value or None

    company = updates.get("business_name", lead.business_name)
    director = updates.get("director_name", lead.director_name)
    phone = updates.get("phone_number", lead.phone_number)
    if not phone or not (company or director):
        return _error("A phone number and a business or director name are required.", 422)
    before = {key: getattr(lead, column) for key, (column, _) in field_map.items() if key in payload}
    for column, value in updates.items():
        setattr(lead, column, value)
    lead.company_name = company
    lead.lead_name = director or company
    lead.updated_by_id = manager.id
    lead.updated_at = datetime.utcnow()
    after = {key: getattr(lead, column) for key, (column, _) in field_map.items() if key in payload}
    db.session.add(AuditLog(
        actor_id=manager.id,
        action="sales_lead_updated",
        entity="SalesLead",
        entity_id=str(lead.id),
        event_metadata={"before": before, "after": after},
    ))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Sales lead edit failed")
        return _error("Unable to update this lead right now.", 500)
    return jsonify({"data": lead.to_dict(), "error": None})


@sales_bp.delete("/leads/<int:lead_id>")
@jwt_required()
def archive_sales_lead(lead_id):
    manager = _user()
    manager_scope = _lead_manager_scope(manager) if manager else None
    if not manager_scope:
        return _error("Leads can only be removed by Sales & Marketing managers.", 403)
    lead = _lead_query_for(manager, manager_scope).filter_by(
        id=lead_id,
        is_archived=False,
    ).first()
    if not lead:
        return _error("Active lead not found in your permitted Sales scope.", 404)
    now = datetime.utcnow()
    lead.is_archived = True
    lead.archived_at = now
    lead.updated_by_id = manager.id
    lead.updated_at = now
    db.session.add(AuditLog(
        actor_id=manager.id,
        action="sales_lead_archived",
        entity="SalesLead",
        entity_id=str(lead.id),
        event_metadata={
            "assigned_to_id": lead.assigned_to_id,
            "call_attempts": len(lead.call_logs),
            "reason": "Archived by Sales & Marketing manager",
        },
    ))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Sales lead archive failed")
        return _error("Unable to remove this lead right now.", 500)
    return jsonify({
        "data": {"id": lead.id, "is_archived": True, "archived_at": now.isoformat()},
        "error": None,
    })


@sales_bp.get("/leads/follow-ups")
@jwt_required()
def list_sales_follow_ups():
    viewer = _user()
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved":
        return _error("Active user not found", 403)
    manager_scope = _lead_manager_scope(viewer)
    query = SalesFollowUp.query.join(SalesLead).filter(SalesFollowUp.is_completed.is_(False))
    if manager_scope:
        query = query.filter(SalesLead.id.in_(_lead_query_for(viewer, manager_scope).with_entities(SalesLead.id)))
        employee_value = request.args.get("employee_id")
        if employee_value:
            try:
                employee_id = int(employee_value)
            except (TypeError, ValueError):
                return _error("employee_id must be a positive integer.", 422)
            query = query.filter(SalesFollowUp.assigned_to_user_id == employee_id)
    else:
        query = query.filter(SalesFollowUp.assigned_to_user_id == viewer.id)
    tasks = query.options(
        joinedload(SalesFollowUp.lead),
        joinedload(SalesFollowUp.assigned_to),
    ).order_by(SalesFollowUp.due_at.asc(), SalesFollowUp.id.asc()).limit(500).all()
    return jsonify({"data": [task.to_dict() for task in tasks], "error": None})


@sales_bp.patch("/leads/follow-ups/<int:follow_up_id>")
@jwt_required()
def complete_sales_follow_up(follow_up_id):
    viewer = _user()
    if not viewer or not viewer.is_currently_active() or viewer.account_status != "approved":
        return _error("Active user not found", 403)
    payload = request.get_json(silent=True)
    if payload != {"is_completed": True}:
        return _error("Set is_completed to true to complete this follow-up.", 422)
    manager_scope = _lead_manager_scope(viewer)
    query = SalesFollowUp.query.filter_by(id=follow_up_id)
    if manager_scope:
        query = query.join(SalesLead).filter(
            SalesLead.id.in_(_lead_query_for(viewer, manager_scope).with_entities(SalesLead.id))
        )
    else:
        query = query.filter_by(assigned_to_user_id=viewer.id)
    task = query.first()
    if not task:
        return _error("Follow-up not found in your permitted Sales scope.", 404)
    task.is_completed = True
    db.session.commit()
    return jsonify({"data": task.to_dict(), "error": None})


@sales_bp.patch("/leads/<int:lead_id>")
@jwt_required()
def update_sales_lead(lead_id):
    actor = _user()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active user not found", 403)
    manager_scope = _lead_manager_scope(actor)
    query = _lead_query_for(actor, manager_scope) if manager_scope else SalesLead.query.filter_by(assigned_to_id=actor.id)
    lead = query.filter_by(id=lead_id).first()
    if not lead:
        return _error("Lead not found", 404)
    payload = request.get_json(silent=True) or {}
    status = payload.get("status", lead.status)
    if not isinstance(status, str) or status not in LEAD_STATUSES:
        return _error("Choose a valid lead status", 422)
    response = LEGACY_RESPONSE_MAP.get(status, status)
    mapped_payload = {
        "reason_for_decline": payload.get("outcome_reason"),
        "notes": payload.get("notes", ""),
    }
    if response == "appointment":
        callback_date_value = payload.get(
            "callback_date", lead.callback_date.isoformat() if lead.callback_date else ""
        )
        callback_time_value = payload.get("callback_time", lead.callback_time or "")
        try:
            callback_date = date.fromisoformat(callback_date_value)
            callback_time = time.fromisoformat(callback_time_value)
            mapped_payload["appointment_datetime"] = datetime.combine(callback_date, callback_time).isoformat()
        except (TypeError, ValueError):
            return _error("A valid callback date and time are required for an appointment.", 422)
    return _create_sales_call(lead, actor, mapped_payload, response)


@sales_bp.get("/reports/<int:report_id>/documents/<path:filename>")
@jwt_required()
def download_document(report_id, filename):
    viewer = _user()
    report = _scope_sales_reports(
        _sales_reports(), viewer
    ).filter_by(id=report_id).first() if viewer else None
    if not viewer or not report:
        return _error("Document not found", 404)
    directory = Path(current_app.config.get("UPLOAD_FOLDER", Path(current_app.root_path).parent / "uploads")) / "sales_reports"
    return send_from_directory(directory, filename, as_attachment=True)


def _v2_page():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 25))))
    except (TypeError, ValueError):
        raise ValueError("page and per_page must be positive integers")
    return page, per_page


def _v2_employee_reports():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return None, None, _error("Active user not found", 403)
    if request.args.get("scope") != "mine":
        return None, None, _error("This endpoint only accepts scope=mine", 403)
    query = _sales_reports().filter_by(employee_id=viewer.id)
    try:
        if request.args.get("from"):
            query = query.filter(SalesDailyReport.date_visited >= _date(request.args["from"]))
        if request.args.get("to"):
            query = query.filter(SalesDailyReport.date_visited <= _date(request.args["to"]))
        page, per_page = _v2_page()
    except ValueError as error:
        return None, None, _error(str(error), 422)
    return viewer, query.order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc()).all(), (page, per_page)


def _v2_team_report_rows():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return None, None, _error("Active user not found", 403)
    if not _sales_management_assignment(viewer):
        return None, None, _error("Team sales reports are available to Sales & Marketing managers.", 403)
    requested_scope = request.args.get("scope")
    if requested_scope and requested_scope != "team":
        return None, None, _error("This endpoint only accepts scope=team", 403)
    query = _scope_sales_reports(_sales_reports(), viewer)
    try:
        if request.args.get("from"):
            query = query.filter(SalesDailyReport.date_visited >= _date(request.args["from"]))
        if request.args.get("to"):
            query = query.filter(SalesDailyReport.date_visited <= _date(request.args["to"]))
        page, per_page = _v2_page()
    except ValueError as error:
        return None, None, _error(str(error), 422)
    return viewer, query.order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc()).all(), (page, per_page)


def _v2_org_report_rows():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return None, None, _error("Active user not found", 403)
    requested_scope = request.args.get("scope")
    if requested_scope and requested_scope != "org":
        return None, None, _error("This endpoint only accepts scope=org", 403)
    query = _sales_reports()
    try:
        if request.args.get("from"):
            query = query.filter(SalesDailyReport.date_visited >= _date(request.args["from"]))
        if request.args.get("to"):
            query = query.filter(SalesDailyReport.date_visited <= _date(request.args["to"]))
        page, per_page = _v2_page()
    except ValueError as error:
        return None, None, _error(str(error), 422)
    return viewer, query.order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc()).all(), (page, per_page)


def _v2_superuser():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return None, None, _error("Active user not found", 403)
    if not is_system_admin(viewer) and not can(viewer, "sales_reports.view"):
        return None, None, _error("Insufficient permissions", 403)
    try:
        page, per_page = _v2_page()
    except ValueError as error:
        return None, None, _error(str(error), 422)
    return viewer, None, (page, per_page)


def _v2_envelope(data):
    return jsonify({"data": data, "error": None})


def _v2_export_url():
    query = request.query_string.decode("utf-8")
    return f"/api/sales/v2/export.csv?{query}" if query else "/api/sales/v2/export.csv"


def _analytics_filters(reports, query_level=False):
    """Validate and apply the shared filters against the scoped report rows."""
    args = request.args
    try:
        from_date = _date(args.get("from"))
        to_date = _date(args.get("to"))
        completion_from = _date(args.get("completion_from"))
        completion_to = _date(args.get("completion_to"))
        if args.get("from") and not from_date:
            raise ValueError("'from' must be an ISO date")
        if args.get("to") and not to_date:
            raise ValueError("'to' must be an ISO date")
        if from_date and to_date and from_date > to_date:
            raise ValueError("'from' must not be after 'to'")
        if args.get("completion_from") and not completion_from:
            raise ValueError("'completion_from' must be an ISO date")
        if args.get("completion_to") and not completion_to:
            raise ValueError("'completion_to' must be an ISO date")
        if completion_from and completion_to and completion_from > completion_to:
            raise ValueError("'completion_from' must not be after 'completion_to'")
        exact_date = _date(args.get("visit_date"))
        if args.get("visit_date") and not exact_date:
            raise ValueError("visit_date must be an ISO date")

        category = (args.get("category") or "").strip().lower()
        if category and category not in CUSTOMER_TYPES:
            raise ValueError("category must be agent or sub_agent")
        outcome = (args.get("outcome") or "").strip().lower()
        if outcome and outcome not in OUTCOMES:
            raise ValueError("outcome is not a supported visit outcome")
        status = (args.get("status") or "").strip().lower()
        if status and status not in {"complete", "incomplete", "not_started"}:
            raise ValueError("status must be complete, incomplete, or not_started")
        registration = (args.get("registration") or "").strip().upper()
        if registration and registration not in {"COMPLETE", "INCOMPLETE"}:
            raise ValueError("registration must be COMPLETE or INCOMPLETE")
        year = int(args["year"]) if args.get("year") else None
        month = int(args["month"]) if args.get("month") else None
        day = int(args["day"]) if args.get("day") else None
        employee_id = int(args["employee_id"]) if args.get("employee_id") else None
        if year is not None and not 1 <= year <= 9999:
            raise ValueError("year must be between 1 and 9999")
        if month is not None and not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        if day is not None and not 0 <= day <= 6:
            raise ValueError("day must be a weekday index from 0 to 6")
        if employee_id is not None and employee_id < 1:
            raise ValueError("employee_id must be a positive integer")

        def optional_bool(name):
            value = args.get(name)
            if value is None or not value.strip():
                return None
            normalized = value.strip().lower()
            if normalized not in {"1", "0", "true", "false", "yes", "no", "y", "n"}:
                raise ValueError(f"{name} must be true or false")
            return _analytics_bool(normalized)

        referral = optional_bool("referral")
        appointment_value = args.get("appointment")
        if appointment_value is None or not appointment_value.strip():
            appointment = None
        else:
            normalized_appointment = appointment_value.strip().lower()
            if normalized_appointment in {"upcoming", "past"}:
                appointment = normalized_appointment
            elif normalized_appointment in {
                "1", "0", "true", "false", "yes", "no", "y", "n"
            }:
                appointment = _analytics_bool(normalized_appointment)
            else:
                raise ValueError("appointment must be upcoming, past, or true/false")
    except (TypeError, ValueError) as error:
        raise ValueError(str(error))

    location = (args.get("location") or "").strip().casefold()
    search = (args.get("search") or "").strip().casefold()
    client_type = (args.get("client_type") or "").strip().casefold()
    if query_level:
        if from_date:
            reports = reports.filter(SalesDailyReport.date_visited >= from_date)
        if to_date:
            reports = reports.filter(SalesDailyReport.date_visited <= to_date)
        if completion_from:
            reports = reports.filter(SalesDailyReport.completion_date >= completion_from)
        if completion_to:
            reports = reports.filter(SalesDailyReport.completion_date <= completion_to)
        if exact_date:
            reports = reports.filter(SalesDailyReport.date_visited == exact_date)
        if year:
            reports = reports.filter(extract("year", SalesDailyReport.date_visited) == year)
        if month:
            reports = reports.filter(extract("month", SalesDailyReport.date_visited) == month)
        if category:
            reports = reports.filter(func.lower(SalesDailyReport.customer_type) == category)
        if employee_id:
            reports = reports.filter(SalesDailyReport.employee_id == employee_id)
        if location:
            reports = reports.filter(func.lower(SalesDailyReport.business_location) == location)
        if outcome:
            reports = reports.filter(func.lower(SalesDailyReport.outcome) == outcome)
        reports = reports.order_by(
            SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc()
        ).yield_per(200)

    def matching_reports():
        for report in reports:
            visit_date = _analytics_date(report.date_visited)
            completion_date = _analytics_date(report.completion_date)
            data = _analytics_report_data(report)
            if from_date and (not visit_date or visit_date < from_date):
                continue
            if to_date and (not visit_date or visit_date > to_date):
                continue
            if completion_from and (not completion_date or completion_date < completion_from):
                continue
            if completion_to and (not completion_date or completion_date > completion_to):
                continue
            if exact_date and visit_date != exact_date:
                continue
            if year and (not visit_date or visit_date.year != year):
                continue
            if month and (not visit_date or visit_date.month != month):
                continue
            if day is not None and (not visit_date or visit_date.weekday() != day):
                continue
            if category and _analytics_category(report) != category:
                continue
            if outcome and str(report.outcome or "").strip().lower() != outcome:
                continue
            if employee_id and report.employee_id != employee_id:
                continue
            if location and location != str(report.business_location or "").casefold():
                continue
            if client_type and client_type != str(data.get("client_type") or "").strip().casefold():
                continue
            has_referral = (
                _analytics_bool(data.get("referral_agreed"))
                or bool(str(data.get("referral_name") or data.get("referral_details") or "").strip())
                or (str(data.get("referral_count") or "0").isdigit() and int(data.get("referral_count") or 0) > 0)
            )
            has_appointment = (
                str(report.outcome or "").lower() == "appointment"
                or bool(str(data.get("appointment_date") or "").strip())
            )
            if referral is not None and has_referral != referral:
                continue
            if appointment in {"upcoming", "past"}:
                appointment_date = _analytics_date(data.get("appointment_date"))
                if not appointment_date:
                    continue
                today = date.today()
                if appointment == "upcoming" and appointment_date < today:
                    continue
                if appointment == "past" and appointment_date >= today:
                    continue
            elif appointment is not None and has_appointment != appointment:
                continue
            derived_status = _analytics_status(report)
            if status and derived_status != status:
                continue
            if registration and derived_status.upper() != registration:
                continue
            if search:
                employee = getattr(report, "employee", None)
                haystack = " ".join(str(value or "") for value in (
                    report.agent_name,
                    report.agent_number,
                    report.store_number,
                    report.business_owner_name,
                    report.business_location,
                    report.notes,
                    getattr(employee, "full_name", ""),
                    report.employee_id,
                    *data.values(),
                )).casefold()
                if search not in haystack:
                    continue
            yield report

    return matching_reports()


def _analytics_authorized_viewer():
    viewer = _user()
    if (
        not viewer
        or not viewer.is_currently_active()
        or viewer.account_status != "approved"
        or not (
            can(viewer, "sales_reports.view")
            or _sales_management_assignment(viewer)
            or is_system_admin(viewer)
        )
    ):
        return None, _error("Insufficient permissions", 403)
    return viewer, None


def _registration_record(report, include_witness_details):
    data = _analytics_report_data(report)
    category = _analytics_category(report)
    documents = [
        {
            "key": key,
            "label": REGISTRATION_DOCUMENT_LABELS.get(key, key.replace("_", " ").title()),
            "applicable": True,
            "submitted": _analytics_document_submitted(report, key),
        }
        for key in REGISTRATION_DOCUMENT_REQUIREMENTS.get(category, ())
    ]
    result = {
        "id": report.id,
        "employee_id": report.employee_id,
        "employee_name": report.employee.full_name if report.employee else None,
        "agent_name": report.agent_name,
        "agent_number": report.agent_number,
        "store_number": report.store_number,
        "business_owner_name": report.business_owner_name,
        "business_location": report.business_location,
        "date_visited": report.date_visited.isoformat() if report.date_visited else None,
        "visit_date": report.date_visited.isoformat() if report.date_visited else None,
        "registration_date": report.registration_date.isoformat() if report.registration_date else None,
        "completion_date": report.completion_date.isoformat() if report.completion_date else None,
        "customer_type": report.customer_type,
        "outcome": report.outcome,
        "registration_status": _analytics_status(report).upper(),
        "stored_registration_status": data.get("registration_status"),
        "registration_started": _analytics_started(report),
        "documents": documents,
        "missing_requirements": _analytics_missing_requirements(report),
        "notes": report.notes,
        "witness_name": report.witness_name,
    }
    if include_witness_details:
        result.update({
            "witness_id_number": report.witness_id_number,
            "witness_phone": report.witness_phone,
        })
    return result


@sales_bp.get("/analytics/registrations")
@jwt_required()
def registration_analytics():
    viewer, error = _analytics_authorized_viewer()
    if error:
        return error
    try:
        reports = _analytics_filters(
            _scope_sales_reports(_sales_reports(), viewer), query_level=True
        )
    except ValueError as error:
        return _error(str(error), 422)
    return jsonify({"data": calculate_registration_analytics(reports), "error": None})


@sales_bp.get("/analytics/registration-records")
@jwt_required()
def registration_analytics_records():
    viewer, error = _analytics_authorized_viewer()
    if error:
        return error
    try:
        page = int(request.args.get("page", 1))
        per_page = min(100, int(request.args.get("per_page", 25)))
        if page < 1 or per_page < 1:
            raise ValueError("page and per_page must be positive integers")
        if request.args.get("per_page") and int(request.args["per_page"]) < 1:
            raise ValueError("per_page must be positive")
        metric = (request.args.get("metric") or "").strip().lower()
        allowed_metrics = {
            "visited", "started", "complete", "incomplete",
            "unconverted", "not_started", "outstanding_followup",
            "document_pending", "document_submitted",
        }
        if metric and metric not in allowed_metrics:
            raise ValueError("metric is not supported")
        document = (request.args.get("document") or request.args.get("document_key") or "").strip()
        known_documents = {
            key for keys in REGISTRATION_DOCUMENT_REQUIREMENTS.values() for key in keys
        } | set(REGISTRATION_DOCUMENT_ALIASES.values())
        if document and document not in known_documents:
            raise ValueError("document must be a known registration document key")
        if metric in {"document_pending", "document_submitted"} and not document:
            raise ValueError("document is required for document_pending/document_submitted metrics")
        query = _analytics_filters(
            _scope_sales_reports(_sales_reports(), viewer), query_level=True
        )
    except (TypeError, ValueError) as error:
        return _error(str(error), 422)

    canonical_document = next(
        (key for key, alias in REGISTRATION_DOCUMENT_ALIASES.items() if alias == document),
        document,
    )
    start = (page - 1) * per_page
    end = start + per_page
    total_rows = 0
    reports_examined = 0
    page_reports = []
    for report in query:
        reports_examined += 1
        if not _analytics_eligible(report):
            continue
        status = _analytics_status(report)
        if metric == "started" and (not _analytics_eligible(report) or not _analytics_started(report)):
            continue
        if metric in {"complete", "incomplete", "not_started"} and (
            not _analytics_eligible(report) or status != metric
        ):
            continue
        if metric == "unconverted" and status != "not_started":
            continue
        if metric == "outstanding_followup" and not _analytics_outstanding_followup(report):
            continue
        if document:
            if metric in {"document_pending", "document_submitted"} and not _analytics_started(report):
                continue
            category = _analytics_category(report)
            applicable = set(REGISTRATION_DOCUMENT_REQUIREMENTS.get(category, ()))
            if canonical_document not in applicable:
                continue
            submitted = _analytics_document_submitted(report, canonical_document)
            if metric == "document_submitted" and not submitted:
                continue
            if metric == "document_pending":
                if submitted:
                    continue
        total_rows += 1
        if start <= total_rows - 1 < end:
            page_reports.append(report)

    writer = can(viewer, "sales_reports.write")
    rows = [_registration_record(report, writer) for report in page_reports]
    filters = {key: value for key, value in request.args.items() if key not in {"page", "per_page"}}
    return jsonify({
        "data": {
            "rows": rows,
            "page": page,
            "per_page": per_page,
            "total_rows": total_rows,
            "filters": filters,
            "calculation": {
                "numerator": total_rows,
                "denominator": reports_examined,
                "formula": "count of filtered records matching metric and document filters",
            },
        },
        "error": None,
    })


@sales_bp.get("/analytics/employee-performance")
@jwt_required()
def employee_registration_performance():
    viewer, error = _analytics_authorized_viewer()
    if error:
        return error
    assignment = _sales_management_assignment(viewer)
    admin_scope = is_system_admin(viewer) or (
        can(viewer, "sales_reports.view") and is_hr_admin(viewer)
    )
    if not assignment and not admin_scope:
        return _error("Employee performance is available to Sales & Marketing managers.", 403)
    try:
        from_date = _date(request.args.get("from"))
        to_date = _date(request.args.get("to"))
        if request.args.get("from") and not from_date:
            raise ValueError("'from' must be an ISO date")
        if request.args.get("to") and not to_date:
            raise ValueError("'to' must be an ISO date")
        if from_date and to_date and from_date > to_date:
            raise ValueError("'from' must not be after 'to'")
        category = (request.args.get("category") or "").strip().lower()
        if category and category not in CUSTOMER_TYPES:
            raise ValueError("category must be agent or sub_agent")
    except (TypeError, ValueError) as error:
        return _error(str(error), 422)

    employee_ids = (
        _sales_employee_ids_for_manager(viewer, assignment)
        if assignment
        else _sales_employee_query()
        .filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        )
        .with_entities(User.id)
    )
    employees = _sales_employee_query().filter(User.id.in_(employee_ids)).order_by(
        User.full_name.asc(), User.id.asc()
    ).all()
    reports = _scope_sales_reports(_sales_reports(), viewer)
    if from_date:
        reports = reports.filter(SalesDailyReport.completion_date >= from_date)
    if to_date:
        reports = reports.filter(SalesDailyReport.completion_date <= to_date)
    if category:
        reports = reports.filter(func.lower(SalesDailyReport.customer_type) == category)
    performance = calculate_employee_performance(
        employees, reports.yield_per(200), from_date, to_date, category or None
    )
    return jsonify({
        "data": {
            **performance,
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
            "category": category or "all",
            "date_basis": "completion_date",
            "scope": assignment.organizational_role if assignment else "org",
        },
        "error": None,
    })


def _field_agent_analytics(reports, employees, from_date, to_date):
    categories = ("agent", "sub_agent")
    by_employee = {}
    feedback = []

    def fresh_metrics():
        return {
            "visits": 0,
            "eligible_visits": 0,
            "registrations_started": 0,
            "complete": 0,
            "incomplete": 0,
        }

    for employee in employees:
        by_employee[employee.id] = {
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "visits": 0,
            "eligible_visits": 0,
            "registrations_started": 0,
            "complete": 0,
            "incomplete": 0,
            "by_category": {category: fresh_metrics() for category in categories},
        }
    for report in reports:
        if report.visit_mode != "field_visit":
            continue
        stats = by_employee.setdefault(report.employee_id, {
            "employee_id": report.employee_id,
            "employee_name": report.employee.full_name if report.employee else "Unknown",
            "visits": 0,
            "eligible_visits": 0,
            "registrations_started": 0,
            "complete": 0,
            "incomplete": 0,
            "by_category": {category: fresh_metrics() for category in categories},
        })
        category = _analytics_category(report)
        status = _analytics_status(report)
        stats["visits"] += 1
        is_eligible_visit = _analytics_eligible(report)
        if is_eligible_visit:
            stats["eligible_visits"] += 1
        cat_stats = stats["by_category"].get(category)
        if cat_stats is None:
            continue
        cat_stats["visits"] += 1
        if is_eligible_visit:
            cat_stats["eligible_visits"] += 1
        if is_eligible_visit and _analytics_started(report):
            stats["registrations_started"] += 1
            cat_stats["registrations_started"] += 1
        if is_eligible_visit and status in {"complete", "incomplete"}:
            stats[status] += 1
            cat_stats[status] += 1
        if status == "incomplete":
            missing = _analytics_missing_requirements(report)
            feedback.append({
                "report_id": report.id,
                "employee_id": report.employee_id,
                "employee_name": stats["employee_name"],
                "client_name": report.business_owner_name or report.agent_name,
                "category": category,
                "date_visited": report.date_visited.isoformat() if report.date_visited else None,
                "missing_requirements": missing,
                "action": "Complete the recovery checklist and verify the missing items.",
            })

    def add_rates(stats):
        eligible_visits = stats["eligible_visits"]
        started = stats["registrations_started"]
        stats["conversion_rate"] = round(started * 100 / eligible_visits, 2) if eligible_visits else 0
        stats["completion_rate"] = round(stats["complete"] * 100 / started, 2) if started else 0
        for category_stats in stats["by_category"].values():
            denominator = category_stats["eligible_visits"]
            started_count = category_stats["registrations_started"]
            category_stats["conversion_rate"] = (
                round(started_count * 100 / denominator, 2) if denominator else 0
            )
            category_stats["completion_rate"] = (
                round(category_stats["complete"] * 100 / started_count, 2)
                if started_count else 0
            )
        if stats["incomplete"]:
            stats["feedback"] = (
                f"Recover {stats['incomplete']} incomplete registration(s); "
                "use the recovery checklist to close missing requirements."
            )
        elif not started:
            stats["feedback"] = "Begin a registration at the next eligible client visit."
        else:
            stats["feedback"] = "Registrations are complete for this range; maintain document checks."

    for stats in by_employee.values():
        add_rates(stats)
    return {
        "from": from_date.isoformat() if from_date else None,
        "to": to_date.isoformat() if to_date else None,
        "agents": sorted(by_employee.values(), key=lambda row: row["employee_name"].casefold()),
        "incomplete_visits": feedback,
        "totals": {
            key: sum(row[key] for row in by_employee.values())
            for key in (
                "visits", "eligible_visits", "registrations_started",
                "complete", "incomplete",
            )
        },
    }


@sales_bp.get("/analytics/field-agents")
@sales_bp.get("/analytics/field-agents/team")
@sales_bp.get("/analytics/field-agents/org")
@jwt_required()
def field_agent_analytics():
    viewer, error = _analytics_authorized_viewer()
    if error:
        return error
    try:
        from_date = _date(request.args.get("from"))
        to_date = _date(request.args.get("to"))
        if request.args.get("from") and not from_date:
            raise ValueError("'from' must be an ISO date")
        if request.args.get("to") and not to_date:
            raise ValueError("'to' must be an ISO date")
        if from_date and to_date and from_date > to_date:
            raise ValueError("'from' must not be after 'to'")
        employee_id = int(request.args["employee_id"]) if request.args.get("employee_id") else None
        if employee_id is not None and employee_id < 1:
            raise ValueError("employee_id must be a positive integer")
    except (TypeError, ValueError) as error:
        return _error(str(error), 422)

    assignment = _sales_management_assignment(viewer)
    if request.path.endswith("/team") and not assignment:
        return _error("Team field-agent analytics are available to Sales & Marketing managers.", 403)
    if request.path.endswith("/org") and not (
        is_system_admin(viewer)
        or (is_hr_admin(viewer) and can(viewer, "sales_reports.view"))
        or (assignment and assignment.organizational_role == "general_manager")
    ):
        return _error("Organization field-agent analytics require organization-level access.", 403)
    if assignment:
        employee_ids = _sales_employee_ids_for_manager(viewer, assignment)
        employees = _sales_employee_query().filter(User.id.in_(employee_ids)).order_by(
            User.full_name.asc(), User.id.asc()
        ).all()
        scope = (
            "org" if assignment.organizational_role == "general_manager" else "team"
        )
    elif is_system_admin(viewer) or (is_hr_admin(viewer) and can(viewer, "sales_reports.view")):
        employees = _sales_employee_query().filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        ).order_by(User.full_name.asc(), User.id.asc()).all()
        scope = "org"
    else:
        employees = [viewer]
        scope = "mine"
    allowed_ids = {employee.id for employee in employees}
    if employee_id and employee_id not in allowed_ids:
        return _error("Employee is outside your permitted Sales scope", 403)
    if employee_id:
        employees = [employee for employee in employees if employee.id == employee_id]

    query = _scope_sales_reports(_sales_reports(), viewer).filter(
        SalesDailyReport.visit_mode == "field_visit"
    )
    if from_date:
        query = query.filter(SalesDailyReport.date_visited >= from_date)
    if to_date:
        query = query.filter(SalesDailyReport.date_visited <= to_date)
    if employee_id:
        query = query.filter(SalesDailyReport.employee_id == employee_id)
    reports = query.order_by(SalesDailyReport.date_visited.desc()).all()
    data = _field_agent_analytics(reports, employees, from_date, to_date)
    data["scope"] = scope
    return jsonify({"data": data, "error": None})


@sales_bp.get("/analytics/field-agents/export.csv")
@sales_bp.get("/analytics/field-agents/export.xlsx")
@jwt_required()
def export_field_agent_analytics():
    response = field_agent_analytics()
    if isinstance(response, tuple):
        return response
    data = response.get_json().get("data") or {}
    headers = [
        "employee_id", "employee_name", "category", "visits",
        "eligible_visits",
        "registrations_started", "complete", "incomplete",
        "conversion_rate", "completion_rate", "feedback",
    ]
    rows = []
    for agent in data.get("agents", []):
        for category, metrics in agent.get("by_category", {}).items():
            rows.append({
                "employee_id": agent["employee_id"],
                "employee_name": agent["employee_name"],
                "category": category,
                **metrics,
                "feedback": agent.get("feedback", ""),
            })
    if request.path.endswith(".xlsx"):
        return Response(
            _xlsx_bytes(rows, headers=headers),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=field-agent-analytics.xlsx"},
        )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=field-agent-analytics.csv"},
    )


@sales_bp.get("/v2/summary")
@require_scope("mine")
@jwt_required()
def v2_summary():
    _viewer, reports, result = _v2_employee_reports()
    if reports is None:
        return result
    page, per_page = result
    data = summary(reports, from_date=request.args.get("from"), to_date=request.args.get("to"))
    start = (page - 1) * per_page
    data.update({"rows": [report.to_dict() for report in reports[start:start + per_page]], "page": page, "per_page": per_page, "total_rows": len(reports), "export_url": _v2_export_url()})
    return _v2_envelope(data)


@sales_bp.get("/v2/submissions/daily")
@require_scope("mine")
@jwt_required()
def v2_daily_submissions():
    _viewer, reports, result = _v2_employee_reports()
    if reports is None:
        return result
    page, per_page = result
    data = daily_submissions(reports, days=request.args.get("days", 30), end_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/funnel")
@require_scope("mine")
@jwt_required()
def v2_funnel():
    _viewer, reports, result = _v2_employee_reports()
    if reports is None:
        return result
    page, per_page = result
    data = funnel(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/referrals")
@require_scope("mine")
@jwt_required()
def v2_referrals():
    _viewer, reports, result = _v2_employee_reports()
    if reports is None:
        return result
    page, per_page = result
    referral_rows = []
    for report in reports:
        payload = report.report_data or {}
        referral_count = payload.get("referral_count", 0)
        referral_name = payload.get("referral_name") or payload.get("referral_details")
        if referral_name or referral_count:
            referral_rows.append({"id": report.id, "date": report.date_visited.isoformat(), "agent_name": report.agent_name, "referral_name": referral_name, "referral_phone": payload.get("referral_phone"), "referral_count": referral_count})
    start = (page - 1) * per_page
    data = {"summary": {"total": len(referral_rows), "referrals": sum(int(row["referral_count"] or 0) for row in referral_rows)}, "rows": referral_rows[start:start + per_page], "page": page, "per_page": per_page, "total_rows": len(referral_rows), "export_url": _v2_export_url()}
    return _v2_envelope(data)


@sales_bp.get("/v2/appointments")
@require_scope({"mine", "team"})
@jwt_required()
def v2_appointments():
    scope = request.args.get("scope", "mine")
    if scope == "team":
        _viewer, reports, result = _v2_team_report_rows()
    else:
        _viewer, reports, result = _v2_employee_reports()
    if reports is None:
        return result
    page, per_page = result
    today = date.today()
    status = request.args.get("status", "upcoming")
    rows = []
    for report in reports:
        payload = report.report_data or {}
        appointment_date = _date(payload.get("appointment_date"))
        if not appointment_date:
            continue
        appointment_status = "upcoming" if appointment_date >= today else "overdue"
        if status not in {"all", appointment_status}:
            continue
        rows.append({"id": report.id, "appointment_date": appointment_date.isoformat(), "appointment_time": payload.get("appointment_time"), "agent_name": report.agent_name, "business_owner_name": report.business_owner_name, "business_location": report.business_location, "status": appointment_status})
    start = (page - 1) * per_page
    data = {"summary": {"total": len(rows), "upcoming": sum(row["status"] == "upcoming" for row in rows), "overdue": sum(row["status"] == "overdue" for row in rows)}, "rows": rows[start:start + per_page], "page": page, "per_page": per_page, "total_rows": len(rows), "export_url": _v2_export_url()}
    return _v2_envelope(data)


@sales_bp.get("/v2/reports")
@require_scope("team")
@jwt_required()
def v2_team_reports():
    _viewer, reports, result = _v2_team_report_rows()
    if reports is None:
        return result
    page, per_page = result
    agent = request.args.get("agent")
    employee_name = (request.args.get("employee_name") or "").strip().casefold()
    category = request.args.get("category")
    status = request.args.get("status")
    filtered = reports
    if agent:
        filtered = [report for report in filtered if agent.lower() in (report.agent_name or "").lower()]
    if employee_name:
        filtered = [
            report for report in filtered
            if employee_name in (report.employee.full_name or "").casefold()
        ]
    if category:
        filtered = [report for report in filtered if (report.customer_type or "").lower() == category.lower()]
    if status:
        filtered = [report for report in filtered if (report.outcome or "").lower() == status.lower()]
    data = summary(filtered, from_date=request.args.get("from"), to_date=request.args.get("to"))
    start = (page - 1) * per_page
    data.update({"rows": [report.to_dict() for report in filtered[start:start + per_page]], "page": page, "per_page": per_page, "total_rows": len(filtered), "export_url": _v2_export_url()})
    return _v2_envelope(data)


@sales_bp.get("/v2/compliance/team")
@require_scope("team")
@jwt_required()
def v2_team_compliance():
    _viewer, reports, result = _v2_team_report_rows()
    if reports is None:
        return result
    page, per_page = result
    data = compliance(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/performance/team")
@require_scope("team")
@jwt_required()
def v2_team_performance():
    _viewer, reports, result = _v2_team_report_rows()
    if reports is None:
        return result
    page, per_page = result
    data = top_performers(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), limit=100, page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/registrations/team")
@require_scope("team")
@jwt_required()
def v2_team_registrations():
    _viewer, reports, result = _v2_team_report_rows()
    if reports is None:
        return result
    page, per_page = result
    category = request.args.get("category")
    if category:
        reports = [report for report in reports if (report.customer_type or "").lower() == category.lower()]
    data = registrations(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/locations")
@require_scope("team")
@jwt_required()
def v2_team_locations():
    _viewer, reports, result = _v2_team_report_rows()
    if reports is None:
        return result
    page, per_page = result
    try:
        limit = min(100, max(1, int(request.args.get("limit", 10))))
    except (TypeError, ValueError):
        return _error("limit must be a positive integer", 422)
    data = locations(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), limit=limit, page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/compliance/org")
@require_scope("org")
@jwt_required()
def v2_org_compliance():
    _viewer, reports, result = _v2_org_report_rows()
    if reports is None:
        return result
    page, per_page = result
    department = request.args.get("dept")
    if department:
        reports = [report for report in reports if (report.department or "").lower() == department.lower()]
    data = compliance(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/registrations/org")
@require_scope("org")
@jwt_required()
def v2_org_registrations():
    _viewer, reports, result = _v2_org_report_rows()
    if reports is None:
        return result
    page, per_page = result
    category = request.args.get("category")
    status = request.args.get("status")
    if category:
        reports = [report for report in reports if (report.customer_type or "").lower() == category.lower()]
    if status:
        reports = [report for report in reports if str((report.report_data or {}).get("registration_status") or "").lower() == status.lower()]
    data = registrations(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/document-gaps")
@require_scope("org")
@jwt_required()
def v2_org_document_gaps():
    _viewer, reports, result = _v2_org_report_rows()
    if reports is None:
        return result
    page, per_page = result
    data = document_gaps(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), document_type=request.args.get("doc_type"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/regions")
@require_scope("org")
@jwt_required()
def v2_org_regions():
    _viewer, reports, result = _v2_org_report_rows()
    if reports is None:
        return result
    page, per_page = result
    data = regions(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/top-performers")
@require_scope("org")
@jwt_required()
def v2_org_top_performers():
    _viewer, reports, result = _v2_org_report_rows()
    if reports is None:
        return result
    page, per_page = result
    try:
        limit = min(100, max(1, int(request.args.get("limit", 10))))
    except (TypeError, ValueError):
        return _error("limit must be a positive integer", 422)
    data = top_performers(reports, from_date=request.args.get("from"), to_date=request.args.get("to"), limit=limit, page=page, per_page=per_page)
    data["export_url"] = _v2_export_url()
    return _v2_envelope(data)


@sales_bp.get("/v2/audit")
@require_scope("org")
@jwt_required()
def v2_superuser_audit():
    _viewer, _unused, result = _v2_superuser()
    if _viewer is None:
        return result
    page, per_page = result
    query = AuditLog.query.filter(
        (AuditLog.entity == "SalesDailyReport")
        | AuditLog.action.like("sales_%")
    )
    if request.args.get("user"):
        try:
            query = query.filter(AuditLog.actor_id == int(request.args["user"]))
        except ValueError:
            return _error("user must be a numeric user id", 422)
    if request.args.get("action"):
        query = query.filter(AuditLog.action.ilike(f"%{request.args['action']}%"))
    try:
        if request.args.get("from"):
            query = query.filter(AuditLog.timestamp >= _date(request.args["from"]))
        if request.args.get("to"):
            query = query.filter(AuditLog.timestamp < _date(request.args["to"]))
    except ValueError as error:
        return _error(str(error), 422)
    entries = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).all()
    start = (page - 1) * per_page
    rows = [{"id": entry.id, "actor_id": entry.actor_id, "actor_name": entry.actor.full_name if entry.actor else None, "action": entry.action, "entity": entry.entity, "entity_id": entry.entity_id, "timestamp": entry.timestamp.isoformat() if entry.timestamp else None, "metadata": entry.event_metadata or {}} for entry in entries[start:start + per_page]]
    data = {"summary": {"total": len(entries)}, "rows": rows, "page": page, "per_page": per_page, "total_rows": len(entries), "export_url": _v2_export_url()}
    return _v2_envelope(data)


@sales_bp.get("/v2/integrity")
@require_scope("org")
@jwt_required()
def v2_superuser_integrity():
    _viewer, _unused, result = _v2_superuser()
    if _viewer is None:
        return result
    reports = _sales_reports().order_by(SalesDailyReport.id.asc()).all()
    return _v2_envelope(integrity(reports))


def _v2_activity(action_prefix):
    _viewer, _unused, result = _v2_superuser()
    if _viewer is None:
        return None, result
    page, per_page = result
    query = AuditLog.query.filter(AuditLog.action.ilike(f"{action_prefix}%"))
    entries = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).all()
    start = (page - 1) * per_page
    rows = [{"id": entry.id, "actor_id": entry.actor_id, "action": entry.action, "entity": entry.entity, "entity_id": entry.entity_id, "timestamp": entry.timestamp.isoformat() if entry.timestamp else None, "metadata": entry.event_metadata or {}} for entry in entries[start:start + per_page]]
    return {"summary": {"total": len(entries)}, "rows": rows, "page": page, "per_page": per_page, "total_rows": len(entries), "export_url": _v2_export_url()}, None


@sales_bp.get("/v2/exports")
@require_scope("org")
@jwt_required()
def v2_superuser_exports():
    data, error = _v2_activity("sales_export")
    if error:
        return error
    return _v2_envelope(data)


@sales_bp.get("/v2/imports")
@require_scope("org")
@jwt_required()
def v2_superuser_imports():
    data, error = _v2_activity("sales_import")
    if error:
        return error
    return _v2_envelope(data)


def _v2_export_rows():
    scope = request.args.get("scope", "mine")
    if scope == "mine":
        _viewer, reports, result = _v2_employee_reports()
    elif scope == "team":
        _viewer, reports, result = _v2_team_report_rows()
    elif scope == "org":
        _viewer, reports, result = _v2_org_report_rows()
    else:
        return None, _error("scope must be mine, team, or org", 403)
    if reports is None:
        return None, result
    agent = request.args.get("agent")
    category = request.args.get("category")
    status = request.args.get("status")
    if agent:
        reports = [report for report in reports if agent.lower() in (report.agent_name or "").lower()]
    if category:
        reports = [report for report in reports if (report.customer_type or "").lower() == category.lower()]
    if status:
        reports = [report for report in reports if (report.outcome or "").lower() == status.lower()]
    return reports, None


def _xlsx_bytes(rows, headers=None):
    headers = headers or (list(rows[0].keys()) if rows else CSV_FIELDS)
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
            cells.append(f'<c r="{column}{row_index}" t="inlineStr"><is><t>{escape(str(value or ""))}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sales Reports" sheetId="1" r:id="rId1"/></sheets></workbook>'
    relationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook_relationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _pdf_bytes(rows, headers, title):
    table_headers = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    table_rows = "".join(
        "<tr>" + "".join(
            f"<td>{escape(str(row.get(header, '') or ''))}</td>"
            for header in headers
        ) + "</tr>"
        for row in rows
    )
    document = f"""<!doctype html>
    <html><head><meta charset="utf-8"><style>
    @page {{ size: A3 landscape; margin: 10mm; }}
    body {{ font: 8px Arial, sans-serif; color: #382719; }}
    h1 {{ color: #783a12; font-size: 17px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: auto; }}
    th {{ background: #f4e9df; color: #783a12; text-align: left; }}
    th, td {{ border: 1px solid #dfd3c8; padding: 4px; overflow-wrap: anywhere; }}
    tr:nth-child(even) {{ background: #fcf8f4; }}
    </style></head><body><h1>{escape(title)}</h1>
    <table><thead><tr>{table_headers}</tr></thead><tbody>{table_rows}</tbody></table>
    </body></html>"""
    from weasyprint import HTML

    return HTML(string=document).write_pdf()


@sales_bp.get("/v2/export.csv")
@require_scope({"mine", "team", "org"})
@jwt_required()
def v2_export_csv():
    reports, error = _v2_export_rows()
    if error:
        return error
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for report in reports:
        row = report.to_dict()
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=sales-reports-v2.csv"})


@sales_bp.get("/v2/export.xlsx")
@require_scope({"mine", "team", "org"})
@jwt_required()
def v2_export_xlsx():
    reports, error = _v2_export_rows()
    if error:
        return error
    rows = [{field: report.to_dict().get(field, "") for field in CSV_FIELDS} for report in reports]
    return Response(_xlsx_bytes(rows), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=sales-reports-v2.xlsx"})


def _v2_action(action):
    actor = _user()
    if not actor or not actor.is_active:
        return None, _error("Active user not found", 403)
    if not can(actor, "sales_reports.write"):
        return None, _error("Insufficient permissions", 403)
    payload = request.get_json(silent=True) or {}
    try:
        report_id = int(payload.get("report_id"))
    except (TypeError, ValueError):
        return None, _error("report_id is required", 422)
    report = _sales_reports().filter_by(id=report_id).first()
    if not report:
        return None, _error("Sales report not found", 404)
    active_assignment = get_active_assignment(actor.id)
    if (
        not active_assignment
        or (report.department or "").strip().lower()
        != active_assignment.department_name.strip().lower()
    ):
        return None, _error("Reports outside your active department are read-only", 403)
    comment = str(payload.get("reason") or payload.get("comment") or "").strip()
    title = {"chase": "Sales report follow-up", "flag": "Sales report flagged", "verify": "Sales report verified"}[action]
    message = comment or {"chase": "Your manager requested a follow-up on this sales report.", "flag": "HR flagged this sales report for review.", "verify": "HR verified this sales report."}[action]
    db.session.add(Notification(user_id=report.employee_id, title=title, body=message))
    db.session.add(AuditLog(actor_id=actor.id, action=f"sales_{action}", entity="SalesDailyReport", entity_id=str(report.id), event_metadata={"reason": comment, "report_id": report.id}))
    db.session.commit()
    return {"id": report.id, "action": action, "notified_user_id": report.employee_id}, None


@sales_bp.post("/v2/actions/chase")
@jwt_required()
def v2_chase_report():
    data, error = _v2_action("chase")
    if error:
        return error
    return _v2_envelope(data)


@sales_bp.post("/v2/actions/flag")
@jwt_required()
def v2_flag_report():
    data, error = _v2_action("flag")
    if error:
        return error
    return _v2_envelope(data)


@sales_bp.post("/v2/actions/verify")
@jwt_required()
def v2_verify_report():
    data, error = _v2_action("verify")
    if error:
        return error
    return _v2_envelope(data)
