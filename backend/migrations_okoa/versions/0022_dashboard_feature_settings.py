"""Add role-scoped dashboard feature settings."""

from alembic import op
import sqlalchemy as sa


revision = "0022_dashboard_feature_settings"
down_revision = "0021_restore_otp_table"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_feature_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("feature", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role", "feature", name="uq_dashboard_feature_role"),
    )


def downgrade():
    op.drop_table("dashboard_feature_settings")