"""Add structured fields to daily sales reports."""

from alembic import op
import sqlalchemy as sa

revision = "0018_sales_report_data"
down_revision = "0017_sales_daily_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sales_daily_reports", sa.Column("report_data", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("sales_daily_reports", "report_data")
