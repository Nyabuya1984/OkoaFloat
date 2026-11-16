"""Use plaintext OTP values only in development and testing."""

from alembic import op
from flask import current_app
import sqlalchemy as sa


revision = "0045_dev_plaintext_only"
down_revision = "0044_telesales_call_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "OTP",
        "code_hash",
        existing_type=sa.String(length=128),
        nullable=True,
    )
    if current_app.config.get("OTP_STORE_PLAINTEXT"):
        op.execute("UPDATE OTP SET code_hash = NULL")
        op.execute(
            "UPDATE OTP SET status = 'expired' "
            "WHERE status = 'active' AND plaintext_code IS NULL"
        )


def downgrade():
    if current_app.config.get("OTP_STORE_PLAINTEXT"):
        op.execute("UPDATE OTP SET code_hash = '' WHERE code_hash IS NULL")
    op.alter_column(
        "OTP",
        "code_hash",
        existing_type=sa.String(length=128),
        nullable=False,
    )
