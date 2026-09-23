"""Merge the chat/handover branch into the OTP branch.

Revision ID: 0011_merge_handover_otp
Revises: 0007_optional_otp_debug_code, 0007_profile_handover_chat
"""
from alembic import op


revision = "0011_merge_handover_otp"
down_revision = ("0010_add_superuser_flag", "0007_profile_handover_chat")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
