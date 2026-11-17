from datetime import datetime, timedelta
from functools import wraps

from flask import g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import select
from sqlalchemy.orm import load_only

from app.extensions import db
from app.models import (
    AgentLocation,
    Department,
    DepartmentAssignmentHistory,
    Role,
    User,
    UserRole,
)
from app.utils.rbac import is_hr_admin, is_system_admin


ORGANIZATIONAL_ROLES = {
    "general_manager",
    "department_manager",
    "team_leader",
    "field_agent",
}
LOCATION_RETENTION_DAYS = 30
LOCATION_PING_INTERVAL_SECONDS = 60
ORGANIZATIONAL_ROLE_LEVELS = {
    "general_manager": 1,
    "department_manager": 2,
    "team_leader": 3,
    "field_agent": 4,
}


def _department_name(user):
    if user.department_record:
        return user.department_record.name
    return user.department or "Unassigned"


def get_active_assignment(user_id):
    return (
        DepartmentAssignmentHistory.query
        .filter_by(user_id=user_id, ended_at=None)
        .options(load_only(
            DepartmentAssignmentHistory.id,
            DepartmentAssignmentHistory.user_id,
            DepartmentAssignmentHistory.department_id,
            DepartmentAssignmentHistory.department_name,
            DepartmentAssignmentHistory.role_id,
            DepartmentAssignmentHistory.organizational_role_id,
            DepartmentAssignmentHistory.role_name,
            DepartmentAssignmentHistory.organizational_role,
            DepartmentAssignmentHistory.assigned_by_id,
            DepartmentAssignmentHistory.started_at,
            DepartmentAssignmentHistory.ended_at,
        ))
        .order_by(DepartmentAssignmentHistory.started_at.desc(), DepartmentAssignmentHistory.id.desc())
        .first()
    )


def has_active_group_leader(department_id):
    """Whether a department currently has an approved, active Group Leader."""
    if department_id is None:
        return False
    now = datetime.utcnow()
    return (
        DepartmentAssignmentHistory.query
        .join(User, User.id == DepartmentAssignmentHistory.user_id)
        .filter(
            DepartmentAssignmentHistory.department_id == department_id,
            DepartmentAssignmentHistory.organizational_role == "team_leader",
            DepartmentAssignmentHistory.ended_at.is_(None),
            DepartmentAssignmentHistory.started_at <= now,
            User.department_id == department_id,
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
            User.account_status == "approved",
        )
        .first()
        is not None
    )


def is_group_leader_substitute(user, department_id=None):
    """Allow a department manager GL duties only while that department has no active GL."""
    if (
        not user
        or not user.is_currently_active()
        or user.account_status != "approved"
    ):
        return False
    assignment = get_active_assignment(user.id)
    if (
        not assignment
        or assignment.organizational_role != "department_manager"
        or assignment.department_id is None
        or assignment.department_id != user.department_id
        or (
            department_id is not None
            and assignment.department_id != department_id
        )
    ):
        return False
    return not has_active_group_leader(assignment.department_id)


def effective_organizational_roles(user, assignment=None):
    """Return dashboard roles without changing the user's actual assignment."""
    assignment = assignment or get_active_assignment(user.id if user else None)
    if not assignment:
        return []
    roles = [assignment.organizational_role]
    if is_group_leader_substitute(user, assignment.department_id):
        roles.append("team_leader")
    return roles


def infer_organizational_role(title):
    normalized = (title or "").strip().lower()
    if "general manager" in normalized:
        return "general_manager"
    if "team leader" in normalized or "group leader" in normalized:
        return "team_leader"
    if "manager" in normalized:
        return "department_manager"
    return "field_agent"


def _organizational_role_record(name):
    role = Role.query.filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name, level=ORGANIZATIONAL_ROLE_LEVELS[name])
        db.session.add(role)
        db.session.flush()
    elif role.level != ORGANIZATIONAL_ROLE_LEVELS[name]:
        role.level = ORGANIZATIONAL_ROLE_LEVELS[name]
    return role


def update_assignment_role(user, role_name, organizational_role=None):
    assignment = get_active_assignment(user.id)
    organizational_role = (
        organizational_role
        or (
            assignment.organizational_role
            if assignment and assignment.organizational_role in ORGANIZATIONAL_ROLES
            else infer_organizational_role(user.job_position_title)
        )
    )
    organizational_role_record = _organizational_role_record(organizational_role)
    role = Role.query.filter_by(name=role_name).one_or_none() if role_name else None
    if assignment is None:
        assignment = DepartmentAssignmentHistory(
            user_id=user.id,
            department_id=user.department_id,
            department_name=_department_name(user),
            organizational_role=organizational_role,
            organizational_role_id=organizational_role_record.id,
            started_at=datetime.utcnow(),
        )
        db.session.add(assignment)
    assignment.organizational_role = organizational_role
    assignment.organizational_role_id = organizational_role_record.id
    assignment.role_id = role.id if role else None
    assignment.role_name = role_name
    return assignment


def transition_department(user, department, role_name, organizational_role, actor):
    """Close the old assignment and replace its single operational role atomically."""
    if organizational_role not in ORGANIZATIONAL_ROLES:
        raise ValueError("organizational_role must be one of the supported hierarchy roles")
    if department is None and organizational_role != "general_manager":
        raise ValueError(
            f"{organizational_role.replace('_', ' ').title()} must belong to a department"
        )
    if organizational_role != "general_manager" and department.id is None:
        raise ValueError("Every non-General Manager must belong to a department")

    role = None
    organizational_role_record = _organizational_role_record(organizational_role)
    if role_name:
        role = Role.query.filter_by(name=role_name).one_or_none()
        if role is None:
            raise ValueError("department_role is not a configured operational role")
        dept = department.name.lower() if department else ""
        expected = {
            "sales": "sales" in dept or "marketing" in dept,
            "debt_collection": "debt" in dept,
            "customer_care": "care" in dept,
        }
        if role_name not in expected or not expected[role_name]:
            raise ValueError("department_role does not match the selected department")
    requires_operational_role = bool(
        department
        and department.name.casefold()
        in {"sales & marketing", "debt collection", "customer care"}
    )
    if organizational_role == "field_agent" and role is None and requires_operational_role:
        raise ValueError("Field agents must have one operational department role")
    validate_assignment_capacity(
        user.id,
        department.id if department else None,
        organizational_role,
    )

    now = datetime.utcnow()
    # Lock the employee row so concurrent transfers cannot create parallel active assignments.
    db.session.execute(select(User.id).where(User.id == user.id).with_for_update())
    DepartmentAssignmentHistory.query.filter_by(
        user_id=user.id, ended_at=None
    ).update({"ended_at": now}, synchronize_session=False)

    user.department_id = department.id if department else None
    user.department = department.name if department else "All"
    user.job_position_title = organizational_role.replace("_", " ").title()

    role_assignment = UserRole.query.filter_by(user_id=user.id).one_or_none()
    if role is None:
        if role_assignment:
            db.session.delete(role_assignment)
    elif role_assignment:
        role_assignment.role_id = role.id
    else:
        db.session.add(UserRole(user_id=user.id, role_id=role.id))

    assignment = DepartmentAssignmentHistory(
        user_id=user.id,
        department_id=department.id if department else None,
        department_name=department.name if department else "All",
        role_id=role.id if role else None,
        role_name=role.name if role else None,
        organizational_role=organizational_role,
        organizational_role_id=organizational_role_record.id,
        assigned_by_id=actor.id if actor else None,
        started_at=now,
    )
    db.session.add(assignment)
    return assignment


def may_assign_organizational_role(actor, organizational_role, department_id):
    if (
        not actor
        or not actor.is_currently_active()
        or actor.account_status != "approved"
        or organizational_role not in ORGANIZATIONAL_ROLES
    ):
        return False
    if organizational_role == "general_manager":
        return is_system_admin(actor)
    if is_system_admin(actor) or is_hr_admin(actor):
        return True

    assignment = get_active_assignment(actor.id)
    if not assignment:
        return False
    if assignment.organizational_role == "general_manager":
        return True
    if (
        assignment.department_id != department_id
        or assignment.organizational_role not in {"department_manager", "team_leader"}
    ):
        return False
    return (
        assignment.organizational_role == "department_manager"
        and organizational_role in {"team_leader", "field_agent"}
    ) or (
        assignment.organizational_role == "team_leader"
        and organizational_role == "field_agent"
    )


def _authorized_user():
    verify_jwt_in_request()
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, user_id)
    if not user or not user.is_currently_active() or user.account_status != "approved":
        return None
    return user


def require_active_department_write(department_key):
    """Require the user to be active in the correct department, even when no
    departmental role record was saved for that assignment yet."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.method == "OPTIONS":
                return None
            user = _authorized_user()
            if user is None:
                return jsonify({
                    "data": None,
                    "error": {
                        "code": "ACTIVE_DEPARTMENT_REQUIRED",
                        "message": "This action is only available in your active department.",
                    },
                }), 403
            assignment = get_active_assignment(user.id)
            matches = {
                "sales": lambda name: "sales" in name.lower() or "marketing" in name.lower(),
                "debt_collection": lambda name: "debt" in name.lower(),
                "customer_care": lambda name: "care" in name.lower(),
            }
            department_name = ((assignment.department_name if assignment else "") or (user.department or "")).strip()
            if not department_name or not matches[department_key](department_name):
                return jsonify({
                    "data": None,
                    "error": {
                        "code": "ACTIVE_DEPARTMENT_REQUIRED",
                        "message": "This action is only available in your active department.",
                    },
                }), 403
            if assignment is not None and assignment.department_id is not None and user.department_id is not None:
                if assignment.department_id != user.department_id and not matches[department_key](user.department or ""):
                    return jsonify({
                        "data": None,
                        "error": {
                            "code": "ACTIVE_DEPARTMENT_REQUIRED",
                            "message": "This action is only available in your active department.",
                        },
                    }), 403
            g.department_assignment = assignment
            g.department_user = user
            return view(*args, **kwargs)
        return wrapped
    return decorator


def can_perform_actions(user_id, target_dept_id):
    """Allow writes only for the current active department assignment."""
    user = db.session.get(User, user_id)
    if (
        not user
        or not user.is_currently_active()
        or user.account_status != "approved"
        or user.department_id != target_dept_id
    ):
        return False
    assignment = get_active_assignment(user.id)
    if not assignment or assignment.department_id != target_dept_id:
        return False
    return assignment.ended_at is None and assignment.started_at <= datetime.utcnow()


def can_view_history(user_id, target_dept_id):
    """Allow current department access or departments recorded in assignment history."""
    user = db.session.get(User, user_id)
    if not user or not user.is_currently_active() or user.account_status != "approved":
        return False
    assignment = get_active_assignment(user.id)
    if assignment and assignment.organizational_role == "general_manager":
        return True
    if is_system_admin(user) or is_hr_admin(user):
        return True
    if user.department_id == target_dept_id:
        return True
    if (
        assignment
        and assignment.organizational_role == "department_manager"
        and assignment.department_id == target_dept_id
    ):
        return True
    return DepartmentAssignmentHistory.query.filter_by(
        user_id=user.id,
        department_id=target_dept_id,
    ).first() is not None


def can_manage_locations(user, target_department_id=None):
    if is_system_admin(user) or is_hr_admin(user):
        return True
    assignment = get_active_assignment(user.id) if user else None
    if assignment is None:
        return False
    if assignment.organizational_role == "general_manager":
        return True
    if assignment.organizational_role in {"department_manager", "team_leader"}:
        return (
            target_department_id is None
            or assignment.department_id == target_department_id
        )
    return False


def may_manage_transfers(actor, target):
    if is_system_admin(actor) or is_hr_admin(actor):
        return True
    actor_assignment = get_active_assignment(actor.id) if actor else None
    target_assignment = get_active_assignment(target.id) if target else None
    if actor_assignment is None:
        return False
    if actor_assignment.organizational_role == "general_manager":
        return True
    within_scope = bool(
        actor_assignment.organizational_role in {"department_manager", "team_leader"}
        and target_assignment
        and target_assignment.department_id == actor_assignment.department_id
        and _position_rank(actor_assignment.organizational_role)
        > _position_rank(target_assignment.organizational_role)
    )
    if not within_scope:
        return False
    return (
        actor_assignment.organizational_role != "team_leader"
        or target.manager_id == actor.id
    )


def _position_rank(position):
    return {
        "general_manager": 5,
        "department_manager": 4,
        "team_leader": 3,
        "field_agent": 1,
    }.get(position, 0)


def validate_assignment_capacity(user_id, department_id, organizational_role):
    if organizational_role not in {
        "general_manager",
        "department_manager",
        "team_leader",
        "field_agent",
    }:
        raise ValueError("Only General Manager, Department Manager, Team Leader, and Employee assignments are supported")
    if organizational_role != "general_manager" and department_id is None:
        raise ValueError(
            f"{organizational_role.replace('_', ' ').title()} must belong to a department"
        )
    if organizational_role == "general_manager":
        conflict = (
            DepartmentAssignmentHistory.query
            .filter(
                DepartmentAssignmentHistory.ended_at.is_(None),
                DepartmentAssignmentHistory.organizational_role == "general_manager",
                DepartmentAssignmentHistory.user_id != user_id,
            )
            .first()
        )
        if conflict:
            raise ValueError("A General Manager is already assigned across the system.")
        return
    if organizational_role not in {"department_manager", "team_leader"}:
        return
    conflict = (
        DepartmentAssignmentHistory.query
        .filter(
            DepartmentAssignmentHistory.ended_at.is_(None),
            DepartmentAssignmentHistory.organizational_role == organizational_role,
            DepartmentAssignmentHistory.department_id == department_id,
            DepartmentAssignmentHistory.user_id != user_id,
        )
        .first()
    )
    if conflict:
        label = organizational_role.replace("_", " ").title()
        department = db.session.get(Department, department_id)
        department_name = department.name if department else str(department_id)
        raise ValueError(f"Department {department_name} already has a {label} assigned.")


def assignment_capacity_conflict_message(error, department, organizational_role):
    error_text = str(error).lower()
    if (
        "uq_active_general_manager" in error_text
        or "active_general_manager_key" in error_text
    ):
        return "A General Manager is already assigned across the system."
    if (
        organizational_role == "department_manager"
        and (
            "uq_active_department_manager_per_department" in error_text
            or "active_department_manager_key" in error_text
        )
    ):
        return f"Department {department.name} already has a Department Manager."
    if (
        organizational_role == "team_leader"
        and (
            "uq_active_team_leader_per_department" in error_text
            or "active_team_leader_key" in error_text
        )
    ):
        return f"Department {department.name} already has a Team Leader."
    return None


def validate_reporting_manager(target, department, organizational_role, requested_manager_id, actor):
    """Resolve and validate the next manager while preserving the reporting hierarchy."""
    if organizational_role not in {
        "general_manager",
        "department_manager",
        "team_leader",
        "field_agent",
    }:
        raise ValueError("Only General Manager, Department Manager, Team Leader, and Employee assignments are supported")
    if department is None and organizational_role != "general_manager":
        raise ValueError(
            f"{organizational_role.replace('_', ' ').title()} must belong to a department"
        )
    validate_assignment_capacity(
        target.id,
        department.id if department else None,
        organizational_role,
    )
    if organizational_role == "general_manager":
        if requested_manager_id:
            raise ValueError("A General Manager cannot have a reporting manager")
        return None

    manager = None
    if requested_manager_id not in (None, ""):
        try:
            manager_id = int(requested_manager_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("manager_id must be an employee ID") from exc
        if manager_id == target.id:
            raise ValueError("An employee cannot report to themselves")
        manager = db.session.get(User, manager_id)
        if not manager or not manager.is_currently_active() or manager.account_status != "approved":
            raise ValueError("The selected manager must be active and approved")
    else:
        current_manager = db.session.get(User, target.manager_id) if target.manager_id else None
        if current_manager and current_manager.department_id == department.id:
            manager = current_manager
        elif actor and actor.department_id == department.id:
            manager = actor

    manager_assignment = get_active_assignment(manager.id) if manager else None
    if not manager_assignment:
        raise ValueError("Select an active manager in the reporting hierarchy")
    has_department_manager = DepartmentAssignmentHistory.query.filter_by(
        department_id=department.id,
        organizational_role="department_manager",
        ended_at=None,
    ).filter(DepartmentAssignmentHistory.user_id != target.id).first() is not None
    has_team_leader = DepartmentAssignmentHistory.query.filter_by(
        department_id=department.id,
        organizational_role="team_leader",
        ended_at=None,
    ).filter(DepartmentAssignmentHistory.user_id != target.id).first() is not None
    direct_general_manager = (
        manager_assignment.organizational_role == "general_manager"
        and (
            (organizational_role == "team_leader" and not has_department_manager)
            or (
                organizational_role == "field_agent"
                and not has_department_manager
                and not has_team_leader
            )
        )
    )
    team_leader_reports_to_general_manager = False
    if (
        organizational_role == "field_agent"
        and manager_assignment.organizational_role == "team_leader"
        and not has_department_manager
        and manager.manager_id
    ):
        manager_parent_assignment = get_active_assignment(manager.manager_id)
        team_leader_reports_to_general_manager = bool(
            manager_parent_assignment
            and manager_parent_assignment.organizational_role == "general_manager"
        )
    valid_reporting_roles = {
        "department_manager": {"general_manager"},
        "team_leader": {"department_manager"},
        "field_agent": {"team_leader"},
    }
    if (
        manager_assignment.organizational_role
        not in valid_reporting_roles[organizational_role]
        and not direct_general_manager
    ):
        raise ValueError("The selected manager is not the correct level in the reporting hierarchy")
    if organizational_role != "department_manager" and not direct_general_manager:
        if manager_assignment.department_id != department.id:
            raise ValueError(
                "Team leaders and employees must report within their department"
            )
    elif manager.department_id != manager_assignment.department_id:
        raise ValueError(
            "Department Managers must have a valid active organizational assignment"
        )
    if manager_assignment.department_id != manager.department_id:
        raise ValueError(
            "The reporting manager's department does not match their active assignment"
        )
    if (
        organizational_role == "department_manager"
        and manager.manager_id is not None
    ):
        raise ValueError("The General Manager cannot report to another user")
    if (
        organizational_role == "team_leader"
        and manager_assignment.department_id != department.id
        and not direct_general_manager
    ):
        raise ValueError("Team Leaders must report to their Department Manager in the same department")
    if organizational_role in {"team_leader", "field_agent"}:
        if direct_general_manager:
            general_manager, general_manager_assignment = _validate_assigned_manager(
                manager.id,
                "general_manager",
            )
            department_assignment = None
        elif team_leader_reports_to_general_manager:
            general_manager, general_manager_assignment = _validate_assigned_manager(
                manager.manager_id,
                "general_manager",
            )
            department_assignment = None
        elif organizational_role == "team_leader":
            department_manager, department_assignment = manager, manager_assignment
            general_manager, general_manager_assignment = _validate_assigned_manager(
                department_manager.manager_id,
                "general_manager",
            )
        else:
            department_manager, department_assignment = _validate_assigned_manager(
                manager.manager_id,
                "department_manager",
                department.id,
            )
            general_manager, general_manager_assignment = _validate_assigned_manager(
                department_manager.manager_id,
                "general_manager",
            )
        if (
            general_manager.manager_id is not None
            or general_manager_assignment.organizational_role != "general_manager"
        ):
            raise ValueError("The General Manager cannot report to another user")
        if (
            organizational_role == "field_agent"
            and manager_assignment.organizational_role != "team_leader"
            and not direct_general_manager
        ):
            raise ValueError("Employees must report to a Team Leader")
        if (
            department_assignment
            and department_assignment.department_id != department.id
        ):
            raise ValueError("The Department Manager must belong to the same department")
    if _position_rank(manager_assignment.organizational_role) <= _position_rank(organizational_role):
        raise ValueError("The reporting manager must be higher in the organizational hierarchy")
    return manager.id


def _validate_assigned_manager(user_id, expected_role, department_id=None):
    manager = db.session.get(User, user_id) if user_id else None
    if (
        not manager
        or not manager.is_currently_active()
        or manager.account_status != "approved"
    ):
        raise ValueError(
            f"A valid {expected_role.replace('_', ' ').title()} is required in the reporting chain"
        )
    assignment = get_active_assignment(manager.id)
    if (
        not assignment
        or assignment.organizational_role != expected_role
        or (
            expected_role != "general_manager"
            and assignment.department_id != manager.department_id
        )
        or (
            department_id is not None
            and manager.department_id != department_id
        )
    ):
        raise ValueError(
            f"The reporting chain must include an active {expected_role.replace('_', ' ').title()}"
        )
    return manager, assignment


def cleanup_expired_locations():
    cutoff = datetime.utcnow() - timedelta(days=LOCATION_RETENTION_DAYS)
    return AgentLocation.query.filter(AgentLocation.recorded_at < cutoff).delete(
        synchronize_session=False
    )
