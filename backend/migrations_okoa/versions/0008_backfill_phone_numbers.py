"""Backfill phone values to Kenyan E.164 format.

Revision ID: 0008_backfill_phone_numbers
Revises: 0007_optional_otp_debug_code
"""
import logging

from alembic import op
import sqlalchemy as sa

from app.utils.phone import normalize_ke_phone


revision = "0008_backfill_phone_numbers"
down_revision = "0007_optional_otp_debug_code"
branch_labels = None
depends_on = None


def _backfill_table(table_name):
    log = logging.getLogger("alembic.runtime.migration")
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(f"SELECT id, phone_number FROM `{table_name}`")
    ).fetchall()
    for row_id, raw in rows:
        normalized = normalize_ke_phone(raw)
        if normalized is None:
            log.warning("[%s.id=%s] Could not normalize phone=%r - skipped", table_name, row_id, raw)
            continue
        if normalized != raw:
            connection.execute(
                sa.text(f"UPDATE `{table_name}` SET phone_number = :phone WHERE id = :id"),
                {"phone": normalized, "id": row_id},
            )


def upgrade():
    _backfill_table("users")
    _backfill_table("OTP")


def downgrade():
    connection = op.get_bind()
    for table_name in ("users", "OTP"):
        connection.execute(sa.text(
            f"UPDATE `{table_name}` SET phone_number = CONCAT('0', SUBSTRING(phone_number, 5)) "
            "WHERE phone_number LIKE '+254%'"
        ))
