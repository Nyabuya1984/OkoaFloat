"""Add an opt-in plaintext OTP field for local testing only.

Revision ID: 0007_optional_otp_debug_code
Revises: 0006_backfill_employee_identity
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_optional_otp_debug_code"
down_revision = "0006_backfill_employee_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("OTP", sa.Column("debug_code", sa.String(length=6), nullable=True))


def downgrade():
    op.drop_column("OTP", "debug_code")