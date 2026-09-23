"""Add auditable leave workflow fields.

Revision ID: 0014_add_leave_workflow_fields
Revises: 0013_add_user_lifecycle_fields
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_add_leave_workflow_fields"
down_revision = "0013_add_user_lifecycle_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leave_requests", sa.Column("workflow_state", sa.String(length=32), nullable=False, server_default="submitted"))
    op.add_column("leave_requests", sa.Column("declaration_accepted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("leave_requests", sa.Column("employee_signature", sa.String(length=160), nullable=True))
    op.add_column("leave_requests", sa.Column("declaration_date", sa.Date(), nullable=True))
    op.add_column("leave_requests", sa.Column("manual_days_override", sa.Numeric(6, 2), nullable=True))
    op.add_column("leave_requests", sa.Column("manual_days_reason", sa.String(length=500), nullable=True))
    op.add_column("leave_requests", sa.Column("supervisor_name", sa.String(length=160), nullable=True))
    op.add_column("leave_requests", sa.Column("supervisor_signature", sa.String(length=160), nullable=True))
    op.add_column("leave_requests", sa.Column("supervisor_decision_date", sa.DateTime(), nullable=True))
    op.add_column("leave_requests", sa.Column("supervisor_decision", sa.String(length=20), nullable=True))
    op.add_column("leave_requests", sa.Column("hr_manager", sa.String(length=160), nullable=True))
    op.add_column("leave_requests", sa.Column("hr_verification_date", sa.DateTime(), nullable=True))
    op.add_column("leave_requests", sa.Column("hr_verification_status", sa.String(length=32), nullable=True))
    op.create_index("ix_leave_requests_workflow_state", "leave_requests", ["workflow_state"])


def downgrade():
    op.drop_index("ix_leave_requests_workflow_state", table_name="leave_requests")
    for column in (
        "hr_verification_status", "hr_verification_date", "hr_manager", "supervisor_decision",
        "supervisor_decision_date", "supervisor_signature", "supervisor_name", "manual_days_reason",
        "manual_days_override", "declaration_date", "employee_signature", "declaration_accepted",
        "workflow_state",
    ):
        op.drop_column("leave_requests", column)
