"""Record whether a registered client is new or existing."""

from alembic import op
import sqlalchemy as sa


revision = "0039_client_registration_status"
down_revision = "0038_strict_reporting_hierarchy"
branch_labels = None
depends_on = None


def upgrade():
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("clients")
    }
    if "client_status" not in columns:
        op.add_column(
            "clients",
            sa.Column("client_status", sa.String(length=16), nullable=True),
        )


def downgrade():
    op.drop_column("clients", "client_status")
