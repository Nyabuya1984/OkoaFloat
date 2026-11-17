from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import os
import re
import secrets
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    has_app_context,
    jsonify,
    request,
    send_from_directory,
)
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.services.otp_email import send_otp_email
from app.models import (
    AuditLog,
    AuthSession,
    Department,
    DepartmentAssignmentHistory,
    LeaveBalance,
    LeavePolicy,
    LeaveType,
    OtpChallenge,
    Role,
    User,
    UserRole,
)
from app.utils.phone import normalize_ke_phone
from app.services.sms import send_otp_sms
from flask_limiter.util import get_remote_address
from app.utils.rbac import is_super_admin, is_system_admin, normalize_role
from app.utils.organization import (
    get_active_assignment,
    assignment_capacity_conflict_message,
    may_assign_organizational_role,
    may_manage_transfers,
    transition_department,
    update_assignment_role,
    validate_reporting_manager,
)


auth_bp = Blueprint("auth", __name__)
_revoked_refresh_tokens = set()
_revoked_admin_access_tokens = set()
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
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    return hmac.new(secret, code.encode("utf-8"), hashlib.sha256).hexdigest()


def _user_response_data(user):
    data = user.to_dict()
    assignment = get_active_assignment(user.id)
    if not assignment:
        return data

    department = (
        "All"
        if assignment.organizational_role == "general_manager"
        else assignment.department_name
    )
    data.update({
        "department": department,
        "department_name": department,
        "department_role": assignment.role_name,
        "organizational_role": assignment.organizational_role,
        "active_assignment": {
            "department_id": assignment.department_id,
            "department": department,
            "department_name": department,
            "department_role": assignment.role_name,
            "organizational_role": assignment.organizational_role,
            "started_at": assignment.started_at.isoformat(),
        },
    })
    return data


def _normalize_email(value):
    return value.strip().lower() if isinstance(value, str) else ""


def _account_for_email(email):
    matches = User.query.filter(
        (db.func.lower(User.email) == email)
        | (db.func.lower(User.personal_email) == email)
    ).limit(2).all()
    return matches[0] if len(matches) == 1 else None


def _valid_email(value):
    # Accept normal public domains, custom domains, and valid single-label
    # domains without restricting users to a provider allowlist.
    if not value or len(value) > 255 or not re.fullmatch(r"[^@\s]+@[^@\s]+", value):
        return False
    local, domain = value.rsplit("@", 1)
    return (
        len(local) <= 64
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and not domain.startswith(".")
        and not domain.endswith(".")
        and ".." not in domain
    )


def _otp_account_rate_limit_key():
    payload = request.get_json(silent=True) or {}
    account_key = normalize_ke_phone(payload.get("phone_number"))
    if not account_key:
        account_key = _normalize_email(payload.get("email"))
    secret = str(current_app.config["SECRET_KEY"]).encode("utf-8")
    digest = hmac.new(secret, account_key.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"otp-account:{digest}"


def _create_otp(user, purpose):
    code = f"{secrets.randbelow(1_000_000):06d}"
    personal_email = _normalize_email(user.personal_email or user.email)
    store_plaintext_otp = bool(
        current_app.debug
        or current_app.testing
        or current_app.config.get("OTP_STORE_PLAINTEXT")
    )
    OtpChallenge.query.filter_by(
        user_id=user.id, purpose=purpose, status="active"
    ).update({"status": "expired"}, synchronize_session=False)
    challenge = OtpChallenge(
        user_id=user.id,
        phone_number=user.phone_number,
        email_address=_normalize_email(user.email),
        personal_email_address=personal_email,
        plaintext_code=code if store_plaintext_otp else None,
        purpose=purpose,
        code_hash=None if store_plaintext_otp else _hash_otp(code),
        status="active",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.add(challenge)
    db.session.flush()
    if store_plaintext_otp:
        current_app.logger.info(
            "\n"
            "========== DEVELOPMENT OTP ==========\n"
            "Purpose: %s\n"
            "Phone:   %s\n"
            "Code:    %s\n"
            "Expires: %s UTC\n"
            "=====================================",
            purpose.replace("_", " ").title(),
            challenge.phone_number,
            code,
            challenge.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    sms_sent = False
    email_sent = False
    if not current_app.testing and current_app.config.get("SMS_ENABLED", True):
        try:
            sms_sent, sms_error = send_otp_sms(user.phone_number, code, purpose)
            if not sms_sent:
                current_app.logger.warning(
                    "SMS delivery skipped or failed for %s (purpose=%s): %s",
                    user.phone_number,
                    purpose,
                    sms_error,
                )
        except Exception:
            current_app.logger.exception(
                "Unexpected error attempting SMS delivery for %s", user.phone_number
            )

    if not current_app.testing:
        try:
            email_sent, email_error = send_otp_email(user.email, code, purpose)
            if not email_sent and email_error != "SMTP credentials or sender are not configured":
                current_app.logger.warning(
                    "OTP email delivery failed for %s (purpose=%s): %s",
                    user.email,
                    purpose,
                    email_error,
                )
        except Exception:
            current_app.logger.exception(
                "Unexpected error attempting OTP email delivery for %s", user.email
            )

    return challenge, sms_sent, email_sent


def _verify_otp(phone_number, code, purpose, email=None):
    challenges = OtpChallenge.query.filter_by(
        phone_number=phone_number,
        purpose=purpose,
        status="active",
        verified_at=None,
    ).order_by(OtpChallenge.created_at.desc()).all()
    now = datetime.utcnow()
    usable = []
    for challenge in challenges:
        if challenge.expires_at <= now:
            challenge.status = "expired"
        elif challenge.attempts < 5:
            usable.append(challenge)
    if not usable:
        if challenges and all(challenge.expires_at <= now for challenge in challenges):
            return None, "OTP has expired"
        if challenges:
            return None, "Too many OTP attempts"
        return None, "Invalid OTP challenge"

    submitted_code = code if isinstance(code, str) else ""
    allow_plaintext_otp = bool(
        current_app.debug
        or current_app.testing
        or current_app.config.get("OTP_STORE_PLAINTEXT")
    )
    for challenge in usable:
        plaintext_matches = bool(
            allow_plaintext_otp
            and challenge.plaintext_code
            and secrets.compare_digest(challenge.plaintext_code, submitted_code)
        )
        hashed_matches = bool(
            challenge.code_hash
            and secrets.compare_digest(challenge.code_hash, _hash_otp(submitted_code))
        )
        if plaintext_matches or hashed_matches:
            submitted_email = _normalize_email(email)
            if email is not None and not any(
                secrets.compare_digest(registered_email, submitted_email)
                for registered_email in (
                    challenge.email_address,
                    challenge.personal_email_address or challenge.email_address,
                )
            ):
                challenge.attempts += 1
                if challenge.attempts >= 5:
                    challenge.status = "expired"
                return None, "Invalid OTP"
            db.session.delete(challenge)
            return challenge, None

    for challenge in usable:
        challenge.attempts += 1
        if challenge.attempts >= 5:
            challenge.status = "expired"
    return None, "Invalid OTP"


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
        "user": _user_response_data(user),
    }


def _error(message, code="BAD_REQUEST", status=400, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return jsonify({"success": False, "error": error}), status


def _is_testing_context():
    return bool(has_app_context() and current_app.testing)


def _mask_phone(phone_number):
    clean = str(phone_number or "").strip()
    last4 = clean[-4:] if len(clean) >= 4 else clean
    return f"...{last4}"


def _otp_generated_message(
    action="verification", sms_sent=False, email_sent=False, phone_number=None
):
    if not _is_testing_context():
        if sms_sent and email_sent:
            return (
                f"The SMS and email providers accepted your 6-digit {action} code request. "
                "Delivery is not confirmed."
            )
        if email_sent:
            return (
                f"The email provider accepted your 6-digit {action} code request. "
                "Delivery is not confirmed."
            )
        if phone_number and sms_sent:
            return (
                f"The SMS provider accepted your 6-digit {action} code request for the phone number ending in "
                f"{_mask_phone(phone_number)}. Delivery to your phone is not confirmed."
            )
        if sms_sent:
            return f"The SMS provider accepted your 6-digit {action} code request. Delivery to your phone is not confirmed."
        return f"We couldn't send a {action} code by SMS or email. Please try again or contact support."
    return (
        f"A {action} code was generated and saved to the database and development console."
    )


def _password_reset_message():
    if not _is_testing_context():
        return "If the account is eligible, a verification code request has been processed."
    return "If the account is eligible, a verification code was generated and saved to the database and development console."


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
    if (
        "department" not in fields
        and _canonical_department_name(payload.get("department")) is None
    ):
        fields["department"] = (
            "Choose Sales & Marketing, Debt Collection, or Customer Care."
        )
    return fields


def _canonical_department_name(name, allow_custom=False):
    if not isinstance(name, str):
        return None
    name = " ".join(name.strip().split())
    if not 2 <= len(name) <= 120 or name.casefold() == "all":
        return None
    normalized = " ".join(
        name.casefold().replace("&", " and ").replace("-", " ").split()
    )
    canonical_name = {
        "sales": "Sales & Marketing",
        "sales and marketing": "Sales & Marketing",
        "sales marketing": "Sales & Marketing",
        "debt collection": "Debt Collection",
        "customer care": "Customer Care",
    }.get(normalized)
    if canonical_name or not allow_custom:
        return canonical_name
    return name


def _department_for(name, allow_custom=False):
    canonical_name = _canonical_department_name(name, allow_custom=allow_custom)
    if not canonical_name:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Department name is required")
        raise ValueError("Department name must be between 2 and 120 characters")
    department = Department.query.filter(
        db.func.lower(Department.name) == canonical_name.lower()
    ).first()
    if not department:
        department = Department(name=canonical_name)
        db.session.add(department)
        db.session.flush()
    return department


def _assignment_department_for(name, organizational_role, allow_custom=True):
    if organizational_role == "general_manager":
        if not isinstance(name, str) or name.strip().casefold() != "all":
            raise ValueError("The General Manager department must be All")
        return None
    return _department_for(name, allow_custom=allow_custom)


def _can_create_user(actor, target_role, target_department_name=None):
    if not actor or not actor.is_active or actor.account_status != "approved":
        return False, "Account is not active"
    actor_role = normalize_role(getattr(actor, "role", None))
    organizational_assignment = get_active_assignment(actor.id)
    organizational_role = (
        organizational_assignment.organizational_role
        if organizational_assignment
        else None
    )
    target_role_name = normalize_role(target_role)
    if is_super_admin(actor):
        return True, None
    if organizational_role == "general_manager":
        if target_role_name not in {"EMPLOYEE", "MANAGER"}:
            return False, "Organizational managers may create employee accounts only"
        return True, None
    if (
        organizational_role == "department_manager"
        and target_role_name == "EMPLOYEE"
        and organizational_assignment.department_name.casefold()
        == (target_department_name or "").strip().casefold()
    ):
        return True, None
    if (
        organizational_role == "team_leader"
        and target_role_name == "EMPLOYEE"
        and organizational_assignment.department_name.casefold()
        == (target_department_name or "").strip().casefold()
    ):
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
    if not phone_number or not password:
        return _error("phone_number and password are required", "VALIDATION_ERROR", 422)
    user = User.query.filter_by(phone_number=phone_number).first()
    password_matches = bool(user and password and user.check_password(password))
    if not user or not password_matches:
        current_app.logger.warning("Phone login rejected: normalized_phone=%s", phone_number)
        _record_security_event(
            "login_failed",
            "Rejected phone login attempt",
            {"phone_number": phone_number, "reason": "wrong_credentials"},
        )
        return _error("Wrong phone number or password", "UNAUTHORIZED", 401)
    if not user.is_currently_active() or user.account_status in ("banned", "deactivated"):
        return _error("This account is no longer active", "FORBIDDEN", 403)
    if user.account_status != "approved":
        return jsonify({
            "account_status": "pending",
            "message": "Your account is pending approval by an administrator or manager.",
        }), 403
    sms_sent = False
    try:
        challenge, sms_sent, email_sent = _create_otp(user, "login")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create login OTP")
        return _error(
            "Unable to create sign-in code. Please try again later.",
            "OTP_CREATION_FAILED",
            502,
        )
    return jsonify({
        "verification_required": True,
        "sms_sent": sms_sent,
        "email_sent": email_sent,
        "message": _otp_generated_message(
            "verification", sms_sent=sms_sent, email_sent=email_sent,
            phone_number=user.phone_number,
        ),
    })


@auth_bp.post("/phone-login")
@auth_bp.post("/login")
@limiter.limit("3 per 10 minutes", key_func=_otp_account_rate_limit_key)
@limiter.limit("3 per 10 minutes", key_func=get_remote_address)
def login():
    return _phone_login(request.get_json(silent=True) or {})


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    email = _normalize_email(payload.get("official_email") or payload.get("email"))
    personal_email = email
    required = ("password",)
    field_errors = _registration_fields(payload)
    if not phone_number:
        field_errors["phone_number"] = "Enter a valid phone number."
    missing = [field for field in required if not payload.get(field)]
    if not email:
        field_errors["official_email"] = "This field is required."
    elif not _valid_email(email):
        field_errors["official_email"] = "Enter a valid email address."
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
    email_addresses = (email,)
    address_conflicts = User.query.filter(
        (db.func.lower(User.email).in_(email_addresses))
        | (db.func.lower(User.personal_email).in_(email_addresses))
    )
    if existing_user:
        address_conflicts = address_conflicts.filter(User.id != existing_user.id)
    if address_conflicts.first():
        return _error("An email address is already assigned to another account", status=409)

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
        user.personal_email = personal_email
        user.phone_number = phone_number
        user.department = department.name
        user.department_id = department.id
        user.contact_phone = phone_number
        user.contact_email = personal_email
        user.account_status = "pending"
        user.is_active = True
        user.set_password(payload["password"])
        db.session.add(user)
        db.session.flush()
        update_assignment_role(
            user, None, organizational_role="field_agent"
        )
        challenge, sms_sent, email_sent = _create_otp(user, "registration")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create registration OTP")
        return _error(
            "Unable to create verification code. Please try again later.",
            "OTP_CREATION_FAILED",
            502,
        )
    return jsonify({
        "verification_required": True,
        "sms_sent": sms_sent,
        "email_sent": email_sent,
        "message": _otp_generated_message(
            "verification", sms_sent=sms_sent, email_sent=email_sent,
            phone_number=user.phone_number,
        ),
    }), 201


@auth_bp.post("/verify-registration")
def verify_registration():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    email = _normalize_email(payload.get("official_email") or payload.get("email"))
    if not phone_number or not payload.get("otp") or not email:
        return _error("phone_number, email, and otp are required")
    try:
        challenge, error = _verify_otp(phone_number, payload["otp"], "registration", email)
        if error:
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        user = db.session.get(User, challenge.user_id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error("Unable to verify registration", "SERVER_ERROR", 500)
    account_status = user.account_status if user else "pending"
    return jsonify({
        "account_status": account_status,
        "message": (
            "Registration verified. Your account is pending approval."
            if account_status == "pending"
            else "Registration verified. You can now sign in."
        ),
    })


@auth_bp.post("/verify-otp")
def verify_otp():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    email = _normalize_email(payload["email"]) if "email" in payload else None
    if not phone_number or not payload.get("otp"):
        return _error("phone_number and otp are required")
    try:
        challenge, error = _verify_otp(phone_number, payload["otp"], "login", email)
        if error:
            _record_security_event(
                "otp_failed",
                "OTP verification failed",
                {"phone_number": phone_number, "reason": error},
            )
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        user = db.session.get(User, challenge.user_id)
        if (
            not user
            or not user.is_currently_active()
            or user.account_status != "approved"
        ):
            db.session.rollback()
            return _error("This account is no longer active", "FORBIDDEN", 403)
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
    assignment = get_active_assignment(actor.id)
    return (
        role in {"MANAGER", "SYSTEM_ADMIN", "HR_ADMIN", "SUPER_ADMIN"}
        or getattr(actor, "is_superuser", False) is True
        or bool(
            assignment
            and assignment.organizational_role in {
                "general_manager", "department_manager", "team_leader"
            }
        )
    )


def _can_manage_target(actor, target):
    if not actor or not target or not _admin_access(actor):
        return False
    if is_super_admin(target) and not is_super_admin(actor):
        return False
    actor_role = normalize_role(getattr(actor, "role", None))
    if is_super_admin(actor) or actor_role in {"SYSTEM_ADMIN", "HR_ADMIN"}:
        return True
    actor_assignment = get_active_assignment(actor.id)
    if actor_assignment and actor_assignment.organizational_role == "general_manager":
        return True
    if actor_assignment and may_manage_transfers(actor, target):
        return True
    return actor_role == "MANAGER" and (target.id == actor.id or target.manager_id == actor.id)


def _protect_super_admin_target(actor, target):
    """Prevent every non-super-admin from reading or mutating the protected account."""
    if is_super_admin(target) and not is_super_admin(actor):
        return _error("Unauthorized action", "FORBIDDEN", 403)
    return None


def _purge_user_references(user_ids):
    user_table = User.__table__
    root_rows = db.session.execute(
        select(user_table).where(user_table.c.id.in_(user_ids))
    ).mappings().all()

    def row_key(table, row):
        return tuple(row[column.name] for column in table.primary_key.columns)

    root_keys = {row_key(user_table, row) for row in root_rows}
    children_by_parent = {}
    for child_table in db.metadata.tables.values():
        for constraint in child_table.foreign_key_constraints:
            elements = tuple(constraint.elements)
            if not elements:
                continue
            parent_table = elements[0].column.table
            if all(element.column.table is parent_table for element in elements):
                children_by_parent.setdefault(parent_table, []).append(
                    (child_table, elements)
                )

    rows_to_delete = {}
    rows_to_clear = {}
    pending = {user_table: {row_key(user_table, row): row for row in root_rows}}
    processed = set()

    while pending:
        parent_table, parent_rows = pending.popitem()
        unprocessed_rows = [
            row
            for key, row in parent_rows.items()
            if (parent_table, key) not in processed
        ]
        if not unprocessed_rows:
            continue

        for offset in range(0, len(unprocessed_rows), 100):
            row_batch = unprocessed_rows[offset:offset + 100]
            processed.update(
                (parent_table, row_key(parent_table, row)) for row in row_batch
            )
            for child_table, elements in children_by_parent.get(parent_table, ()):
                conditions = [
                    and_(*(
                        child_table.c[element.parent.name] == row[element.column.name]
                        for element in elements
                    ))
                    for row in row_batch
                ]
                related_rows = db.session.execute(
                    select(child_table).where(or_(*conditions))
                ).mappings().all()
                required_reference = any(
                    not element.parent.nullable for element in elements
                )

                for row in related_rows:
                    key = row_key(child_table, row)
                    if child_table is user_table and key in root_keys:
                        if not required_reference:
                            rows_to_clear.setdefault(child_table, {}).setdefault(
                                key, {}
                            ).update({
                                element.parent.name: None for element in elements
                            })
                        continue
                    if required_reference:
                        table_rows = rows_to_delete.setdefault(child_table, {})
                        if key not in table_rows:
                            table_rows[key] = row
                            pending.setdefault(child_table, {})[key] = row
                    else:
                        table_rows = rows_to_clear.setdefault(child_table, {})
                        table_rows.setdefault(key, {}).update(
                            {element.parent.name: None for element in elements}
                        )

    for table, records in rows_to_clear.items():
        for key, column_names in records.items():
            predicate = and_(
                *(column == value for column, value in zip(table.primary_key.columns, key))
            )
            db.session.execute(
                update(table).where(predicate).values(
                    {column_name: None for column_name in column_names}
                )
            )

    remaining_tables = set(rows_to_delete)
    while remaining_tables:
        blocked_parent_tables = set()
        for child_table in remaining_tables:
            for constraint in child_table.foreign_key_constraints:
                elements = tuple(constraint.elements)
                if not elements or any(element.parent.nullable for element in elements):
                    continue
                parent_table = elements[0].column.table
                if parent_table in remaining_tables and all(
                    element.column.table is parent_table for element in elements
                ):
                    blocked_parent_tables.add(parent_table)

        leaf_tables = remaining_tables - blocked_parent_tables
        if not leaf_tables:
            raise ValueError("Cannot determine a safe order for dependent user records")

        for table in leaf_tables:
            predicates = [
                and_(
                    *(column == value for column, value in zip(table.primary_key.columns, key))
                )
                for key in rows_to_delete[table]
            ]
            db.session.execute(table.delete().where(or_(*predicates)))
        remaining_tables -= leaf_tables


def _apply_admin_user_status(actor, target, status):
    if not isinstance(status, str):
        return _error(
            "status must be pending, active, deactivated, or archived",
            "VALIDATION_ERROR",
            422,
        )
    status = status.strip().lower()
    if status not in {"pending", "active", "deactivated", "archived"}:
        return _error(
            "status must be pending, active, deactivated, or archived",
            "VALIDATION_ERROR",
            422,
        )
    if target.id == actor.id:
        return _error("You cannot change your own account status", "CONFLICT", 409)

    if status == "active":
        assignment = get_active_assignment(target.id)
        if (
            not assignment
            and not is_super_admin(actor)
        ):
            return _error(
                "A valid department assignment is required before activation",
                "ORGANIZATION_ASSIGNMENT_REQUIRED",
                409,
            )
        if assignment and (
            not assignment.department_id
            or assignment.department_id != target.department_id
        ):
            return _error(
                "A valid department assignment is required before activation",
                "ORGANIZATION_ASSIGNMENT_REQUIRED",
                409,
            )
        if assignment and (
            assignment.organizational_role != "general_manager"
            and not target.manager_id
        ):
            return _error(
                "A valid reporting manager is required before activation",
                "REPORTING_MANAGER_REQUIRED",
                409,
            )
        if assignment:
            department = db.session.get(Department, assignment.department_id)
            if not department:
                return _error(
                    "The assigned department no longer exists",
                    "ORGANIZATION_ASSIGNMENT_REQUIRED",
                    409,
                )
            try:
                validate_reporting_manager(
                    target,
                    department,
                    assignment.organizational_role,
                    target.manager_id,
                    actor,
                )
            except ValueError as error:
                return _error(str(error), "INVALID_REPORTING_CHAIN", 409)

    if status == "pending":
        target.is_active = True
        target.is_archived = False
        target.account_status = "pending"
        target.approved_by = None
        target.approved_at = None
        target.deactivated_at = None
        target.deactivated_by = None
        target.archived_at = None
        target.archived_by = None
    elif status == "active":
        was_pending = target.account_status == "pending"
        target.is_active = True
        target.is_archived = False
        target.account_status = "approved"
        if was_pending:
            target.approved_by = actor.id
            target.approved_at = datetime.utcnow()
        target.deactivated_at = None
        target.deactivated_by = None
        target.archived_at = None
        target.archived_by = None
    else:
        target.is_active = False
        target.is_archived = status == "archived"
        target.account_status = "deactivated"
        target.deactivated_at = datetime.utcnow()
        target.deactivated_by = actor.id
        if status == "archived":
            target.archived_at = datetime.utcnow()
            target.archived_by = actor.id
        else:
            target.archived_at = None
            target.archived_by = None
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
    if not is_system_admin(actor):
        return _error("Only the super admin can create departments", "FORBIDDEN", 403)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    canonical_name = _canonical_department_name(name, allow_custom=True)
    if canonical_name is None:
        return _error("Department name must be between 2 and 120 characters", "VALIDATION_ERROR", 422)
    name = canonical_name
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
    if not is_system_admin(actor):
        return _error("Only the super admin can update departments", "FORBIDDEN", 403)
    dept = db.session.get(Department, department_id)
    if not dept:
        return _error("Department not found", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    canonical_name = _canonical_department_name(name, allow_custom=True)
    if canonical_name is None:
        return _error("Department name must be between 2 and 120 characters", "VALIDATION_ERROR", 422)
    name = canonical_name
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
    if not is_system_admin(actor):
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
    if not is_system_admin(actor):
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
    if not is_system_admin(actor):
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
        annual_entitlement_days=float(leave_type.default_days_per_year or 0),
        max_carryover=0,
        notice_days_required=0,
    ))
    db.session.commit()
    return jsonify({"data": {"id": leave_type.id, "name": leave_type.name, "code": leave_type.code}, "error": None, "message": "Leave type created"})


@auth_bp.patch("/admin/leave-types/<int:leave_type_id>")
@jwt_required()
def update_leave_type(leave_type_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not is_system_admin(actor):
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
    if "default_days_per_year" in payload:
        try:
            annual_days = Decimal(str(payload["default_days_per_year"]))
            if not annual_days.is_finite() or annual_days < 0 or annual_days > 366:
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            return _error("default_days_per_year must be between 0 and 366", "VALIDATION_ERROR", 422)
        leave_type.default_days_per_year = annual_days
    policy = LeavePolicy.query.filter_by(leave_type_id=leave_type.id).first()
    if not policy:
        policy = LeavePolicy(leave_type_id=leave_type.id)
        db.session.add(policy)
    policy.annual_entitlement_days = leave_type.default_days_per_year
    policy.accrual_rate = leave_type.default_days_per_year
    LeaveBalance.query.filter_by(
        leave_type_id=leave_type.id,
        year=datetime.utcnow().year,
        is_manual_override=False,
    ).update({"entitled_days": leave_type.default_days_per_year}, synchronize_session=False)
    db.session.commit()
    return jsonify({"data": {"id": leave_type.id, "name": leave_type.name, "code": leave_type.code}, "error": None, "message": "Leave type updated"})


@auth_bp.delete("/admin/leave-types/<int:leave_type_id>")
@jwt_required()
def delete_leave_type(leave_type_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not is_system_admin(actor):
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
    if not is_system_admin(actor):
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
    if not is_system_admin(actor):
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
    if not is_system_admin(actor):
        return _error("Only the super admin can view security events", "FORBIDDEN", 403)
    events = AuditLog.query.filter(
        AuditLog.action.in_(["login_failed", "rate_limit_hit"])
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
    actor_role = normalize_role(getattr(actor, "role", None))
    query = User.query if is_super_admin(actor) else User.query.filter(User.is_superuser.is_(False), User.role != "SUPER_ADMIN")
    actor_assignment = get_active_assignment(actor.id)
    if actor_assignment and actor_assignment.organizational_role in {
        "department_manager", "team_leader"
    }:
        query = query.filter(User.department_id == actor_assignment.department_id)
        if actor_assignment.organizational_role == "team_leader":
            query = query.filter(
                or_(User.manager_id == actor.id, User.id == actor.id)
            )
    elif actor_role == "MANAGER":
        query = query.filter(User.department_id == actor.department_id)
    users = query.order_by(User.created_at.desc()).all()
    role_assignments = dict(
        db.session.query(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .filter(UserRole.user_id.in_([user.id for user in users]))
        .all()
    ) if users else {}
    active_assignments = (
        DepartmentAssignmentHistory.query.filter(
            DepartmentAssignmentHistory.user_id.in_([user.id for user in users]),
            DepartmentAssignmentHistory.ended_at.is_(None),
        )
        .order_by(DepartmentAssignmentHistory.started_at.desc())
        .all()
    ) if users else []
    organization_by_user = {}
    for assignment in active_assignments:
        organization_by_user.setdefault(assignment.user_id, assignment)
    return jsonify({
        "data": [
            {
                **user.to_dict(),
                "rbac_role": role_assignments.get(user.id),
                "organizational_role": (
                    organization_by_user[user.id].organizational_role
                    if user.id in organization_by_user
                    else None
                ),
                "department_role": (
                    organization_by_user[user.id].role_name
                    if user.id in organization_by_user
                    else None
                ),
            }
            for user in users
        ],
        "error": None,
    })


@auth_bp.post("/admin/users/<int:user_id>/access")
@jwt_required()
def start_admin_user_access(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if (
        actor is None
        or not actor.is_currently_active()
        or actor.account_status != "approved"
        or not is_super_admin(actor)
    ):
        return _error("Only an active super administrator can access user accounts", "FORBIDDEN", 403)

    target = db.session.get(User, user_id)
    if target is None or not target.is_currently_active() or target.account_status != "approved":
        return _error("Only active, approved user accounts can be accessed", "NOT_FOUND", 404)
    if target.id == actor.id:
        return _error("You are already signed in to this account", "VALIDATION_ERROR", 422)

    _record_security_event(
        "admin_user_access_started",
        "A super administrator started a read-only user account session.",
        {"admin_id": actor.id, "user_id": target.id},
    )
    db.session.commit()
    access_token = create_access_token(
        identity=str(target.id),
        additional_claims={
            **_claims(target),
            "acting_admin_id": actor.id,
            "acting_admin_name": actor.full_name,
        },
        expires_delta=timedelta(minutes=10),
    )
    return jsonify({
        "data": {
            "access_token": access_token,
            "user": _user_response_data(target),
            "acting_as": {"id": actor.id, "name": actor.full_name},
        },
        "error": None,
    })


@auth_bp.post("/admin/users/access/stop")
@jwt_required()
def stop_admin_user_access():
    claims = get_jwt()
    try:
        admin_id = int(claims.get("acting_admin_id"))
    except (TypeError, ValueError):
        return _error("This session is not accessing another user account", "FORBIDDEN", 403)
    admin = db.session.get(User, admin_id)
    if not admin or not is_super_admin(admin):
        return _error("The initiating super administrator is no longer authorized", "FORBIDDEN", 403)

    _revoked_admin_access_tokens.add(claims.get("jti"))
    _record_security_event(
        "admin_user_access_ended",
        "A super administrator ended a read-only user account session.",
        {"admin_id": admin.id, "user_id": int(get_jwt_identity())},
    )
    db.session.commit()
    return jsonify({"data": {"success": True}, "error": None})


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
    email = _normalize_email(payload.get("official_email") or payload.get("email"))
    personal_email = email
    phone_number = normalize_ke_phone(payload.get("phone_number") or payload.get("contact_phone"))
    contact_phone = normalize_ke_phone(payload.get("contact_phone") or phone_number)
    contact_email = email
    password = payload.get("password") or ""
    if role not in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
        return _error("Invalid role selected", "VALIDATION_ERROR", 422)
    if not full_name or not email or not phone_number or len(password) < 8:
        return _error("full_name, official_email, phone_number, and a password of at least 8 characters are required", "VALIDATION_ERROR", 422)
    if not _valid_email(email):
        return _error("Enter a valid email address", "VALIDATION_ERROR", 422)
    if User.query.filter(
        (db.func.lower(User.email) == email)
        | (db.func.lower(User.personal_email) == email)
        | (User.phone_number == phone_number)
    ).first():
        return _error("A user with that email or phone number already exists", "CONFLICT", 409)

    hire_date = None
    if payload.get("hire_date"):
        try:
            hire_date = datetime.strptime(str(payload.get("hire_date")), "%Y-%m-%d").date()
        except ValueError:
            return _error("hire_date must be a valid YYYY-MM-DD value", "VALIDATION_ERROR", 422)

    try:
        organizational_role = payload.get("organizational_role") or "field_agent"
        department = _assignment_department_for(
            department_name, organizational_role
        )
    except ValueError as exc:
        db.session.rollback()
        return _error(str(exc), "VALIDATION_ERROR", 422)
    if (
        not isinstance(organizational_role, str)
        or not may_assign_organizational_role(
            actor, organizational_role, department.id if department else None
        )
    ):
        db.session.rollback()
        return _error(
            "You are not authorized to assign that organizational role",
            "FORBIDDEN",
            403,
        )
    department_role = payload.get("department_role")
    if department_role == "":
        department_role = None
    if department_role is not None and not isinstance(department_role, str):
        db.session.rollback()
        return _error(
            "department_role must be a configured department role or null",
            "VALIDATION_ERROR",
            422,
        )
    if (
        organizational_role in {"field_agent", "team_leader", "department_manager"}
        and _canonical_department_name(department.name) is not None
        and not department_role
    ):
        db.session.rollback()
        return _error(
            "Department employees and managers must have a role matching their department",
            "VALIDATION_ERROR",
            422,
        )
    user = User(
        employee_id=f"EMP-{secrets.token_hex(4).upper()}",
        full_name=full_name,
        employee_name=full_name,
        job_position_title=payload.get("job_position_title") or "Staff",
        employer=payload.get("employer") or "Okoa Float Ltd",
        email=email,
        personal_email=personal_email,
        phone_number=phone_number,
        contact_phone=contact_phone,
        contact_email=contact_email,
        department=department.name if department else "All",
        department_id=department.id if department else None,
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
    )
    user.set_password(password)
    try:
        db.session.add(user)
        db.session.flush()
        manager_id = validate_reporting_manager(
            user,
            department,
            organizational_role,
            payload.get("manager_id"),
            actor,
        )
        actor_assignment = get_active_assignment(actor.id)
        if (
            actor_assignment
            and actor_assignment.organizational_role == "team_leader"
            and manager_id != actor.id
        ):
            db.session.rollback()
            return _error(
                "Team Leaders can only add employees who report directly to them",
                "FORBIDDEN",
                403,
            )
        transition_department(
            user, department, department_role, organizational_role, actor
        )
        user.manager_id = manager_id
        if payload.get("job_position_title"):
            user.job_position_title = str(payload["job_position_title"]).strip()
        _, sms_sent, email_sent = _create_otp(user, "registration")
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return _error(str(exc), "VALIDATION_ERROR", 422)
    except IntegrityError as exc:
        db.session.rollback()
        message = assignment_capacity_conflict_message(
            exc, department, organizational_role
        )
        if message:
            return _error(message, "ORGANIZATION_CONFLICT", 409)
        current_app.logger.exception("Unable to create user organizational assignment")
        return _error("Unable to create the user and organizational assignment", "SERVER_ERROR", 500)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create user organizational assignment")
        return _error("Unable to create the user and organizational assignment", "SERVER_ERROR", 500)
    return jsonify({
        "data": user.to_dict(),
        "verification_required": True,
        "sms_sent": sms_sent,
        "email_sent": email_sent,
        "error": None,
        "message": "User created successfully",
    })


@auth_bp.delete("/admin/users/<int:user_id>")
@jwt_required()
def delete_admin_user(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    target = db.session.get(User, user_id)
    protected = _protect_super_admin_target(actor, target)
    if protected:
        return protected
    if not target:
        return _error("User not found", "NOT_FOUND", 404)
    if target.id == actor.id:
        return _error("You cannot delete your own account", "CONFLICT", 409)
    if not is_super_admin(actor):
        return _error(
            "Only the super administrator can permanently delete users",
            "FORBIDDEN",
            403,
        )
    try:
        _purge_user_references([user_id])
        db.session.execute(User.__table__.delete().where(User.id == user_id))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to permanently delete user %s", user_id)
        return _error("Unable to permanently delete user", "SERVER_ERROR", 500)
    return jsonify({
        "data": {"id": user_id, "permanently_deleted": True},
        "error": None,
        "message": "User permanently deleted",
    })


@auth_bp.post("/admin/users/bulk-delete")
@jwt_required()
def bulk_delete_admin_users():
    actor = db.session.get(User, int(get_jwt_identity()))
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Only an active administrator can bulk delete users", "FORBIDDEN", 403)
    if not is_super_admin(actor):
        return _error("Only the super administrator can permanently delete users", "FORBIDDEN", 403)

    payload = request.get_json(silent=True) or {}
    user_ids = payload.get("user_ids")
    if not isinstance(user_ids, list) or not user_ids:
        return _error("user_ids must be a non-empty list", "VALIDATION_ERROR", 422)

    ids = []
    for user_id in user_ids:
        try:
            value = int(user_id)
        except (TypeError, ValueError):
            return _error("Each user_id must be an integer", "VALIDATION_ERROR", 422)
        if value == actor.id:
            return _error("You cannot delete your own account", "CONFLICT", 409)
        ids.append(value)

    targets = User.query.filter(User.id.in_(ids)).all()
    if not targets:
        return _error("No users were found for deletion", "NOT_FOUND", 404)

    deleted_ids = []
    for target in targets:
        protected = _protect_super_admin_target(actor, target)
        if protected:
            return protected
        if not _can_manage_target(actor, target):
            return _error(f"You cannot delete user {target.id}", "FORBIDDEN", 403)
        deleted_ids.append(target.id)

    try:
        _purge_user_references(deleted_ids)
        db.session.execute(User.__table__.delete().where(User.id.in_(deleted_ids)))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to permanently delete selected users")
        return _error("Unable to permanently delete selected users", "SERVER_ERROR", 500)
    return jsonify({
        "data": {"deleted_ids": deleted_ids, "permanently_deleted": len(deleted_ids)},
        "error": None,
        "message": f"Permanently deleted {len(deleted_ids)} user(s)",
    })


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
    if "official_email" in payload and "email" not in payload:
        payload["email"] = payload["official_email"]
    requested_department = payload.get("department")
    assignment_fields = {
        "organizational_role",
        "department_role",
        "manager_id",
    }
    updates_assignment = bool(assignment_fields.intersection(payload))
    department_changed = (
        isinstance(requested_department, str)
        and requested_department.strip().casefold()
        != (target.department or "").strip().casefold()
    )
    manager_changed = (
        "manager_id" in payload
        and str(payload.get("manager_id") or "") != str(target.manager_id or "")
    )
    if (department_changed or manager_changed) and not updates_assignment:
        return _error(
            "Department and reporting-line changes require an organizational assignment",
            "ORGANIZATION_TRANSFER_REQUIRED",
            409,
        )
    assignment = get_active_assignment(target.id)
    if updates_assignment:
        if not assignment_fields.issubset(payload) or not isinstance(requested_department, str):
            return _error(
                "organizational_role, department_role, manager_id, and department are required to update an organizational assignment",
                "VALIDATION_ERROR",
                422,
            )
        organizational_role = payload.get("organizational_role")
        department_role = payload.get("department_role")
        if department_role == "":
            department_role = None
        if department_role is not None and not isinstance(department_role, str):
            return _error(
                "department_role must be a configured department role or null",
                "VALIDATION_ERROR",
                422,
            )
        if (
            not isinstance(organizational_role, str)
            or organizational_role not in {
                "general_manager",
                "department_manager",
                "team_leader",
                "field_agent",
            }
        ):
            return _error("Invalid organizational role selected", "VALIDATION_ERROR", 422)
        if (
            organizational_role in {"field_agent", "team_leader", "department_manager"}
            and _canonical_department_name(requested_department) is not None
            and not department_role
        ):
            return _error(
                "Department employees and managers must have a role matching their department",
                "VALIDATION_ERROR",
                422,
            )
        try:
            department = _assignment_department_for(
                requested_department, organizational_role
            )
        except ValueError as exc:
            db.session.rollback()
            return _error(str(exc), "VALIDATION_ERROR", 422)
        assignment_changed = (
            not assignment
            or assignment.department_id != (department.id if department else None)
            or assignment.organizational_role != organizational_role
            or assignment.role_name != department_role
        )
        if assignment_changed or manager_changed:
            if not may_manage_transfers(actor, target):
                db.session.rollback()
                return _error(
                    "You are not authorized to change this employee's organizational assignment",
                    "FORBIDDEN",
                    403,
                )
        if assignment_changed and not may_assign_organizational_role(
            actor,
            organizational_role,
            department.id if department else None,
        ):
            db.session.rollback()
            return _error(
                "You are not authorized to assign that organizational role",
                "FORBIDDEN",
                403,
            )
    editable_fields = (
        "full_name",
        "employee_name",
        "job_position_title",
        "employer",
        "email",
        "personal_email",
        "phone_number",
        "contact_phone",
        "contact_email",
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
        if field in {"email", "personal_email", "contact_email"}:
            value = _normalize_email(value)
            if field == "email" and not _valid_email(value):
                return _error("Enter a valid email address", "VALIDATION_ERROR", 422)
            if field in {"personal_email", "contact_email"} and not _valid_email(value):
                return _error("Enter a valid email address", "VALIDATION_ERROR", 422)
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
        if field == "full_name":
            target.full_name = value
            target.employee_name = value
            continue
        if field == "email":
            duplicate = User.query.filter(
                User.id != target.id,
                (db.func.lower(User.email) == value)
                | (db.func.lower(User.personal_email) == value),
            ).first()
            if duplicate:
                return _error("A user with that email already exists", "CONFLICT", 409)
            target.email = value
            target.personal_email = value
            target.contact_email = value
            continue
        if field in {"personal_email", "contact_email"}:
            duplicate = User.query.filter(
                User.id != target.id,
                (db.func.lower(User.email) == value)
                | (db.func.lower(User.personal_email) == value),
            ).first()
            if duplicate:
                return _error("A user with that official email already exists", "CONFLICT", 409)
            target.email = value
            target.personal_email = value
            target.contact_email = value
            continue
        if field == "contact_phone":
            target.contact_phone = value
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
    if updates_assignment and (assignment_changed or manager_changed):
        try:
            manager_id = validate_reporting_manager(
                target,
                department,
                organizational_role,
                payload.get("manager_id"),
                actor,
            )
            if assignment_changed:
                transition_department(
                    target,
                    department,
                    department_role,
                    organizational_role,
                    actor,
                )
            target.manager_id = manager_id
        except ValueError as exc:
            db.session.rollback()
            return _error(str(exc), "VALIDATION_ERROR", 422)
    if "status" in payload:
        status_error = _apply_admin_user_status(actor, target, payload["status"])
        if status_error:
            return status_error
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        message = assignment_capacity_conflict_message(
            exc,
            department if updates_assignment else None,
            payload.get("organizational_role") if updates_assignment else None,
        )
        if message:
            return _error(message, "ORGANIZATION_CONFLICT", 409)
        current_app.logger.exception("Unable to save admin user changes")
        return _error("Unable to save user changes", "SERVER_ERROR", 500)
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
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if isinstance(status, str):
        status = status.strip().lower()
    status_error = _apply_admin_user_status(actor, target, status)
    if status_error:
        return status_error
    db.session.commit()
    return jsonify({"data": target.to_dict(), "error": None, "message": f"User {status}"})


@auth_bp.post("/admin/users/<int:user_id>/role")
@jwt_required()
def update_admin_user_role(user_id):
    actor = db.session.get(User, int(get_jwt_identity()))
    if not is_system_admin(actor):
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
    db.session.flush()
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
    if not is_system_admin(actor):
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
@limiter.limit("3 per 10 minutes", key_func=_otp_account_rate_limit_key)
@limiter.limit("3 per 10 minutes", key_func=get_remote_address)
def request_password_reset():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    if not phone_number:
        return jsonify({
            "message": _password_reset_message()
        })
    user = User.query.filter_by(phone_number=phone_number).first()
    if not user or not user.is_currently_active() or user.account_status in ("banned", "deactivated"):
        return jsonify({
                "message": _password_reset_message()
        })
    sms_sent = False
    try:
        challenge, sms_sent, email_sent = _create_otp(user, "reset")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create password-reset OTP")
        return _error(
            "Unable to create reset code. Please try again later.",
            "OTP_CREATION_FAILED",
            502,
        )
    return jsonify({
        "message": _password_reset_message()
    })


@auth_bp.post("/reset-password")
def reset_password():
    payload = request.get_json(silent=True) or {}
    phone_number = normalize_ke_phone(payload.get("phone_number"))
    new_password = payload.get("new_password")
    if not phone_number or not payload.get("otp") or not new_password:
        return _error("phone_number, otp, and new_password are required")
    if not isinstance(new_password, str) or len(new_password) < 8:
        return _error("new_password must be at least 8 characters")
    user = User.query.filter_by(phone_number=phone_number).first()
    if not user:
        return _error("Invalid OTP challenge", "UNAUTHORIZED", 401)
    try:
        challenge, error = _verify_otp(user.phone_number, payload["otp"], "reset")
        if error:
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        user = db.session.get(User, challenge.user_id)
        user.set_password(new_password)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Password reset failed unexpectedly")
        return _error("Unable to reset password", "SERVER_ERROR", 500)
    return jsonify({"message": "Password reset successfully"})


@auth_bp.post("/request-phone-recovery")
@auth_bp.post("/request-account-recovery")
def request_phone_recovery():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get("email"))
    if not _valid_email(email):
        return _error("Enter a valid registered email address", "VALIDATION_ERROR", 422)
    user = _account_for_email(email)
    if not user or not user.is_active or user.account_status in ("banned", "deactivated"):
        return jsonify({"message": _otp_generated_message("recovery", sms_sent=False)})
    if not _resend_allowed(user, "account_recovery"):
        return _error(
            f"Please wait {OTP_RESEND_DELAY_SECONDS} seconds before requesting another OTP",
            "TOO_MANY_REQUESTS",
            429,
        )
    sms_sent = False
    try:
        challenge, sms_sent, email_sent = _create_otp(user, "account_recovery")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create account-recovery OTP")
        return _error(
            "Unable to create recovery code. Please try again later.",
            "OTP_CREATION_FAILED",
            502,
        )
    return jsonify({
        "verification_required": True,
        "sms_sent": sms_sent,
        "email_sent": email_sent,
        "message": _otp_generated_message(
            "recovery", sms_sent=sms_sent, email_sent=email_sent
        ),
    })


@auth_bp.post("/recover-phone")
def recover_phone():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get("email"))
    otp = payload.get("otp")
    if not _valid_email(email) or not otp:
        return _error("email and otp are required")
    user = _account_for_email(email)
    if not user:
        return _error("Invalid OTP challenge", "UNAUTHORIZED", 401)
    try:
        challenge, error = _verify_otp(user.phone_number, otp, "account_recovery", email)
        if error:
            db.session.commit()
            return _error(error, "UNAUTHORIZED", 401)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Phone recovery failed unexpectedly")
        return _error("Unable to recover account", "SERVER_ERROR", 500)
    return jsonify({"phone_number": user.phone_number, "message": "Phone number recovered successfully"})


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
    if actor_role == "MANAGER":
        actor_assignment = get_active_assignment(actor.id)
        target_assignment = get_active_assignment(user.id)
        if not actor_assignment or not target_assignment:
            return _error(
                "An active organizational assignment is required to approve accounts",
                "FORBIDDEN",
                403,
            )
        permitted = (
            actor_assignment.organizational_role == "general_manager"
            or (
                actor_assignment.organizational_role == "department_manager"
                and actor_assignment.department_id == user.department_id
                and target_assignment.organizational_role
                in {"team_leader", "field_agent"}
            )
            or (
                actor_assignment.organizational_role == "team_leader"
                and actor_assignment.department_id == user.department_id
                and target_assignment.organizational_role == "field_agent"
                and user.manager_id == actor.id
            )
        )
        if not permitted:
            return _error(
                "You can only approve accounts within your reporting authority",
                "FORBIDDEN",
                403,
            )
    status_error = _apply_admin_user_status(actor, user, "active")
    if status_error:
        return status_error
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
    if not user or not user.is_currently_active() or user.account_status != "approved":
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
    user_data = _user_response_data(user)
    claims = get_jwt()
    if claims.get("acting_admin_id") is not None:
        user_data["acting_as"] = {
            "id": claims["acting_admin_id"],
            "name": claims.get("acting_admin_name", "Super Administrator"),
        }
    response = jsonify({"user": user_data})
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
        if field == "contact_email":
            value = _normalize_email(value)
            if not _valid_email(value):
                return _error("Enter a valid personal email address", "VALIDATION_ERROR", 422)
            duplicate = User.query.filter(
                User.id != user.id,
                (db.func.lower(User.email) == value)
                | (db.func.lower(User.personal_email) == value),
            ).first()
            if duplicate:
                return _error("A user with that personal email already exists", "CONFLICT", 409)
            user.email = value
            user.personal_email = value
            user.contact_email = value
            continue
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
