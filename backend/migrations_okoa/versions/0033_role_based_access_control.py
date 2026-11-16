"""Create normalized role and permission tables."""

from alembic import op
import sqlalchemy as sa


revision = "0033_rbac"
down_revision = "0032_okoa_care_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
    )
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="CASCADE",
            name="fk_role_permissions_role",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="CASCADE",
            name="fk_role_permissions_permission",
        ),
        sa.UniqueConstraint(
            "role_id", "permission_id", "effect",
            name="uq_role_permission_effect",
        ),
        sa.CheckConstraint(
            "effect IN ('allow', 'deny')", name="ck_role_permission_effect"
        ),
    )
    op.create_index(
        "ix_role_permissions_role_effect",
        "role_permissions",
        ["role_id", "effect"],
    )
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_user_roles_user",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="RESTRICT",
            name="fk_user_roles_role",
        ),
        sa.UniqueConstraint("user_id", name="uq_user_single_role"),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])


def downgrade():
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index("ix_role_permissions_role_effect", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
