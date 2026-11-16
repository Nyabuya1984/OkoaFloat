"""Store super-admin department page selections."""

from alembic import op
import sqlalchemy as sa


revision = "0042_department_page_config"
down_revision = "0041_debt_imported_balance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "department_page_configurations",
        sa.Column(
            "department_id",
            sa.Integer(),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("department_page_configurations")
