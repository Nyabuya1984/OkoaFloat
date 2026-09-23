"""Add E.164 checks after phone backfill.

Revision ID: 0009_phone_e164_constraints
Revises: 0008_backfill_phone_numbers
"""
from alembic import op


revision = "0009_phone_e164_constraints"
down_revision = "0008_backfill_phone_numbers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_users_phone_e164",
        "users",
        "phone_number REGEXP '^\\\\+254[71][0-9]{8}$'",
    )
    op.create_check_constraint(
        "ck_otp_phone_e164",
        "OTP",
        "phone_number REGEXP '^\\\\+254[71][0-9]{8}$'",
    )


def downgrade():
    op.drop_constraint("ck_otp_phone_e164", "OTP", type_="check")
    op.drop_constraint("ck_users_phone_e164", "users", type_="check")
