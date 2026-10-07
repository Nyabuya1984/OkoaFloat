import pytest

from app.models import Department, User


REGISTRATION_BASE = {
    "full_name": "Legacy Alias",
    "employee_name": "Jane Wanjiku",
    "job_position_title": "Operations Officer",
    "employer": "Okoa Float Ltd",
    "department": "Operations",
    "email": "jane@example.com",
    "personal_email": "jane.personal@example.com",
    "phone_number": "+254711222333",
    "password": "Password123!",
}


@pytest.mark.parametrize(
    "field",
    ["employee_name", "job_position_title", "employer", "department", "personal_email"],
)
def test_registration_requires_work_identity_fields(client, field):
    payload = {**REGISTRATION_BASE, field: ""}

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert field in body["error"]["fields"]


def test_registration_creates_user_and_reuses_department(client, session):
    first = client.post("/api/auth/register", json=REGISTRATION_BASE)
    assert first.status_code == 201, first.get_json()

    second_payload = {
        **REGISTRATION_BASE,
        "employee_name": "John Otieno",
        "email": "john@example.com",
        "personal_email": "john.personal@example.com",
        "phone_number": "+254722333444",
        "department": " operations ",
    }
    second = client.post("/api/auth/register", json=second_payload)
    assert second.status_code == 201, second.get_json()

    first_user = session.query(User).filter_by(email="jane@example.com").one()
    second_user = session.query(User).filter_by(email="john@example.com").one()
    departments = session.query(Department).filter(Department.name == "Operations").all()

    assert first_user.employee_name == "Jane Wanjiku"
    assert first_user.full_name == "Jane Wanjiku"
    assert first_user.department_id == second_user.department_id
    assert first_user.department == "Operations"
    assert len(departments) == 1


def test_registration_deduplicates_phone_formats(client, session):
    first = client.post("/api/auth/register", json=REGISTRATION_BASE)
    assert first.status_code == 201, first.get_json()

    duplicate = {
        **REGISTRATION_BASE,
        "employee_name": "Duplicate Employee",
        "email": "duplicate@example.com",
        "personal_email": "duplicate.personal@example.com",
        "phone_number": "+254 711 222 333",
    }
    second = client.post("/api/auth/register", json=duplicate)

    assert second.status_code == 409
    assert session.query(User).filter_by(phone_number="+254711222333").count() == 1
