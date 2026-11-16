"""Add Okoa customer-care caller, shift, and escalation fields."""

from alembic import op
import sqlalchemy as sa


revision = "0032_okoa_care_operations"
down_revision = "0031_customer_care"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("customer_care_customers") as batch:
        batch.add_column(sa.Column("caller_type", sa.String(40), nullable=True))
        batch.add_column(sa.Column("location", sa.String(255), nullable=True))
        batch.add_column(sa.Column("agent_name", sa.String(160), nullable=True))
        batch.add_column(sa.Column("agent_number", sa.String(80), nullable=True))
        batch.add_column(sa.Column("store_number", sa.String(80), nullable=True))
        batch.create_index("ix_customer_care_customers_caller_type", ["caller_type"])

    with op.batch_alter_table("customer_care_call_logs") as batch:
        batch.add_column(sa.Column("concern_category", sa.String(40), nullable=True))
        batch.add_column(sa.Column("outbound_reason", sa.String(40), nullable=True))
        batch.add_column(sa.Column("requires_escalation", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("escalated_to", sa.String(40), nullable=True))
        batch.add_column(sa.Column("escalation_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("escalated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("escalation_resolved", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("shift_code", sa.String(1), nullable=True))
        batch.add_column(sa.Column("reference_number", sa.String(20), nullable=True))
        batch.add_column(sa.Column("call_started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("outcome", sa.String(40), nullable=True))
        batch.create_index("ix_customer_care_call_logs_concern_category", ["concern_category"])
        batch.create_index("ix_customer_care_call_logs_outbound_reason", ["outbound_reason"])
        batch.create_index("ix_customer_care_call_logs_requires_escalation", ["requires_escalation"])
        batch.create_index("ix_customer_care_call_logs_escalation_resolved", ["escalation_resolved"])
        batch.create_index("ix_customer_care_call_logs_shift_code", ["shift_code"])
        batch.create_index("ix_customer_care_call_logs_call_started_at", ["call_started_at"])
        batch.create_index("ix_customer_care_call_logs_reference_number", ["reference_number"], unique=True)

    op.create_table(
        "customer_care_shift_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(1), nullable=False, unique=True),
        sa.Column("start_weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_weekday", sa.Integer(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
    )
    op.create_table(
        "customer_care_escalations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), nullable=False),
        sa.Column("to_dept", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["customer_care_call_logs.id"], name="fk_customer_care_escalation_call"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
    )
    op.create_index("ix_customer_care_escalations_call_id", "customer_care_escalations", ["call_id"])
    op.create_index("ix_customer_care_escalations_to_dept", "customer_care_escalations", ["to_dept"])
    op.create_index("ix_customer_care_escalations_status", "customer_care_escalations", ["status"])
    op.create_index("ix_customer_care_escalations_created_at", "customer_care_escalations", ["created_at"])
    op.create_table(
        "customer_care_concern_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("is_escalation_trigger", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_customer_care_concern_categories_direction",
        "customer_care_concern_categories",
        ["direction"],
    )
    op.create_table(
        "customer_care_loan_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("mpesa_number", sa.String(40), nullable=True),
        sa.Column("loan_limit", sa.Numeric(14, 2), nullable=True),
        sa.Column("outstanding_balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("last_limit_increase_at", sa.DateTime(), nullable=True),
        sa.Column("commission_status", sa.String(80), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="customer_claim"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customer_care_customers.id"],
            name="fk_customer_care_snapshot_customer",
        ),
    )
    op.create_index("ix_customer_care_loan_snapshots_customer_id", "customer_care_loan_snapshots", ["customer_id"])
    op.create_table(
        "customer_care_reference_counters",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_table("customer_care_reference_counters")
    op.drop_index("ix_customer_care_loan_snapshots_customer_id", table_name="customer_care_loan_snapshots")
    op.drop_table("customer_care_loan_snapshots")
    op.drop_index("ix_customer_care_concern_categories_direction", table_name="customer_care_concern_categories")
    op.drop_table("customer_care_concern_categories")
    for index in (
        "ix_customer_care_escalations_created_at",
        "ix_customer_care_escalations_status",
        "ix_customer_care_escalations_to_dept",
        "ix_customer_care_escalations_call_id",
    ):
        op.drop_index(index, table_name="customer_care_escalations")
    op.drop_table("customer_care_escalations")
    op.drop_table("customer_care_shift_definitions")
    with op.batch_alter_table("customer_care_call_logs") as batch:
        for index in (
            "ix_customer_care_call_logs_reference_number",
            "ix_customer_care_call_logs_call_started_at",
            "ix_customer_care_call_logs_shift_code",
            "ix_customer_care_call_logs_escalation_resolved",
            "ix_customer_care_call_logs_requires_escalation",
            "ix_customer_care_call_logs_outbound_reason",
            "ix_customer_care_call_logs_concern_category",
        ):
            batch.drop_index(index)
        for column in (
            "outcome", "call_started_at", "reference_number", "shift_code",
            "escalation_resolved", "escalated_at", "escalation_reason",
            "escalated_to", "requires_escalation", "outbound_reason", "concern_category",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("customer_care_customers") as batch:
        batch.drop_index("ix_customer_care_customers_caller_type")
        for column in ("store_number", "agent_number", "agent_name", "location", "caller_type"):
            batch.drop_column(column)
