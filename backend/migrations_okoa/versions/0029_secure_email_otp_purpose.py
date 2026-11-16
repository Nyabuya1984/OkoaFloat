"""Add reset as a dedicated OTP purpose."""

from alembic import op
import sqlalchemy as sa


revision = "0029_secure_email_otp_purpose"
down_revision = "0028_debt_loan_archive"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "OTP",
        "purpose",
        existing_type=sa.Enum(
            "registration",
            "login",
            "password_reset",
            "account_recovery",
            name="otp_purpose",
        ),
        type_=sa.Enum(
            "registration",
            "login",
            "password_reset",
            "account_recovery",
            "reset",
            name="otp_purpose",
        ),
        existing_nullable=False,
    )


def downgrade():
    op.execute("UPDATE OTP SET purpose = 'password_reset' WHERE purpose = 'reset'")
    op.alter_column(
        "OTP",
        "purpose",
        existing_type=sa.Enum(
            "registration",
            "login",
            "password_reset",
            "account_recovery",
            "reset",
            name="otp_purpose",
        ),
        type_=sa.Enum(
            "registration",
            "login",
            "password_reset",
            "account_recovery",
            name="otp_purpose",
        ),
        existing_nullable=False,
    )
