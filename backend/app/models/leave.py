from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(64), unique=True, nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    employee_name = db.Column(db.String(120), nullable=True)
    job_position_title = db.Column(db.String(120), nullable=True)
    employer = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    personal_email = db.Column(db.String(255), nullable=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=True)
    contact_phone = db.Column(db.String(30), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    profile_photo_url = db.Column(db.String(500), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    address_line1 = db.Column(db.String(200), nullable=True)
    address_line2 = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    country = db.Column(db.String(80), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(32),
        nullable=False,
        default="EMPLOYEE",
    )
    department = db.Column(db.String(120), nullable=True)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    hire_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    deactivated_at = db.Column(db.DateTime, nullable=True)
    deactivated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    deactivation_reason = db.Column(db.String(500), nullable=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    archive_reason = db.Column(db.String(500), nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    delete_reason = db.Column(db.String(500), nullable=True)
    is_superuser = db.Column(db.Boolean, nullable=False, default=False)
    account_status = db.Column(db.String(20), nullable=False, default="pending")
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    manager = db.relationship(
        "User",
        remote_side=[id],
        foreign_keys=[manager_id],
        backref="direct_reports",
    )
    department_record = db.relationship("Department", backref=db.backref("users", lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_currently_active(self):
        return bool(self.is_active and not self.is_archived and not self.is_deleted)

    def state(self):
        if self.is_deleted:
            return "deleted"
        if self.is_archived:
            return "archived"
        if not self.is_active:
            return "deactivated"
        return "active"

    @classmethod
    def active_query(cls):
        return cls.query.filter(
            cls.is_active.is_(True),
            cls.is_archived.is_(False),
            cls.is_deleted.is_(False),
        )

    @classmethod
    def including_archived_query(cls):
        return cls.query.filter(cls.is_deleted.is_(False))

    @classmethod
    def archived_only_query(cls):
        return cls.query.filter(
            cls.is_archived.is_(True),
            cls.is_deleted.is_(False),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "full_name": self.full_name,
            "employee_name": self.employee_name or self.full_name,
            "job_position_title": self.job_position_title,
            "employer": self.employer,
            "email": self.email,
            "personal_email": self.personal_email or self.email,
            "phone_number": self.phone_number,
            "profile_photo_url": self.profile_photo_url,
            "department_id": self.department_id,
            "department_details": (
                {"id": self.department_record.id, "name": self.department_record.name}
                if self.department_record else None
            ),
            "contact": {
                "phone": self.contact_phone or self.phone_number,
                "email": self.personal_email or self.contact_email or self.email,
                "address_line1": self.address_line1,
                "address_line2": self.address_line2,
                "city": self.city,
                "country": self.country,
                "postal_code": self.postal_code,
            },
            "role": self.role,
            "department": self.department,
            "manager_id": self.manager_id,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "is_active": self.is_active,
            "is_archived": self.is_archived,
            "is_deleted": self.is_deleted,
            "state": self.state(),
            "is_superuser": self.is_superuser,
            "account_status": self.account_status,
            "must_change_password": self.must_change_password,
        }


class LeaveType(db.Model):
    __tablename__ = "leave_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(40), unique=True, nullable=False)
    is_paid = db.Column(db.Boolean, nullable=False, default=True)
    requires_document = db.Column(db.Boolean, nullable=False, default=False)
    default_days_per_year = db.Column(db.Numeric(6, 2), nullable=False, default=0)


class LeavePolicy(db.Model):
    __tablename__ = "leave_policies"

    id = db.Column(db.Integer, primary_key=True)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    accrual_rate = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    max_carryover = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    notice_days_required = db.Column(db.Integer, nullable=False, default=0)
    gender_restriction = db.Column(db.String(20), nullable=True)
    min_service_months = db.Column(db.Integer, nullable=False, default=0)

    leave_type = db.relationship("LeaveType", backref=db.backref("policies", lazy=True))


class LeaveBalance(db.Model):
    __tablename__ = "leave_balances"
    __table_args__ = (db.UniqueConstraint("user_id", "leave_type_id", "year"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    entitled_days = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    used_days = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    pending_days = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    carried_over = db.Column(db.Numeric(6, 2), nullable=False, default=0)

    user = db.relationship("User", backref=db.backref("leave_balances", lazy=True))
    leave_type = db.relationship("LeaveType")


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_requested = db.Column(db.Numeric(6, 2), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    contact_phone = db.Column(db.String(30), nullable=True)
    contact_email = db.Column(db.String(120), nullable=True)
    address_line1 = db.Column(db.String(200), nullable=True)
    address_line2 = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    country = db.Column(db.String(80), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    handover_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    handover_name = db.Column(db.String(160), nullable=True)
    handover_statement = db.Column(db.Text, nullable=True)
    handover_agreed_at = db.Column(db.DateTime, nullable=True)
    handover_signature = db.Column(db.String(160), nullable=True)
    handover_signature_date = db.Column(db.Date, nullable=True)
    handover_report = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("pending", "approved", "rejected", "cancelled", name="leave_status"),
        nullable=False,
        default="pending",
    )
    workflow_state = db.Column(db.String(32), nullable=False, default="submitted", index=True)
    declaration_accepted = db.Column(db.Boolean, nullable=False, default=False)
    employee_signature = db.Column(db.String(160), nullable=True)
    declaration_date = db.Column(db.Date, nullable=True)
    manual_days_override = db.Column(db.Numeric(6, 2), nullable=True)
    manual_days_reason = db.Column(db.String(500), nullable=True)
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    supervisor_name = db.Column(db.String(160), nullable=True)
    supervisor_signature = db.Column(db.String(160), nullable=True)
    supervisor_decision_date = db.Column(db.DateTime, nullable=True)
    supervisor_decision = db.Column(db.String(20), nullable=True)
    hr_manager = db.Column(db.String(160), nullable=True)
    hr_verification_date = db.Column(db.DateTime, nullable=True)
    hr_verification_status = db.Column(db.String(32), nullable=True)
    decision_comment = db.Column(db.Text, nullable=True)
    applied_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("leave_requests", lazy=True))
    leave_type = db.relationship("LeaveType")
    approver = db.relationship("User", foreign_keys=[approver_id])
    handover_user = db.relationship("User", foreign_keys=[handover_user_id])


class CompanyHoliday(db.Model):
    __tablename__ = "company_holidays"
    __table_args__ = (db.UniqueConstraint("date", "country"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    date = db.Column(db.Date, nullable=False)
    country = db.Column(db.String(80), nullable=False, default="Kenya")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    entity = db.Column(db.String(120), nullable=False)
    entity_id = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    event_metadata = db.Column("metadata", db.JSON, nullable=True)

    actor = db.relationship("User", foreign_keys=[actor_id])


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("notifications", lazy=True))
