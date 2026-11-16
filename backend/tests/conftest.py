import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pymysql
import pytest
from flask_jwt_extended import create_access_token
from app import create_app
from app.api.auth import _hash_otp
from app.config import config
from app.extensions import db
from app.models import (
    Department,
    DepartmentAssignmentHistory,
    LeaveBalance,
    LeavePolicy,
    LeaveType,
    OtpChallenge,
    User,
)
from app.utils.rbac import assign_user_role
from app.utils.rbac_seed import seed_rbac


TEST_DATABASE = os.getenv(
    "TEST_DATABASE", f"Okoa_Float_DB_test_{uuid.uuid4().hex[:8]}"
)
ADMIN_EMAIL = "admin@okoa.local"
ADMIN_PASSWORD = "Admin@2026!"
ADMIN_PHONE = "+254721143189"


def _database_settings():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "okoa_user"),
        "password": os.getenv("DB_PASSWORD", "admin123"),
    }


def _server_connection():
    return pymysql.connect(
        **_database_settings(),
        charset="utf8mb4",
        autocommit=True,
    )


def _test_database_uri(database_name=None):
    settings = _database_settings()
    database_name = database_name or TEST_DATABASE
    return (
        "mysql+pymysql://"
        f"{settings['user']}:{settings['password']}"
        f"@{settings['host']}:{settings['port']}"
        f"/{database_name}"
    )


def _setup_test_database():
    target_database = TEST_DATABASE
    application_database = os.getenv("DB_NAME", "Okoa_Float_DB")
    if target_database.casefold() == application_database.casefold():
        raise RuntimeError(
            "TEST_DATABASE must be different from DB_NAME; refusing to run "
            "destructive test setup against the application database."
        )

    connection = _server_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{target_database}`")
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{target_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            return target_database
    finally:
        connection.close()


def _reset_database():
    db.session.remove()
    db.engine.dispose()
    with db.engine.begin() as connection:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for table_name in connection.dialect.get_table_names(connection):
                connection.exec_driver_sql(f"DELETE FROM `{table_name}`")
        finally:
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")


def _seed_database():
    admin = User(
        id=1,
        employee_id="HR-0001",
        full_name="System Administrator",
        email=ADMIN_EMAIL,
        personal_email="admin.personal@example.com",
        phone_number=ADMIN_PHONE,
        role="SUPER_ADMIN",
        department="HR",
        hire_date=date(2020, 1, 1),
        is_active=True,
        is_superuser=True,
        account_status="approved",
        must_change_password=True,
    )
    admin.set_password(ADMIN_PASSWORD)
    db.session.add(admin)
    db.session.flush()
    seed_rbac()

    leave_definitions = [
        ("ANNUAL", "Annual Leave", True, False, 21, 1.75, 5, 14, None, 0),
        ("SICK", "Sick Leave", True, True, 14, 1.17, 0, 0, None, 0),
        ("MATERNITY", "Maternity Leave", True, True, 90, 0, 0, 30, "Female", 12),
        ("PATERNITY", "Paternity Leave", True, False, 14, 0, 0, 14, "Male", 0),
        ("COMPASSIONATE", "Compassionate Leave", True, False, 7, 0, 0, 0, None, 0),
        ("STUDY", "Study Leave", True, True, 10, 0, 0, 30, None, 12),
        ("UNPAID", "Unpaid Leave", False, False, 0, 0, 0, 0, None, 0),
    ]

    for code, name, paid, document, days, accrual, carryover, notice, gender, minimum in leave_definitions:
        leave_type = LeaveType(
            code=code,
            name=name,
            is_paid=paid,
            requires_document=document,
            default_days_per_year=Decimal(str(days)),
        )
        db.session.add(leave_type)
        db.session.flush()
        db.session.add(
            LeavePolicy(
                leave_type_id=leave_type.id,
                accrual_rate=Decimal(str(accrual)),
                max_carryover=Decimal(str(carryover)),
                notice_days_required=notice,
                gender_restriction=gender,
                min_service_months=minimum,
            )
        )
        if code in ("ANNUAL", "SICK"):
            db.session.add(
                LeaveBalance(
                    user_id=admin.id,
                    leave_type_id=leave_type.id,
                    year=2026,
                    entitled_days=Decimal(str(days)),
                    used_days=Decimal("0.00"),
                    pending_days=Decimal("0.00"),
                    carried_over=Decimal("0.00"),
                )
            )

    db.session.commit()


@pytest.fixture(scope="session")
def app():
    database_name = _setup_test_database()
    config["testing"].SQLALCHEMY_DATABASE_URI = _test_database_uri(database_name)
    application = create_app("testing")
    application.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)

    with application.app_context():
        db.create_all()
        _seed_database()
        yield application
        db.session.remove()
        db.engine.dispose()

    connection = _server_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def reset_test_data(app):
    with app.app_context():
        db.session.rollback()
        _reset_database()
        db.create_all()
        _seed_database()
        db.engine.dispose()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session(app):
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.remove()


@pytest.fixture
def admin_token(client):
    return _login_with_otp(client, ADMIN_PHONE, ADMIN_PASSWORD)


@pytest.fixture
def rbac_tokens(app):
    with app.app_context():
        tokens = {}
        for index, role_name in enumerate(
            ("customer_care", "debt_collection", "sales"),
            start=1,
        ):
            user = User.query.filter_by(
                email=f"rbac.{role_name}@example.test"
            ).one_or_none()
            if user is None:
                user = User(
                    employee_id=f"RBAC-{index}",
                    full_name=f"RBAC {role_name}",
                    email=f"rbac.{role_name}@example.test",
                    phone_number=f"+25470000100{index}",
                    role="employee",
                    department=role_name,
                    is_active=True,
                    account_status="approved",
                )
                user.set_password("RBAC-Test-Password!")
                db.session.add(user)
                db.session.flush()
                assign_user_role(user, role_name)
            tokens[role_name] = create_access_token(identity=str(user.id))
        sales_department = Department.query.filter_by(
            name="Sales & Marketing"
        ).one_or_none()
        if sales_department is None:
            sales_department = Department(name="Sales & Marketing")
            db.session.add(sales_department)
            db.session.flush()
        sales_employee = User.query.filter_by(email="rbac.sales@example.test").one()
        sales_employee.department_id = sales_department.id
        hierarchy = []
        manager_id = None
        for index, (position, name) in enumerate(
            (
                ("general_manager", "Leave Test General Manager"),
                ("department_manager", "Leave Test Department Manager"),
                ("team_leader", "Leave Test Team Leader"),
            ),
            start=1,
        ):
            manager = User(
                employee_id=f"LEAVE-MGR-{index}",
                full_name=name,
                email=f"leave.manager{index}@example.test",
                phone_number=f"+25470000900{index}",
                role="manager",
                department=(
                    "All" if position == "general_manager" else sales_department.name
                ),
                department_id=(
                    None if position == "general_manager" else sales_department.id
                ),
                is_active=True,
                account_status="approved",
            )
            manager.set_password("Leave-Test-Password!")
            db.session.add(manager)
            db.session.flush()
            manager.manager_id = manager_id
            db.session.add(DepartmentAssignmentHistory(
                user_id=manager.id,
                department_id=(
                    None if position == "general_manager" else sales_department.id
                ),
                department_name=(
                    "All" if position == "general_manager" else sales_department.name
                ),
                organizational_role=position,
            ))
            hierarchy.append((position, manager))
            manager_id = manager.id
        sales_employee.manager_id = hierarchy[-1][1].id
        db.session.add(DepartmentAssignmentHistory(
            user_id=sales_employee.id,
            department_id=sales_department.id,
            department_name=sales_department.name,
            organizational_role="field_agent",
        ))
        tokens["general_manager"] = create_access_token(
            identity=str(hierarchy[0][1].id)
        )
        tokens["department_manager"] = create_access_token(
            identity=str(hierarchy[1][1].id)
        )
        tokens["team_leader"] = create_access_token(
            identity=str(hierarchy[2][1].id)
        )
        db.session.commit()
        return tokens


def _login_with_otp(client, phone_number, password):
    login_response = client.post(
        "/api/auth/login",
        json={"phone_number": phone_number, "password": password},
    )
    assert login_response.status_code == 200, login_response.get_json()
    with client.application.app_context():
        challenge = OtpChallenge.query.filter_by(
            phone_number=phone_number, purpose="login"
        ).order_by(OtpChallenge.created_at.desc()).first()
        assert challenge is not None
        code = challenge.plaintext_code
        if not code:
            code = "123456"
            challenge.code_hash = _hash_otp(code)
            db.session.commit()
    response = client.post(
        "/api/auth/verify-otp",
        json={
            "phone_number": phone_number,
            "otp": code,
        },
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["access_token"]


@pytest.fixture
def login_with_otp(client):
    return lambda phone_number, password: _login_with_otp(client, phone_number, password)
