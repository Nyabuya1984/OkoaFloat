"""Add user lifecycle state and audit fields.

Revision ID: 0013_add_user_lifecycle_fields
Revises: 0012_add_handover_report_tables
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_add_user_lifecycle_fields"
down_revision = "0012_add_handover_report_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("deactivated_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("deactivation_reason", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("archived_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("archive_reason", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("deleted_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("delete_reason", sa.String(length=500), nullable=True))
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_users_is_archived", "users", ["is_archived"])
    op.create_index("ix_users_is_deleted", "users", ["is_deleted"])
    op.create_foreign_key(
        "fk_users_deactivated_by_users",
        "users",
        "users",
        ["deactivated_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_users_archived_by_users",
        "users",
        "users",
        ["archived_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_users_deleted_by_users",
        "users",
        "users",
        ["deleted_by"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_archived_by_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_deactivated_by_users", "users", type_="foreignkey")
    op.drop_index("ix_users_is_deleted", table_name="users")
    op.drop_index("ix_users_is_archived", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_column("users", "delete_reason")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "archive_reason")
    op.drop_column("users", "archived_by")
    op.drop_column("users", "archived_at")
    op.drop_column("users", "deactivation_reason")
    op.drop_column("users", "deactivated_by")
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "is_deleted")
    op.drop_column("users", "is_archived")
