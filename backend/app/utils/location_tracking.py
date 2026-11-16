"""Schedule and manager-override evaluation for field-agent GPS collection."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_

from app.models import (
    AgentLocationOverride,
    AgentLocationPolicy,
    DepartmentAssignmentHistory,
    User,
)
from app.utils.organization import get_active_assignment


WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_TIMEZONE = "Africa/Nairobi"


def default_policy_dict():
    return {
        "enabled": False,
        "timezone": DEFAULT_TIMEZONE,
        "days": [],
        "start_time": "08:00",
        "end_time": "17:00",
        "updated_at": None,
    }


def location_tracking_policy():
    return AgentLocationPolicy.query.filter_by(id=1).one_or_none()


def policy_data(policy=None):
    return policy.to_dict() if policy else default_policy_dict()


def _utc_datetime(value):
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def schedule_is_active(policy, now=None):
    if not policy or not policy.is_enabled:
        return False
    try:
        zone = ZoneInfo(policy.timezone)
        start = time.fromisoformat(policy.start_time)
        end = time.fromisoformat(policy.end_time)
    except (ValueError, ZoneInfoNotFoundError):
        return False

    days = set(policy.days or [])
    if not days:
        return False

    local_now = _utc_datetime(now).astimezone(zone)
    today = WEEKDAY_NAMES[local_now.weekday()]
    previous_day = WEEKDAY_NAMES[(local_now.weekday() - 1) % 7]
    current_time = local_now.timetz().replace(tzinfo=None)
    if start < end:
        return today in days and start <= current_time < end
    return (
        (today in days and current_time >= start)
        or (previous_day in days and current_time < end)
    )


def next_schedule_boundary(policy, now=None):
    if not policy or not policy.is_enabled or not policy.days:
        return None
    try:
        zone = ZoneInfo(policy.timezone)
        start = time.fromisoformat(policy.start_time)
        end = time.fromisoformat(policy.end_time)
    except (ValueError, ZoneInfoNotFoundError):
        return None

    now_utc = _utc_datetime(now)
    local_today = now_utc.astimezone(zone).date()
    selected_days = set(policy.days or [])
    candidates = set()
    for offset in range(-1, 9):
        day = local_today + timedelta(days=offset)
        if WEEKDAY_NAMES[day.weekday()] not in selected_days:
            continue
        start_local = datetime.combine(day, start, tzinfo=zone)
        end_day = day + timedelta(days=1) if end <= start else day
        end_local = datetime.combine(end_day, end, tzinfo=zone)
        candidates.add(start_local.astimezone(timezone.utc))
        candidates.add(end_local.astimezone(timezone.utc))

    for boundary in sorted(candidate for candidate in candidates if candidate > now_utc):
        before = boundary - timedelta(seconds=1)
        after = boundary + timedelta(seconds=1)
        if schedule_is_active(policy, before) != schedule_is_active(policy, after):
            return boundary.replace(tzinfo=None)
    return None


def manager_location_scope(actor):
    assignment = get_active_assignment(actor.id) if actor else None
    if not assignment:
        return None
    if assignment.organizational_role == "general_manager":
        return {"type": "organization", "id": 0, "label": "Organization"}
    if assignment.organizational_role == "department_manager":
        if assignment.department_id is None:
            return None
        return {
            "type": "department",
            "id": assignment.department_id,
            "label": assignment.department_name,
        }
    if assignment.organizational_role == "team_leader":
        return {
            "type": "team",
            "id": actor.id,
            "department_id": assignment.department_id,
            "label": f"Team led by {actor.full_name}",
        }
    return None


def location_scope_for_agent(
    agent,
    assignment=None,
    manager=None,
    manager_assignment=None,
):
    assignment = assignment or (get_active_assignment(agent.id) if agent else None)
    if not assignment:
        return []
    scopes = []
    if manager is None and agent.manager_id:
        manager = User.query.filter_by(id=agent.manager_id).one_or_none()
    if manager_assignment is None and manager:
        manager_assignment = get_active_assignment(manager.id)
    if (
        manager
        and manager_assignment
        and manager_assignment.organizational_role == "team_leader"
        and manager_assignment.department_id == assignment.department_id
    ):
        scopes.append(("team", manager.id, 3))
    if assignment.department_id is not None:
        scopes.append(("department", assignment.department_id, 2))
    scopes.append(("organization", 0, 1))
    return scopes


def _scope_override(scopes, now, overrides_by_scope=None):
    if not scopes:
        return None
    ranks = {(scope_type, scope_id): rank for scope_type, scope_id, rank in scopes}
    if overrides_by_scope is None:
        keys = list(ranks)
        if not keys:
            return None
        predicate = or_(*[
            (AgentLocationOverride.scope_type == scope_type)
            & (AgentLocationOverride.scope_id == scope_id)
            for scope_type, scope_id in keys
        ])
        overrides_by_scope = {
            (override.scope_type, override.scope_id): override
            for override in AgentLocationOverride.query.filter(
                AgentLocationOverride.expires_at > now,
                predicate,
            ).all()
        }
    matching = [
        override
        for key in ranks
        if (override := overrides_by_scope.get(key)) is not None
    ]
    return max(matching, key=lambda override: ranks[(override.scope_type, override.scope_id)]) if matching else None


def _tracking_state(policy, now_utc, override):
    scheduled_enabled = schedule_is_active(policy, now_utc)
    enabled = (
        bool(override.is_enabled)
        if scheduled_enabled and override
        else scheduled_enabled
    )
    next_boundary = next_schedule_boundary(policy, now_utc) if policy else None
    return {
        "enabled": enabled,
        "scheduled_enabled": scheduled_enabled,
        "schedule_configured": bool(policy and policy.is_enabled),
        "override_active": bool(scheduled_enabled and override),
        "next_transition_at": next_boundary.isoformat() if next_boundary else None,
    }


def tracking_state_for_agent(agent, policy=None, now=None):
    policy = policy if policy is not None else location_tracking_policy()
    now_utc = _utc_datetime(now)
    now_naive = now_utc.replace(tzinfo=None)
    override = _scope_override(location_scope_for_agent(agent), now_naive)
    return _tracking_state(policy, now_utc, override)


def tracking_states_for_agents(agents, policy=None, now=None):
    policy = policy if policy is not None else location_tracking_policy()
    now_utc = _utc_datetime(now)
    now_naive = now_utc.replace(tzinfo=None)
    user_ids = {agent.id for agent in agents}
    manager_ids = {agent.manager_id for agent in agents if agent.manager_id}
    manager_users = {
        user.id: user
        for user in User.query.filter(User.id.in_(manager_ids)).all()
    } if manager_ids else {}
    assignment_user_ids = user_ids | manager_ids
    assignments = {}
    if assignment_user_ids:
        assignment_rows = (
            DepartmentAssignmentHistory.query
            .filter(
                DepartmentAssignmentHistory.user_id.in_(assignment_user_ids),
                DepartmentAssignmentHistory.ended_at.is_(None),
            )
            .order_by(
                DepartmentAssignmentHistory.started_at.desc(),
                DepartmentAssignmentHistory.id.desc(),
            )
            .all()
        )
        for assignment in assignment_rows:
            assignments.setdefault(assignment.user_id, assignment)
    scopes_by_agent = {
        agent.id: location_scope_for_agent(
            agent,
            assignment=assignments.get(agent.id),
            manager=manager_users.get(agent.manager_id),
            manager_assignment=assignments.get(agent.manager_id),
        )
        for agent in agents
    }
    keys = {
        (scope_type, scope_id)
        for scopes in scopes_by_agent.values()
        for scope_type, scope_id, _rank in scopes
    }
    overrides_by_scope = {}
    if keys:
        predicate = or_(*[
            (AgentLocationOverride.scope_type == scope_type)
            & (AgentLocationOverride.scope_id == scope_id)
            for scope_type, scope_id in keys
        ])
        overrides_by_scope = {
            (override.scope_type, override.scope_id): override
            for override in AgentLocationOverride.query.filter(
                AgentLocationOverride.expires_at > now_naive,
                predicate,
            ).all()
        }
    return {
        agent.id: _tracking_state(
            policy,
            now_utc,
            _scope_override(
                scopes_by_agent[agent.id],
                now_naive,
                overrides_by_scope,
            ),
        )
        for agent in agents
    }


def tracking_state_for_scope(scope, policy=None, now=None):
    policy = policy if policy is not None else location_tracking_policy()
    now_utc = _utc_datetime(now)
    scheduled_enabled = schedule_is_active(policy, now_utc)
    now_naive = now_utc.replace(tzinfo=None)
    if scope["type"] == "team":
        scopes = [
            ("team", scope["id"], 3),
            ("department", scope["department_id"], 2),
            ("organization", 0, 1),
        ]
    elif scope["type"] == "department":
        scopes = [
            ("department", scope["id"], 2),
            ("organization", 0, 1),
        ]
    else:
        scopes = [("organization", 0, 1)]
    override = _scope_override(scopes, now_naive)
    enabled = (
        bool(override.is_enabled)
        if scheduled_enabled and override
        else scheduled_enabled
    )
    next_boundary = next_schedule_boundary(policy, now_utc) if policy else None
    transition = (
        override.expires_at
        if scheduled_enabled and override
        else next_boundary
    )
    return {
        "scope": scope,
        "enabled": enabled,
        "scheduled_enabled": scheduled_enabled,
        "schedule_configured": bool(policy and policy.is_enabled),
        "timezone": policy.timezone if policy else DEFAULT_TIMEZONE,
        "override_active": bool(scheduled_enabled and override),
        "override_expires_at": override.expires_at.isoformat() if override else None,
        "next_transition_at": transition.isoformat() if transition else None,
    }
