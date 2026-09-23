"""Remove the plaintext OTP debug column and add OTP lifecycle status.

Revision ID: 0019_clean_otp_table
Revises: 0018_sales_report_data
"""
from alembic import op
import sqlalchemy as sa


revision = "0019_clean_otp_table"
down_revision = "0018_sales_report_data"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "OTP",
        sa.Column(
            "status",
            sa.Enum("active", "expired", "verified", name="otp_status"),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_index("ix_OTP_status", "OTP", ["status"])
    op.drop_column("OTP", "debug_code")


def downgrade():
    op.add_column("OTP", sa.Column("debug_code", sa.String(length=6), nullable=True))
    op.drop_index("ix_OTP_status", table_name="OTP")
    op.drop_column("OTP", "status")
