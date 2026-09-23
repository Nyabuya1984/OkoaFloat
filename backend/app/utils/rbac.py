from functools import wraps

from flask import g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models import User

ROLE_TIERS = {
    "EMPLOYEE": 1,
    "MANAGER": 2,
    "HR_ADMIN": 3,
    "SYSTEM_ADMIN": 3,
    "SUPER_ADMIN": 4,
}
SUPERUSER_TIER = 4


def normalize_role(value):
    if value is None:
        return "EMPLOYEE"
    normalized = str(value).strip().replace("-", "_").replace(" ", "_").upper()
    aliases = {
        "SUPER_ADMIN": "SUPER_ADMIN",
        "SUPERADMIN": "SUPER_ADMIN",
        "SUPERUSER": "SUPER_ADMIN",
        "SYSTEM_ADMIN": "SYSTEM_ADMIN",
        "SYSTEMADMIN": "SYSTEM_ADMIN",
        "SYSTEM_ADMINISTRATOR": "SYSTEM_ADMIN",
        "HR_ADMIN": "HR_ADMIN",
        "HRADMIN": "HR_ADMIN",
        "HR_ADMINISTRATOR": "HR_ADMIN",
        "EMP": "EMPLOYEE",
        "EMPLOYEE": "EMPLOYEE",
        "STAFF": "EMPLOYEE",
        "ADMIN": "SYSTEM_ADMIN",
        "MANAGER": "MANAGER",
    }
    canonical = aliases.get(normalized, normalized)
    if canonical in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
        return canonical
    return "EMPLOYEE"


def is_super_admin(user):
    """Return whether a user is the protected super-admin account."""
    if not user:
        return False
    role = normalize_role(getattr(user, "role", None))
    return bool(getattr(user, "is_superuser", False) or role == "SUPER_ADMIN")


def is_system_admin(user):
    if not user:
        return False
    role = normalize_role(getattr(user, "role", None))
    return bool(role in {"SYSTEM_ADMIN", "SUPER_ADMIN"} or getattr(user, "is_superuser", False))


def is_hr_admin(user):
    if not user:
        return False
    return normalize_role(getattr(user, "role", None)) == "HR_ADMIN"


def _forbidden(message="Insufficient permissions"):
    return jsonify({"data": None, "error": {"code": "FORBIDDEN", "message": message}}), 403


def user_tier(user):
    """Return the authoritative RBAC tier for a database user."""
    role = normalize_role(getattr(user, "role", None))
    if role == "SUPER_ADMIN":
        return SUPERUSER_TIER
    if role in {"SYSTEM_ADMIN", "HR_ADMIN"}:
        return ROLE_TIERS.get(role, 3)
    return ROLE_TIERS.get(role, 0)


def _authenticated_user():
    verify_jwt_in_request()
    try:
        identity = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, identity)
    if not user or not user.is_currently_active() or user.account_status != "approved":
        return None
    return user


def require_min_tier(minimum_tier):
    """Require an active, approved user at or above the requested RBAC tier."""
    if minimum_tier not in {1, 2, 3, SUPERUSER_TIER}:
        raise ValueError("minimum_tier must be 1, 2, 3, or 4")

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            actor = _authenticated_user()
            if actor is None:
                return _forbidden("Account is not active or approved")
            if user_tier(actor) < minimum_tier:
                return _forbidden(
                    f"This action requires RBAC tier {minimum_tier} or higher"
                )
            return view(*args, **kwargs)

        return wrapped

    return decorator


def role_required(*roles):
    allowed_roles = {normalize_role(role) for role in roles}

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = _authenticated_user()
            if user is None:
                return _forbidden("Account is not active or approved")
            if is_super_admin(user):
                return view(*args, **kwargs)
            if normalize_role(getattr(user, "role", None)) not in allowed_roles:
                return _forbidden()
            return view(*args, **kwargs)

        return wrapped

    return decorator


def self_or_manager(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        actor = _authenticated_user()
        if actor is None:
            return _forbidden("Account is not active or approved")
        try:
            identity = int(get_jwt_identity())
        except (TypeError, ValueError):
            return _forbidden("Invalid authenticated user")
        if not actor or not actor.is_active or actor.account_status != "approved":
            return _forbidden("Account is not active")
        target_user_id = kwargs.get("user_id")
        if target_user_id is None:
            target_user_id = kwargs.get("request_id")
        if target_user_id is None:
            return _forbidden("A target resource is required")
        target = db.session.get(User, target_user_id)
        actor_role = normalize_role(getattr(actor, "role", None))
        if is_super_admin(actor):
            return view(*args, **kwargs)
        if not target or (
            target.id != identity
            and target.manager_id != identity
            and actor_role not in {"HR_ADMIN", "SYSTEM_ADMIN"}
        ):
            return _forbidden()
        return view(*args, **kwargs)

    return wrapped


def require_scope(scope):
    """Authorize the V2 data scope while preserving the caller's role tier."""
    if scope not in {"mine", "team", "org"}:
        raise ValueError("scope must be mine, team, or org")

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            actor = _authenticated_user()
            if actor is None:
                return _forbidden("Account is not active or approved")
            requested_scope = request.args.get("scope")
            if requested_scope and requested_scope != scope:
                return _forbidden(f"This endpoint requires scope={scope}")
            actor_role = normalize_role(getattr(actor, "role", None))
            if scope == "team" and actor_role not in {"MANAGER", "SYSTEM_ADMIN", "HR_ADMIN"} and not user_tier(actor) == SUPERUSER_TIER:
                return _forbidden("Team scope requires manager or HR permissions")
            if scope == "org" and actor_role not in {"SYSTEM_ADMIN", "HR_ADMIN"} and not is_super_admin(actor):
                return _forbidden("Organization scope requires HR permissions")
            g.sales_scope = scope
            g.sales_actor = actor
            return view(*args, **kwargs)

        return wrapped

    return decorator
