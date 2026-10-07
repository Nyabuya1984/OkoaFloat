"""Drop the obsolete OTP challenge table."""

from alembic import op


revision = "0020_drop_otp_table"
down_revision = "0019_clean_otp_table"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("OTP")


def downgrade():
    raise RuntimeError("The dropped OTP table cannot be restored with its data")