"""Mark synthetic agent location records as simulated."""

from alembic import op
import sqlalchemy as sa


revision = "0035_simulated_locations"
down_revision = "0034_org_tracking"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_locations",
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("agent_locations", "is_simulated")
