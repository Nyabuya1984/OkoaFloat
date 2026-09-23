"""Administrative user lifecycle read APIs."""

from sqlalchemy import or_
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models import User
from app.utils.rbac import is_super_admin, normalize_role, require_min_tier, user_tier


admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

VALID_STATUSES = {"active", "deactivated", "archived", "deleted", "all"}


def _error(message, code="BAD_REQUEST", status=400):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


def _actor():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _visible_query(actor):
    query = User.query
    if not is_super_admin(actor):
        query = query.filter(User.is_superuser.is_(False), User.role != "SUPER_ADMIN")
    actor_role = normalize_role(getattr(actor, "role", None))
    if actor_role == "MANAGER":
        query = query.filter(or_(User.id == actor.id, User.manager_id == actor.id))
    elif actor_role not in {"SYSTEM_ADMIN", "HR_ADMIN", "SUPER_ADMIN"}:
        query = query.filter(User.id == actor.id)
    return query


def _apply_status(query, status):
    if status == "active":
        return query.filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        )
    if status == "deactivated":
        return query.filter(
            User.is_active.is_(False),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        )
    if status == "archived":
        return query.filter(User.is_archived.is_(True), User.is_deleted.is_(False))
    if status == "deleted":
        return query.filter(User.is_deleted.is_(True))
    return query


def _user_summary(user):
    return {
        **user.to_dict(),
        "state": user.state(),
    }


@admin_bp.get("/users")
@require_min_tier(3)
def list_admin_users():
    actor = _actor()
    if actor is None:
        return _error("Authenticated user could not be found", "FORBIDDEN", 403)

    status = request.args.get("status", "active").strip().lower()
    if status not in VALID_STATUSES:
        return _error("status must be active, deactivated, archived, deleted, or all", "VALIDATION_ERROR", 422)

    include_archived = request.args.get("include_archived", "false").lower() == "true"
    include_deleted = request.args.get("include_deleted", "false").lower() == "true"
    if include_deleted and user_tier(actor) < 4:
        return _error("Only superusers can include deleted users", "FORBIDDEN", 403)
    if status == "deleted" and user_tier(actor) < 4:
        return _error("Only superusers can view deleted users", "FORBIDDEN", 403)

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 25))))
    except ValueError:
        return _error("page and per_page must be integers", "VALIDATION_ERROR", 422)

    query = _visible_query(actor)
    query = _apply_status(query, status)
    if not include_deleted and status != "deleted":
        query = query.filter(User.is_deleted.is_(False))
    if status == "active" and include_archived:
        query = _visible_query(actor).filter(User.is_deleted.is_(False))
    if status == "active" and include_deleted:
        query = _visible_query(actor)

    search = request.args.get("q", "").strip()
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                User.full_name.ilike(term),
                User.employee_name.ilike(term),
                User.employee_id.ilike(term),
                User.email.ilike(term),
                User.phone_number.ilike(term),
            )
        )
    role = request.args.get("role")
    if role:
        normalized = normalize_role(role)
        if normalized not in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}:
            return _error("role is invalid", "VALIDATION_ERROR", 422)
        query = query.filter(User.role == normalized)
    department_id = request.args.get("department_id")
    if department_id:
        try:
            query = query.filter(User.department_id == int(department_id))
        except ValueError:
            return _error("department_id must be an integer", "VALIDATION_ERROR", 422)

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify(
        {
            "data": {
                "items": [_user_summary(user) for user in pagination.items],
                "pagination": {
                    "page": pagination.page,
                    "per_page": pagination.per_page,
                    "total": pagination.total,
                    "pages": pagination.pages,
                },
                "filters": {
                    "status": status,
                    "q": search,
                    "role": role,
                    "department_id": department_id,
                },
            },
            "error": None,
        }
    )


@admin_bp.get("/users/summary")
@require_min_tier(3)
def admin_users_summary():
    actor = _actor()
    if actor is None:
        return _error("Authenticated user could not be found", "FORBIDDEN", 403)
    query = _visible_query(actor)
    counts = {
        "active": query.filter(
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        ).count(),
        "deactivated": query.filter(
            User.is_active.is_(False),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
        ).count(),
        "archived": query.filter(User.is_archived.is_(True), User.is_deleted.is_(False)).count(),
        "deleted": query.filter(User.is_deleted.is_(True)).count()
        if user_tier(actor) >= 4
        else 0,
    }
    counts["all"] = sum(counts.values())
    return jsonify({"data": counts, "error": None})
