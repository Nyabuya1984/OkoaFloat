"""Okoa Float customer-care business rules.

Datetimes persisted by the application are naive UTC values for compatibility
with the existing schema. A naive input is therefore interpreted as UTC before
being converted to the configured operations timezone for shift calculations.
"""
from datetime import datetime, time, timezone
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, has_app_context
from sqlalchemy import select

from app.extensions import db
from app.models.customer_care import ReferenceCounter


INBOUND_CONCERNS = {
    "INFORMATION_INQUIRY", "REPAYMENT_PERIOD", "ELIGIBILITY",
    "LIMITS_MIN_MAX", "USAGE_FREQUENCY", "TRANSFER_CHARGES", "TRANSACTIONAL_CHARGES",
    "REGISTRATION_DOCS", "LOAN_BALANCE", "LOAN_LIMIT",
    "LOAN_INCREASE_REQUEST", "REGISTRATION_PROCESS", "RECONCILIATION",
    "PAYMENT_METHOD", "ACCOUNT_STATUS", "PRODUCT_INFO", "GENERAL_INQUIRY",
    "CALLER_READY_TO_REGISTER",
    "SALES_REG_VERIFICATION",
}
OUTBOUND_REASONS = {
    "VERIFY_DOCS", "VERIFY_REGISTRATION", "POST_LIMIT_SET", "POST_LIMIT_INCREASE",
    "LIMIT_STATUS_ACCEPTED", "LIMIT_STATUS_REJECTED",
}
ESCALATION_CATEGORIES = {
    "RECONCILIATION", "LOAN_INCREASE_REQUEST", "LOAN_LIMIT_RESET_PASSWORD",
    "COMMISSION_STATUS_CHANGED", "LOAN_DEFAULTER", "DISBURSEMENT_FAILURE",
    "PENDING_LOAN", "USSD_ISSUE", "PAYMENT_NOT_REFLECTING",
}
_reference_lock = Lock()
_standalone_reference_value = 0


def _operations_timezone():
    name = current_app.config.get("TIMEZONE", "Africa/Nairobi") if has_app_context() else "Africa/Nairobi"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid TIMEZONE setting: {name}") from exc


def _as_local(dt):
    if not isinstance(dt, datetime):
        raise TypeError("dt must be a datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_operations_timezone())


def compute_shift(dt):
    """Return active A/B/C shift for a datetime in configured local time."""
    local = _as_local(dt)
    weekday = local.weekday()  # Monday=0
    now = local.timetz().replace(tzinfo=None)
    if ((weekday == 0 and now >= time(8)) or weekday == 1 or
            (weekday == 2 and now < time(12))):
        return "A"
    if ((weekday == 2 and now >= time(12)) or weekday == 3 or
            (weekday == 4 and now < time(16))):
        return "B"
    return "C"


def should_escalate(concern_category, priority=None, outcome=None):
    """Return (required, destination), routing USSD operational issues to IT."""
    category = (concern_category or "").strip().upper()
    detail = " ".join(str(value or "") for value in (category, outcome)).lower()
    ussd = "ussd" in detail or category == "USSD_ISSUE"
    triggers = ussd or category in ESCALATION_CATEGORIES or any(
        phrase in detail for phrase in (
            "payment not reflect", "payment not reflecting", "limit reset",
            "commission status changed", "loan defaulter", "disbursement fail",
            "pending loan", "loan limit increase", "reconciliation",
        )
    )
    urgent = str(priority or "").strip().upper() == "URGENT"
    if not triggers and not urgent:
        return False, None
    return True, "it_support" if ussd else "general_manager"


def generate_reference_number(reference_id=None):
    """Allocate an OF-YYYY-NNNNNN reference; call IDs provide concurrency safety."""
    global _standalone_reference_value
    year = datetime.now(timezone.utc).year
    if reference_id is not None:
        if not isinstance(reference_id, int) or reference_id < 1:
            raise ValueError("reference_id must be a positive integer")
        return f"OF-{year}-{reference_id:06d}"
    if not has_app_context():
        with _reference_lock:
            _standalone_reference_value += 1
            return f"OF-{year}-{_standalone_reference_value:06d}"

    with db.session.no_autoflush:
        counter = db.session.execute(
            select(ReferenceCounter).where(ReferenceCounter.year == year).with_for_update()
        ).scalar_one_or_none()
    if counter is None:
        counter = ReferenceCounter(year=year, next_value=2)
        db.session.add(counter)
        db.session.flush()
        value = 1
    else:
        value = counter.next_value
        counter.next_value += 1
        db.session.flush()
    return f"OF-{year}-{value:06d}"


def validate_caller_fields(caller_type, payload):
    """Raise ValueError with a client-safe message when caller details are incomplete."""
    if caller_type not in {"agent", "sub_agent", "sales_rep", "potential_client"}:
        raise ValueError("caller_type must be agent, sub_agent, sales_rep, or potential_client")
    if caller_type in {"agent", "sub_agent"}:
        missing = [
            field for field in ("agent_name", "agent_number", "store_number", "location")
            if not isinstance(payload.get(field), str) or not payload[field].strip()
        ]
        if missing:
            raise ValueError("Required caller fields missing: " + ", ".join(missing))
