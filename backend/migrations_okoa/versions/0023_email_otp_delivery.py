"""Persist OTP email destinations and support phone recovery codes."""

from alembic import op
import sqlalchemy as sa


revision = "0023_email_otp_delivery"
down_revision = "0022_dashboard_feature_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("OTP", sa.Column("email_address", sa.String(length=255), nullable=True))
    op.execute(
        "UPDATE OTP JOIN users ON users.id = OTP.user_id "
        "SET OTP.email_address = LOWER(TRIM(users.email)) "
        "WHERE OTP.email_address IS NULL"
    )
    op.alter_column(
        "OTP",
        "email_address",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "OTP",
        "purpose",
        existing_type=sa.Enum("registration", "login", "password_reset", name="otp_purpose"),
        type_=sa.Enum(
            "registration", "login", "password_reset", "account_recovery",
            name="otp_purpose",
        ),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "OTP",
        "purpose",
        existing_type=sa.Enum(
            "registration", "login", "password_reset", "account_recovery",
            name="otp_purpose",
        ),
        type_=sa.Enum("registration", "login", "password_reset", name="otp_purpose"),
        existing_nullable=False,
    )
    op.drop_column("OTP", "email_address")
