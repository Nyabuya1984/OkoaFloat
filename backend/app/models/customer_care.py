from datetime import datetime

from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customer_care_customers"
    __table_args__ = (
        db.UniqueConstraint("phone_number", name="uq_customer_care_customer_phone"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    phone_number = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    company = db.Column(db.String(160), nullable=True)
    caller_type = db.Column(db.String(40), nullable=True, index=True)
    location = db.Column(db.String(255), nullable=True)
    agent_name = db.Column(db.String(160), nullable=True)
    agent_number = db.Column(db.String(80), nullable=True)
    store_number = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    call_logs = db.relationship("CallLog", back_populates="customer", lazy="select")


class CallLog(db.Model):
    __tablename__ = "customer_care_call_logs"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "customer_care_customers.id",
            name="fk_customer_care_call_log_customer",
        ),
        nullable=False,
        index=True,
    )
    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_customer_care_call_log_staff"),
        nullable=False,
        index=True,
    )
    call_type = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(80), nullable=False, index=True)
    priority = db.Column(db.String(20), nullable=False, default="Normal", index=True)
    summary = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(40), nullable=False, default="Pending Follow-up", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    concern_category = db.Column(db.String(40), nullable=True, index=True)
    outbound_reason = db.Column(db.String(40), nullable=True, index=True)
    requires_escalation = db.Column(db.Boolean, nullable=False, default=False, index=True)
    escalated_to = db.Column(db.String(40), nullable=True)
    escalation_reason = db.Column(db.Text, nullable=True)
    escalated_at = db.Column(db.DateTime, nullable=True)
    escalation_resolved = db.Column(db.Boolean, nullable=False, default=False, index=True)
    shift_code = db.Column(db.String(1), nullable=True, index=True)
    reference_number = db.Column(db.String(20), nullable=True, unique=True, index=True)
    call_started_at = db.Column(db.DateTime, nullable=True, index=True)
    outcome = db.Column(db.String(40), nullable=True)

    customer = db.relationship("Customer", back_populates="call_logs")
    staff = db.relationship("User", foreign_keys=[staff_id])
    follow_ups = db.relationship(
        "CallFollowUp",
        back_populates="call_log",
        cascade="all, delete-orphan",
        lazy="select",
    )
    escalations = db.relationship(
        "Escalation", back_populates="call_log", cascade="all, delete-orphan", lazy="select"
    )


class ShiftDefinition(db.Model):
    __tablename__ = "customer_care_shift_definitions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(1), nullable=False, unique=True)
    start_weekday = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_weekday = db.Column(db.Integer, nullable=False)
    end_time = db.Column(db.Time, nullable=False)


class Escalation(db.Model):
    __tablename__ = "customer_care_escalations"

    id = db.Column(db.Integer, primary_key=True)
    call_id = db.Column(
        db.Integer,
        db.ForeignKey("customer_care_call_logs.id", name="fk_customer_care_escalation_call"),
        nullable=False,
        index=True,
    )
    to_dept = db.Column(db.String(40), nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    call_log = db.relationship("CallLog", back_populates="escalations")
    resolver = db.relationship("User", foreign_keys=[resolved_by])


class ConcernCategory(db.Model):
    __tablename__ = "customer_care_concern_categories"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    label = db.Column(db.String(160), nullable=False)
    direction = db.Column(db.String(12), nullable=False, index=True)
    is_escalation_trigger = db.Column(db.Boolean, nullable=False, default=False)


class LoanSnapshot(db.Model):
    __tablename__ = "customer_care_loan_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customer_care_customers.id", name="fk_customer_care_snapshot_customer"),
        nullable=False,
        index=True,
    )
    mpesa_number = db.Column(db.String(40), nullable=True)
    loan_limit = db.Column(db.Numeric(14, 2), nullable=True)
    outstanding_balance = db.Column(db.Numeric(14, 2), nullable=True)
    last_limit_increase_at = db.Column(db.DateTime, nullable=True)
    commission_status = db.Column(db.String(80), nullable=True)
    captured_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    source = db.Column(db.String(20), nullable=False, default="customer_claim")


class ReferenceCounter(db.Model):
    __tablename__ = "customer_care_reference_counters"

    year = db.Column(db.Integer, primary_key=True)
    next_value = db.Column(db.Integer, nullable=False, default=1)


class CallFollowUp(db.Model):
    __tablename__ = "customer_care_follow_ups"

    id = db.Column(db.Integer, primary_key=True)
    call_log_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "customer_care_call_logs.id",
            name="fk_customer_care_follow_up_call_log",
        ),
        nullable=False,
        index=True,
    )
    assigned_to = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_customer_care_follow_up_assignee"),
        nullable=False,
        index=True,
    )
    due_date = db.Column(db.Date, nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    call_log = db.relationship("CallLog", back_populates="follow_ups")
    assignee = db.relationship("User", foreign_keys=[assigned_to])
