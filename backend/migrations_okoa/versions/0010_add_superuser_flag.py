"""Add is_superuser flag to users.

Revision ID: 0010_add_superuser_flag
Revises: 0009_phone_e164_constraints
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_add_superuser_flag"
down_revision = "0009_phone_e164_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE users SET is_superuser = false WHERE is_superuser IS NULL")
    op.alter_column("users", "is_superuser", server_default=None)


def downgrade():
    op.drop_column("users", "is_superuser")
