"""Idempotent reference-data seeding for Okoa customer care."""
from datetime import time

from app.extensions import db
from app.models.customer_care import ConcernCategory, ShiftDefinition
from app.utils.okia_business import ESCALATION_CATEGORIES, INBOUND_CONCERNS, OUTBOUND_REASONS


_LABELS = {
    "INFORMATION_INQUIRY": "Okoa Float service overview",
    "REPAYMENT_PERIOD": "Repayment period",
    "ELIGIBILITY": "Eligibility",
    "LIMITS_MIN_MAX": "Minimum and maximum float amount",
    "USAGE_FREQUENCY": "Usage frequency",
    "TRANSFER_CHARGES": "Float transfer charges",
    "TRANSACTIONAL_CHARGES": "Other transactional charges",
    "REGISTRATION_DOCS": "Required registration documents",
    "LOAN_BALANCE": "Loan balance inquiry",
    "LOAN_LIMIT": "Loan limit inquiry",
    "LOAN_INCREASE_REQUEST": "Loan limit increase request",
    "REGISTRATION_PROCESS": "Registration process",
    "CALLER_READY_TO_REGISTER": "Caller ready to register",
    "RECONCILIATION": "Payment reconciliation dispute",
    "PAYMENT_METHOD": "Payment method",
    "ACCOUNT_STATUS": "Account or loan status",
    "PRODUCT_INFO": "Product information",
    "GENERAL_INQUIRY": "General inquiry",
    "SALES_REG_VERIFICATION": "Sales registration verification",
    "VERIFY_DOCS": "Verify registration documents",
    "VERIFY_REGISTRATION": "Verify new registration",
    "POST_LIMIT_SET": "Follow-up after limit set",
    "POST_LIMIT_INCREASE": "Follow-up after limit increase",
    "LIMIT_STATUS_ACCEPTED": "Limit accepted",
    "LIMIT_STATUS_REJECTED": "Limit rejected",
}
_TRIGGER_CODES = ESCALATION_CATEGORIES | {"LOAN_INCREASE_REQUEST"}
_SHIFTS = (
    ("A", 0, time(8), 2, time(12)),
    ("B", 2, time(12), 4, time(16)),
    ("C", 4, time(16), 0, time(8)),
)


def seed_reference_data():
    """Insert/update Okoa shift and controlled concern reference rows."""
    ConcernCategory.query.filter(
        ConcernCategory.code.in_({"REGISTRATION_HOW", "REPAYMENT_HOW"})
    ).delete(synchronize_session=False)

    for code, start_day, start_time, end_day, end_time in _SHIFTS:
        row = ShiftDefinition.query.filter_by(code=code).first()
        if row is None:
            row = ShiftDefinition(code=code)
            db.session.add(row)
        row.start_weekday = start_day
        row.start_time = start_time
        row.end_weekday = end_day
        row.end_time = end_time

    for code in sorted(INBOUND_CONCERNS | OUTBOUND_REASONS):
        direction = "inbound" if code in INBOUND_CONCERNS else "outbound"
        row = ConcernCategory.query.filter_by(code=code).first()
        if row is None:
            row = ConcernCategory(code=code)
            db.session.add(row)
        row.label = _LABELS[code]
        row.direction = direction
        row.is_escalation_trigger = code in _TRIGGER_CODES
    db.session.commit()
