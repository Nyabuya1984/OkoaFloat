"""Store the date a sales registration became complete."""

from alembic import op
import sqlalchemy as sa


revision = "0040_sales_completion_date"
down_revision = "0039_client_registration_status"
branch_labels = None
depends_on = None


def upgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("sales_daily_reports")
    }
    if "completion_date" not in columns:
        op.add_column(
            "sales_daily_reports",
            sa.Column("completion_date", sa.Date(), nullable=True),
        )


def downgrade():
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("sales_daily_reports")
    }
    if "completion_date" in columns:
        op.drop_column("sales_daily_reports", "completion_date")
