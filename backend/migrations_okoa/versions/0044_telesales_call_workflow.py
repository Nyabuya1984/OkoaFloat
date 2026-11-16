"""Add structured telesales call logs, registrations and follow-up tasks."""

from alembic import op
import sqlalchemy as sa


revision = "0044_telesales_call_workflow"
down_revision = "0043_sales_leads_audit_stamps"
branch_labels = None
depends_on = None


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    additions = (
        ("company_name", sa.String(length=160), True),
        ("director_name", sa.String(length=160), True),
        ("head_office_location", sa.String(length=240), True),
        ("business_location", sa.String(length=240), True),
        ("mpesa_agent_name", sa.String(length=160), True),
        ("mpesa_agent_number", sa.String(length=80), True),
        ("mpesa_store_number", sa.String(length=80), True),
        ("is_archived", sa.Boolean(), False),
        ("archived_at", sa.DateTime(), True),
    )
    existing = _columns("sales_leads")
    for name, column_type, nullable in additions:
        if name not in existing:
            op.add_column(
                "sales_leads",
                sa.Column(name, column_type, nullable=nullable, server_default=sa.false() if name == "is_archived" else None),
            )
    op.create_index("ix_sales_leads_is_archived", "sales_leads", ["is_archived"])

    op.create_table(
        "sales_call_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("sales_leads.id"), nullable=False),
        sa.Column("contacted_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contact_datetime", sa.DateTime(), nullable=False),
        sa.Column("contact_date", sa.Date(), nullable=False),
        sa.Column("contact_day", sa.String(length=12), nullable=False),
        sa.Column("contact_time", sa.String(length=8), nullable=False),
        sa.Column("response", sa.String(length=32), nullable=False),
        sa.Column("reason_for_decline", sa.String(length=500), nullable=True),
        sa.Column("appointment_datetime", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reached", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sales_call_logs_lead_id", "sales_call_logs", ["lead_id"])
    op.create_index("ix_sales_call_logs_contacted_by_user_id", "sales_call_logs", ["contacted_by_user_id"])
    op.create_index("ix_sales_call_logs_contact_datetime", "sales_call_logs", ["contact_datetime"])
    op.create_index("ix_sales_call_logs_contact_date", "sales_call_logs", ["contact_date"])
    op.create_index("ix_sales_call_logs_response", "sales_call_logs", ["response"])
    op.create_index("ix_sales_call_logs_reached", "sales_call_logs", ["reached"])
    op.create_index(
        "ix_sales_call_contact_actor",
        "sales_call_logs",
        ["contact_datetime", "contacted_by_user_id"],
    )
    op.create_index(
        "ix_sales_call_response",
        "sales_call_logs",
        ["response", "contact_datetime"],
    )

    op.create_table(
        "sales_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("sales_leads.id"), nullable=False, unique=True),
        sa.Column("registered_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("documents", sa.JSON(), nullable=False),
        sa.Column("reason_for_incompleteness", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sales_registrations_registered_by_user_id", "sales_registrations", ["registered_by_user_id"])
    op.create_index("ix_sales_registrations_status", "sales_registrations", ["status"])
    op.create_index("ix_sales_registrations_created_at", "sales_registrations", ["created_at"])

    op.create_table(
        "sales_follow_ups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("sales_leads.id"), nullable=False),
        sa.Column("call_log_id", sa.Integer(), sa.ForeignKey("sales_call_logs.id"), nullable=True),
        sa.Column("registration_id", sa.Integer(), sa.ForeignKey("sales_registrations.id"), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sales_follow_ups_lead_id", "sales_follow_ups", ["lead_id"])
    op.create_index("ix_sales_follow_ups_call_log_id", "sales_follow_ups", ["call_log_id"])
    op.create_index("ix_sales_follow_ups_registration_id", "sales_follow_ups", ["registration_id"])
    op.create_index("ix_sales_follow_ups_assigned_to_user_id", "sales_follow_ups", ["assigned_to_user_id"])
    op.create_index("ix_sales_follow_ups_due_at", "sales_follow_ups", ["due_at"])
    op.create_index("ix_sales_follow_ups_is_completed", "sales_follow_ups", ["is_completed"])
    op.create_index(
        "ix_sales_follow_up_assignee_due_open",
        "sales_follow_ups",
        ["assigned_to_user_id", "due_at", "is_completed"],
    )


def downgrade():
    op.drop_table("sales_follow_ups")
    op.drop_table("sales_registrations")
    op.drop_table("sales_call_logs")
    op.drop_index("ix_sales_leads_is_archived", table_name="sales_leads")
    for column in (
        "archived_at",
        "is_archived",
        "mpesa_store_number",
        "mpesa_agent_number",
        "mpesa_agent_name",
        "business_location",
        "head_office_location",
        "director_name",
        "company_name",
    ):
        op.drop_column("sales_leads", column)
