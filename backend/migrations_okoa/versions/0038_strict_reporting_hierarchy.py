"""Enforce hierarchy capacity and record sequential leave approvals."""

from alembic import op
import sqlalchemy as sa


revision = "0038_strict_reporting_hierarchy"
down_revision = "0037_scheduled_agent_tracking"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    hierarchy_columns = {
        column["name"]
        for column in inspector.get_columns("department_assignment_history")
    }
    for column_name, expression in (
        (
            "active_general_manager_key",
            "CASE WHEN ended_at IS NULL AND organizational_role = "
            "'general_manager' THEN 1 ELSE NULL END",
        ),
        (
            "active_department_manager_key",
            "CASE WHEN ended_at IS NULL AND organizational_role = "
            "'department_manager' THEN department_id ELSE NULL END",
        ),
        (
            "active_team_leader_key",
            "CASE WHEN ended_at IS NULL AND organizational_role = "
            "'team_leader' THEN department_id ELSE NULL END",
        ),
    ):
        if column_name not in hierarchy_columns:
            op.add_column(
                "department_assignment_history",
                sa.Column(
                    column_name,
                    sa.Integer(),
                    sa.Computed(expression, persisted=False),
                    nullable=True,
                ),
            ),

    hierarchy_unique_constraints = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints(
            "department_assignment_history"
        )
    }
    for constraint_name, column_name in (
        ("uq_active_general_manager", "active_general_manager_key"),
        (
            "uq_active_department_manager_per_department",
            "active_department_manager_key",
        ),
        ("uq_active_team_leader_per_department", "active_team_leader_key"),
    ):
        if constraint_name not in hierarchy_unique_constraints:
            op.create_unique_constraint(
                constraint_name,
                "department_assignment_history",
                [column_name],
            )

    if not inspector.has_table("leave_approval_steps"):
        op.create_table(
            "leave_approval_steps",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("leave_request_id", sa.Integer(), nullable=False),
            sa.Column("stage_role", sa.String(length=32), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("decision", sa.String(length=20), nullable=False),
            sa.Column("decision_comment", sa.Text(), nullable=True),
            sa.Column("signature", sa.String(length=160), nullable=True),
            sa.Column(
                "decided_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["leave_request_id"],
                ["leave_requests.id"],
                ondelete="CASCADE",
                name="fk_leave_approval_step_request",
            ),
            sa.ForeignKeyConstraint(
                ["actor_id"],
                ["users.id"],
                ondelete="SET NULL",
                name="fk_leave_approval_step_actor",
            ),
            sa.UniqueConstraint(
                "leave_request_id",
                "stage_role",
                name="uq_leave_approval_request_stage",
            ),
        )
        inspector = sa.inspect(op.get_bind())

    if "ix_leave_approval_actor_decided" not in {
        index["name"] for index in inspector.get_indexes("leave_approval_steps")
    }:
        op.create_index(
            "ix_leave_approval_actor_decided",
            "leave_approval_steps",
            ["actor_id", "decided_at"],
        )

    op.execute(
        """
        UPDATE leave_balances AS lb
        JOIN (
            SELECT lr.user_id, lr.leave_type_id,
                   YEAR(lr.start_date) AS leave_year,
                   SUM(lr.days_requested) AS days_to_restore
            FROM leave_requests AS lr
            JOIN leave_types AS leave_type
              ON leave_type.id = lr.leave_type_id
            WHERE lr.workflow_state = 'hr_verification'
              AND lr.status = 'approved'
              AND UPPER(leave_type.code) != 'UNPAID'
            GROUP BY lr.user_id, lr.leave_type_id, YEAR(lr.start_date)
        ) AS legacy_request
          ON legacy_request.user_id = lb.user_id
         AND legacy_request.leave_type_id = lb.leave_type_id
         AND legacy_request.leave_year = lb.year
        SET lb.used_days = GREATEST(
                0, lb.used_days - legacy_request.days_to_restore
            ),
            lb.pending_days = lb.pending_days
                + legacy_request.days_to_restore
        """
    )
    op.execute(
        "UPDATE leave_requests SET workflow_state = 'team_leader_pending' "
        "WHERE workflow_state IN ('supervisor_pending', 'hr_verification') "
        "AND status IN ('pending', 'approved')"
    )
    op.execute(
        "UPDATE leave_requests SET status = 'pending', decided_at = NULL "
        "WHERE workflow_state = 'team_leader_pending' AND status = 'approved'"
    )


def downgrade():
    op.execute(
        "UPDATE leave_requests SET workflow_state = 'supervisor_pending' "
        "WHERE workflow_state = 'team_leader_pending'"
    )
    op.drop_index(
        "ix_leave_approval_actor_decided",
        table_name="leave_approval_steps",
    )
    op.drop_table("leave_approval_steps")
    op.drop_constraint(
        "uq_active_team_leader_per_department",
        "department_assignment_history",
        type_="unique",
    )
    op.drop_constraint(
        "uq_active_department_manager_per_department",
        "department_assignment_history",
        type_="unique",
    )
    op.drop_constraint(
        "uq_active_general_manager",
        "department_assignment_history",
        type_="unique",
    )
    op.drop_column("department_assignment_history", "active_team_leader_key")
    op.drop_column("department_assignment_history", "active_department_manager_key")
    op.drop_column("department_assignment_history", "active_general_manager_key")
