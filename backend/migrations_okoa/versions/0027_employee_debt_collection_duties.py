"""Add employee-specific dashboard duties."""

from alembic import op
import sqlalchemy as sa


revision = "0027_debt_duties"
down_revision = "0026_debt_collection_module"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "debt_collection_duty_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("duty", sa.String(length=40), nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "duty", name="uq_debt_collection_user_duty"),
    )
    op.create_index(
        op.f("ix_debt_collection_duty_assignments_duty"),
        "debt_collection_duty_assignments",
        ["duty"],
        unique=False,
    )
    op.create_index(
        op.f("ix_debt_collection_duty_assignments_user_id"),
        "debt_collection_duty_assignments",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_debt_collection_duty_assignments_assigned_by"),
        "debt_collection_duty_assignments",
        ["assigned_by"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_debt_collection_duty_assignments_assigned_by"), table_name="debt_collection_duty_assignments")
    op.drop_index(op.f("ix_debt_collection_duty_assignments_user_id"), table_name="debt_collection_duty_assignments")
    op.drop_index(op.f("ix_debt_collection_duty_assignments_duty"), table_name="debt_collection_duty_assignments")
    op.drop_table("debt_collection_duty_assignments")