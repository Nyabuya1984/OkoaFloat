import csv
import io
import zipfile
from html import escape
from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_from_directory, Response
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import AuditLog, Notification, SalesDailyReport, User
from app.services.sales_reports_v2 import compliance, daily_submissions, document_gaps, funnel, integrity, locations, regions, registrations, summary, top_performers
from app.utils.rbac import require_scope

sales_bp = Blueprint("sales", __name__, url_prefix="/api/sales")
DOCUMENT_FIELDS = {"business_permit", "individual_kra_pin", "six_months_commission", "subagent_agent_contract", "owner_national_id", "sign_contract", "certificate_of_incorporation", "company_kra_pin", "owners_directors_national_ids", "cr12_directors", "commission_statement", "kra_pin", "national_id", "contract", "cr12"}
CUSTOMER_TYPES = {"agent", "sub_agent"}
OUTCOMES = {"existing", "interested", "registered", "ready_to_register", "appointment", "undecided", "promised", "declined"}
DOCUMENT_REQUIREMENTS = {
    "sub_agent": {"business_permit", "individual_kra_pin", "six_months_commission", "subagent_agent_contract", "owner_national_id", "sign_contract"},
    "agent": {"certificate_of_incorporation", "company_kra_pin", "six_months_commission", "owners_directors_national_ids", "cr12_directors"},
}
DOCUMENT_ALIASES = {"individual_kra_pin": "kra_pin", "six_months_commission": "commission_statement", "subagent_agent_contract": "contract", "owner_national_id": "national_id", "certificate_of_incorporation": "incorporation_certificate", "owners_directors_national_ids": "national_id", "cr12_directors": "cr12"}
REPORT_DATA_FIELDS = {
    "new_client", "heard_about_okoa", "interested_in_okoa", "already_uses_okoa", "customers_visited",
    "registered_count", "appointment_count", "undecided_count", "not_interested_count", "referral_count",
    "referral_details", "referral_agreed", "appointment_date", "appointment_time", "follow_up_details", "contract_status", "registration_status",
    "mpesa_admin_id_number", "mpesa_admin_phone",
}
CSV_FIELDS = [
    "agent_name", "agent_number", "store_number", "business_owner_name", "contact_phone", "id_number",
    "business_location", "date_visited", "registration_date", "customer_type", "outcome", "visit_mode",
    "new_client", "heard_about_okoa", "interested_in_okoa", "already_uses_okoa", "customers_visited",
    "registered_count", "appointment_count", "undecided_count", "not_interested_count", "referral_count",
    "referral_details", "follow_up_details", "notes",
]


def _user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _date(value):
    return date.fromisoformat(value) if value else None


def _error(message, status=400):
    return jsonify({"data": None, "error": {"message": message}}), status


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
    report = SalesDailyReport(
        employee_id=employee.id,
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
        admin_name=payload.get("admin_name", "").strip() or None,
        witness_name=payload.get("witness_name", "").strip() or None,
        witness_id_number=payload.get("witness_id_number", "").strip() or None,
        witness_phone=payload.get("witness_phone", "").strip() or None,
        customer_type=payload["customer_type"],
        outcome=payload["outcome"],
        visit_mode=payload.get("visit_mode", "field_visit"),
        notes=payload.get("notes", "").strip() or None,
        documents=documents,
        uploaded_files=uploaded_files or [],
        report_data=report_data,
    )
    return report, None, 201


@sales_bp.post("/reports")
@jwt_required()
def create_report():
    employee = _user()
    if not employee or not employee.is_active:
        return _error("Active user not found", 403)
    department = (employee.department or "").strip()
    if employee.role != "employee":
        return _error("Daily reports are available to employees only", 403)

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
    db.session.commit()
    return jsonify({"data": report.to_dict(), "error": None, "message": "Daily sales report submitted."}), 201


@sales_bp.get("/reports")
@jwt_required()
def list_reports():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)
    query = SalesDailyReport.query
    if viewer.role not in {"manager", "hr_admin"} and not viewer.is_superuser:
        query = query.filter_by(employee_id=viewer.id)
    if request.args.get("from"):
        query = query.filter(SalesDailyReport.date_visited >= _date(request.args["from"]))
    if request.args.get("to"):
        query = query.filter(SalesDailyReport.date_visited <= _date(request.args["to"]))
    if request.args.get("employee_id") and viewer.role in {"manager", "hr_admin"}:
        query = query.filter_by(employee_id=int(request.args["employee_id"]))
    reports = query.order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.created_at.desc()).all()
    return jsonify({"data": [report.to_dict() for report in reports], "error": None})


@sales_bp.patch("/reports/<int:report_id>")
@jwt_required()
def update_report(report_id):
    viewer = _user()
    report = db.session.get(SalesDailyReport, report_id)
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)
    if not report:
        return _error("Sales report not found", 404)
    if viewer.role not in {"manager", "hr_admin"} and not viewer.is_superuser:
        return _error("Only managers and administrators can edit sales reports", 403)

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
    if "report_data" in payload:
        if not isinstance(payload["report_data"], dict):
            return _error("report_data must be an object", 422)
        report.report_data = {**(report.report_data or {}), **payload["report_data"]}
    db.session.add(AuditLog(actor_id=viewer.id, action="sales_report_updated", entity="SalesDailyReport", entity_id=str(report.id), event_metadata={"report_id": report.id}))
    db.session.commit()
    return jsonify({"data": report.to_dict(), "error": None, "message": "Sales report updated."})


@sales_bp.get("/reports/template")
@jwt_required()
def report_template():
    return Response(",".join(CSV_FIELDS) + "\n", mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=sales-report-template.csv"})


@sales_bp.get("/reports/export")
@jwt_required()
def export_reports():
    viewer = _user()
    if not viewer or not viewer.is_active:
        return _error("Active user not found", 403)
    query = SalesDailyReport.query if viewer.role in {"manager", "hr_admin"} or viewer.is_superuser else SalesDailyReport.query.filter_by(employee_id=viewer.id)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for report in query.order_by(SalesDailyReport.date_visited.desc()).all():
        row = report.to_dict()
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=sales-reports.csv"})


@sales_bp.post("/reports/import")
@jwt_required()
def import_reports():
    employee = _user()
    if not employee or not employee.is_active or employee.role != "employee":
        return _error("Active employee not found", 403)
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename.lower().endswith(".csv"):
        return _error("Upload a CSV file", 422)
    try:
        rows = list(csv.DictReader(io.TextIOWrapper(uploaded.stream, encoding="utf-8-sig", newline="")))
    except (UnicodeDecodeError, csv.Error):
        return _error("The CSV file could not be read", 422)
    if len(rows) > 500:
        return _error("CSV uploads are limited to 500 rows", 422)
    created = []
    errors = []
    for index, row in enumerate(rows, start=2):
        report, error, _ = _create_report(employee, row)
        if error:
            errors.append({"row": index, "message": error})
        else:
            created.append(report)
    if errors:
        return jsonify({"data": {"created": 0, "errors": errors}, "error": {"message": "CSV validation failed"}}), 422
    db.session.add_all(created)
    db.session.commit()
    return jsonify({"data": {"created": len(created), "errors": []}, "error": None, "message": f"Imported {len(created)} daily reports."}), 201


@sales_bp.get("/reports/<int:report_id>/documents/<path:filename>")
@jwt_required()
def download_document(report_id, filename):
    viewer = _user()
    report = db.session.get(SalesDailyReport, report_id)
    if not viewer or not report or (viewer.role not in {"manager", "hr_admin"} and not viewer.is_superuser and report.employee_id != viewer.id):
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
    query = SalesDailyReport.query.filter_by(employee_id=viewer.id)
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
    if viewer.role not in {"manager", "hr_admin"} and not viewer.is_superuser:
        return None, None, _error("Team scope requires manager or HR permissions", 403)
    requested_scope = request.args.get("scope")
    if requested_scope and requested_scope != "team":
        return None, None, _error("This endpoint only accepts scope=team", 403)
    query = SalesDailyReport.query.filter(
        SalesDailyReport.employee_id.in_(db.session.query(User.id).filter(User.manager_id == viewer.id))
    )
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
    if viewer.role != "hr_admin" and not viewer.is_superuser:
        return None, None, _error("Organization scope requires HR permissions", 403)
    requested_scope = request.args.get("scope")
    if requested_scope and requested_scope != "org":
        return None, None, _error("This endpoint only accepts scope=org", 403)
    query = SalesDailyReport.query
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
    if viewer.role != "hr_admin" or not viewer.is_superuser:
        return None, None, _error("Super-admin permissions are required", 403)
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
    category = request.args.get("category")
    status = request.args.get("status")
    filtered = reports
    if agent:
        filtered = [report for report in filtered if agent.lower() in (report.agent_name or "").lower()]
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
    query = AuditLog.query
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
    reports = SalesDailyReport.query.order_by(SalesDailyReport.id.asc()).all()
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


def _xlsx_bytes(rows):
    headers = list(rows[0].keys()) if rows else CSV_FIELDS
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


@sales_bp.get("/v2/export.csv")
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
    payload = request.get_json(silent=True) or {}
    try:
        report_id = int(payload.get("report_id"))
    except (TypeError, ValueError):
        return None, _error("report_id is required", 422)
    report = db.session.get(SalesDailyReport, report_id)
    if not report:
        return None, _error("Sales report not found", 404)
    employee = db.session.get(User, report.employee_id)
    can_manage = actor.role == "hr_admin" or actor.is_superuser or (actor.role == "manager" and employee and employee.manager_id == actor.id)
    if action == "chase" and not can_manage:
        return None, _error("Only the direct manager or HR can chase a report", 403)
    if action in {"flag", "verify"} and actor.role != "hr_admin":
        return None, _error("Only HR can perform this action", 403)
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
