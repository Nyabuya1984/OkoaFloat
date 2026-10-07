"""Add personal email OTP destinations."""

from alembic import op
import sqlalchemy as sa


revision = "0024_personal_email_otp_delivery"
down_revision = "0023_email_otp_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("personal_email", sa.String(length=255), nullable=True))
    op.execute(
        "UPDATE users SET personal_email = LOWER(TRIM(COALESCE("
        "NULLIF(contact_email, ''), email))) WHERE personal_email IS NULL "
        "OR TRIM(personal_email) = ''"
    )
    op.alter_column(
        "users",
        "contact_email",
        existing_type=sa.String(length=120),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.add_column(
        "OTP",
        sa.Column("personal_email_address", sa.String(length=255), nullable=True),
    )
    op.execute(
        "UPDATE OTP JOIN users ON users.id = OTP.user_id "
        "SET OTP.personal_email_address = COALESCE("
        "NULLIF(LOWER(TRIM(users.personal_email)), ''), "
        "LOWER(TRIM(users.email))) WHERE OTP.personal_email_address IS NULL"
    )


def downgrade():
    op.drop_column("OTP", "personal_email_address")
    op.alter_column(
        "users",
        "contact_email",
        existing_type=sa.String(length=255),
        type_=sa.String(length=120),
        existing_nullable=True,
    )
    op.drop_column("users", "personal_email")
