"""RBAC policy matrix and protected-route tests."""

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token

from app.api.customer_care import customer_care_bp
from app.api.debt_collection import collector_bp, debt_collection_bp
from app.api.admin import admin_bp
from app.api.leave import leave_bp
from app.api.okoa_customer_care import okoa_customer_care_bp
from app.api.sales import sales_bp
from app.extensions import db, jwt
from app.models import Permission, Role, RolePermission, User
from app.models.rbac import UserRole
from app.utils.rbac import assign_user_role, can
from app.utils.rbac_seed import load_rbac_policy, seed_rbac


ROLES = ("customer_care", "debt_collection", "sales")
MATRIX = (
    ("customer_care.calls.read", "customer_care"),
    ("sales_reports.view", "sales"),
    ("sales_reports.write", "sales"),
    ("debt_collection.records.read", "debt_collection"),
    ("debt_collection.related.portfolio.read", "debt_collection"),
    ("leave.apply", None),
)
ROUTES = (
    ("customer_care", "get", "/api/customer-care/customers", "customer_care"),
    ("sales_reports.view", "get", "/api/sales/reports", "sales"),
    ("sales_reports.write", "post", "/api/sales/reports", "sales"),
    ("debt_collection", "get", "/api/debt-collection/records", "debt_collection"),
    (
        "debt_collection.related",
        "get",
        "/api/collector/my-portfolio",
        "debt_collection",
    ),
    ("leave.apply", "post", "/api/leave/requests", None),
)


@pytest.fixture(scope="module")
def rbac_client():
    app = Flask("rbac_test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="rbac-test-key-with-at-least-32-bytes",
        TESTING=True,
    )
    db.init_app(app)
    jwt.init_app(app)
    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_care_bp)
    app.register_blueprint(okoa_customer_care_bp)
    app.register_blueprint(debt_collection_bp)
    app.register_blueprint(collector_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(leave_bp)

    with app.app_context():
        db.create_all()
        seed_rbac()
        users = {}
        headers = {}
        for index, role_name in enumerate(ROLES, start=1):
            user = User(
                employee_id=f"RBAC-{index}",
                full_name=f"RBAC {role_name}",
                email=f"{role_name}@example.invalid",
                role="employee",
                department=role_name,
                is_active=True,
                account_status="approved",
            )
            user.set_password("test-only-password")
            db.session.add(user)
            db.session.flush()
            assign_user_role(user, role_name)
            users[role_name] = user
        admin = User(
            employee_id="RBAC-SYSTEM-ADMIN",
            full_name="RBAC System Admin",
            email="system-admin@example.invalid",
            role="system_admin",
            is_active=True,
            account_status="approved",
        )
        admin.set_password("test-only-password")
        db.session.add(admin)
        db.session.flush()
        users["system_admin"] = admin
        db.session.commit()
        for role_name, user in users.items():
            token = create_access_token(identity=str(user.id))
            headers[role_name] = {"Authorization": f"Bearer {token}"}

        yield app.test_client(), users, headers
        db.session.remove()
        db.drop_all()


@pytest.mark.parametrize(("permission", "allowed_role"), MATRIX)
@pytest.mark.parametrize("role_name", ROLES)
def test_can_covers_every_permission_matrix_cell(
    rbac_client, permission, allowed_role, role_name
):
    _, users, _ = rbac_client
    expected = allowed_role is None or role_name == allowed_role
    assert can(users[role_name], permission) is expected


def test_can_denies_permissions_not_in_the_policy(rbac_client):
    _, users, _ = rbac_client
    assert not can(users["sales"], "customer_care.not_a_feature")
    assert not can(users["customer_care"], "unlisted.permission")


def test_policy_file_encodes_the_exact_role_rules():
    assert load_rbac_policy() == {
        "customer_care": {
            "allow": ["customer_care.*", "leave.apply"],
            "deny": [
                "sales_reports.view",
                "sales_reports.write",
                "debt_collection.*",
                "debt_collection.related.*",
            ],
        },
        "debt_collection": {
            "allow": [
                "debt_collection.*",
                "debt_collection.related.*",
                "leave.apply",
            ],
            "deny": [
                "customer_care.*",
                "sales.*",
                "sales_reports.*",
            ],
        },
        "sales": {
            "allow": [
                "sales.*",
                "sales_reports.view",
                "sales_reports.write",
                "leave.apply",
            ],
            "deny": [
                "customer_care.*",
                "debt_collection.*",
                "debt_collection.related.*",
            ],
        },
    }


def test_can_denies_nested_cross_department_access(rbac_client):
    _, users, _ = rbac_client
    assert not can(users["sales"], "debt_collection.related.deep.read")
    assert not can(users["debt_collection"], "customer_care.reports.deep.read")


def test_deny_overrides_a_matching_allow_rule(rbac_client):
    _, users, _ = rbac_client
    permission = Permission.query.filter_by(name="debt_collection.related.*").one()
    sales_role = Role.query.filter_by(name="sales").one()
    db.session.add(
        RolePermission(
            role_id=sales_role.id,
            permission_id=permission.id,
            effect="allow",
        )
    )
    db.session.commit()

    assert not can(users["sales"], permission.name)


def test_superuser_without_an_assigned_role_is_denied(rbac_client):
    _, _, _ = rbac_client
    user = User(
        employee_id="RBAC-UNASSIGNED",
        full_name="Unassigned Superuser",
        email="unassigned@example.invalid",
        role="SUPER_ADMIN",
        is_superuser=True,
        is_active=True,
        account_status="approved",
    )
    user.set_password("test-only-password")
    db.session.add(user)
    db.session.commit()

    assert not can(user, "customer_care.anything")


def test_sales_wildcard_is_explicit_and_covers_subpermissions(rbac_client):
    _, users, _ = rbac_client
    assert can(users["sales"], "sales.pipeline.read")
    assert not can(users["customer_care"], "sales.pipeline.read")
    assert not can(users["debt_collection"], "sales.pipeline.read")


@pytest.mark.parametrize(("permission", "method", "path", "allowed_role"), ROUTES)
@pytest.mark.parametrize("role_name", ROLES)
def test_protected_routes_enforce_the_policy(
    rbac_client, permission, method, path, allowed_role, role_name
):
    client, _, headers = rbac_client
    response = getattr(client, method)(path, headers=headers[role_name], json={})

    if allowed_role is None or role_name == allowed_role:
        assert response.status_code != 403, response.get_json()
    else:
        assert response.status_code == 403, response.get_json()


def test_debt_collector_list_is_scoped_to_debt_collection_role(rbac_client):
    client, users, headers = rbac_client

    response = client.get(
        "/api/debt-collection/collectors",
        headers=headers["debt_collection"],
    )

    assert response.status_code == 200, response.get_json()
    assert [item["id"] for item in response.get_json()["data"]] == [
        users["debt_collection"].id
    ]


def test_admin_cannot_assign_role_outside_active_department(rbac_client):
    client, users, headers = rbac_client
    target = users["customer_care"]
    department_before = target.department

    response = client.put(
        f"/api/admin/users/{target.id}/department-role",
        headers=headers["system_admin"],
        json={"role": "sales"},
    )

    assert response.status_code == 422, response.get_json()
    assert not can(target, "sales_reports.view")
    assert can(target, "customer_care.calls.read")
    assert not can(target, "debt_collection.records.read")
    assert UserRole.query.filter_by(user_id=target.id).count() == 1
    assert target.department == department_before
