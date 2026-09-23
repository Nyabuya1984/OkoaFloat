"""Backfill policies for leave types created by administration.

Revision ID: 0016_backfill_policies
Revises: 0015_add_handover_signature_fields
"""

from alembic import op

revision = "0016_backfill_policies"
down_revision = "0015_handover_signature"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO leave_policies
            (leave_type_id, accrual_rate, max_carryover, notice_days_required, min_service_months)
        SELECT lt.id, lt.default_days_per_year, 0, 0, 0
        FROM leave_types lt
        WHERE NOT EXISTS (
            SELECT 1 FROM leave_policies lp WHERE lp.leave_type_id = lt.id
        )
        """
    )


def downgrade():
    pass
