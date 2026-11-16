from datetime import datetime

from app.extensions import db


class SalesDailyReport(db.Model):
    __tablename__ = "sales_daily_reports"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    department = db.Column(db.String(120), nullable=False, default="Sales and Marketing")
    agent_name = db.Column(db.String(160), nullable=False)
    agent_number = db.Column(db.String(80), nullable=True)
    store_number = db.Column(db.String(80), nullable=True)
    business_owner_name = db.Column(db.String(160), nullable=True)
    contact_phone = db.Column(db.String(40), nullable=True)
    id_number = db.Column(db.String(80), nullable=True)
    business_location = db.Column(db.String(240), nullable=True)
    date_visited = db.Column(db.Date, nullable=False)
    registration_date = db.Column(db.Date, nullable=True)
    completion_date = db.Column(db.Date, nullable=True)
    admin_name = db.Column(db.String(160), nullable=True)
    witness_name = db.Column(db.String(160), nullable=True)
    witness_id_number = db.Column(db.String(80), nullable=True)
    witness_phone = db.Column(db.String(40), nullable=True)
    customer_type = db.Column(db.String(40), nullable=False)
    outcome = db.Column(db.String(40), nullable=False)
    visit_mode = db.Column(db.String(30), nullable=False, default="field_visit")
    notes = db.Column(db.Text, nullable=True)
    documents = db.Column(db.JSON, nullable=False, default=dict)
    uploaded_files = db.Column(db.JSON, nullable=False, default=list)
    report_data = db.Column(db.JSON, nullable=True, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee = db.relationship(
        "User",
        foreign_keys=[employee_id],
        backref=db.backref("sales_daily_reports", lazy=True),
    )
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_name": self.employee.full_name if self.employee else None,
            "created_by_id": self.created_by_id,
            "updated_by_id": self.updated_by_id,
            "department": self.department,
            "agent_name": self.agent_name,
            "agent_number": self.agent_number,
            "store_number": self.store_number,
            "business_owner_name": self.business_owner_name,
            "contact_phone": self.contact_phone,
            "id_number": self.id_number,
            "business_location": self.business_location,
            "date_visited": self.date_visited.isoformat() if self.date_visited else None,
            "registration_date": self.registration_date.isoformat() if self.registration_date else None,
            "admin_name": self.admin_name,
            "witness_name": self.witness_name,
            "witness_id_number": self.witness_id_number,
            "witness_phone": self.witness_phone,
            "customer_type": self.customer_type,
            "outcome": self.outcome,
            "visit_mode": self.visit_mode,
            "notes": self.notes,
            "documents": self.documents or {},
            "uploaded_files": self.uploaded_files or [],
            **(self.report_data or {}),
            "completion_date": self.completion_date.isoformat() if self.completion_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SalesLead(db.Model):
    """A Sales & Marketing prospect and its allocation/contact audit trail."""

    __tablename__ = "sales_leads"

    id = db.Column(db.Integer, primary_key=True)
    lead_name = db.Column(db.String(160), nullable=False)
    business_name = db.Column(db.String(160), nullable=True)
    company_name = db.Column(db.String(160), nullable=True)
    director_name = db.Column(db.String(160), nullable=True)
    phone_number = db.Column(db.String(40), nullable=False, index=True)
    email = db.Column(db.String(160), nullable=True)
    location = db.Column(db.String(240), nullable=True)
    head_office_location = db.Column(db.String(240), nullable=True)
    business_location = db.Column(db.String(240), nullable=True)
    mpesa_agent_name = db.Column(db.String(160), nullable=True)
    mpesa_agent_number = db.Column(db.String(80), nullable=True)
    mpesa_store_number = db.Column(db.String(80), nullable=True)
    source = db.Column(db.String(120), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="new", index=True)
    outcome_reason = db.Column(db.String(240), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    callback_date = db.Column(db.Date, nullable=True)
    callback_time = db.Column(db.String(20), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    allocated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    allocated_at = db.Column(db.DateTime, nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = db.relationship("User", foreign_keys=[assigned_to_id])
    allocator = db.relationship("User", foreign_keys=[allocated_by_id])
    creator = db.relationship("User", foreign_keys=[created_by_id])
    updater = db.relationship("User", foreign_keys=[updated_by_id])
    department = db.relationship("Department")
    call_logs = db.relationship(
        "SalesCallLog",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="SalesCallLog.contact_datetime.desc()",
    )
    registration = db.relationship(
        "SalesRegistration",
        back_populates="lead",
        uselist=False,
        cascade="all, delete-orphan",
    )
    follow_ups = db.relationship(
        "SalesFollowUp",
        back_populates="lead",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "lead_name": self.lead_name,
            "business_name": self.business_name,
            "company_name": self.company_name,
            "director_name": self.director_name,
            "phone_number": self.phone_number,
            "email": self.email,
            "location": self.location,
            "head_office_location": self.head_office_location,
            "business_location": self.business_location,
            "mpesa_agent_name": self.mpesa_agent_name,
            "mpesa_agent_number": self.mpesa_agent_number,
            "mpesa_store_number": self.mpesa_store_number,
            "source": self.source,
            "department_id": self.department_id,
            "status": self.status,
            "outcome_reason": self.outcome_reason,
            "notes": self.notes,
            "callback_date": self.callback_date.isoformat() if self.callback_date else None,
            "callback_time": self.callback_time,
            "assigned_to_id": self.assigned_to_id,
            "assignee_name": self.assignee.full_name if self.assignee else None,
            "allocated_by_id": self.allocated_by_id,
            "allocated_at": self.allocated_at.isoformat() if self.allocated_at else None,
            "is_archived": bool(self.is_archived),
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "created_by_id": self.created_by_id,
            "updated_by_id": self.updated_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "registration": self.registration.to_dict() if self.registration else None,
            "call_logs": [log.to_dict() for log in self.call_logs],
            "open_follow_up_count": sum(not task.is_completed for task in self.follow_ups),
            "open_escalation_count": sum(
                not task.is_completed and task.task_type == "manager_escalation"
                for task in self.follow_ups
            ),
        }


class SalesCallLog(db.Model):
    """Immutable attempt record for an outbound telesales call."""

    __tablename__ = "sales_call_logs"
    __table_args__ = (
        db.Index("ix_sales_call_contact_actor", "contact_datetime", "contacted_by_user_id"),
        db.Index("ix_sales_call_response", "response", "contact_datetime"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("sales_leads.id"), nullable=False, index=True)
    contacted_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    contact_datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    contact_date = db.Column(db.Date, nullable=False, index=True)
    contact_day = db.Column(db.String(12), nullable=False)
    contact_time = db.Column(db.String(8), nullable=False)
    response = db.Column(db.String(32), nullable=False, index=True)
    reason_for_decline = db.Column(db.String(500), nullable=True)
    appointment_datetime = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    reached = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    lead = db.relationship("SalesLead", back_populates="call_logs")
    contacted_by = db.relationship("User", foreign_keys=[contacted_by_user_id])
    follow_ups = db.relationship("SalesFollowUp", back_populates="call_log")

    def to_dict(self):
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "contacted_by_user_id": self.contacted_by_user_id,
            "contacted_by_name": self.contacted_by.full_name if self.contacted_by else None,
            "contact_date": self.contact_date.isoformat() if self.contact_date else None,
            "contact_day": self.contact_day,
            "contact_time": self.contact_time,
            "contact_datetime": self.contact_datetime.isoformat() if self.contact_datetime else None,
            "response": self.response,
            "reason_for_decline": self.reason_for_decline,
            "appointment_datetime": self.appointment_datetime.isoformat() if self.appointment_datetime else None,
            "notes": self.notes,
            "reached": bool(self.reached),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SalesRegistration(db.Model):
    __tablename__ = "sales_registrations"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("sales_leads.id"), nullable=False, unique=True)
    registered_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, index=True)
    documents = db.Column(db.JSON, nullable=False, default=dict)
    reason_for_incompleteness = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead = db.relationship("SalesLead", back_populates="registration")
    registered_by = db.relationship("User", foreign_keys=[registered_by_user_id])
    follow_ups = db.relationship("SalesFollowUp", back_populates="registration")

    def to_dict(self):
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "registered_by_user_id": self.registered_by_user_id,
            "registered_by_name": self.registered_by.full_name if self.registered_by else None,
            "status": self.status,
            "documents": self.documents or {},
            "reason_for_incompleteness": self.reason_for_incompleteness,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SalesFollowUp(db.Model):
    __tablename__ = "sales_follow_ups"
    __table_args__ = (
        db.Index("ix_sales_follow_up_assignee_due_open", "assigned_to_user_id", "due_at", "is_completed"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("sales_leads.id"), nullable=False, index=True)
    call_log_id = db.Column(db.Integer, db.ForeignKey("sales_call_logs.id"), nullable=True, index=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("sales_registrations.id"), nullable=True, index=True)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    due_at = db.Column(db.DateTime, nullable=False, index=True)
    task_type = db.Column(db.String(32), nullable=False)
    notes = db.Column(db.String(1000), nullable=True)
    is_completed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    lead = db.relationship("SalesLead", back_populates="follow_ups")
    call_log = db.relationship("SalesCallLog", back_populates="follow_ups")
    registration = db.relationship("SalesRegistration", back_populates="follow_ups")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "lead_name": self.lead.lead_name if self.lead else None,
            "phone_number": self.lead.phone_number if self.lead else None,
            "call_log_id": self.call_log_id,
            "registration_id": self.registration_id,
            "assigned_to_user_id": self.assigned_to_user_id,
            "assigned_to_name": self.assigned_to.full_name if self.assigned_to else None,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "task_type": self.task_type,
            "notes": self.notes,
            "is_completed": bool(self.is_completed),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
