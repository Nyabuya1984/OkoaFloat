"""Add scheduled agent tracking policy and manager overrides."""

from alembic import op
import sqlalchemy as sa


revision = "0037_scheduled_agent_tracking"
down_revision = "0036_location_sharing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_location_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Africa/Nairobi",
        ),
        sa.Column("days", sa.JSON(), nullable=False),
        sa.Column(
            "start_time",
            sa.String(length=5),
            nullable=False,
            server_default="08:00",
        ),
        sa.Column(
            "end_time",
            sa.String(length=5),
            nullable=False,
            server_default="17:00",
        ),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_agent_location_policy_updated_by",
        ),
    )
    op.create_table(
        "agent_location_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_agent_location_override_updated_by",
        ),
        sa.UniqueConstraint(
            "scope_type",
            "scope_id",
            name="uq_location_override_scope",
        ),
    )
    op.create_index(
        "ix_location_override_expiry",
        "agent_location_overrides",
        ["expires_at"],
    )


def downgrade():
    op.drop_index(
        "ix_location_override_expiry",
        table_name="agent_location_overrides",
    )
    op.drop_table("agent_location_overrides")
    op.drop_table("agent_location_policies")
