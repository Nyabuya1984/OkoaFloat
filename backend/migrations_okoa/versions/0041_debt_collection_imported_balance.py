"""Preserve balances imported from legacy debt portfolio sheets."""

from alembic import op
import sqlalchemy as sa


revision = "0041_debt_imported_balance"
down_revision = "0040_sales_completion_date"
branch_labels = None
depends_on = None


def upgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("debt_collection_loans")
    }
    if "imported_balance" not in columns:
        op.add_column(
            "debt_collection_loans",
            sa.Column("imported_balance", sa.Numeric(14, 2), nullable=True),
        )


def downgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("debt_collection_loans")
    }
    if "imported_balance" in columns:
        op.drop_column("debt_collection_loans", "imported_balance")
