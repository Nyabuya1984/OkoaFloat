"""Administrative user lifecycle read APIs."""

from sqlalchemy import or_
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models import DashboardFeatureSetting, DebtCollectionAuditLog, DebtCollectionDutyAssignment, User
from app.utils.rbac import is_super_admin, is_system_admin, normalize_role, require_min_tier, user_tier


admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

VALID_STATUSES = {"active", "deactivated", "archived", "deleted", "all"}
FEATURE_ROLES = {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
FEATURE_NAMES = {"sales_reports", "debt_collection"}


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


def _feature_enabled(role, feature):
    setting = DashboardFeatureSetting.query.filter_by(role=role, feature=feature).first()
    return setting.enabled if setting else True


@admin_bp.get("/dashboard-features")
@require_min_tier(1)
def get_dashboard_features():
    actor = _actor()
    if actor is None:
        return _error("Authenticated user could not be found", "FORBIDDEN", 403)

    role = normalize_role(actor.role)
    duties = {
        assignment.duty
        for assignment in DebtCollectionDutyAssignment.query.filter_by(user_id=actor.id).all()
    }
    if role == "EMPLOYEE" and duties:
        sales_enabled = "sales_marketing_executive" in duties
        debt_enabled = bool(duties & {"departmental_manager", "debt_collector_agent"})
    else:
        sales_enabled = role in {"EMPLOYEE", "MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
        debt_enabled = role in {"MANAGER", "HR_ADMIN", "SYSTEM_ADMIN", "SUPER_ADMIN"}
    sales_enabled = sales_enabled and _feature_enabled(role, "sales_reports")
    debt_enabled = debt_enabled and _feature_enabled(role, "debt_collection")
    data = {
        "features": {
            "sales_reports": sales_enabled,
            "debt_collection": debt_enabled,
        },
        "duties": sorted(duties),
    }
    if is_system_admin(actor):
        data["roles"] = {
            feature_role: {
                "sales_reports": _feature_enabled(feature_role, "sales_reports"),
                "debt_collection": _feature_enabled(feature_role, "debt_collection"),
            }
            for feature_role in sorted(FEATURE_ROLES)
        }
    return jsonify({"data": data, "error": None})


@admin_bp.get("/user-duties")
@jwt_required()
def list_user_duties():
    actor = _actor()
    if actor is None or not actor.is_currently_active() or not is_super_admin(actor):
        return _error("Only a super administrator can view employee duties", "FORBIDDEN", 403)
    assignments = DebtCollectionDutyAssignment.query.order_by(
        DebtCollectionDutyAssignment.user_id,
        DebtCollectionDutyAssignment.duty,
    ).all()
    data = {}
    for assignment in assignments:
        data.setdefault(str(assignment.user_id), []).append(assignment.duty)
    return jsonify({"data": data, "error": None})


@admin_bp.put("/users/<int:user_id>/duties")
@jwt_required()
def update_user_duties(user_id):
    from app.models.debt_collection import DUTY_ROLES

    actor = _actor()
    if actor is None or not actor.is_currently_active() or not is_super_admin(actor):
        return _error("Only a super administrator can assign employee duties", "FORBIDDEN", 403)
    target = db.session.get(User, user_id)
    if not target or not target.is_currently_active():
        return _error("Active employee not found", "NOT_FOUND", 404)
    payload = request.get_json(silent=True)
    duties = payload.get("duties") if isinstance(payload, dict) else None
    if not isinstance(duties, list) or any(not isinstance(duty, str) for duty in duties):
        return _error("duties must be a list of role identifiers", "VALIDATION_ERROR", 422)
    requested = set(duties)
    if requested - DUTY_ROLES:
        return _error("duties contains an unsupported role", "VALIDATION_ERROR", 422)

    existing = {
        assignment.duty: assignment
        for assignment in DebtCollectionDutyAssignment.query.filter_by(user_id=target.id).all()
    }
    changed = sorted(set(existing) ^ requested)
    for duty in set(existing) - requested:
        db.session.delete(existing[duty])
    for duty in requested - set(existing):
        db.session.add(DebtCollectionDutyAssignment(
            user_id=target.id,
            duty=duty,
            assigned_by=actor.id,
        ))
    for duty in changed:
        db.session.add(DebtCollectionAuditLog(
            user_id=actor.id,
            entity="UserDutyAssignment",
            action="duty_assigned" if duty in requested else "duty_removed",
            before={"user_id": target.id, "duty": duty} if duty in existing else None,
            after={"user_id": target.id, "duty": duty} if duty in requested else None,
        ))
    db.session.commit()
    return jsonify({"data": {"user_id": target.id, "duties": sorted(requested)}, "error": None})


@admin_bp.patch("/dashboard-features")
@jwt_required()
def update_dashboard_feature():
    actor = _actor()
    if actor is None or not actor.is_currently_active() or not is_system_admin(actor):
        return _error("Only a system administrator can update dashboard features", "FORBIDDEN", 403)
    payload = request.get_json(silent=True) or {}
    role_value = payload.get("role")
    role_key = role_value.strip().replace("-", "_").replace(" ", "_").upper() if isinstance(role_value, str) else ""
    role = normalize_role(role_key) if role_key in FEATURE_ROLES else ""
    feature = str(payload.get("feature", "")).strip().lower()
    enabled = payload.get("enabled")
    if role not in FEATURE_ROLES or feature not in FEATURE_NAMES or not isinstance(enabled, bool):
        return _error("A valid role, feature, and enabled value are required", "VALIDATION_ERROR", 422)

    setting = DashboardFeatureSetting.query.filter_by(role=role, feature=feature).first()
    if setting is None:
        setting = DashboardFeatureSetting(role=role, feature=feature, enabled=enabled)
        db.session.add(setting)
    else:
        setting.enabled = enabled
    db.session.commit()
    return jsonify({"data": {"role": role, "feature": feature, "enabled": enabled}, "error": None})


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
