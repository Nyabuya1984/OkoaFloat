"""Add reversible archive state to debt collection loans."""

from alembic import op
import sqlalchemy as sa


revision = "0028_debt_loan_archive"
down_revision = "0027_debt_duties"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "debt_collection_loans",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        op.f("ix_debt_collection_loans_is_archived"),
        "debt_collection_loans",
        ["is_archived"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_debt_collection_loans_is_archived"),
        table_name="debt_collection_loans",
    )
    op.drop_column("debt_collection_loans", "is_archived")
