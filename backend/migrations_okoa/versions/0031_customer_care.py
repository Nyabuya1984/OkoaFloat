"""Create customer care customers, call logs, and follow-ups."""

from alembic import op
import sqlalchemy as sa


revision = "0031_customer_care"
down_revision = "0030_leave_policy_entitlement"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_care_customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("phone_number", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("phone_number", name="uq_customer_care_customer_phone"),
    )
    op.create_index(
        "ix_customer_care_customers_name",
        "customer_care_customers",
        ["name"],
    )

    op.create_table(
        "customer_care_call_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=False),
        sa.Column("call_type", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer_care_customers.id"],
            name="fk_customer_care_call_log_customer",
        ),
        sa.ForeignKeyConstraint(["staff_id"], ["users.id"], name="fk_customer_care_call_log_staff"),
    )
    op.create_index("ix_customer_care_call_logs_customer_id", "customer_care_call_logs", ["customer_id"])
    op.create_index("ix_customer_care_call_logs_staff_id", "customer_care_call_logs", ["staff_id"])
    op.create_index("ix_customer_care_call_logs_category", "customer_care_call_logs", ["category"])
    op.create_index("ix_customer_care_call_logs_priority", "customer_care_call_logs", ["priority"])
    op.create_index("ix_customer_care_call_logs_status", "customer_care_call_logs", ["status"])
    op.create_index("ix_customer_care_call_logs_created_at", "customer_care_call_logs", ["created_at"])

    op.create_table(
        "customer_care_follow_ups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_log_id", sa.Integer(), nullable=False),
        sa.Column("assigned_to", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["call_log_id"],
            ["customer_care_call_logs.id"],
            name="fk_customer_care_follow_up_call_log",
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], name="fk_customer_care_follow_up_assignee"),
    )
    op.create_index("ix_customer_care_follow_ups_call_log_id", "customer_care_follow_ups", ["call_log_id"])
    op.create_index("ix_customer_care_follow_ups_assigned_to", "customer_care_follow_ups", ["assigned_to"])
    op.create_index("ix_customer_care_follow_ups_due_date", "customer_care_follow_ups", ["due_date"])
    op.create_index("ix_customer_care_follow_ups_is_completed", "customer_care_follow_ups", ["is_completed"])


def downgrade():
    op.drop_table("customer_care_follow_ups")
    op.drop_table("customer_care_call_logs")
    op.drop_table("customer_care_customers")
