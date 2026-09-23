"""Add persisted daily sales reports."""

from alembic import op
import sqlalchemy as sa

revision = "0017_sales_daily_reports"
down_revision = "0016_backfill_policies"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sales_daily_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("agent_name", sa.String(length=160), nullable=False),
        sa.Column("agent_number", sa.String(length=80)),
        sa.Column("store_number", sa.String(length=80)),
        sa.Column("business_owner_name", sa.String(length=160)),
        sa.Column("contact_phone", sa.String(length=40)),
        sa.Column("id_number", sa.String(length=80)),
        sa.Column("business_location", sa.String(length=240)),
        sa.Column("date_visited", sa.Date(), nullable=False),
        sa.Column("registration_date", sa.Date()),
        sa.Column("admin_name", sa.String(length=160)),
        sa.Column("witness_name", sa.String(length=160)),
        sa.Column("witness_id_number", sa.String(length=80)),
        sa.Column("witness_phone", sa.String(length=40)),
        sa.Column("customer_type", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("visit_mode", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("documents", sa.JSON(), nullable=False),
        sa.Column("uploaded_files", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_daily_reports_employee_id", "sales_daily_reports", ["employee_id"])


def downgrade():
    op.drop_index("ix_sales_daily_reports_employee_id", table_name="sales_daily_reports")
    op.drop_table("sales_daily_reports")
