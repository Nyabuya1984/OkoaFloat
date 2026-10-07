"""Restore OTP storage without a client challenge identifier."""

from alembic import op
import sqlalchemy as sa


revision = "0021_restore_otp_table"
down_revision = "0020_drop_otp_table"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "OTP",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum("registration", "login", "password_reset", name="otp_purpose"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "expired", "verified", name="otp_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_OTP_status", "OTP", ["status"])


def downgrade():
    op.drop_table("OTP")