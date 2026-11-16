"""Add annual leave allocation and employee balance override tracking."""

from alembic import op
import sqlalchemy as sa


revision = "0030_leave_policy_entitlement"
down_revision = "0029_secure_email_otp_purpose"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    leave_policy_columns = {column["name"] for column in inspector.get_columns("leave_policies")}
    leave_balance_columns = {column["name"] for column in inspector.get_columns("leave_balances")}

    if "annual_entitlement_days" not in leave_policy_columns:
        op.add_column(
            "leave_policies",
            sa.Column("annual_entitlement_days", sa.Numeric(6, 2), nullable=True),
        )
    if "is_manual_override" not in leave_balance_columns:
        op.add_column(
            "leave_balances",
            sa.Column(
                "is_manual_override",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    op.execute(
        """
        UPDATE leave_policies
        SET annual_entitlement_days = COALESCE(
            (
                SELECT default_days_per_year
                FROM leave_types
                WHERE leave_types.id = leave_policies.leave_type_id
            ),
            0
        )
        """
    )
    op.alter_column(
        "leave_policies",
        "annual_entitlement_days",
        existing_type=sa.Numeric(6, 2),
        nullable=False,
    )


def downgrade():
    op.drop_column("leave_balances", "is_manual_override")
    op.drop_column("leave_policies", "annual_entitlement_days")
