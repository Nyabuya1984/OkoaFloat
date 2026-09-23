"""Add extended employee identity and departments.

Revision ID: 0005_extended_user_identity
Revises: 0004_account_approval_state
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_extended_user_identity"
down_revision = "0004_account_approval_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column("users", sa.Column("employee_name", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("job_position_title", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("employer", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("profile_photo_url", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("contact_phone", sa.String(length=30), nullable=True))
    op.add_column("users", sa.Column("contact_email", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("address_line1", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("address_line2", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("postal_code", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        "fk_users_department_id", "users", "departments", ["department_id"], ["id"]
    )

    # Preserve existing employee identity while making the new fields usable.
    op.execute(
        "INSERT IGNORE INTO departments (name, created_at) "
        "SELECT DISTINCT TRIM(department), UTC_TIMESTAMP() FROM users "
        "WHERE department IS NOT NULL AND TRIM(department) <> ''"
    )
    op.execute(
        "UPDATE users u JOIN departments d ON LOWER(TRIM(u.department)) = LOWER(d.name) "
        "SET u.department_id = d.id WHERE u.department IS NOT NULL"
    )
    op.execute("UPDATE users SET employee_name = full_name WHERE employee_name IS NULL")
    op.execute("UPDATE users SET contact_phone = phone_number WHERE contact_phone IS NULL")
    op.execute("UPDATE users SET contact_email = email WHERE contact_email IS NULL")


def downgrade():
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    for column in (
        "postal_code", "country", "city", "address_line2", "address_line1",
        "contact_email", "contact_phone", "profile_photo_url", "department_id",
        "employer", "job_position_title", "employee_name",
    ):
        op.drop_column("users", column)
    op.drop_table("departments")
