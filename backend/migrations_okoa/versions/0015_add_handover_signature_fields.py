"""Add auditable delegate signature fields.

Revision ID: 0015_handover_signature
Revises: 0014_add_leave_workflow_fields
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_handover_signature"
down_revision = "0014_add_leave_workflow_fields"
branch_labels = None
depends_on = None


def upgrade():
    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("leave_requests")}
    if "handover_signature" not in existing_columns:
        op.add_column("leave_requests", sa.Column("handover_signature", sa.String(length=160), nullable=True))
    if "handover_signature_date" not in existing_columns:
        op.add_column("leave_requests", sa.Column("handover_signature_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("leave_requests", "handover_signature_date")
    op.drop_column("leave_requests", "handover_signature")
