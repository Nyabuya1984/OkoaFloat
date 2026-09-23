"""Add handover report and related tables.

Revision ID: 0012_add_handover_report_tables
Revises: 0011_merge_handover_otp
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_add_handover_report_tables"
down_revision = "0011_merge_handover_otp"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "handover_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("leave_request_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False, server_default="v1"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["leave_request_id"], ["leave_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("leave_request_id"),
    )

    op.create_table(
        "handover_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("handover_report_id", sa.Integer(), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "not_started",
                "in_progress",
                "blocked",
                "awaiting_review",
                "almost_done",
                "done",
                name="handover_task_status",
            ),
            nullable=True,
        ),
        sa.Column("percent_complete", sa.SmallInteger(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", "critical", name="handover_task_priority"),
            nullable=True,
        ),
        sa.Column("stakeholder", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["handover_report_id"], ["handover_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "handover_recurring",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("handover_report_id", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=200), nullable=True),
        sa.Column(
            "cadence",
            sa.Enum("daily", "weekly", "monthly", "quarterly", name="handover_cadence"),
            nullable=True,
        ),
        sa.Column("where_link", sa.String(length=500), nullable=True),
        sa.Column("definition_of_done", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["handover_report_id"], ["handover_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "handover_escalations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("handover_report_id", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(length=200), nullable=True),
        sa.Column("contact_user_id", sa.Integer(), nullable=True),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("contact_role", sa.String(length=120), nullable=True),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("contact_email", sa.String(length=120), nullable=True),
        sa.Column("when_to_escalate", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["handover_report_id"], ["handover_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "handover_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("handover_report_id", sa.Integer(), nullable=False),
        sa.Column("system_name", sa.String(length=120), nullable=True),
        sa.Column(
            "access_level",
            sa.Enum("read", "write", "admin", name="handover_access_level"),
            nullable=True,
        ),
        sa.Column("how_to_request", sa.Text(), nullable=False),
        sa.Column("ticket_raised", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["handover_report_id"], ["handover_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "handover_risks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("handover_report_id", sa.Integer(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=True),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["handover_report_id"], ["handover_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "handover_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("handover_report_id", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=80), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["handover_report_id"], ["handover_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "handover_acceptances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("delegate_id", sa.Integer(), nullable=False),
        sa.Column("acknowledgment_text", sa.Text(), nullable=True),
        sa.Column("signature_name", sa.String(length=120), nullable=True),
        sa.Column("signature_date", sa.Date(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["request_id"], ["leave_requests.id"]),
        sa.ForeignKeyConstraint(["delegate_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("handover_acceptances")
    op.drop_table("handover_attachments")
    op.drop_table("handover_risks")
    op.drop_table("handover_access")
    op.drop_table("handover_escalations")
    op.drop_table("handover_recurring")
    op.drop_table("handover_tasks")
    op.drop_table("handover_reports")
