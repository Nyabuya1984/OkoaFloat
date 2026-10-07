"""Store plaintext OTPs only for local development and testing."""

from alembic import op
import sqlalchemy as sa


revision = "0025_dev_plaintext_otp"
down_revision = "0024_personal_email_otp_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("OTP", sa.Column("plaintext_code", sa.String(length=6), nullable=True))


def downgrade():
    op.drop_column("OTP", "plaintext_code")
