"""Move legacy Operations users into Customer Care and normalize General Manager scope."""

from sqlalchemy import func, or_

from app import create_app
from app.extensions import db
from app.models import Department, DepartmentAssignmentHistory, Role, User
from app.utils.organization import (
    get_active_assignment,
    transition_department,
    validate_reporting_manager,
)


def normalize_departments():
    app = create_app()
    with app.app_context():
        try:
            customer_care = Department.query.filter_by(name="Customer Care").one_or_none()
            if customer_care is None:
                raise RuntimeError("Customer Care department must exist before migration.")

            care_role = Role.query.filter_by(name="customer_care").one_or_none()
            if care_role is None:
                raise RuntimeError("Seed RBAC roles before migrating departments.")

            active_team_leaders = [
                assignment
                for assignment in DepartmentAssignmentHistory.query.filter_by(
                    department_id=customer_care.id,
                    organizational_role="team_leader",
                    ended_at=None,
                ).all()
                if assignment.user and assignment.user.is_currently_active()
            ]
            if len(active_team_leaders) != 1:
                raise RuntimeError(
                    "Customer Care must have exactly one active Team Leader before migration."
                )
            team_leader = active_team_leaders[0].user

            active_general_managers = DepartmentAssignmentHistory.query.filter_by(
                organizational_role="general_manager",
                ended_at=None,
            ).all()
            if len(active_general_managers) != 1:
                raise RuntimeError(
                    "The system must have exactly one active General Manager before migration."
                )
            general_manager = active_general_managers[0].user
            admin = User.query.filter_by(is_superuser=True, is_active=True).order_by(User.id).first()
            if admin is None:
                raise RuntimeError("An active system administrator is required.")

            operations = Department.query.filter(
                func.lower(Department.name) == "operations"
            ).one_or_none()
            legacy_users_query = User.query.filter(
                func.lower(User.department) == "operations"
            )
            if operations:
                legacy_users_query = User.query.filter(
                    or_(
                        User.department_id == operations.id,
                        func.lower(User.department) == "operations",
                    )
                )
            legacy_users = legacy_users_query.order_by(User.id).all()

            gm_assignment = get_active_assignment(general_manager.id)
            if (
                general_manager.department != "All"
                or general_manager.department_id is not None
                or general_manager.manager_id is not None
                or not gm_assignment
                or gm_assignment.department_name != "All"
                or gm_assignment.department_id is not None
            ):
                transition_department(
                    general_manager,
                    None,
                    None,
                    "general_manager",
                    admin,
                )
                general_manager.manager_id = None

            for user in legacy_users:
                assignment = get_active_assignment(user.id)
                if assignment and assignment.organizational_role != "field_agent":
                    raise RuntimeError(
                        f"Refusing to move {user.full_name}: their active role is "
                        f"{assignment.organizational_role}."
                    )
                validate_reporting_manager(
                    user,
                    customer_care,
                    "field_agent",
                    team_leader.id,
                    admin,
                )
                transition_department(
                    user,
                    customer_care,
                    "customer_care",
                    "field_agent",
                    admin,
                )
                user.manager_id = team_leader.id

            if operations:
                if User.query.filter_by(department_id=operations.id).count():
                    raise RuntimeError("Operations still has users assigned.")
                db.session.delete(operations)

            db.session.commit()
            print(
                f"Normalized {len(legacy_users)} Operations user(s); "
                "General Manager department is All."
            )
        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    normalize_departments()
