import json
import math
import re
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import (
    AgentLocation,
    AgentLocationOverride,
    AgentLocationPolicy,
    AgentLocationSharing,
    Client,
    Department,
    DepartmentAssignmentHistory,
    Role,
    SalesDailyReport,
    User,
    UserRole,
)
from app.utils.organization import (
    LOCATION_PING_INTERVAL_SECONDS,
    LOCATION_RETENTION_DAYS,
    can_manage_locations,
    can_perform_actions,
    can_view_history,
    cleanup_expired_locations,
    get_active_assignment,
    effective_organizational_roles,
    is_group_leader_substitute,
    assignment_capacity_conflict_message,
    may_manage_transfers,
    transition_department,
    validate_reporting_manager,
)
from app.utils.location_tracking import (
    DEFAULT_TIMEZONE,
    WEEKDAY_NAMES,
    location_tracking_policy,
    manager_location_scope,
    next_schedule_boundary,
    policy_data,
    schedule_is_active,
    tracking_state_for_agent,
    tracking_state_for_scope,
    tracking_states_for_agents,
)
from app.utils.rbac import is_hr_admin, is_system_admin


organization_bp = Blueprint("organization", __name__, url_prefix="/api/organization")
reports_bp = Blueprint("organization_reports", __name__, url_prefix="/api/reports")
organization_compat_bp = Blueprint("organization_compat", __name__)
ACTIVE_FIELD_VISIT_MAX_HOURS = 8
ORG_POSITIONS = {
    "general_manager",
    "department_manager",
    "team_leader",
    "field_agent",
}
CLIENT_TYPES = {"agent", "sub_agent", "individual", "business"}


def _error(message, status=400, code="VALIDATION_ERROR"):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


def _actor():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _valid_coordinate(value, lower, upper):
    if isinstance(value, bool):
        return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    return coordinate if math.isfinite(coordinate) and lower <= coordinate <= upper else None


def _valid_accuracy(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        accuracy = float(value)
    except (TypeError, ValueError):
        return None
    return accuracy if math.isfinite(accuracy) and 0 <= accuracy <= 100000 else None


def _active_field_agent(user):
    if not user or not user.is_currently_active() or user.account_status != "approved":
        return None
    assignment = get_active_assignment(user.id)
    if (
        assignment
        and assignment.organizational_role == "field_agent"
        and assignment.department_id == user.department_id
        and assignment.role_id
        and _assignment_role_matches(user, assignment.role_name)
    ):
        return assignment
    return None


def _normalized_department_name(value):
    return " ".join(
        (value or "").casefold().replace("&", " and ").replace("-", " ").split()
    )


def _assignment_role_matches(user, role_name):
    assignment = get_active_assignment(user.id)
    user_role = UserRole.query.filter_by(user_id=user.id).one_or_none()
    role = db.session.get(Role, user_role.role_id) if user_role else None
    return bool(
        assignment
        and assignment.ended_at is None
        and assignment.department_id == user.department_id
        and assignment.role_name == role_name
        and role
        and role.name == role_name
        and assignment.role_id == role.id
    )


@organization_bp.get("/departments")
@jwt_required()
def list_departments():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active user not found", 403, "FORBIDDEN")
    departments = Department.query.order_by(Department.name.asc()).all()
    return jsonify({
        "data": [{"id": dept.id, "name": dept.name} for dept in departments],
        "error": None,
    })


@organization_bp.get("/transfer-candidates")
@jwt_required()
def transfer_candidates():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    actor_assignment = get_active_assignment(actor.id)
    if not (
        is_system_admin(actor)
        or is_hr_admin(actor)
        or (
            actor_assignment
            and actor_assignment.organizational_role
            in {"general_manager", "department_manager", "team_leader"}
        )
    ):
        return _error("Manager access is required to view transfer candidates", 403, "FORBIDDEN")
    query = User.active_query().filter(User.account_status == "approved")
    if (
        actor_assignment
        and actor_assignment.organizational_role in {"department_manager", "team_leader"}
        and not (is_system_admin(actor) or is_hr_admin(actor))
    ):
        query = query.filter(User.department_id == actor_assignment.department_id)
        if actor_assignment.organizational_role == "team_leader":
            query = query.filter(or_(User.manager_id == actor.id, User.id == actor.id))
    candidates = query.order_by(User.full_name.asc()).limit(1000).all()
    candidate_ids = [user.id for user in candidates]
    assignments = (
        DepartmentAssignmentHistory.query.filter(
            DepartmentAssignmentHistory.user_id.in_(candidate_ids),
            DepartmentAssignmentHistory.ended_at.is_(None),
        )
        .order_by(DepartmentAssignmentHistory.started_at.desc())
        .all()
    ) if candidate_ids else []
    assignment_by_user = {}
    for assignment in assignments:
        assignment_by_user.setdefault(assignment.user_id, assignment)
    rows = []
    for user in candidates:
        assignment = assignment_by_user.get(user.id)
        rows.append({
            "id": user.id,
            "employee_id": user.employee_id,
            "name": user.full_name,
            "department_id": user.department_id,
            "department": user.department,
            "manager_id": user.manager_id,
            "department_role": assignment.role_name if assignment else None,
            "organizational_role": (
                assignment.organizational_role if assignment else "field_agent"
            ),
        })
    return jsonify({"data": rows, "error": None})


@organization_bp.get("/assignment/me")
@jwt_required()
def current_assignment():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    assignment = get_active_assignment(actor.id)
    if not assignment:
        return jsonify({"data": None, "error": None})
    active_role = _assignment_role_matches(actor, assignment.role_name) if assignment.role_name else False
    effective_roles = effective_organizational_roles(actor, assignment)
    group_leader_substitute = is_group_leader_substitute(
        actor, assignment.department_id
    )
    return jsonify({
        "data": {
            "department_id": assignment.department_id,
            "department": assignment.department_name,
            "department_role": assignment.role_name if active_role else None,
            "organizational_role": assignment.organizational_role,
            "effective_organizational_roles": effective_roles,
            "group_leader_substitute": group_leader_substitute,
            "started_at": assignment.started_at.isoformat(),
        },
        "error": None,
    })


@organization_bp.post("/users/<int:user_id>/transfer")
@organization_bp.post("/employees/transfer")
@jwt_required()
def transfer_department(user_id=None):
    actor = _actor()
    payload = request.get_json(silent=True)
    if user_id is None and isinstance(payload, dict):
        try:
            user_id = int(payload.get("user_id"))
        except (TypeError, ValueError):
            user_id = None
    target = db.session.get(User, user_id) if user_id else None
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not target or target.is_deleted:
        return _error("Employee not found", 404, "NOT_FOUND")
    if actor.id == target.id:
        return _error("Employees cannot transfer their own department assignment", 403, "FORBIDDEN")
    if not may_manage_transfers(actor, target):
        return _error("You are not authorized to transfer this employee", 403, "FORBIDDEN")

    if not isinstance(payload, dict):
        return _error("A JSON request body is required")
    try:
        raw_department_id = payload.get("department_id")
        if isinstance(raw_department_id, bool) or not isinstance(raw_department_id, (int, str)):
            raise ValueError
        department_id = int(raw_department_id)
        if department_id < 1 or (isinstance(raw_department_id, str) and str(department_id) != raw_department_id.strip()):
            raise ValueError
    except (TypeError, ValueError):
        return _error("department_id must be an integer")
    department = db.session.get(Department, department_id)
    if department is None:
        return _error("Department not found", 404, "NOT_FOUND")

    role_name = payload.get("department_role")
    if role_name is not None and not isinstance(role_name, str):
        return _error("department_role must be text or null")
    role_name = role_name.strip() if role_name else None
    organizational_role = payload.get("organizational_role")
    if not isinstance(organizational_role, str) or organizational_role not in ORG_POSITIONS:
        return _error(
            "organizational_role must be one of the supported hierarchy roles"
        )
    actor_assignment = get_active_assignment(actor.id)
    actor_position = actor_assignment.organizational_role if actor_assignment else None
    if organizational_role == "general_manager" and not is_system_admin(actor):
        return _error("Only a system administrator can assign a General Manager", 403, "FORBIDDEN")
    if (
        organizational_role == "department_manager"
        and actor_position != "general_manager"
        and not (is_system_admin(actor) or is_hr_admin(actor))
    ):
        return _error("Only General Management or HR can assign a Department Manager", 403, "FORBIDDEN")
    if (
        actor_position == "team_leader"
        and organizational_role != "field_agent"
    ):
        return _error("Team leaders may only transfer field agents", 403, "FORBIDDEN")
    if (
        organizational_role == "field_agent"
        and not role_name
    ):
        return _error("Field agents must have one active department role")

    try:
        manager_id = validate_reporting_manager(
            target,
            department,
            organizational_role,
            payload.get("manager_id"),
            actor,
        )
        assignment = transition_department(
            target, department, role_name, organizational_role, actor
        )
        target.manager_id = manager_id
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return _error(str(exc), 422)
    except IntegrityError as exc:
        db.session.rollback()
        message = assignment_capacity_conflict_message(
            exc, department, organizational_role
        )
        if message:
            return _error(message, 409, "ORGANIZATION_CONFLICT")
        current_app.logger.exception("Unable to record employee department transfer")
        return _error("Unable to complete the department transfer", 500, "TRANSFER_FAILED")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to record employee department transfer")
        return _error("Unable to complete the department transfer", 500, "TRANSFER_FAILED")

    return jsonify({
        "data": {
            "user_id": target.id,
            "department_id": assignment.department_id,
            "department": assignment.department_name,
            "department_role": assignment.role_name,
            "organizational_role": assignment.organizational_role,
            "started_at": assignment.started_at.isoformat(),
            "revoked_previous_department_access": True,
        },
        "error": None,
    })


@organization_bp.post("/locations/ping")
@organization_bp.post("/agent/location")
@jwt_required()
def record_location_ping():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    assignment = _active_field_agent(actor)
    if not assignment:
        return _error("Only active field agents can send location updates", 403, "FORBIDDEN")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required")
    tracking_mode = payload.get("tracking_mode", "scheduled")
    if tracking_mode == "active_visit":
        active_visit = AgentLocationSharing.query.filter_by(
            user_id=actor.id, is_enabled=True
        ).first()
        if (
            not active_visit
            or not active_visit.updated_at
            or active_visit.updated_at < datetime.utcnow() - timedelta(hours=ACTIVE_FIELD_VISIT_MAX_HOURS)
        ):
            return _error(
                "Start an active field visit and explicitly opt in before sharing location",
                403,
                "ACTIVE_VISIT_REQUIRED",
            )
    elif tracking_mode == "scheduled":
        tracking_state = tracking_state_for_agent(actor)
        if not tracking_state["enabled"]:
            return _error(
                "Agent location tracking is outside its scheduled or authorized period",
                403,
                "LOCATION_TRACKING_DISABLED",
            )
    else:
        return _error("tracking_mode must be active_visit or scheduled", 422)
    latitude = _valid_coordinate(payload.get("latitude"), -90, 90)
    longitude = _valid_coordinate(payload.get("longitude"), -180, 180)
    if latitude is None or longitude is None:
        return _error("Valid latitude and longitude are required")
    accuracy = _valid_accuracy(payload.get("accuracy_meters"))
    if payload.get("accuracy_meters") is not None and accuracy is None:
        return _error("accuracy_meters must be between 0 and 100000")

    last_ping = (
        AgentLocation.query.filter_by(user_id=actor.id)
        .filter(AgentLocation.is_simulated.is_(False))
        .order_by(AgentLocation.recorded_at.desc())
        .first()
    )
    now = datetime.utcnow()
    if (
        last_ping
        and (now - last_ping.recorded_at).total_seconds()
        < LOCATION_PING_INTERVAL_SECONDS
    ):
        return _error(
            f"Location updates are limited to one every {LOCATION_PING_INTERVAL_SECONDS} seconds",
            429,
            "RATE_LIMITED",
        )
    cleanup_expired_locations()
    location = AgentLocation(
        user_id=actor.id,
        department_id=assignment.department_id,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy,
        recorded_at=now,
    )
    db.session.add(location)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to store employee location ping")
        return _error("Unable to store the location update", 500, "LOCATION_PING_FAILED")
    return jsonify({
        "data": {"id": location.id, "recorded_at": location.recorded_at.isoformat()},
        "error": None,
    }), 201


@organization_bp.get("/agent/location-sharing")
@jwt_required()
def get_location_sharing_status():
    actor = _actor()
    assignment = _active_field_agent(actor)
    if not assignment:
        return _error("Only active field agents can manage location sharing", 403, "FORBIDDEN")
    state = tracking_state_for_agent(actor)
    sharing = AgentLocationSharing.query.filter_by(user_id=actor.id).first()
    active_visit = bool(
        sharing
        and sharing.is_enabled
        and sharing.updated_at
        and sharing.updated_at >= datetime.utcnow() - timedelta(hours=ACTIVE_FIELD_VISIT_MAX_HOURS)
    )
    return jsonify({
        "data": {
            **state,
            "active_visit": active_visit,
            "active_visit_started_at": sharing.updated_at.isoformat()
            if active_visit else None,
            "updated_at": None,
        },
        "error": None,
    })


@organization_bp.post("/agent/active-visit")
@jwt_required()
def set_active_field_visit():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not _active_field_agent(actor):
        return _error("Only active field agents can share visit locations", 403, "FORBIDDEN")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("action") not in {"start", "stop"}:
        return _error("action must be start or stop", 422)
    sharing = AgentLocationSharing.query.filter_by(user_id=actor.id).first()
    if sharing is None:
        sharing = AgentLocationSharing(user_id=actor.id, is_enabled=False)
        db.session.add(sharing)
    sharing.is_enabled = payload["action"] == "start"
    sharing.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to update active field visit sharing")
        return _error("Unable to update field-visit location sharing", 500)
    return jsonify({
        "data": {
            "active_visit": sharing.is_enabled,
            "started_at": sharing.updated_at.isoformat() if sharing.is_enabled else None,
        },
        "error": None,
    })


@organization_bp.put("/agent/location-sharing")
@jwt_required()
def set_location_sharing_status():
    return _error(
        "Field-agent tracking is controlled by the administrator schedule and manager controls",
        403,
        "LOCATION_TRACKING_MANAGED",
    )


@organization_bp.get("/location-tracking/schedule")
@jwt_required()
def get_location_tracking_schedule():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not is_system_admin(actor):
        return _error("Only a system administrator can manage the tracking schedule", 403, "FORBIDDEN")
    return jsonify({"data": policy_data(location_tracking_policy()), "error": None})


@organization_bp.put("/location-tracking/schedule")
@jwt_required()
def set_location_tracking_schedule():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not is_system_admin(actor):
        return _error("Only a system administrator can manage the tracking schedule", 403, "FORBIDDEN")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required")
    enabled = payload.get("enabled")
    days = payload.get("days")
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    timezone_name = payload.get("timezone", DEFAULT_TIMEZONE)
    if not isinstance(enabled, bool):
        return _error("enabled must be true or false")
    if (
        not isinstance(days, list)
        or any(not isinstance(day, str) for day in days)
        or any(day not in WEEKDAY_NAMES for day in days)
        or len(days) != len(set(days))
        or (enabled and not days)
    ):
        return _error("days must contain unique weekday codes; an enabled schedule needs at least one day")
    if (
        not isinstance(start_time, str)
        or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time)
        or not isinstance(end_time, str)
        or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end_time)
        or start_time == end_time
    ):
        return _error("start_time and end_time must be different 24-hour HH:MM values")
    if timezone_name != DEFAULT_TIMEZONE:
        return _error(f"timezone must be {DEFAULT_TIMEZONE}")

    now = datetime.utcnow()
    policy = location_tracking_policy()
    if policy is None:
        policy = AgentLocationPolicy(id=1)
        db.session.add(policy)
    policy.is_enabled = enabled
    policy.timezone = timezone_name
    policy.days = days
    policy.start_time = start_time
    policy.end_time = end_time
    policy.updated_by_id = actor.id
    policy.updated_at = now
    try:
        AgentLocationOverride.query.delete()
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to update the agent tracking schedule")
        return _error("Unable to update the agent tracking schedule", 500, "LOCATION_SCHEDULE_FAILED")
    return jsonify({"data": policy.to_dict(), "error": None})


def _tracking_manager_scope(actor):
    scope = manager_location_scope(actor)
    if not scope:
        return None
    if scope["type"] == "department" and not can_manage_locations(actor, scope["id"]):
        return None
    return scope


@organization_bp.get("/location-tracking/control")
@jwt_required()
def get_location_tracking_control():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    scope = _tracking_manager_scope(actor)
    if not scope:
        return _error(
            "Only team leaders, department managers, and general managers can control tracking",
            403,
            "FORBIDDEN",
        )
    return jsonify({
        "data": tracking_state_for_scope(scope),
        "error": None,
    })


@organization_bp.put("/location-tracking/control")
@jwt_required()
def set_location_tracking_control():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    scope = _tracking_manager_scope(actor)
    if not scope:
        return _error(
            "Only team leaders, department managers, and general managers can control tracking",
            403,
            "FORBIDDEN",
        )
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        return _error("enabled must be true or false")

    policy = location_tracking_policy()
    if not policy or not policy.is_enabled:
        return _error("The system administrator must configure and enable a schedule first", 409, "LOCATION_SCHEDULE_DISABLED")
    now = datetime.utcnow()
    if payload["enabled"] and not schedule_is_active(policy, now):
        return _error("Tracking cannot be turned on outside the configured schedule", 409, "LOCATION_OUTSIDE_SCHEDULE")
    expires_at = next_schedule_boundary(policy, now)
    if expires_at is None:
        return _error("The tracking schedule has no upcoming transition", 409, "LOCATION_SCHEDULE_INVALID")

    override = AgentLocationOverride.query.filter_by(
        scope_type=scope["type"],
        scope_id=scope["id"],
    ).one_or_none()
    if override is None:
        override = AgentLocationOverride(
            scope_type=scope["type"],
            scope_id=scope["id"],
        )
        db.session.add(override)
    override.is_enabled = payload["enabled"]
    override.expires_at = expires_at
    override.updated_by_id = actor.id
    override.updated_at = now
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to update the manager tracking override")
        return _error("Unable to update the tracking control", 500, "LOCATION_CONTROL_FAILED")
    return jsonify({
        "data": tracking_state_for_scope(scope),
        "error": None,
    })


@organization_bp.get("/locations/live")
@organization_bp.get("/manager/agents/live-locations")
@jwt_required()
def get_live_locations():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not can_manage_locations(actor):
        return _error("Manager access is required to view employee locations", 403, "FORBIDDEN")

    now = datetime.utcnow()
    cleanup_expired_locations()
    active_users = User.active_query().filter(User.account_status == "approved")
    actor_assignment = get_active_assignment(actor.id)
    is_company_wide_manager = bool(
        actor_assignment
        and actor_assignment.organizational_role == "general_manager"
    )
    if not (
        actor.is_superuser
        or is_system_admin(actor)
        or is_hr_admin(actor)
        or is_company_wide_manager
    ):
        if actor_assignment and actor_assignment.organizational_role == "team_leader":
            active_users = active_users.filter(User.manager_id == actor.id)
        elif actor_assignment and actor_assignment.organizational_role == "department_manager":
            active_users = active_users.filter(
                User.department_id == actor_assignment.department_id
            )
    scoped_user_ids = [
        row.id for row in active_users.with_entities(User.id).all()
    ]
    active_agent_ids = {
        row.user_id
        for row in (
            db.session.query(DepartmentAssignmentHistory.user_id)
            .join(User, User.id == DepartmentAssignmentHistory.user_id)
            .join(
                UserRole,
                (UserRole.user_id == DepartmentAssignmentHistory.user_id)
                & (UserRole.role_id == DepartmentAssignmentHistory.role_id),
            )
            .join(Role, Role.id == DepartmentAssignmentHistory.role_id)
            .filter(
                DepartmentAssignmentHistory.user_id.in_(scoped_user_ids),
                DepartmentAssignmentHistory.ended_at.is_(None),
                DepartmentAssignmentHistory.organizational_role == "field_agent",
                DepartmentAssignmentHistory.department_id == User.department_id,
                DepartmentAssignmentHistory.role_name == Role.name,
                User.is_active.is_(True),
                User.is_archived.is_(False),
                User.is_deleted.is_(False),
                User.account_status == "approved",
            )
            .distinct()
            .all()
        )
    } if scoped_user_ids else set()
    user_ids = list(active_agent_ids)
    tracking_policy = location_tracking_policy()
    visit_sharing_by_user = {
        sharing.user_id: sharing
        for sharing in AgentLocationSharing.query.filter(
            AgentLocationSharing.user_id.in_(user_ids),
            AgentLocationSharing.is_enabled.is_(True),
            AgentLocationSharing.updated_at >= now - timedelta(hours=ACTIVE_FIELD_VISIT_MAX_HOURS),
        ).all()
    } if user_ids else {}
    locations = (
        AgentLocation.query.join(User, User.id == AgentLocation.user_id).filter(
            AgentLocation.user_id.in_(user_ids),
            AgentLocation.recorded_at >= now - timedelta(hours=24),
            AgentLocation.department_id == User.department_id,
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        )
        .order_by(AgentLocation.recorded_at.desc())
        .limit(5000)
        .all()
    ) if user_ids else []
    latest_by_user = {}
    latest_real_by_user = {}
    trails = {}
    for location in locations:
        latest_by_user.setdefault(location.user_id, location)
        if not location.is_simulated:
            latest_real_by_user.setdefault(location.user_id, location)
        trails.setdefault(location.user_id, []).append(location)

    users_by_id = {
        user.id: user
        for user in User.active_query()
        .filter(User.id.in_(user_ids), User.account_status == "approved")
        .all()
    } if user_ids else {}
    tracking_states = tracking_states_for_agents(
        list(users_by_id.values()),
        policy=tracking_policy,
        now=now,
    )
    agents = []
    for user_id in sorted(active_agent_ids):
        visit_sharing = visit_sharing_by_user.get(user_id)
        active_visit = bool(visit_sharing)
        visit_points = [
            point for point in trails.get(user_id, [])
            if visit_sharing and point.recorded_at >= visit_sharing.updated_at
        ]
        latest_real = (
            visit_points[0] if active_visit and visit_points
            else latest_real_by_user.get(user_id) if not active_visit
            else None
        )
        latest = (
            latest_real or (visit_points[0] if active_visit and visit_points
                            else latest_by_user.get(user_id) if not active_visit else None)
        )
        user = users_by_id.get(user_id)
        if not user:
            continue
        last_ping_at = latest_real.recorded_at if latest_real else None
        has_recent_ping = bool(
            last_ping_at and last_ping_at >= now - timedelta(minutes=3)
        )
        tracking_state = tracking_states[user_id]
        sharing_enabled = tracking_state["enabled"]
        agents.append({
            "user_id": user.id,
            "name": user.full_name,
            "department": user.department,
            "active_visit": active_visit,
            "active_visit_started_at": visit_sharing.updated_at.isoformat()
            if visit_sharing else None,
            "latitude": latest.latitude if latest else None,
            "longitude": latest.longitude if latest else None,
            "accuracy_meters": latest.accuracy_meters if latest else None,
            "is_simulated": latest.is_simulated if latest else False,
            "recorded_at": latest.recorded_at.isoformat() if latest else None,
            "is_live": (
                bool(latest_real)
                and (sharing_enabled or active_visit)
                and has_recent_ping
            ),
            "sharing_enabled": sharing_enabled,
            "tracking_enabled": sharing_enabled,
            "scheduled_enabled": tracking_state["scheduled_enabled"],
            "override_active": tracking_state["override_active"],
            "sharing_status": (
                "on" if (sharing_enabled or active_visit) and has_recent_ping
                else "stale" if sharing_enabled or active_visit
                else "off"
            ),
            "sharing_updated_at": None,
            "last_ping_at": last_ping_at.isoformat() if last_ping_at else None,
            "trail": [
                {
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                    "recorded_at": point.recorded_at.isoformat(),
                    "is_simulated": point.is_simulated,
                }
                for point in reversed(
                    (visit_points if active_visit else trails.get(user_id, []))[:100]
                )
            ],
        })
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to retrieve and expire agent locations")
        return _error("Unable to retrieve live locations", 500, "LOCATION_QUERY_FAILED")
    return jsonify({
        "data": {
            "agents": agents,
            "retention_days": LOCATION_RETENTION_DAYS,
            "trail_window_hours": 24,
            "refreshed_at": now.isoformat(),
        },
        "error": None,
    })


@organization_bp.get("/locations/stream")
@jwt_required()
def stream_live_locations():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not can_manage_locations(actor):
        return _error("Manager access is required to view employee locations", 403, "FORBIDDEN")

    @stream_with_context
    def event_stream():
        expires_at = time.monotonic() + 240
        while time.monotonic() < expires_at:
            result = get_live_locations()
            if isinstance(result, tuple):
                response, status = result
            else:
                response, status = result, result.status_code
            payload = response.get_json()
            if status != 200:
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
                return
            yield f"data: {json.dumps(payload['data'])}\n\n"
            time.sleep(15)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@organization_bp.get("/manager/agents/<int:user_id>/location-trail")
@jwt_required()
def get_agent_location_trail(user_id):
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if not can_manage_locations(actor):
        return _error("Manager access is required to view employee locations", 403, "FORBIDDEN")

    target = User.active_query().filter_by(
        id=user_id,
        account_status="approved",
    ).first()
    target_assignment = get_active_assignment(user_id)
    if (
        not target
        or not target_assignment
        or target_assignment.organizational_role != "field_agent"
        or target_assignment.department_id != target.department_id
        or not target_assignment.role_id
        or not _assignment_role_matches(target, target_assignment.role_name)
    ):
        return _error("Active field agent not found", 404, "NOT_FOUND")

    actor_assignment = get_active_assignment(actor.id)
    company_wide = bool(
        is_system_admin(actor)
        or is_hr_admin(actor)
        or (
            actor_assignment
            and actor_assignment.organizational_role == "general_manager"
        )
    )
    if not company_wide and (
        not actor_assignment
        or actor_assignment.organizational_role
        not in {"department_manager", "team_leader"}
        or actor_assignment.department_id != target_assignment.department_id
    ):
        return _error("Employee location is outside your management scope", 403, "FORBIDDEN")
    if (
        actor_assignment
        and actor_assignment.organizational_role == "team_leader"
        and target.manager_id != actor.id
    ):
        return _error("Employee location is outside your team", 403, "FORBIDDEN")

    raw_start = request.args.get("start")
    raw_end = request.args.get("end")
    now = datetime.utcnow()
    if raw_start or raw_end:
        if not raw_start or not raw_end:
            return _error("Both start and end ISO-8601 timestamps are required")
        try:
            start = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
        except ValueError:
            return _error("start and end must be ISO-8601 timestamps")
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = start.astimezone(timezone.utc).replace(tzinfo=None)
        end = end.astimezone(timezone.utc).replace(tzinfo=None)
        if start >= end:
            return _error("start must be earlier than end")
        if end > now:
            return _error("end cannot be in the future")
        if start < now - timedelta(days=LOCATION_RETENTION_DAYS):
            return _error(
                f"Location history is retained for {LOCATION_RETENTION_DAYS} days"
            )
        hours = (end - start).total_seconds() / 3600
    else:
        raw_hours = request.args.get("hours", "24")
        try:
            hours = int(raw_hours)
        except (TypeError, ValueError):
            return _error("hours must be an integer between 1 and 24")
        if not 1 <= hours <= 24:
            return _error("hours must be an integer between 1 and 24")
        end = now
        start = end - timedelta(hours=hours)

    points = (
        AgentLocation.query.filter_by(
            user_id=target.id,
            department_id=target_assignment.department_id,
        )
        .filter(
            AgentLocation.recorded_at >= start,
            AgentLocation.recorded_at <= end,
        )
        .order_by(AgentLocation.recorded_at.desc())
        .limit(1500)
        .all()
    )
    return jsonify({
        "data": {
            "user_id": target.id,
            "name": target.full_name,
            "department": target_assignment.department_name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "hours": hours,
            "trail": [
                {
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                    "accuracy_meters": point.accuracy_meters,
                    "is_simulated": point.is_simulated,
                    "recorded_at": point.recorded_at.isoformat(),
                }
                for point in reversed(points)
            ],
        },
        "error": None,
    })


@organization_bp.post("/clients")
@organization_bp.post("/clients/register")
@jwt_required()
def register_client():
    actor = _actor()
    if (
        not actor
        or not actor.is_currently_active()
        or actor.account_status != "approved"
        or not _assignment_role_matches(actor, "sales")
    ):
        return _error("Active Sales and Marketing assignment required", 403, "FORBIDDEN")
    assignment = get_active_assignment(actor.id)
    department_name = assignment.department_name.lower()
    if "sales" not in department_name and "marketing" not in department_name:
        return _error("Client registration is only available to Sales and Marketing", 403, "FORBIDDEN")

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required")
    name = payload.get("name")
    phone_number = payload.get("phone_number")
    client_type = payload.get("client_type")
    if not isinstance(name, str) or not name.strip():
        return _error("Client name is required")
    if not isinstance(phone_number, str) or not phone_number.strip():
        return _error("Client phone number is required")
    if not isinstance(client_type, str) or client_type not in CLIENT_TYPES:
        return _error("client_type is not supported")
    client_status = payload.get("client_status")
    if (
        not isinstance(client_status, str)
        or client_status not in {"new", "existing"}
    ):
        return _error("client_status must be new or existing")
    optional_fields = {
        "email": 255,
        "business_name": 160,
        "business_location": 255,
    }
    for field, max_length in optional_fields.items():
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            return _error(f"{field} must be text")
        if value and len(value.strip()) > max_length:
            return _error(f"{field} cannot exceed {max_length} characters")
    if payload.get("email") and not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", payload["email"].strip()
    ):
        return _error("Enter a valid email address")
    if len(name.strip()) > 160 or len(phone_number.strip()) > 40:
        return _error("Client name or phone number exceeds the allowed length")
    latitude = _valid_coordinate(payload.get("latitude"), -90, 90)
    longitude = _valid_coordinate(payload.get("longitude"), -180, 180)
    if latitude is None and payload.get("latitude") not in (None, ""):
        return _error("latitude must be a valid coordinate between -90 and 90")
    if longitude is None and payload.get("longitude") not in (None, ""):
        return _error("longitude must be a valid coordinate between -180 and 180")
    latitude = latitude if latitude is not None else 0.0
    longitude = longitude if longitude is not None else 0.0
    accuracy = _valid_accuracy(payload.get("location_accuracy_meters"))
    if payload.get("location_accuracy_meters") is not None and accuracy is None:
        return _error("location_accuracy_meters must be between 0 and 100000")

    client = Client(
        name=name.strip(),
        phone_number=phone_number.strip(),
        email=(payload.get("email") or "").strip() or None,
        client_type=client_type,
        client_status=client_status,
        business_name=(payload.get("business_name") or "").strip() or None,
        business_location=(payload.get("business_location") or "").strip() or None,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_meters=accuracy,
        department_id=assignment.department_id,
        created_by_id=actor.id,
    )
    db.session.add(client)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to save registered client")
        return _error("Unable to register client", 500, "CLIENT_REGISTRATION_FAILED")
    return jsonify({"data": client.to_dict(), "error": None}), 201


@organization_bp.get("/reports/history")
@jwt_required()
def historical_department_reports():
    actor = _actor()
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    previous_departments = (
        DepartmentAssignmentHistory.query.filter(
            DepartmentAssignmentHistory.user_id == actor.id,
            DepartmentAssignmentHistory.ended_at.is_not(None),
        )
        .with_entities(DepartmentAssignmentHistory.department_name)
        .distinct()
        .all()
    )
    department_names = {
        _normalized_department_name(row.department_name)
        for row in previous_departments
    }
    reports = []
    if department_names:
        own_reports = (
            SalesDailyReport.query.filter_by(employee_id=actor.id)
            .order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc())
            .limit(2000)
            .all()
        )
        reports = [
            report for report in own_reports
            if _normalized_department_name(report.department) in department_names
        ][:500]
    return jsonify({
        "data": [
            {**report.to_dict(), "read_only": True, "can_edit": False}
            for report in reports
        ],
        "error": None,
    })


@reports_bp.get("/<int:department_id>")
@jwt_required()
def reports_for_department(department_id):
    actor = _actor()
    department = db.session.get(Department, department_id)
    if not actor or not actor.is_currently_active() or actor.account_status != "approved":
        return _error("Active, approved account required", 403, "FORBIDDEN")
    if department is None:
        return _error("Department not found", 404, "NOT_FOUND")
    if not can_view_history(actor.id, department_id):
        return _error("You do not have access to this department's reports", 403, "FORBIDDEN")

    assignment_rows = DepartmentAssignmentHistory.query.filter_by(
        department_id=department_id
    ).all()
    department_names = {department.name}
    department_names.update(row.department_name for row in assignment_rows)
    assignment = get_active_assignment(actor.id)
    is_company_wide = (
        is_system_admin(actor)
        or is_hr_admin(actor)
        or bool(
            assignment
            and assignment.organizational_role == "general_manager"
        )
    )
    if is_company_wide:
        employee_ids = {row.user_id for row in assignment_rows}
    elif assignment and assignment.department_id == department_id and assignment.organizational_role in {
        "department_manager", "team_leader"
    }:
        employee_ids = {row.user_id for row in assignment_rows}
        employee_ids.add(actor.id)
        if assignment.organizational_role == "team_leader":
            employee_ids = {
                user.id for user in User.query.filter(
                    or_(User.manager_id == actor.id, User.id == actor.id)
                ).all()
            }
    else:
        employee_ids = {actor.id}
    normalized_names = {
        _normalized_department_name(name) for name in department_names
    }
    rows = (
        SalesDailyReport.query.filter(
            SalesDailyReport.employee_id.in_(employee_ids),
            db.func.lower(SalesDailyReport.department).in_(
                [name.lower() for name in department_names]
            ),
        )
        .order_by(SalesDailyReport.date_visited.desc(), SalesDailyReport.id.desc())
        .limit(1000)
        .all()
    ) if employee_ids else []
    if normalized_names:
        rows = [
            row for row in rows
            if _normalized_department_name(row.department) in normalized_names
        ]
    can_edit = can_perform_actions(actor.id, department_id)
    return jsonify({
        "data": {
            "department": {"id": department.id, "name": department.name},
            "read_only": not can_edit,
            "can_edit": can_edit,
            "reports": [
                {**row.to_dict(), "read_only": not can_edit, "can_edit": can_edit}
                for row in rows
            ],
        },
        "error": None,
    })


organization_compat_bp.add_url_rule(
    "/api/employees/transfer",
    endpoint="transfer_department",
    view_func=transfer_department,
    methods=["POST"],
)
organization_compat_bp.add_url_rule(
    "/api/agent/location",
    endpoint="record_location_ping",
    view_func=record_location_ping,
    methods=["POST"],
)
organization_compat_bp.add_url_rule(
    "/api/clients/register",
    endpoint="register_client",
    view_func=register_client,
    methods=["POST"],
)
organization_compat_bp.add_url_rule(
    "/api/manager/agents/live-locations",
    endpoint="get_live_locations",
    view_func=get_live_locations,
    methods=["GET"],
)
