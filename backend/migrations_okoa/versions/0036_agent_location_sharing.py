"""Store employee location-sharing opt-in state."""

from alembic import op
import sqlalchemy as sa


revision = "0036_location_sharing"
down_revision = "0035_simulated_locations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_location_sharing",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_agent_location_sharing_user",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade():
    op.drop_table("agent_location_sharing")
