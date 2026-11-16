from datetime import datetime

from sqlalchemy.orm import synonym

from app.extensions import db


class DepartmentPageConfiguration(db.Model):
    __tablename__ = "department_page_configurations"

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pages = db.Column(db.JSON, nullable=False, default=list)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = db.relationship("Department")


class DepartmentAssignmentHistory(db.Model):
    __tablename__ = "department_assignment_history"
    __table_args__ = (
        db.Index("ix_assignment_history_user_active", "user_id", "ended_at"),
        db.Index("ix_assignment_history_department", "department_id", "started_at"),
        db.UniqueConstraint(
            "active_general_manager_key",
            name="uq_active_general_manager",
        ),
        db.UniqueConstraint(
            "active_department_manager_key",
            name="uq_active_department_manager_per_department",
        ),
        db.UniqueConstraint(
            "active_team_leader_key",
            name="uq_active_team_leader_per_department",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    department_name = db.Column(db.String(120), nullable=False)
    role_id = db.Column(
        db.Integer, db.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    organizational_role_id = db.Column(
        db.Integer, db.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    role_name = db.Column(db.String(64), nullable=True)
    organizational_role = db.Column(db.String(32), nullable=False, default="field_agent")
    assigned_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    active_general_manager_key = db.Column(
        db.Integer,
        db.Computed(
            "CASE WHEN ended_at IS NULL AND organizational_role = 'general_manager' "
            "THEN 1 ELSE NULL END",
            persisted=False,
        ),
    )
    active_department_manager_key = db.Column(
        db.Integer,
        db.Computed(
            "CASE WHEN ended_at IS NULL AND organizational_role = 'department_manager' "
            "THEN department_id ELSE NULL END",
            persisted=False,
        ),
    )
    active_team_leader_key = db.Column(
        db.Integer,
        db.Computed(
            "CASE WHEN ended_at IS NULL AND organizational_role = 'team_leader' "
            "THEN department_id ELSE NULL END",
            persisted=False,
        ),
    )
    start_date = synonym("started_at")
    end_date = synonym("ended_at")

    user = db.relationship("User", foreign_keys=[user_id])
    department = db.relationship("Department")
    role = db.relationship("Role", foreign_keys=[role_id])
    organizational_role_record = db.relationship(
        "Role", foreign_keys=[organizational_role_id]
    )
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])


class LeaveApprovalStep(db.Model):
    __tablename__ = "leave_approval_steps"
    __table_args__ = (
        db.UniqueConstraint(
            "leave_request_id",
            "stage_role",
            name="uq_leave_approval_request_stage",
        ),
        db.Index("ix_leave_approval_actor_decided", "actor_id", "decided_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    leave_request_id = db.Column(
        db.Integer,
        db.ForeignKey("leave_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_role = db.Column(db.String(32), nullable=False)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision = db.Column(db.String(20), nullable=False)
    decision_comment = db.Column(db.Text, nullable=True)
    signature = db.Column(db.String(160), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    actor = db.relationship("User")


class AgentLocation(db.Model):
    __tablename__ = "agent_locations"
    __table_args__ = (
        db.Index("ix_agent_locations_user_recorded", "user_id", "recorded_at"),
        db.Index("ix_agent_locations_recorded_at", "recorded_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy_meters = db.Column(db.Float, nullable=True)
    is_simulated = db.Column(db.Boolean, nullable=False, default=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    timestamp = synonym("recorded_at")

    user = db.relationship("User")
    department = db.relationship("Department")


class AgentLocationSharing(db.Model):
    __tablename__ = "agent_location_sharing"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User")


class AgentLocationPolicy(db.Model):
    __tablename__ = "agent_location_policies"

    id = db.Column(db.Integer, primary_key=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    timezone = db.Column(db.String(64), nullable=False, default="Africa/Nairobi")
    days = db.Column(db.JSON, nullable=False, default=list)
    start_time = db.Column(db.String(5), nullable=False, default="08:00")
    end_time = db.Column(db.String(5), nullable=False, default="17:00")
    updated_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    updated_by = db.relationship("User")

    def to_dict(self):
        return {
            "enabled": self.is_enabled,
            "timezone": self.timezone,
            "days": self.days or [],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentLocationOverride(db.Model):
    __tablename__ = "agent_location_overrides"
    __table_args__ = (
        db.UniqueConstraint("scope_type", "scope_id", name="uq_location_override_scope"),
        db.Index("ix_location_override_expiry", "expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    scope_type = db.Column(db.String(20), nullable=False)
    scope_id = db.Column(db.Integer, nullable=False, default=0)
    is_enabled = db.Column(db.Boolean, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    updated_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    updated_by = db.relationship("User")


class Client(db.Model):
    __tablename__ = "clients"
    __table_args__ = (
        db.Index("ix_clients_department_created", "department_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    phone_number = db.Column(db.String(40), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True)
    client_type = db.Column(db.String(40), nullable=False)
    client_status = db.Column(db.String(16), nullable=True)
    business_name = db.Column(db.String(160), nullable=True)
    business_location = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    location_accuracy_meters = db.Column(db.Float, nullable=True)
    department_id = db.Column(
        db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    registered_by_user_id = synonym("created_by_id")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    department = db.relationship("Department")
    created_by = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone_number": self.phone_number,
            "email": self.email,
            "client_type": self.client_type,
            "client_status": self.client_status,
            "business_name": self.business_name,
            "business_location": self.business_location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_accuracy_meters": self.location_accuracy_meters,
            "department_id": self.department_id,
            "created_by_id": self.created_by_id,
            "registered_by_user_id": self.registered_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


DepartmentHistory = DepartmentAssignmentHistory
