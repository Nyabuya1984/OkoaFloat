from datetime import datetime

from app.extensions import db


class SalesDailyReport(db.Model):
    __tablename__ = "sales_daily_reports"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
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

    employee = db.relationship("User", backref=db.backref("sales_daily_reports", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_name": self.employee.full_name if self.employee else None,
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
