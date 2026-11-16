from flask import Flask
from flask_jwt_extended import create_access_token

from app.api.auth import _registration_fields, auth_bp
from app.extensions import db, jwt
from app.models import Department, User
from app.utils.organization import (
    get_active_assignment,
    transition_department,
    validate_reporting_manager,
)


def test_registration_only_accepts_the_three_canonical_departments():
    base = {
        "employee_name": "Test Employee",
        "job_position_title": "Field Agent",
        "employer": "Okoa Float Ltd",
        "department": "sales and marketing",
    }

    assert "department" not in _registration_fields(base)
    assert "department" in _registration_fields({**base, "department": "Operations"})


def test_admin_cannot_create_or_rename_a_department_outside_the_supported_set():
    app = Flask("department_policy_test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="department-policy-test-key-long-enough",
        TESTING=True,
    )
    db.init_app(app)
    jwt.init_app(app)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    with app.app_context():
        db.create_all()
        admin = User(
            employee_id="ADMIN-1",
            full_name="System Administrator",
            email="admin@example.invalid",
            role="SUPER_ADMIN",
            is_superuser=True,
            is_active=True,
            account_status="approved",
        )
        admin.set_password("test-only")
        department = Department(name="Customer Care")
        db.session.add_all([admin, department])
        db.session.commit()
        headers = {
            "Authorization": f"Bearer {create_access_token(identity=str(admin.id))}"
        }
        client = app.test_client()

        rejected_create = client.post(
            "/api/auth/admin/departments",
            headers=headers,
            json={"name": "Operations"},
        )
        rejected_rename = client.patch(
            f"/api/auth/admin/departments/{department.id}",
            headers=headers,
            json={"name": "Operations"},
        )

        assert rejected_create.status_code == 422
        assert rejected_rename.status_code == 422
        assert [row.name for row in Department.query.order_by(Department.name).all()] == [
            "Customer Care"
        ]
        created_manager = client.post(
            "/api/auth/admin/users",
            headers=headers,
            json={
                "full_name": "General Manager",
                "official_email": "gm@example.invalid",
                "phone_number": "+254700000001",
                "password": "general-manager-password",
                "department": "All",
                "department_role": None,
                "organizational_role": "general_manager",
            },
        )

        assert created_manager.status_code == 200, created_manager.get_json()
        assert created_manager.get_json()["data"]["department"] == "All"
        assert created_manager.get_json()["data"]["department_id"] is None
        manager_id = created_manager.get_json()["data"]["id"]
        updated_manager = client.patch(
            f"/api/auth/admin/users/{manager_id}",
            headers=headers,
            json={
                "department": "All",
                "organizational_role": "general_manager",
                "department_role": None,
                "manager_id": None,
            },
        )
        assert updated_manager.status_code == 200, updated_manager.get_json()
        assert updated_manager.get_json()["data"]["department"] == "All"
        assert updated_manager.get_json()["data"]["department_id"] is None
        db.session.remove()
        db.drop_all()


def test_general_manager_uses_all_without_a_department_and_remains_unique():
    app = Flask("general_manager_scope_test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="general-manager-scope-test-key",
        TESTING=True,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        manager = User(
            employee_id="GM-1",
            full_name="General Manager",
            email="gm@example.invalid",
            role="MANAGER",
            department="All",
            is_active=True,
            account_status="approved",
        )
        manager.set_password("test-only")
        db.session.add(manager)
        db.session.flush()

        assert validate_reporting_manager(
            manager, None, "general_manager", None, None
        ) is None
        transition_department(manager, None, None, "general_manager", None)
        db.session.commit()

        assignment = get_active_assignment(manager.id)
        assert manager.department == "All"
        assert manager.department_id is None
        assert assignment.department_name == "All"
        assert assignment.department_id is None

        other_manager = User(
            employee_id="GM-2",
            full_name="Second General Manager",
            email="second.gm@example.invalid",
            role="MANAGER",
            department="All",
            is_active=True,
            account_status="approved",
        )
        other_manager.set_password("test-only")
        db.session.add(other_manager)
        db.session.flush()

        try:
            validate_reporting_manager(
                other_manager, None, "general_manager", None, None
            )
        except ValueError as exc:
            assert "already assigned" in str(exc)
        else:
            raise AssertionError("A second active General Manager was allowed")

        db.session.remove()
        db.drop_all()
