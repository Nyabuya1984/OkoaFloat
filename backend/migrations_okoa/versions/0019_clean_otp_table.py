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
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("OTP")}
    indexes = {index["name"] for index in inspector.get_indexes("OTP")}
    if "status" not in columns:
        op.add_column(
            "OTP",
            sa.Column(
                "status",
                sa.Enum("active", "expired", "verified", name="otp_status"),
                nullable=False,
                server_default="active",
            ),
        )
    if "ix_OTP_status" not in indexes:
        op.create_index("ix_OTP_status", "OTP", ["status"])
    if "debug_code" in columns:
        op.drop_column("OTP", "debug_code")


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("OTP")}
    indexes = {index["name"] for index in inspector.get_indexes("OTP")}
    if "debug_code" not in columns:
        op.add_column("OTP", sa.Column("debug_code", sa.String(length=6), nullable=True))
    if "ix_OTP_status" in indexes:
        op.drop_index("ix_OTP_status", table_name="OTP")
    if "status" in columns:
        op.drop_column("OTP", "status")
