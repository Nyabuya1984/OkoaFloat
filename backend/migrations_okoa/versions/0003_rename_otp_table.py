"""Rename the OTP challenge table to OTP.

Revision ID: 0003_rename_otp_table
Revises: 0002_phone_otp_sessions
"""
from alembic import op


revision = "0003_rename_otp_table"
down_revision = "0002_phone_otp_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("otp_challenges", "OTP")


def downgrade():
    op.rename_table("OTP", "otp_challenges")