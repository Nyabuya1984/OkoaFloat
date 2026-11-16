"""Add lead allocation and sales record audit stamps."""

from alembic import op
import sqlalchemy as sa


revision = "0043_sales_leads_audit_stamps"
down_revision = "0042_department_page_config"
branch_labels = None
depends_on = None


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    report_columns = _columns("sales_daily_reports")
    if "created_by_id" not in report_columns:
        op.add_column(
            "sales_daily_reports",
            sa.Column("created_by_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_sales_report_created_by", "sales_daily_reports", "users",
            ["created_by_id"], ["id"],
        )
    if "updated_by_id" not in report_columns:
        op.add_column(
            "sales_daily_reports",
            sa.Column("updated_by_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_sales_report_updated_by", "sales_daily_reports", "users",
            ["updated_by_id"], ["id"],
        )

    op.create_table(
        "sales_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_name", sa.String(length=160), nullable=False),
        sa.Column("business_name", sa.String(length=160), nullable=True),
        sa.Column("phone_number", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("location", sa.String(length=240), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("outcome_reason", sa.String(length=240), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("callback_date", sa.Date(), nullable=True),
        sa.Column("callback_time", sa.String(length=20), nullable=True),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column("allocated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("allocated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["allocated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
    )
    op.create_index("ix_sales_leads_phone_number", "sales_leads", ["phone_number"])
    op.create_index("ix_sales_leads_status", "sales_leads", ["status"])
    op.create_index("ix_sales_leads_assigned_to_id", "sales_leads", ["assigned_to_id"])
    op.create_index("ix_sales_leads_department_id", "sales_leads", ["department_id"])


def downgrade():
    op.drop_table("sales_leads")
    op.drop_constraint(
        "fk_sales_report_updated_by", "sales_daily_reports", type_="foreignkey"
    )
    op.drop_column("sales_daily_reports", "updated_by_id")
    op.drop_constraint(
        "fk_sales_report_created_by", "sales_daily_reports", type_="foreignkey"
    )
    op.drop_column("sales_daily_reports", "created_by_id")
