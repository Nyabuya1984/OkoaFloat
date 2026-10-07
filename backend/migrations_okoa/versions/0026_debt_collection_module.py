"""Add debt collection schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0026_debt_collection_module"
down_revision = "0025_dev_plaintext_otp"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "debt_collection_debtors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("other_names", sa.String(length=180), nullable=True),
        sa.Column("agent_msisdn", sa.String(length=40), nullable=False),
        sa.Column("owner_msisdn", sa.String(length=40), nullable=True),
        sa.Column("operator_msisdn", sa.String(length=40), nullable=True),
        sa.Column("agent_no", sa.String(length=80), nullable=False),
        sa.Column("store_number", sa.String(length=80), nullable=True),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=180), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_no", name="uq_debt_collection_agent_no"),
    )
    op.create_index(op.f("ix_debt_collection_debtors_agent_msisdn"), "debt_collection_debtors", ["agent_msisdn"], unique=False)
    op.create_index(op.f("ix_debt_collection_debtors_business_name"), "debt_collection_debtors", ["business_name"], unique=False)
    op.create_index(op.f("ix_debt_collection_debtors_is_deleted"), "debt_collection_debtors", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_debt_collection_debtors_location"), "debt_collection_debtors", ["location"], unique=False)
    op.create_index(op.f("ix_debt_collection_debtors_store_number"), "debt_collection_debtors", ["store_number"], unique=False)

    op.create_table(
        "debt_collection_loans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debtor_id", sa.Integer(), nullable=False),
        sa.Column("loan_amount", mysql.DECIMAL(precision=14, scale=2), nullable=False, server_default="0.00"),
        sa.Column("amount_paid", mysql.DECIMAL(precision=14, scale=2), nullable=False, server_default="0.00"),
        sa.Column("loan_date", sa.Date(), nullable=False),
        sa.Column("last_interest_calc_date", sa.Date(), nullable=True),
        sa.Column("no_of_days", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="Active"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["debtor_id"], ["debt_collection_debtors.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_loans_debtor_id"), "debt_collection_loans", ["debtor_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_loans_is_deleted"), "debt_collection_loans", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_debt_collection_loans_status"), "debt_collection_loans", ["status"], unique=False)

    op.create_table(
        "debt_collection_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debtor_id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("collector_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("unassigned_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["collector_id"], ["users.id"], ),
        sa.ForeignKeyConstraint(["debtor_id"], ["debt_collection_debtors.id"], ),
        sa.ForeignKeyConstraint(["loan_id"], ["debt_collection_loans.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_assignments_collector_id"), "debt_collection_assignments", ["collector_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_assignments_debtor_id"), "debt_collection_assignments", ["debtor_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_assignments_is_active"), "debt_collection_assignments", ["is_active"], unique=False)
    op.create_index(op.f("ix_debt_collection_assignments_loan_id"), "debt_collection_assignments", ["loan_id"], unique=False)

    op.create_table(
        "debt_collection_call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debtor_id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=True),
        sa.Column("collector_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=60), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("promised_date", sa.Date(), nullable=True),
        sa.Column("promised_time", sa.String(length=20), nullable=True),
        sa.Column("promised_amount", mysql.DECIMAL(precision=14, scale=2), nullable=True),
        sa.Column("callback_date", sa.Date(), nullable=True),
        sa.Column("callback_time", sa.String(length=20), nullable=True),
        sa.Column("amount_paid", mysql.DECIMAL(precision=14, scale=2), nullable=True, server_default="0.00"),
        sa.Column("parent_call_log_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["collector_id"], ["users.id"], ),
        sa.ForeignKeyConstraint(["debtor_id"], ["debt_collection_debtors.id"], ),
        sa.ForeignKeyConstraint(["loan_id"], ["debt_collection_loans.id"], ),
        sa.ForeignKeyConstraint(["parent_call_log_id"], ["debt_collection_call_logs.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_call_logs_collector_id"), "debt_collection_call_logs", ["collector_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_call_logs_debtor_id"), "debt_collection_call_logs", ["debtor_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_call_logs_loan_id"), "debt_collection_call_logs", ["loan_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_call_logs_outcome"), "debt_collection_call_logs", ["outcome"], unique=False)

    op.create_table(
        "debt_collection_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("collector_id", sa.Integer(), nullable=False),
        sa.Column("amount", mysql.DECIMAL(precision=14, scale=2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_type", sa.String(length=40), nullable=False, server_default="partial"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["collector_id"], ["users.id"], ),
        sa.ForeignKeyConstraint(["loan_id"], ["debt_collection_loans.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_payments_loan_id"), "debt_collection_payments", ["loan_id"], unique=False)

    op.create_table(
        "debt_collection_follow_up_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debtor_id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=True),
        sa.Column("collector_id", sa.Integer(), nullable=False),
        sa.Column("follow_up_type", sa.String(length=40), nullable=False, server_default="PTP"),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="Pending"),
        sa.Column("source_call_log_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["collector_id"], ["users.id"], ),
        sa.ForeignKeyConstraint(["debtor_id"], ["debt_collection_debtors.id"], ),
        sa.ForeignKeyConstraint(["loan_id"], ["debt_collection_loans.id"], ),
        sa.ForeignKeyConstraint(["source_call_log_id"], ["debt_collection_call_logs.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_follow_up_schedule_collector_id"), "debt_collection_follow_up_schedule", ["collector_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_follow_up_schedule_debtor_id"), "debt_collection_follow_up_schedule", ["debtor_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_follow_up_schedule_due_at"), "debt_collection_follow_up_schedule", ["due_at"], unique=False)
    op.create_index(op.f("ix_debt_collection_follow_up_schedule_source_call_log_id"), "debt_collection_follow_up_schedule", ["source_call_log_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_follow_up_schedule_status"), "debt_collection_follow_up_schedule", ["status"], unique=False)

    op.create_table(
        "debt_collection_credit_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debtor_id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=True),
        sa.Column("grade", sa.String(length=5), nullable=False, server_default="C"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["debtor_id"], ["debt_collection_debtors.id"], ),
        sa.ForeignKeyConstraint(["loan_id"], ["debt_collection_loans.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_credit_ratings_debtor_id"), "debt_collection_credit_ratings", ["debtor_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_credit_ratings_loan_id"), "debt_collection_credit_ratings", ["loan_id"], unique=False)

    op.create_table(
        "debt_collection_loan_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("loan_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ),
        sa.ForeignKeyConstraint(["loan_id"], ["debt_collection_loans.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_loan_status_history_loan_id"), "debt_collection_loan_status_history", ["loan_id"], unique=False)
    op.create_index(op.f("ix_debt_collection_loan_status_history_changed_by"), "debt_collection_loan_status_history", ["changed_by"], unique=False)

    op.create_table(
        "debt_collection_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_audit_logs_entity"), "debt_collection_audit_logs", ["entity"], unique=False)
    op.create_index(op.f("ix_debt_collection_audit_logs_user_id"), "debt_collection_audit_logs", ["user_id"], unique=False)

    op.create_table(
        "debt_collection_import_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("uploaded_file", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_import_jobs_uploaded_by"), "debt_collection_import_jobs", ["uploaded_by"], unique=False)

    op.create_table(
        "debt_collection_import_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["debt_collection_import_jobs.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debt_collection_import_issues_job_id"), "debt_collection_import_issues", ["job_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_debt_collection_import_issues_job_id"), table_name="debt_collection_import_issues")
    op.drop_table("debt_collection_import_issues")
    op.drop_index(op.f("ix_debt_collection_import_jobs_uploaded_by"), table_name="debt_collection_import_jobs")
    op.drop_table("debt_collection_import_jobs")
    op.drop_index(op.f("ix_debt_collection_audit_logs_user_id"), table_name="debt_collection_audit_logs")
    op.drop_index(op.f("ix_debt_collection_audit_logs_entity"), table_name="debt_collection_audit_logs")
    op.drop_table("debt_collection_audit_logs")
    op.drop_index(op.f("ix_debt_collection_loan_status_history_changed_by"), table_name="debt_collection_loan_status_history")
    op.drop_index(op.f("ix_debt_collection_loan_status_history_loan_id"), table_name="debt_collection_loan_status_history")
    op.drop_table("debt_collection_loan_status_history")
    op.drop_index(op.f("ix_debt_collection_credit_ratings_loan_id"), table_name="debt_collection_credit_ratings")
    op.drop_index(op.f("ix_debt_collection_credit_ratings_debtor_id"), table_name="debt_collection_credit_ratings")
    op.drop_table("debt_collection_credit_ratings")
    op.drop_index(op.f("ix_debt_collection_follow_up_schedule_status"), table_name="debt_collection_follow_up_schedule")
    op.drop_index(op.f("ix_debt_collection_follow_up_schedule_source_call_log_id"), table_name="debt_collection_follow_up_schedule")
    op.drop_index(op.f("ix_debt_collection_follow_up_schedule_due_at"), table_name="debt_collection_follow_up_schedule")
    op.drop_index(op.f("ix_debt_collection_follow_up_schedule_debtor_id"), table_name="debt_collection_follow_up_schedule")
    op.drop_index(op.f("ix_debt_collection_follow_up_schedule_collector_id"), table_name="debt_collection_follow_up_schedule")
    op.drop_table("debt_collection_follow_up_schedule")
    op.drop_index(op.f("ix_debt_collection_payments_loan_id"), table_name="debt_collection_payments")
    op.drop_table("debt_collection_payments")
    op.drop_index(op.f("ix_debt_collection_call_logs_outcome"), table_name="debt_collection_call_logs")
    op.drop_index(op.f("ix_debt_collection_call_logs_loan_id"), table_name="debt_collection_call_logs")
    op.drop_index(op.f("ix_debt_collection_call_logs_debtor_id"), table_name="debt_collection_call_logs")
    op.drop_index(op.f("ix_debt_collection_call_logs_collector_id"), table_name="debt_collection_call_logs")
    op.drop_table("debt_collection_call_logs")
    op.drop_index(op.f("ix_debt_collection_assignments_loan_id"), table_name="debt_collection_assignments")
    op.drop_index(op.f("ix_debt_collection_assignments_is_active"), table_name="debt_collection_assignments")
    op.drop_index(op.f("ix_debt_collection_assignments_debtor_id"), table_name="debt_collection_assignments")
    op.drop_index(op.f("ix_debt_collection_assignments_collector_id"), table_name="debt_collection_assignments")
    op.drop_table("debt_collection_assignments")
    op.drop_index(op.f("ix_debt_collection_loans_status"), table_name="debt_collection_loans")
    op.drop_index(op.f("ix_debt_collection_loans_is_deleted"), table_name="debt_collection_loans")
    op.drop_index(op.f("ix_debt_collection_loans_debtor_id"), table_name="debt_collection_loans")
    op.drop_table("debt_collection_loans")
    op.drop_index(op.f("ix_debt_collection_debtors_store_number"), table_name="debt_collection_debtors")
    op.drop_index(op.f("ix_debt_collection_debtors_location"), table_name="debt_collection_debtors")
    op.drop_index(op.f("ix_debt_collection_debtors_is_deleted"), table_name="debt_collection_debtors")
    op.drop_index(op.f("ix_debt_collection_debtors_business_name"), table_name="debt_collection_debtors")
    op.drop_index(op.f("ix_debt_collection_debtors_agent_msisdn"), table_name="debt_collection_debtors")
    op.drop_table("debt_collection_debtors")
