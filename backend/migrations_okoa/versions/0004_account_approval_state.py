"""Add account approval and moderation state.

Revision ID: 0004_account_approval_state
Revises: 0003_rename_otp_table
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_account_approval_state"
down_revision = "0003_rename_otp_table"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("account_status", sa.String(length=20), nullable=False, server_default="approved"))
    op.add_column("users", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_users_approved_by", "users", "users", ["approved_by"], ["id"])


def downgrade():
    op.drop_constraint("fk_users_approved_by", "users", type_="foreignkey")
    op.drop_column("users", "approved_at")
    op.drop_column("users", "approved_by")
    op.drop_column("users", "account_status")