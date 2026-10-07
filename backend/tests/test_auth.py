import hashlib

from app.models import OtpChallenge, User


def test_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={
            "phone_number": "+254700000001",
            "password": "Admin@2026!",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["verification_required"] is True
    assert "challenge_id" not in payload


def test_login_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={
            "phone_number": "+254700000001",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_verify_login_otp_issues_session_without_challenge_id(client, session):
    response = client.post(
        "/api/auth/login",
        json={
            "phone_number": "+254700000001",
            "password": "Admin@2026!",
        },
    )

    assert response.status_code == 200
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254700000001", purpose="login"
    ).one()
    challenge.code_hash = hashlib.sha256(b"123456").hexdigest()
    session.commit()

    response = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "+254700000001", "email": "admin@okoa.local", "otp": "123456"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["access_token"]
    assert payload["refresh_token"]


def test_registration_verification_keeps_account_pending(client, session):
    response = client.post(
        "/api/auth/register",
        json={
            "phone_number": "+254712345678",
            "email": "new.employee@example.com",
            "personal_email": "new.employee.personal@example.com",
            "password": "Employee@2026!",
            "employee_name": "New Employee",
            "job_position_title": "Employee",
            "employer": "Okoa Float Ltd",
            "department": "Sales",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["verification_required"] is True
    assert "challenge_id" not in payload

    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254712345678", purpose="registration"
    ).one()
    challenge.code_hash = hashlib.sha256(b"654321").hexdigest()
    session.commit()
    verification = client.post(
        "/api/auth/verify-registration",
        json={"phone_number": "+254712345678", "email": "new.employee@example.com", "otp": "654321"},
    )
    assert verification.status_code == 200
    assert verification.get_json()["account_status"] == "pending"


def test_password_reset_uses_otp_without_challenge_id(client, session):
    request_response = client.post(
        "/api/auth/request-password-reset",
        json={"phone_number": "+254700000001"},
    )
    assert request_response.status_code == 200
    assert "challenge_id" not in request_response.get_json()
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254700000001", purpose="password_reset"
    ).one()
    challenge.code_hash = hashlib.sha256(b"112233").hexdigest()
    session.commit()

    response = client.post(
        "/api/auth/reset-password",
        json={
            "phone_number": "+254700000001",
            "email": "admin@okoa.local",
            "otp": "112233",
            "new_password": "Changed@2026!",
        },
    )
    assert response.status_code == 200
    user = session.query(User).filter_by(phone_number="+254700000001").one()
    assert user.check_password("Changed@2026!")


def test_me_requires_jwt(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_with_jwt(client, admin_token):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["id"] == 1


def test_manager_can_approve_pending_registration(client, session, login_with_otp):
    manager = User(
        employee_id="MGR-0001",
        full_name="Team Manager",
        email="manager@okoa.local",
        phone_number="+254700000002",
        role="manager",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    manager.set_password("Manager@2026!")
    pending = User(
        employee_id="EMP-0002",
        full_name="New Employee",
        email="new.employee@okoa.local",
        phone_number="+254700000003",
        role="employee",
        department="Sales",
        is_active=True,
        account_status="pending",
    )
    pending.set_password("Employee@2026!")
    session.add_all([manager, pending])
    session.commit()

    manager_token = login_with_otp(manager.phone_number, "Manager@2026!")
    response = client.post(
        f"/api/auth/accounts/{pending.id}/approve",
        headers={"Authorization": f"Bearer {manager_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["account_status"] == "approved"
    assert response.get_json()["user"]["is_active"] is True


def test_admin_user_status_supports_pending_activation_deactivation_and_archive(
    client, session, admin_token
):
    user = User(
        employee_id="EMP-STATUS-01",
        full_name="Status Test User",
        email="status.test@okoa.local",
        phone_number="+254700000004",
        role="employee",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    user.set_password("Employee@2026!")
    session.add(user)
    session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}
    endpoint = f"/api/auth/admin/users/{user.id}/status"

    response = client.post(endpoint, headers=headers, json={"status": "pending"})
    assert response.status_code == 200
    assert response.get_json()["data"]["account_status"] == "pending"
    assert response.get_json()["data"]["is_active"] is True

    response = client.post(endpoint, headers=headers, json={"status": "active"})
    assert response.status_code == 200
    assert response.get_json()["data"]["account_status"] == "approved"
    session.refresh(user)
    assert user.approved_by == 1

    response = client.post(endpoint, headers=headers, json={"status": "deactivated"})
    assert response.status_code == 200
    assert response.get_json()["data"]["state"] == "deactivated"

    response = client.post(endpoint, headers=headers, json={"status": "archived"})
    assert response.status_code == 200
    assert response.get_json()["data"]["state"] == "archived"