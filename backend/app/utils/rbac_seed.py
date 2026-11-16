import json
from pathlib import Path

from app.extensions import db
from app.models.rbac import Permission, Role, RolePermission


POLICY_FILE = Path(__file__).parents[1] / "policies" / "rbac.json"


def load_rbac_policy():
    with POLICY_FILE.open(encoding="utf-8") as policy_file:
        policy = json.load(policy_file)

    if set(policy) != {"customer_care", "debt_collection", "sales"}:
        raise ValueError("RBAC policy must define exactly the three specified roles")
    for role_name, rules in policy.items():
        if set(rules) != {"allow", "deny"}:
            raise ValueError(f"Invalid allow/deny policy for {role_name}")
        for effect in ("allow", "deny"):
            if not isinstance(rules[effect], list) or not all(
                isinstance(permission, str) and permission
                for permission in rules[effect]
            ):
                raise ValueError(f"Invalid {effect} rules for {role_name}")
    return policy


def seed_rbac():
    policy = load_rbac_policy()

    for role_name, rules in policy.items():
        role = Role.query.filter_by(name=role_name).one_or_none()
        if role is None:
            role = Role(name=role_name)
            db.session.add(role)
            db.session.flush()

        RolePermission.query.filter_by(role_id=role.id).delete(
            synchronize_session=False
        )
        for effect, permissions in rules.items():
            for permission_name in permissions:
                permission = Permission.query.filter_by(
                    name=permission_name
                ).one_or_none()
                if permission is None:
                    permission = Permission(name=permission_name)
                    db.session.add(permission)
                    db.session.flush()
                db.session.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                        effect=effect,
                    )
                )

    referenced_permissions = db.session.query(RolePermission.permission_id)
    Permission.query.filter(~Permission.id.in_(referenced_permissions)).delete(
        synchronize_session=False
    )
    db.session.commit()
