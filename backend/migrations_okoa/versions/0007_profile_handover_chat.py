"""Add leave handover fields and employee chat."""

from alembic import op
import sqlalchemy as sa


revision = "0007_profile_handover_chat"
down_revision = "0006_backfill_employee_identity"
branch_labels = None
depends_on = None


def upgrade():
    for name, column in (
        ("contact_phone", sa.String(30)),
        ("contact_email", sa.String(120)),
        ("address_line1", sa.String(200)),
        ("address_line2", sa.String(200)),
        ("city", sa.String(80)),
        ("country", sa.String(80)),
        ("postal_code", sa.String(20)),
        ("handover_name", sa.String(160)),
        ("handover_statement", sa.Text()),
        ("handover_agreed_at", sa.DateTime()),
        ("handover_report", sa.Text()),
    ):
        op.add_column("leave_requests", sa.Column(name, column, nullable=True))
    op.add_column("leave_requests", sa.Column("handover_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_leave_requests_handover_user", "leave_requests", "users", ["handover_user_id"], ["id"])
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("chat_messages")
    op.drop_constraint("fk_leave_requests_handover_user", "leave_requests", type_="foreignkey")
    for name in ("handover_user_id", "handover_report", "handover_agreed_at", "handover_statement", "handover_name", "postal_code", "country", "city", "address_line2", "address_line1", "contact_email", "contact_phone"):
        op.drop_column("leave_requests", name)