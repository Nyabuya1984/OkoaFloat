from datetime import datetime, timedelta
import hashlib
import os
import re
import secrets
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import or_, text

from app.extensions import db
from app.models import AuditLog, AuthSession, Department, LeavePolicy, LeaveType, OtpChallenge, User
from app.utils.phone import normalize_ke_phone
from app.utils.rbac import is_super_admin, normalize_role


auth_bp = Blueprint("auth", __name__)
_revoked_refresh_tokens = set()
OTP_RESEND_DELAY_SECONDS = 5
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def _claims(user):
    return {
        "role": user.role,
        "employee_id": user.employee_id,
        "is_superuser": bool(getattr(user, "is_superuser", False)),
    }


def _hash_otp(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _create_otp(user, purpose):
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OtpChallenge(
        challenge_id=secrets.token_urlsafe(32),
        user_id=user.id,
        phone_number=user.phone_number,
        purpose=purpose,
        code_hash=_hash_otp(code),
        status="active",
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.session.add(challenge)
    db.session.flush()
    if current_app.config.get("STORE_PLAINTEXT_OTP"):
        message = (
            "\n"
            "================ DEVELOPMENT OTP ================\n"
            f"  PURPOSE:   {purpose.upper()}\n"
            f"  PHONE:     {user.phone_number}\n"
            f"  OTP CODE:  {code}\n"
            f"  EXPIRES:   {challenge.expires_at.isoformat()} UTC\n"
            "=================================================="
        )
        current_app.logger.warning("%s", message)
    else:
        current_app.logger.info(
            "OTP generated: purpose=%s expires=%s UTC",
            purpose.upper(),
            challenge.expires_at.isoformat(),
        )
    return challenge


def _verify_otp(challenge_id, phone_number, code, purpose):
    challenge = OtpChallenge.query.filter_by(
        challenge_id=challenge_id,
        phone_number=phone_number,
        purpose=purpose,
        verified_at=None,
    ).first()
    if not challenge:
        return None, "Invalid OTP challenge"
    if challenge.expires_at < datetime.utcnow():
        challenge.status = "expired"
        return None, "OTP has expired"
    if challenge.attempts >= 5:
        return None, "Too many OTP attempts"
    challenge.attempts += 1
    if not secrets.compare_digest(challenge.code_hash, _hash_otp(code or "")):
        return None, "Invalid OTP"
    challenge.verified_at = datetime.utcnow()
    challenge.status = "verified"
    return challenge, None


def _resend_allowed(user, purpose):
    latest = OtpChallenge.query.filter_by(
        user_id=user.id, purpose=purpose
    ).order_by(OtpChallenge.created_at.desc()).first()
    if latest and latest.created_at > datetime.utcnow() - timedelta(seconds=OTP_RESEND_DELAY_SECONDS):
        return False
    return True


def _session_response(user):
    session_id = secrets.token_urlsafe(32)
    db.session.add(
        AuthSession(
            session_id=session_id,
            user_id=user.id,
            expires_at=datetime.utcnow() + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        )
    )
    claims = {**_claims(user), "session_id": session_id}
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
        "session_id": session_id,
        "user": user.to_dict(),
    }


def _error(message, code="BAD_REQUEST", status=400, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return jsonify({"success": False, "error": error}), status


def _record_security_event(action, message, metadata=None):
    metadata = metadata or {}
    db.session.add(
        AuditLog(
            action=action,
            entity="SecurityEvent",
            entity_id=metadata.get("phone_number") or metadata.get("user_id") or None,
            event_metadata={"message": message, **metadata},
        )
    )


def _registration_fields(payload):
    fields = {}
    for field in ("employee_name", "job_position_title", "employer", "department"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            fields[field] = "This field is required."
        elif not 2 <= len(value.strip()) <= 120:
            fields[field] = "Must be between 2 and 120 characters."
    return fields


def _department_for(name):
    normalized = " ".join((name or "").split())
    if not normalized:
        raise ValueError("Department name is required")
    department = Department.query.filter(db.func.lower(Department.name) == normalized.lower()).first()
    if not department:
        department = Department(name=normalized)
        db.session.add(department)
        db.session.flush()
    return department


def _can_create_user(actor, target_role, target_department_name=None):
    if not actor or not actor.is_active or actor.account_status != "approved":
        return False, "Account is not active"
    actor_role = normalize_role(getattr(actor, "role", None))
    target_role_name = normalize_role(target_role)
    if is_super_admin(actor):
        return True, None
    if actor_role in {"SYSTEM_ADMIN", "HR_ADMIN"}:
        if target_role_name == "SUPER_ADMIN":
            return False, "Only the super admin can create super admin accounts"
        if actor_role == "HR_ADMIN" and target_role_name in {"SYSTEM_ADMIN", "SUPER_ADMIN"}:
            return False, "HR administrators can only create employees and managers"
        return True, None
    if actor_role == "MANAGER":
        if target_role_name != "EMPLOYEE":
            return False, "Managers can only create employees"
        if not target_department_name:
            return False, "A department is required for employee creation"
        if (actor.department or "").lower() != target_department_name.lower():
            return False, "Managers can only create employees in their own department"
        return True, None
    return False, "You do not have permission to create users"


def _phone_login(payload):
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    password = payload.get("password")
    user = User.query.filter_by(phone_number=phone_number).first() if phone_number else None
    password_matches = bool(user and password and user.check_password(password))
    if not user or not password_matches:
        current_app.logger.warning(
            "Phone login rejected: normalized_phone=%s user_found=%s password_matches=%s",
            phone_number,
            bool(user),
            password_matches,
        )
        _record_security_event(
            "login_failed",
            "Rejected phone login attempt",
            {"phone_number": phone_number, "reason": "wrong_credentials"},
        )
        return _error("Wrong phone number or password", "UNAUTHORIZED", 401)
    if user.account_status in ("banned", "deactivated") or not user.is_active:
        return _error("This account is no longer active", "FORBIDDEN", 403)
    if user.account_status != "approved":
        return jsonify({
            "account_status": "pending",
            "message": "Your account is pending approval by an administrator or manager.",
        }), 403
    if not _resend_allowed(user, "login"):
        return _error(
            f"Please wait {OTP_RESEND_DELAY_SECONDS} seconds before requesting another OTP",
            "TOO_MANY_REQUESTS",
            429,
        )
    try:
        challenge = _create_otp(user, "login")
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Database failure while creating login OTP")
        message = "Database unavailable. Start MySQL and verify migrations."
        if current_app.debug:
            message = f"{message} ({error})"
        return _error(message, "DATABASE_UNAVAILABLE", 503)
    return jsonify({
        "verification_required": True,
        "challenge_id": challenge.challenge_id,
        "message": (
            "OTP generated. Check the configured delivery channel."
            if not current_app.config.get("STORE_PLAINTEXT_OTP")
            else "OTP generated. Check the development server console."
        ),
    })


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    password = payload.get("password")
    if not phone_number or not password:
        return _error("phone_number and password are required", "VALIDATION_ERROR", 422)
    return _phone_login(payload)


@auth_bp.post("/phone-login")
def phone_login():
    return _phone_login(request.get_json(silent=True) or {})


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    raw_email = payload.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
    required = ("email", "password")
    field_errors = _registration_fields(payload)
    if not phone_number:
        field_errors["phone_number"] = "Enter a valid phone number."
    missing = [field for field in required if not payload.get(field)]
    email = email.strip().lower()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        field_errors["email"] = "Enter a valid email address."
    if missing:
        field_errors.update({field: "This field is required." for field in missing})
    if field_errors:
        return _error("Registration fields are invalid", "VALIDATION_ERROR", 422, field_errors)
    if not isinstance(payload.get("password"), str) or len(payload["password"]) < 8:
        return _error(
            "Registration fields are invalid",
            "VALIDATION_ERROR",
            422,
            {"password": "Must be at least 8 characters."},
        )
    existing_by_email = User.query.filter_by(email=email).first()
    existing_by_phone = User.query.filter_by(phone_number=phone_number).first()
    existing_user = existing_by_email or existing_by_phone

    if existing_by_email and existing_by_phone and existing_by_email.id != existing_by_phone.id:
        return _error("Email and phone number belong to different accounts", status=409)

    if existing_user and (
        existing_user.approved_at is not None
        or (
            existing_user.account_status == "approved"
            and existing_user.is_active
        )
    ):
        return _error("This account is already registered", status=409)

    if existing_user and existing_user.account_status in ("banned", "deactivated"):
        return _error("This account cannot be registered", status=403)

    if existing_user and not _resend_allowed(existing_user, "registration"):
        return _error(
            f"Please wait {OTP_RESEND_DELAY_SECONDS} seconds before requesting another OTP",
            "TOO_MANY_REQUESTS",
            429,
        )
    try:
        user = existing_user or User(
            employee_id=f"EMP-{secrets.token_hex(4).upper()}",
            role="employee",
            is_active=True,
            account_status="pending",
            must_change_password=False,
        )
        employee_name = payload["employee_name"].strip()
        department = _department_for(payload["department"])
        user.full_name = employee_name
        user.employee_name = employee_name
        user.job_position_title = payload["job_position_title"].strip()
        user.employer = payload["employer"].strip()
        user.email = email
        user.phone_number = phone_number
        user.department = department.name
        user.department_id = department.id
        user.contact_phone = phone_number
        user.contact_email = email
        user.account_status = "pending"
        user.is_active = True
        user.set_password(payload["password"])
        db.session.add(user)
        db.session.flush()
        challenge = _create_otp(user, "registration")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Database failure while creating employee registration")
        return _error("Database unavailable. Start MySQL and try again.", "DATABASE_UNAVAILABLE", 503)
    return jsonify({
        "verification_required": True,
        "challenge_id": challenge.challenge_id,
        "message": "A verification code was generated for your phone",
    }), 201


@auth_bp.post("/verify-registration")
def verify_registration():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    if not phone_number or not payload.get("challenge_id") or not payload.get("otp"):
        return _error("phone_number, challenge_id, and otp are required")
    try:
        challenge, error = _verify_otp(
            payload["challenge_id"], phone_number, payload["otp"], "registration"
        )
        if error:
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        user = db.session.get(User, challenge.user_id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error("Unable to verify registration", "SERVER_ERROR", 500)
    return jsonify({
        "account_status": "pending",
        "message": "Registration verified. Your account is pending approval.",
    })


@auth_bp.post("/verify-otp")
def verify_otp():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    if not phone_number or not payload.get("challenge_id") or not payload.get("otp"):
        return _error("phone_number, challenge_id, and otp are required")
    try:
        challenge, error = _verify_otp(
            payload["challenge_id"], phone_number, payload["otp"], "login"
        )
        if error:
            _record_security_event(
                "otp_failed",
                "OTP verification failed",
                {"phone_number": phone_number, "challenge_id": payload.get("challenge_id"), "reason": error},
            )
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        user = db.session.get(User, challenge.user_id)
        response = _session_response(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("OTP verification failed unexpectedly")
        return _error("Unable to verify OTP", "SERVER_ERROR", 500)
    return jsonify(response)


def _admin_access(actor):
    if not actor or not actor.is_active or actor.account_status != "approved":
        return False
    role = normalize_role(getattr(actor, "role", None))
    return role in {"MANAGER", "SYSTEM_ADMIN", "HR_ADMIN", "SUPER_ADMIN"} or getattr(actor, "is_superuser", False) is True


def _can_manage_target(actor, target):
    if not actor or not target or not _admin_access(actor):
        return False
    if is_super_admin(target) and not is_super_admin(actor):
        return False
    actor_role = normalize_role(getattr(actor, "role", None))
    if is_super_admin(actor) or actor_role in {"SYSTEM_ADMIN", "HR_ADMIN"}:
        return True
    return actor_role == "MANAGER" and (target.id == actor.id or target.manager_id == actor.id)


def _protect_super_admin_target(actor, target):
    """Prevent every non-super-admin from reading or mutating the protected account."""
    if is_super_admin(target) and not is_super_admin(actor):
        return _error("Unauthorized action", "FORBIDDEN", 403)
    return None


@auth_bp.get("/admin/departments")
@jwt_required()
def admin_departments():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not _admin_access(actor):
        return _error("Only HR admin and super admin accounts can view departments", "FORBIDDEN", 403)
    departments = Department.query.order_by(Department.name.asc()).all()
    payload = []
    for dept in departments:
        payload.append({
            "id": dept.id,
            "name": dept.name,
            "user_count": User.query.filter_by(department_id=dept.id).count(),
        })
    return jsonify({"data": payload, "error": None})


@auth_bp.post("/admin/departments")
@jwt_required()
def create_department():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can create departments", "FORBIDDEN", 403)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return _error("Department name is required", "VALIDATION_ERROR", 422)
    existing = Department.query.filter(db.func.lower(Department.name) == name.lower()).first()
    if existing:
        return jsonify({"data": {"id": existing.id, "name": existing.name}, "error": None, "message": "Department already exists"})
    dept = Department(name=name)
    db.session.add(dept)
    db.session.commit()
    return jsonify({"data": {"id": dept.id, "name": dept.name, "user_count": 0}, "error": None, "message": "Department created"})


@auth_bp.patch("/admin/departments/<int:department_id>")
@jwt_required()
def update_department(department_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can update departments", "FORBIDDEN", 403)
    dept = db.session.get(Department, department_id)
    if not dept:
        return _error("Department not found", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return _error("Department name is required", "VALIDATION_ERROR", 422)
    duplicate = Department.query.filter(db.func.lower(Department.name) == name.lower(), Department.id != dept.id).first()
    if duplicate:
        return _error("A department with that name already exists", "CONFLICT", 409)
    dept.name = name
    db.session.commit()
    return jsonify({
        "data": {"id": dept.id, "name": dept.name, "user_count": User.query.filter_by(department_id=dept.id).count()},
        "error": None,
        "message": "Department updated",
    })


@auth_bp.delete("/admin/departments/<int:department_id>")
@jwt_required()
def delete_department(department_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can delete departments", "FORBIDDEN", 403)
    dept = db.session.get(Department, department_id)
    if not dept:
        return _error("Department not found", "NOT_FOUND", 404)
    if User.query.filter_by(department_id=dept.id).count() > 0:
        return _error("Department cannot be deleted while it still has users assigned", "CONFLICT", 409)
    db.session.delete(dept)
    db.session.commit()
    return jsonify({"data": {"id": department_id}, "error": None, "message": "Department deleted"})


@auth_bp.get("/admin/leave-types")
@jwt_required()
def admin_leave_types():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can manage leave types", "FORBIDDEN", 403)
    leave_types = LeaveType.query.order_by(LeaveType.name.asc()).all()
    return jsonify({
        "data": [{
            "id": leave_type.id,
            "name": leave_type.name,
            "code": leave_type.code,
            "is_paid": bool(leave_type.is_paid),
            "requires_document": bool(leave_type.requires_document),
            "default_days_per_year": float(leave_type.default_days_per_year or 0),
        } for leave_type in leave_types],
        "error": None,
    })


@auth_bp.post("/admin/leave-types")
@jwt_required()
def create_leave_type():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can create leave types", "FORBIDDEN", 403)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip().upper()
    if not name or not code:
        return _error("Leave type name and code are required", "VALIDATION_ERROR", 422)
    if LeaveType.query.filter((db.func.lower(LeaveType.name) == name.lower()) | (db.func.lower(LeaveType.code) == code.lower())).first():
        return _error("A leave type with that name or code already exists", "CONFLICT", 409)
    leave_type = LeaveType(
        name=name,
        code=code,
        is_paid=bool(payload.get("is_paid", True)),
        requires_document=bool(payload.get("requires_document", False)),
        default_days_per_year=float(payload.get("default_days_per_year") or 0),
    )
    db.session.add(leave_type)
    db.session.flush()
    db.session.add(LeavePolicy(
        leave_type_id=leave_type.id,
        accrual_rate=float(leave_type.default_days_per_year or 0),
        max_carryover=0,
        notice_days_required=0,
    ))
    db.session.commit()
    return jsonify({"data": {"id": leave_type.id, "name": leave_type.name, "code": leave_type.code}, "error": None, "message": "Leave type created"})


@auth_bp.patch("/admin/leave-types/<int:leave_type_id>")
@jwt_required()
def update_leave_type(leave_type_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can update leave types", "FORBIDDEN", 403)
    leave_type = db.session.get(LeaveType, leave_type_id)
    if not leave_type:
        return _error("Leave type not found", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or leave_type.name).strip()
    code = (payload.get("code") or leave_type.code).strip().upper()
    if not name or not code:
        return _error("Leave type name and code are required", "VALIDATION_ERROR", 422)
    duplicate = LeaveType.query.filter(
        (db.func.lower(LeaveType.name) == name.lower()) | (db.func.lower(LeaveType.code) == code.lower()),
        LeaveType.id != leave_type.id,
    ).first()
    if duplicate:
        return _error("A leave type with that name or code already exists", "CONFLICT", 409)
    leave_type.name = name
    leave_type.code = code
    leave_type.is_paid = bool(payload.get("is_paid", leave_type.is_paid))
    leave_type.requires_document = bool(payload.get("requires_document", leave_type.requires_document))
    leave_type.default_days_per_year = float(payload.get("default_days_per_year") or leave_type.default_days_per_year or 0)
    db.session.commit()
    return jsonify({"data": {"id": leave_type.id, "name": leave_type.name, "code": leave_type.code}, "error": None, "message": "Leave type updated"})


@auth_bp.delete("/admin/leave-types/<int:leave_type_id>")
@jwt_required()
def delete_leave_type(leave_type_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can delete leave types", "FORBIDDEN", 403)
    leave_type = db.session.get(LeaveType, leave_type_id)
    if not leave_type:
        return _error("Leave type not found", "NOT_FOUND", 404)
    db.session.delete(leave_type)
    db.session.commit()
    return jsonify({"data": {"id": leave_type_id}, "error": None, "message": "Leave type deleted"})


@auth_bp.get("/admin/workflow-settings")
@jwt_required()
def admin_workflow_settings():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can review workflow settings", "FORBIDDEN", 403)
    default_settings = {
        "handover_threshold_days": 2,
        "handover_report_threshold_days": 3,
        "approval_routing": "manager_then_hr",
        "hr_verification_required": True,
        "require_delegate_for_extended_leave": True,
    }
    settings = current_app.config.get("WORKFLOW_SETTINGS", default_settings)
    return jsonify({"data": settings, "error": None})


@auth_bp.patch("/admin/workflow-settings")
@jwt_required()
def update_admin_workflow_settings():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can update workflow settings", "FORBIDDEN", 403)
    payload = request.get_json(silent=True) or {}
    settings = {
        **current_app.config.get("WORKFLOW_SETTINGS", {
            "handover_threshold_days": 2,
            "handover_report_threshold_days": 3,
            "approval_routing": "manager_then_hr",
            "hr_verification_required": True,
            "require_delegate_for_extended_leave": True,
        }),
        **payload,
    }
    current_app.config["WORKFLOW_SETTINGS"] = settings
    return jsonify({"data": settings, "error": None, "message": "Workflow settings updated"})


@auth_bp.get("/admin/security-events")
@jwt_required()
def admin_security_events():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can view security events", "FORBIDDEN", 403)
    events = AuditLog.query.filter(
        AuditLog.action.in_(["login_failed", "otp_failed", "password_reset_failed", "rate_limit_hit"])
    ).order_by(AuditLog.timestamp.desc()).limit(25).all()
    payload = []
    for event in events:
        actor_user = db.session.get(User, event.actor_id) if event.actor_id else None
        metadata = event.event_metadata or {}
        payload.append({
            "id": event.id,
            "action": event.action,
            "actor": actor_user.full_name if actor_user else "System",
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "message": metadata.get("message") or "Security event",
            "details": metadata,
        })
    return jsonify({"data": payload, "error": None})


@auth_bp.get("/admin/users")
@jwt_required()
def admin_users():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not _admin_access(actor):
        return _error("Only HR admin and super admin accounts can view system users", "FORBIDDEN", 403)
    query = User.query if is_super_admin(actor) else User.query.filter(User.is_superuser.is_(False), User.role != "SUPER_ADMIN")
    users = query.order_by(User.created_at.desc()).all()
    return jsonify({"data": [user.to_dict() for user in users], "error": None})


@auth_bp.post("/admin/users")
@jwt_required()
def create_admin_user():
    actor = db.session.get(User, int(get_jwt_identity()))
    payload = request.get_json(silent=True) or {}
    role = normalize_role(payload.get("role") or "EMPLOYEE")
    department_name = (payload.get("department") or "General").strip() or "General"
    can_create, reason = _can_create_user(actor, role, department_name)
    if not can_create:
        return _error(reason or "You do not have permission to create that user", "FORBIDDEN", 403)

    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    phone_number = normalize_ke_phone(payload.get("phone_number") or payload.get("contact_phone"))
    contact_phone = normalize_ke_phone(payload.get("contact_phone") or phone_number)
    contact_email = (payload.get("contact_email") or email).strip().lower()
    password = payload.get("password") or ""
    if role not in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
        return _error("Invalid role selected", "VALIDATION_ERROR", 422)
    if not full_name or not email or not phone_number or len(password) < 8:
        return _error("full_name, email, phone_number, and a password of at least 8 characters are required", "VALIDATION_ERROR", 422)
    if User.query.filter((User.email == email) | (User.phone_number == phone_number)).first():
        return _error("A user with that email or phone number already exists", "CONFLICT", 409)

    hire_date = None
    if payload.get("hire_date"):
        try:
            hire_date = datetime.strptime(str(payload.get("hire_date")), "%Y-%m-%d").date()
        except ValueError:
            return _error("hire_date must be a valid YYYY-MM-DD value", "VALIDATION_ERROR", 422)

    department = _department_for(department_name)
    user = User(
        employee_id=f"EMP-{secrets.token_hex(4).upper()}",
        full_name=full_name,
        employee_name=full_name,
        job_position_title=payload.get("job_position_title") or "Staff",
        employer=payload.get("employer") or "Okoa Float Ltd",
        email=email,
        phone_number=phone_number,
        contact_phone=contact_phone,
        contact_email=contact_email,
        department=department.name,
        department_id=department.id,
        address_line1=(payload.get("address_line1") or "").strip() or None,
        address_line2=(payload.get("address_line2") or "").strip() or None,
        city=(payload.get("city") or "").strip() or None,
        country=(payload.get("country") or "").strip() or None,
        postal_code=(payload.get("postal_code") or "").strip() or None,
        hire_date=hire_date,
        role=role,
        is_active=True,
        account_status="approved",
        must_change_password=True,
        is_superuser=bool(payload.get("is_superuser")) and is_super_admin(actor),
        manager_id=actor.id if normalize_role(getattr(actor, "role", None)) == "MANAGER" and role == "EMPLOYEE" else None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"data": user.to_dict(), "error": None, "message": "User created successfully"})


@auth_bp.delete("/admin/users/<int:user_id>")
@jwt_required()
def delete_admin_user(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    target = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, target)
    if protected:
        return protected
    if not target or not _can_manage_target(actor, target):
        return _error("User not found", "NOT_FOUND", 404)
    if target.id == actor.id:
        return _error("You cannot delete your own account", "CONFLICT", 409)
    target.is_deleted = True
    target.is_active = False
    target.account_status = "deactivated"
    target.deleted_at = datetime.utcnow()
    target.deleted_by = actor.id
    target.delete_reason = "Deleted by administrator"
    db.session.commit()
    return jsonify({"data": {"id": user_id}, "error": None, "message": "User deleted"})


@auth_bp.patch("/admin/users/<int:user_id>")
@jwt_required()
def update_admin_user(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    target = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, target)
    if protected:
        return protected
    if not target or not _can_manage_target(actor, target):
        return _error("User not found", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    editable_fields = (
        "full_name",
        "employee_name",
        "job_position_title",
        "employer",
        "email",
        "phone_number",
        "contact_phone",
        "contact_email",
        "department",
        "address_line1",
        "address_line2",
        "city",
        "country",
        "postal_code",
        "hire_date",
    )
    for field in editable_fields:
        if field not in payload:
            continue
        value = payload[field]
        if field in {"email", "contact_email"}:
            value = str(value).strip().lower()
        elif field in {"phone_number", "contact_phone"}:
            value = normalize_ke_phone(value)
        elif field == "hire_date":
            if not value:
                target.hire_date = None
                continue
            try:
                target.hire_date = datetime.strptime(str(value), "%Y-%m-%d").date()
                continue
            except ValueError:
                return _error("hire_date must be a valid YYYY-MM-DD value", "VALIDATION_ERROR", 422)
        elif field in {"department", "full_name", "employee_name", "job_position_title", "employer", "address_line1", "address_line2", "city", "country", "postal_code"}:
            value = str(value).strip()
        if not value and field not in {"address_line1", "address_line2", "city", "country", "postal_code"}:
            return _error(f"{field} is required", "VALIDATION_ERROR", 422)
        if field == "department":
            department = _department_for(value or "General")
            target.department = department.name
            target.department_id = department.id
            continue
        if field == "full_name":
            target.full_name = value
            target.employee_name = value
            continue
        if field == "email":
            target.email = value
            if not target.contact_email:
                target.contact_email = value
            continue
        if field == "contact_phone":
            target.contact_phone = value
            continue
        if field == "contact_email":
            target.contact_email = value
            continue
        if field == "phone_number":
            target.phone_number = value
            if not target.contact_phone:
                target.contact_phone = value
            continue
        setattr(target, field, value or None)
    if "full_name" in payload:
        target.employee_name = target.full_name
    if is_super_admin(actor):
        if "role" in payload:
            next_role = normalize_role(payload["role"])
            if next_role not in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
                return _error("Invalid role selected", "VALIDATION_ERROR", 422)
            target.role = next_role
        if "is_superuser" in payload:
            target.is_superuser = bool(payload["is_superuser"])
        if "manager_id" in payload:
            target.manager_id = payload["manager_id"] or None
    db.session.commit()
    return jsonify({"data": target.to_dict(), "error": None, "message": "User updated successfully"})


@auth_bp.post("/admin/users/<int:user_id>/status")
@jwt_required()
def update_admin_user_status(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    target = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, target)
    if protected:
        return protected
    if not target or not _can_manage_target(actor, target):
        return _error("User not found", "NOT_FOUND", 404)
    if target.id == actor.id:
        return _error("You cannot change your own account status", "CONFLICT", 409)
    status = (request.get_json(silent=True) or {}).get("status", "").strip().lower()
    if status not in {"active", "deactivated", "archived"}:
        return _error("status must be active, deactivated, or archived", "VALIDATION_ERROR", 422)
    target.is_active = status == "active"
    target.is_archived = status == "archived"
    target.account_status = "approved" if status == "active" else "deactivated"
    target.deactivated_at = None if status == "active" else datetime.utcnow()
    target.deactivated_by = None if status == "active" else actor.id
    db.session.commit()
    return jsonify({"data": target.to_dict(), "error": None, "message": f"User {status}"})


@auth_bp.post("/admin/users/<int:user_id>/role")
@jwt_required()
def update_admin_user_role(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can change user roles", "FORBIDDEN", 403)
    target = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, target)
    if protected:
        return protected
    if not target:
        return _error("User not found", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    role = (payload.get("role") or target.role).strip()
    role = normalize_role(role)
    if role not in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
        return _error("Invalid role selected", "VALIDATION_ERROR", 422)
    if role == "SUPER_ADMIN" and not is_super_admin(actor):
        return _error("Unauthorized action", "FORBIDDEN", 403)
    if role in {"SYSTEM_ADMIN", "HR_ADMIN"} and not payload.get("is_superuser", False):
        target.is_superuser = False
    else:
        target.is_superuser = bool(payload.get("is_superuser"))
    target.role = role
    db.session.commit()
    return jsonify({"data": target.to_dict(), "error": None, "message": "Role updated successfully"})


@auth_bp.get("/admin/audit")
@jwt_required()
def admin_audit():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not _admin_access(actor):
        return _error("Only HR admin and super admin accounts can view the audit log", "FORBIDDEN", 403)
    logs = []
    for entry in db.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(20).all():
        actor_user = db.session.get(User, entry.actor_id) if entry.actor_id else None
        logs.append({
            "id": entry.id,
            "action": entry.action,
            "entity": entry.entity,
            "entity_id": entry.entity_id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "actor": actor_user.full_name if actor_user else "System",
            "metadata": entry.event_metadata,
        })
    return jsonify({"data": logs, "error": None})


@auth_bp.get("/admin/system-health")
@jwt_required()
def admin_system_health():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not getattr(actor, "is_superuser", False):
        return _error("Only the super admin can view system health", "FORBIDDEN", 403)

    upload_dir = os.path.abspath(os.path.join(current_app.root_path, "..", "uploads"))
    os.makedirs(upload_dir, exist_ok=True)
    try:
        db.session.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception:
        database_status = "disconnected"
    return jsonify({
        "data": {
            "database": database_status,
            "uploads_dir": upload_dir,
            "uploads_ready": os.path.isdir(upload_dir),
            "active_users": User.query.filter_by(is_active=True).count(),
            "pending_users": User.query.filter_by(account_status="pending").count(),
        },
        "error": None,
    })


@auth_bp.post("/request-password-reset")
def request_password_reset():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    user = User.query.filter_by(phone_number=phone_number).first() if phone_number else None
    if not user or not user.is_active or user.account_status in ("banned", "deactivated"):
        return jsonify({"message": "If the phone number is registered, a verification code was sent"})
    if not _resend_allowed(user, "password_reset"):
        return _error(
            f"Please wait {OTP_RESEND_DELAY_SECONDS} seconds before requesting another OTP",
            "TOO_MANY_REQUESTS",
            429,
        )
    try:
        challenge = _create_otp(user, "password_reset")
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error("Unable to send verification code", "SERVER_ERROR", 500)
    return jsonify({
        "verification_required": True,
        "challenge_id": challenge.challenge_id,
        "message": (
            "OTP generated. Check the development server console."
            if current_app.config.get("STORE_PLAINTEXT_OTP")
            else "OTP generated. Check the configured delivery channel."
        ),
    })


@auth_bp.post("/reset-password")
def reset_password():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    new_password = payload.get("new_password")
    if not phone_number or not payload.get("challenge_id") or not payload.get("otp") or not new_password:
        return _error("phone_number, challenge_id, otp, and new_password are required")
    if len(new_password) < 8:
        return _error("new_password must be at least 8 characters")
    try:
        challenge, error = _verify_otp(
            payload["challenge_id"], phone_number, payload["otp"], "password_reset"
        )
        if error:
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        user = db.session.get(User, challenge.user_id)
        user.set_password(new_password)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error("Unable to reset password", "SERVER_ERROR", 500)
    return jsonify({"message": "Password reset successfully"})


@auth_bp.post("/accounts/<int:user_id>/approve")
@jwt_required()
def approve_account(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not actor or actor.account_status != "approved":
        return _error("Manager or administrator approval is required", "FORBIDDEN", 403)
    actor_role = normalize_role(getattr(actor, "role", None))
    if actor_role not in {"MANAGER", "SYSTEM_ADMIN", "HR_ADMIN"} and not is_super_admin(actor):
        return _error("Manager or administrator approval is required", "FORBIDDEN", 403)
    user = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, user)
    if protected:
        return protected
    if not user:
        return _error("User not found", "NOT_FOUND", 404)
    user.account_status = "approved"
    user.is_active = True
    user.approved_by = actor.id
    user.approved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Account approved", "user": user.to_dict()})


@auth_bp.post("/accounts/<int:user_id>/deactivate")
@jwt_required()
def deactivate_account(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not actor or actor.account_status != "approved":
        return _error("Manager or administrator access is required", "FORBIDDEN", 403)
    actor_role = normalize_role(getattr(actor, "role", None))
    if actor_role not in {"MANAGER", "SYSTEM_ADMIN", "HR_ADMIN"} and not is_super_admin(actor):
        return _error("Manager or administrator access is required", "FORBIDDEN", 403)
    user = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, user)
    if protected:
        return protected
    if not user:
        return _error("User not found", "NOT_FOUND", 404)
    user.account_status = "deactivated"
    user.is_active = False
    db.session.commit()
    return jsonify({"message": "Account deactivated"})


@auth_bp.post("/accounts/<int:user_id>/ban")
@jwt_required()
def ban_account(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not actor or actor.account_status != "approved":
        return _error("Manager or administrator access is required", "FORBIDDEN", 403)
    actor_role = normalize_role(getattr(actor, "role", None))
    if actor_role not in {"MANAGER", "SYSTEM_ADMIN", "HR_ADMIN"} and not is_super_admin(actor):
        return _error("Manager or administrator access is required", "FORBIDDEN", 403)
    user = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, user)
    if protected:
        return protected
    if not user:
        return _error("User not found", "NOT_FOUND", 404)
    user.account_status = "banned"
    user.is_active = False
    db.session.commit()
    return jsonify({"message": "Account banned"})


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    token = get_jwt().get("jti")
    if token in _revoked_refresh_tokens:
        return _error("Refresh token has been revoked", "UNAUTHORIZED", 401)
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active or user.account_status != "approved":
        return _error("User is inactive", "UNAUTHORIZED", 401)
    return jsonify({"access_token": create_access_token(identity=str(user.id), additional_claims=_claims(user))})


@auth_bp.post("/logout")
@jwt_required(refresh=True)
def logout():
    _revoked_refresh_tokens.add(get_jwt().get("jti"))
    return jsonify({"success": True, "message": "Refresh token revoked", "logged_out_at": datetime.utcnow().isoformat()})


@auth_bp.get("/me")
@jwt_required()
def current_user():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return _error("User not found", "NOT_FOUND", 404)
    response = jsonify({"user": user.to_dict()})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization"
    return response


@auth_bp.patch("/me")
@jwt_required()
def update_current_user():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active:
        return _error("User not found or inactive", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    editable_fields = (
        "employee_name", "job_position_title", "employer", "department",
        "contact_phone", "contact_email", "address_line1", "address_line2",
        "city", "country", "postal_code", "profile_photo_url",
    )
    for field in editable_fields:
        if field not in payload:
            continue
        value = payload[field]
        if value is not None and not isinstance(value, str):
            return _error(f"{field} must be text", "VALIDATION_ERROR", 422)
        if isinstance(value, str) and len(value) > 500:
            return _error(f"{field} is too long", "VALIDATION_ERROR", 422)
        if field == "profile_photo_url" and value and not value.startswith("data:image/"):
            return _error("profile_photo_url must be an image upload", "VALIDATION_ERROR", 422)
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    if "employee_name" in payload:
        user.full_name = user.employee_name
    if "department" in payload and user.department:
        user.department = user.department.strip()
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": "Profile updated"})


@auth_bp.post("/me/photo")
@jwt_required()
def upload_profile_photo():
    user = db.session.get(User, int(get_jwt_identity()))
    photo = request.files.get("photo")
    if not user or not user.is_active:
        return _error("User not found or inactive", "NOT_FOUND", 404)
    if not photo or not photo.filename:
        return _error("A photo file is required", "VALIDATION_ERROR", 422)
    extension = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
    if extension not in ALLOWED_PHOTO_EXTENSIONS:
        return _error("Photo must be JPG, PNG, GIF, or WEBP", "VALIDATION_ERROR", 422)
    contents = photo.read(MAX_PHOTO_BYTES + 1)
    if len(contents) > MAX_PHOTO_BYTES:
        return _error("Photo must be 5 MB or smaller", "VALIDATION_ERROR", 422)
    upload_dir = os.path.abspath(os.path.join(current_app.root_path, "..", "uploads"))
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"profile-{user.id}-{uuid4().hex}.{extension}"
    with open(os.path.join(upload_dir, filename), "wb") as uploaded:
        uploaded.write(contents)
    user.profile_photo_url = f"/api/auth/photos/{filename}"
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": "Profile photo updated"})


@auth_bp.delete("/me/photo")
@jwt_required()
def delete_profile_photo():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active:
        return _error("User not found or inactive", "NOT_FOUND", 404)
    if user.profile_photo_url and user.profile_photo_url.startswith("/api/auth/photos/"):
        filename = user.profile_photo_url.rsplit("/", 1)[-1]
        photo_path = os.path.abspath(os.path.join(current_app.root_path, "..", "uploads", filename))
        if os.path.isfile(photo_path):
            os.remove(photo_path)
    user.profile_photo_url = None
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": "Profile photo removed"})


@auth_bp.get("/photos/<path:filename>")
def profile_photo(filename):
    upload_dir = os.path.abspath(os.path.join(current_app.root_path, "..", "uploads"))
    return send_from_directory(upload_dir, filename)
