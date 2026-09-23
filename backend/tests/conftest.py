import os
from datetime import date
from decimal import Decimal

import pymysql
import pytest

from app import create_app
from app.config import config
from app.extensions import db
from app.models import LeaveBalance, LeavePolicy, LeaveType, User


TEST_DATABASE = "Okoa_Float_DB_test"
ADMIN_EMAIL = "admin@okoa.local"
ADMIN_PASSWORD = "Admin@2026!"


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


def _test_database_uri():
    settings = _database_settings()
    return (
        "mysql+pymysql://"
        f"{settings['user']}:{settings['password']}"
        f"@{settings['host']}:{settings['port']}"
        f"/{TEST_DATABASE}"
    )


def _seed_database():
    admin = User(
        employee_id="HR-0001",
        full_name="System Administrator",
        email=ADMIN_EMAIL,
        phone_number="+254700000001",
        role="hr_admin",
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

    leave_definitions = [
        ("ANNUAL", "Annual Leave", True, False, 21, 1.75, 5, 14, None, 0),
        ("SICK", "Sick Leave", True, True, 14, 1.17, 0, 0, None, 0),
        ("MATERNITY", "Maternity Leave", True, True, 90, 0, 0, 30, "Female", 12),
        ("PATERNITY", "Paternity Leave", True, False, 14, 0, 0, 14, "Male", 0),
        ("COMPASSIONATE", "Compassionate Leave", True, False, 7, 0, 0, 0, None, 0),
        ("STUDY", "Study Leave", True, True, 10, 0, 0, 30, None, 12),
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
    connection = _server_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{TEST_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()

    config["testing"].SQLALCHEMY_DATABASE_URI = _test_database_uri()
    application = create_app("testing")
    application.config["JWT_ACCESS_TOKEN_EXPIRES"] = False

    with application.app_context():
        db.create_all()
        _seed_database()
        yield application
        db.session.remove()
        db.drop_all()

    connection = _server_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{TEST_DATABASE}`")
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def reset_test_data(app):
    yield
    with app.app_context():
        db.session.rollback()
        db.drop_all()
        db.create_all()
        _seed_database()


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
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["access_token"]
