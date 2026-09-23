"""Backfill normalized employee identity for existing users.

Revision ID: 0006_backfill_employee_identity
Revises: 0005_extended_user_identity
"""
from alembic import op


revision = "0006_backfill_employee_identity"
down_revision = "0005_extended_user_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT IGNORE INTO departments (name, created_at) "
        "SELECT DISTINCT TRIM(department), UTC_TIMESTAMP() FROM users "
        "WHERE department IS NOT NULL AND TRIM(department) <> ''"
    )
    op.execute(
        "UPDATE users u JOIN departments d ON LOWER(TRIM(u.department)) = LOWER(d.name) "
        "SET u.department_id = d.id "
        "WHERE u.department IS NOT NULL AND u.department_id IS NULL"
    )
    op.execute("UPDATE users SET employee_name = full_name WHERE employee_name IS NULL")
    op.execute("UPDATE users SET contact_phone = phone_number WHERE contact_phone IS NULL")
    op.execute("UPDATE users SET contact_email = email WHERE contact_email IS NULL")


def downgrade():
    # Identity values are intentionally retained during downgrade.
    pass
