from app.models import OtpChallenge
from app.models import User


def test_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@okoa.local",
            "password": "Admin@2026!",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["access_token"]
    assert payload["user"]["email"] == "admin@okoa.local"


def test_login_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@okoa.local",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_phone_login_commits_otp_and_enforces_five_second_resend_delay(client, session):
    response = client.post(
        "/api/auth/phone-login",
        json={
            "phone_number": "+254700000001",
            "password": "Admin@2026!",
        },
    )

    assert response.status_code == 200
    challenge_id = response.get_json()["challenge_id"]
    challenge = session.query(OtpChallenge).filter_by(challenge_id=challenge_id).one()
    assert challenge.purpose == "login"
    assert challenge.verified_at is None

    second_response = client.post(
        "/api/auth/phone-login",
        json={
            "phone_number": "+254700000001",
            "password": "Admin@2026!",
        },
    )

    assert second_response.status_code == 429
    assert "5 seconds" in second_response.get_json()["error"]["message"]


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


def test_manager_can_approve_pending_registration(client, session):
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

    login = client.post(
        "/api/auth/login",
        json={"email": manager.email, "password": "Manager@2026!"},
    )
    assert login.status_code == 200
    response = client.post(
        f"/api/auth/accounts/{pending.id}/approve",
        headers={"Authorization": f"Bearer {login.get_json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["account_status"] == "approved"
    assert response.get_json()["user"]["is_active"] is True