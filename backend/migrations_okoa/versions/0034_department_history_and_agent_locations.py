"""Add department assignment history, client registration, and agent locations."""

from alembic import op
import sqlalchemy as sa


revision = "0034_org_tracking"
down_revision = "0033_rbac"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "roles",
        sa.Column("level", sa.Integer(), nullable=False, server_default="4"),
    )
    op.execute(
        """
        INSERT INTO roles (name, level)
        SELECT hierarchy.name, hierarchy.level
        FROM (
            SELECT 'general_manager' AS name, 1 AS level
            UNION ALL SELECT 'hr_manager', 2
            UNION ALL SELECT 'department_manager', 2
            UNION ALL SELECT 'team_leader', 3
            UNION ALL SELECT 'field_agent', 4
        ) AS hierarchy
        LEFT JOIN roles existing ON existing.name = hierarchy.name
        WHERE existing.id IS NULL
        """
    )
    op.execute(
        """
        UPDATE roles
        SET level = CASE name
            WHEN 'general_manager' THEN 1
            WHEN 'hr_manager' THEN 2
            WHEN 'department_manager' THEN 2
            WHEN 'team_leader' THEN 3
            WHEN 'field_agent' THEN 4
            ELSE level
        END
        WHERE name IN (
            'general_manager', 'hr_manager', 'department_manager',
            'team_leader', 'field_agent'
        )
        """
    )
    op.create_table(
        "department_assignment_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("department_name", sa.String(120), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.Column("organizational_role_id", sa.Integer(), nullable=True),
        sa.Column("role_name", sa.String(64), nullable=True),
        sa.Column(
            "organizational_role",
            sa.String(32),
            nullable=False,
            server_default="field_agent",
        ),
        sa.Column("assigned_by_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_assignment_history_user",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], ondelete="SET NULL",
            name="fk_assignment_history_department",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="SET NULL",
            name="fk_assignment_history_role",
        ),
        sa.ForeignKeyConstraint(
            ["organizational_role_id"], ["roles.id"], ondelete="SET NULL",
            name="fk_assignment_history_organizational_role",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"], ["users.id"], ondelete="SET NULL",
            name="fk_assignment_history_assigned_by",
        ),
    )
    op.create_index(
        "ix_assignment_history_user_active",
        "department_assignment_history",
        ["user_id", "ended_at"],
    )
    op.create_index(
        "ix_assignment_history_department",
        "department_assignment_history",
        ["department_id", "started_at"],
    )
    op.execute(
        """
        INSERT INTO department_assignment_history
            (user_id, department_id, department_name, role_id, role_name,
             organizational_role_id,
             organizational_role, assigned_by_id, started_at, ended_at)
        SELECT
            u.id,
            u.department_id,
            COALESCE(d.name, NULLIF(u.department, ''), 'Unassigned'),
            r.id,
            r.name,
            org_role.id,
            CASE
                WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%general manager%'
                    THEN 'general_manager'
                WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%hr manager%'
                    THEN 'hr_manager'
                WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%manager%'
                    THEN 'department_manager'
                WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%team leader%'
                    THEN 'team_leader'
                ELSE 'field_agent'
            END,
            NULL,
            COALESCE(u.created_at, CURRENT_TIMESTAMP),
            CASE
                WHEN u.is_active = 1 AND u.is_archived = 0 AND u.is_deleted = 0
                    THEN NULL
                ELSE CURRENT_TIMESTAMP
            END
        FROM users u
        LEFT JOIN departments d ON d.id = u.department_id
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        LEFT JOIN roles org_role ON org_role.name = CASE
            WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%general manager%'
                THEN 'general_manager'
            WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%hr manager%'
                THEN 'hr_manager'
            WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%manager%'
                THEN 'department_manager'
            WHEN LOWER(COALESCE(u.job_position_title, '')) LIKE '%team leader%'
                THEN 'team_leader'
            ELSE 'field_agent'
        END
        """
    )

    op.create_table(
        "agent_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_agent_locations_user",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], ondelete="SET NULL",
            name="fk_agent_locations_department",
        ),
    )
    op.create_index(
        "ix_agent_locations_user_recorded",
        "agent_locations",
        ["user_id", "recorded_at"],
    )
    op.create_index(
        "ix_agent_locations_recorded_at", "agent_locations", ["recorded_at"]
    )

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone_number", sa.String(40), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("client_type", sa.String(40), nullable=False),
        sa.Column("business_name", sa.String(160), nullable=True),
        sa.Column("business_location", sa.String(255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("location_accuracy_meters", sa.Float(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], ondelete="SET NULL",
            name="fk_clients_department",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="SET NULL",
            name="fk_clients_created_by",
        ),
    )
    op.create_index("ix_clients_phone_number", "clients", ["phone_number"])
    op.create_index(
        "ix_clients_department_created", "clients", ["department_id", "created_at"]
    )


def downgrade():
    op.drop_index("ix_clients_department_created", table_name="clients")
    op.drop_index("ix_clients_phone_number", table_name="clients")
    op.drop_table("clients")
    op.drop_index("ix_agent_locations_recorded_at", table_name="agent_locations")
    op.drop_index("ix_agent_locations_user_recorded", table_name="agent_locations")
    op.drop_table("agent_locations")
    op.drop_index(
        "ix_assignment_history_department", table_name="department_assignment_history"
    )
    op.drop_index(
        "ix_assignment_history_user_active", table_name="department_assignment_history"
    )
    op.drop_table("department_assignment_history")
    op.execute(
        "DELETE FROM roles WHERE name IN "
        "('general_manager', 'hr_manager', 'department_manager', 'team_leader', 'field_agent')"
    )
    op.drop_column("roles", "level")
