from datetime import datetime
from decimal import Decimal

from app.extensions import db


DUTY_ROLES = {
    "departmental_manager",
    "department_manager",
    "group_leader",
    "team_leader",
    "sales_marketing_executive",
    "debt_collector_agent",
}


class DebtCollectionDutyAssignment(db.Model):
    __tablename__ = "debt_collection_duty_assignments"
    __table_args__ = (
        db.UniqueConstraint("user_id", "duty", name="uq_debt_collection_user_duty"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    duty = db.Column(db.String(40), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("debt_collection_duties", lazy="dynamic"))
    assigner = db.relationship("User", foreign_keys=[assigned_by])


class DebtCollectionDebtor(db.Model):
    __tablename__ = "debt_collection_debtors"
    __table_args__ = (
        db.UniqueConstraint("agent_no", name="uq_debt_collection_agent_no"),
    )

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    other_names = db.Column(db.String(180), nullable=True)
    agent_msisdn = db.Column(db.String(40), nullable=False, index=True)
    owner_msisdn = db.Column(db.String(40), nullable=True)
    operator_msisdn = db.Column(db.String(40), nullable=True)
    agent_no = db.Column(db.String(80), nullable=False)
    store_number = db.Column(db.String(80), nullable=True, index=True)
    business_name = db.Column(db.String(200), nullable=False, index=True)
    location = db.Column(db.String(180), nullable=True, index=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    loans = db.relationship("DebtCollectionLoan", back_populates="debtor", lazy="dynamic")
    assignments = db.relationship("DebtCollectionAssignment", back_populates="debtor", lazy="dynamic")
    call_logs = db.relationship("DebtCollectionCallLog", back_populates="debtor", lazy="dynamic")
    follow_ups = db.relationship("DebtCollectionFollowUpSchedule", back_populates="debtor", lazy="dynamic")
    ratings = db.relationship("DebtCollectionCreditRating", back_populates="debtor", lazy="dynamic")


class DebtCollectionLoan(db.Model):
    __tablename__ = "debt_collection_loans"

    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("debt_collection_debtors.id"), nullable=False, index=True)
    loan_amount = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    amount_paid = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    imported_balance = db.Column(db.Numeric(14, 2), nullable=True)
    loan_date = db.Column(db.Date, nullable=False)
    last_interest_calc_date = db.Column(db.Date, nullable=True)
    no_of_days = db.Column(db.Integer, nullable=True, default=0)
    status = db.Column(db.String(40), nullable=False, default="Active", index=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    debtor = db.relationship("DebtCollectionDebtor", back_populates="loans")
    payments = db.relationship("DebtCollectionPayment", back_populates="loan", lazy="dynamic")
    assignments = db.relationship("DebtCollectionAssignment", back_populates="loan", lazy="dynamic")
    call_logs = db.relationship("DebtCollectionCallLog", back_populates="loan", lazy="dynamic")
    follow_ups = db.relationship("DebtCollectionFollowUpSchedule", back_populates="loan", lazy="dynamic")
    status_history = db.relationship("DebtCollectionLoanStatusHistory", back_populates="loan", lazy="dynamic")
    ratings = db.relationship("DebtCollectionCreditRating", back_populates="loan", lazy="dynamic")

    @property
    def loan_balance(self):
        if self.imported_balance is not None:
            return self.imported_balance
        return self.loan_amount - self.amount_paid


class DebtCollectionAssignment(db.Model):
    __tablename__ = "debt_collection_assignments"

    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("debt_collection_debtors.id"), nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("debt_collection_loans.id"), nullable=False, index=True)
    collector_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    unassigned_at = db.Column(db.DateTime, nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    debtor = db.relationship("DebtCollectionDebtor", back_populates="assignments")
    loan = db.relationship("DebtCollectionLoan", back_populates="assignments")
    collector = db.relationship("User", foreign_keys=[collector_id], backref=db.backref("debt_collection_collections", lazy="dynamic"))
    assignee = db.relationship("User", foreign_keys=[assigned_by], backref=db.backref("debt_collection_assignments_made", lazy="dynamic"))


class DebtCollectionCallLog(db.Model):
    __tablename__ = "debt_collection_call_logs"

    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("debt_collection_debtors.id"), nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("debt_collection_loans.id"), nullable=True, index=True)
    collector_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    outcome = db.Column(db.String(60), nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)
    promised_date = db.Column(db.Date, nullable=True)
    promised_time = db.Column(db.String(20), nullable=True)
    promised_amount = db.Column(db.Numeric(14, 2), nullable=True)
    callback_date = db.Column(db.Date, nullable=True)
    callback_time = db.Column(db.String(20), nullable=True)
    amount_paid = db.Column(db.Numeric(14, 2), nullable=True, default=Decimal("0.00"))
    parent_call_log_id = db.Column(db.Integer, db.ForeignKey("debt_collection_call_logs.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    debtor = db.relationship("DebtCollectionDebtor", back_populates="call_logs")
    loan = db.relationship("DebtCollectionLoan", back_populates="call_logs")
    collector = db.relationship("User", foreign_keys=[collector_id], backref=db.backref("debt_collection_calls", lazy="dynamic"))
    parent_call = db.relationship("DebtCollectionCallLog", remote_side=[id], backref=db.backref("corrections", lazy="dynamic"))


class DebtCollectionPayment(db.Model):
    __tablename__ = "debt_collection_payments"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("debt_collection_loans.id"), nullable=False, index=True)
    collector_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_type = db.Column(db.String(40), nullable=False, default="partial")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    loan = db.relationship("DebtCollectionLoan", back_populates="payments")
    collector = db.relationship("User", foreign_keys=[collector_id], backref=db.backref("debt_collection_payments", lazy="dynamic"))


class DebtCollectionFollowUpSchedule(db.Model):
    __tablename__ = "debt_collection_follow_up_schedule"

    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("debt_collection_debtors.id"), nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("debt_collection_loans.id"), nullable=True, index=True)
    collector_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    follow_up_type = db.Column(db.String(40), nullable=False, default="PTP")
    due_at = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Pending", index=True)
    source_call_log_id = db.Column(db.Integer, db.ForeignKey("debt_collection_call_logs.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    debtor = db.relationship("DebtCollectionDebtor", back_populates="follow_ups")
    loan = db.relationship("DebtCollectionLoan", back_populates="follow_ups")
    collector = db.relationship("User", foreign_keys=[collector_id], backref=db.backref("debt_collection_follow_ups", lazy="dynamic"))
    source_call = db.relationship("DebtCollectionCallLog", foreign_keys=[source_call_log_id], backref=db.backref("follow_ups", lazy="dynamic"))


class DebtCollectionCreditRating(db.Model):
    __tablename__ = "debt_collection_credit_ratings"

    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("debt_collection_debtors.id"), nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("debt_collection_loans.id"), nullable=True, index=True)
    grade = db.Column(db.String(5), nullable=False, default="C")
    score = db.Column(db.Integer, nullable=False, default=50)
    computed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reason = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    debtor = db.relationship("DebtCollectionDebtor", back_populates="ratings")
    loan = db.relationship("DebtCollectionLoan", back_populates="ratings")
    approver = db.relationship("User", foreign_keys=[approved_by], backref=db.backref("debt_collection_rating_approvals", lazy="dynamic"))


class DebtCollectionLoanStatusHistory(db.Model):
    __tablename__ = "debt_collection_loan_status_history"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("debt_collection_loans.id"), nullable=False, index=True)
    old_status = db.Column(db.String(40), nullable=True)
    new_status = db.Column(db.String(40), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    loan = db.relationship("DebtCollectionLoan", back_populates="status_history")
    changer = db.relationship("User", foreign_keys=[changed_by], backref=db.backref("debt_collection_status_changes", lazy="dynamic"))


class DebtCollectionAuditLog(db.Model):
    __tablename__ = "debt_collection_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    entity = db.Column(db.String(100), nullable=False, index=True)
    action = db.Column(db.String(120), nullable=False)
    before = db.Column(db.JSON, nullable=True)
    after = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    actor = db.relationship("User", backref=db.backref("debt_collection_audit_logs", lazy="dynamic"))


class DebtCollectionImportJob(db.Model):
    __tablename__ = "debt_collection_import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=False)
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    accepted_rows = db.Column(db.Integer, nullable=False, default=0)
    rejected_rows = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    uploaded_file = db.Column(db.String(255), nullable=True)

    uploader = db.relationship("User", backref=db.backref("debt_collection_import_jobs", lazy="dynamic"))
    issues = db.relationship("DebtCollectionImportIssue", back_populates="job", lazy="dynamic")


class DebtCollectionImportIssue(db.Model):
    __tablename__ = "debt_collection_import_issues"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("debt_collection_import_jobs.id"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    job = db.relationship("DebtCollectionImportJob", back_populates="issues")
