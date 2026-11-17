import re
from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from app.api.auth import _hash_otp
from app.models import OtpChallenge, User
from app.services.otp_email import send_otp_email


def _latest_code(session, phone_number, purpose):
    challenge = (
        session.query(OtpChallenge)
        .filter_by(phone_number=phone_number, purpose=purpose)
        .one()
    )
    assert re.fullmatch(r"\d{6}", challenge.plaintext_code)
    return challenge.plaintext_code


def test_registration_otp_uses_one_official_email_for_confirmation(
    client, session
):
    response = client.post(
        "/api/auth/register",
        json={
            "employee_name": "Custom Domain User",
            "job_position_title": "Analyst",
            "employer": "Okoa Float",
            "department": "Sales",
            "official_email": "  User@Mail.Custom  ",
            "phone_number": "+254712300001",
            "password": "Password@2026",
        },
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["sms_sent"] is False
    assert "database and development console" in response.get_json()["message"]

    user = session.query(User).filter_by(phone_number="+254712300001").one()
    assert user.email == "user@mail.custom"
    assert user.personal_email == "user@mail.custom"
    code = _latest_code(session, user.phone_number, "registration")

    mismatch = client.post(
        "/api/auth/verify-registration",
        json={"phone_number": user.phone_number, "email": "someone@mail.custom", "otp": code},
    )
    assert mismatch.status_code == 401

    verified = client.post(
        "/api/auth/verify-registration",
        json={
            "phone_number": user.phone_number,
            "official_email": " USER@MAIL.CUSTOM ",
            "otp": code,
        },
    )
    assert verified.status_code == 200


def test_login_otp_is_stored_and_single_use(client, session, caplog):
    response = client.post(
        "/api/auth/login",
        json={"phone_number": "+254721143189", "password": "Admin@2026!"},
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["sms_sent"] is False
    assert response.get_json()["email_sent"] is False
    assert "database and development console" in response.get_json()["message"]
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254721143189", purpose="login"
    ).one()
    code = challenge.plaintext_code
    assert re.fullmatch(r"\d{6}", code)
    assert challenge.code_hash is None
    assert "========== DEVELOPMENT OTP ==========" in caplog.text
    assert "Purpose: Login" in caplog.text
    assert "Phone:   +254721143189" in caplog.text
    assert f"Code:    {code}" in caplog.text
    assert "Expires:" in caplog.text
    assert "=====================================" in caplog.text

    verified = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "+254721143189", "otp": code},
    )
    assert verified.status_code == 200
    assert verified.get_json()["access_token"]
    assert (
        session.query(OtpChallenge)
        .filter_by(phone_number="+254721143189", purpose="login")
        .count()
        == 0
    )


def test_otp_email_is_sent_via_configured_smtp(client, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["connection"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self, context):
            sent["tls"] = context

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr("app.services.otp_email.smtplib.SMTP", FakeSMTP)
    client.application.config.update(
        MAIL_SERVER="smtp.example.test",
        MAIL_PORT=587,
        MAIL_USERNAME="sender@example.test",
        MAIL_PASSWORD="smtp-password",
        MAIL_DEFAULT_SENDER="Okoa Float <sender@example.test>",
        MAIL_USE_TLS=True,
        MAIL_USE_SSL=False,
    )

    with client.application.app_context():
        sent_ok, error = send_otp_email("user@example.test", "123456", "login")

    assert sent_ok is True
    assert error is None
    assert sent["connection"] == ("smtp.example.test", 587, 12)
    assert sent["login"] == ("sender@example.test", "smtp-password")
    assert sent["message"]["To"] == "user@example.test"
    assert "123456" in sent["message"].get_content()


def test_password_and_phone_recovery_use_database_otp(client, session):
    requested = client.post(
        "/api/auth/request-password-reset", json={"phone_number": "+254721143189"}
    )
    assert requested.status_code == 200, requested.get_json()
    reset_code = _latest_code(session, "+254721143189", "reset")
    reset = client.post(
        "/api/auth/reset-password",
        json={
            "phone_number": "+254721143189",
            "otp": reset_code,
            "new_password": "Changed@2026!",
        },
    )
    assert reset.status_code == 200
    assert session.query(User).filter_by(phone_number="+254721143189").one().check_password(
        "Changed@2026!"
    )

    requested = client.post(
        "/api/auth/request-phone-recovery", json={"email": "admin.personal@example.com"}
    )
    assert requested.status_code == 200
    recovery_code = _latest_code(session, "+254721143189", "account_recovery")
    recovered = client.post(
        "/api/auth/recover-phone",
        json={"email": "ADMIN.PERSONAL@EXAMPLE.COM", "otp": recovery_code},
    )
    assert recovered.status_code == 200
    assert recovered.get_json()["phone_number"] == "+254721143189"


def test_reset_request_response_does_not_disclose_account_existence(client):
    existing = client.post(
        "/api/auth/request-password-reset",
        json={"phone_number": "+254721143189"},
    )
    missing = client.post(
        "/api/auth/request-password-reset",
        json={"phone_number": "+254700009999"},
    )

    assert existing.status_code == missing.status_code == 200
    assert existing.get_json() == missing.get_json()


def test_fifth_incorrect_code_invalidates_challenge(client, session):
    client.post(
        "/api/auth/login",
        json={"phone_number": "+254721143189", "password": "Admin@2026!"},
    )
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254721143189", purpose="login"
    ).one()
    challenge.code_hash = _hash_otp("012345")
    session.commit()

    for _ in range(5):
        response = client.post(
            "/api/auth/verify-otp",
            json={"phone_number": "+254721143189", "otp": "999999"},
        )
        assert response.status_code == 401

    session.refresh(challenge)
    assert challenge.attempts == 5
    assert challenge.status == "expired"
    assert re.fullmatch(r"\d{6}", challenge.plaintext_code)


def test_admin_created_user_uses_one_official_email_and_assigns_hierarchy(
    client, session
):
    admin = session.query(User).filter_by(phone_number="+254721143189").one()
    with client.application.app_context():
        admin_token = create_access_token(identity=str(admin.id))
    response = client.post(
        "/api/auth/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Admin Created User",
            "official_email": "created@example.com",
            "phone_number": "+254712300002",
            "password": "Password@2026",
            "department": "All",
            "organizational_role": "general_manager",
        },
    )
    assert response.status_code == 200, response.get_json()
    user = session.query(User).filter_by(email="created@example.com").one()
    assert user.personal_email == "created@example.com"
    assert response.get_json()["data"]["official_email"] == "created@example.com"
    assert response.get_json()["verification_required"] is True
    assert (
        session.query(OtpChallenge)
        .filter_by(user_id=user.id, purpose="registration")
        .count()
        == 1
    )


def test_otp_expires_after_ten_minutes(client, session):
    response = client.post(
        "/api/auth/request-password-reset", json={"phone_number": "+254721143189"}
    )
    assert response.status_code == 200
    challenge = session.query(OtpChallenge).filter_by(purpose="reset").one()
    assert abs(
        (challenge.expires_at - challenge.created_at) - timedelta(minutes=10)
    ) < timedelta(seconds=1)
    challenge.expires_at = datetime.utcnow() - timedelta(seconds=1)
    session.commit()
    expired = client.post(
        "/api/auth/reset-password",
        json={
            "phone_number": "+254721143189",
            "otp": challenge.plaintext_code,
            "new_password": "Changed@2026!",
        },
    )
    assert expired.status_code == 401
    assert "expired" in expired.get_json()["error"]["message"].lower()
