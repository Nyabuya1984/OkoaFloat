import re
from datetime import datetime, timedelta

from flask import Flask

from app.extensions import db
from app.models import OtpChallenge, User
from app.utils.email_delivery import send_otp_email


def test_gmail_smtp_uses_starttls_and_app_password(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["From"]))

    monkeypatch.setattr("app.utils.email_delivery.smtplib.SMTP", FakeSMTP)
    app = Flask(__name__)
    app.config.update(
        SMTP_HOST="smtp.gmail.com",
        SMTP_PORT=587,
        SMTP_USERNAME="sender@gmail.com",
        SMTP_PASSWORD="google-app-password",
        SMTP_FROM_EMAIL="sender@gmail.com",
        SMTP_USE_TLS=True,
        SMTP_USE_SSL=False,
    )

    with app.app_context():
        send_otp_email(
            "recipient@example.com",
            "login",
            "+254712345678",
            "012345",
            datetime(2026, 10, 4, 18, 0),
        )

    assert calls == [
        ("connect", "smtp.gmail.com", 587, 15),
        ("starttls",),
        ("login", "sender@gmail.com", "google-app-password"),
        ("send", "recipient@example.com", "sender@gmail.com"),
    ]


def _latest_code(app, recipient):
    sent = [
        message
        for message in app.config["TEST_EMAIL_OUTBOX"]
        if message["recipient"] == recipient
    ][-1]
    return re.search(r"OTP: (\d{6})", sent["body"]).group(1)


def test_registration_delivers_to_any_valid_registered_email_and_requires_confirmation(
    client, app, session
):
    response = client.post(
        "/api/auth/register",
        json={
            "employee_name": "Custom Domain User",
            "job_position_title": "Analyst",
            "employer": "Okoa Float",
            "department": "Sales",
            "email": "  User@Mail.Custom  ",
            "personal_email": " User.Personal@Mail.Custom ",
            "phone_number": "+254712300001",
            "password": "Password@2026",
        },
    )
    assert response.status_code == 201, response.get_json()
    assert {item["recipient"] for item in app.config["TEST_EMAIL_OUTBOX"][-2:]} == {
        "user@mail.custom",
        "user.personal@mail.custom",
    }
    user = session.query(User).filter_by(phone_number="+254712300001").one()
    assert user.email == "user@mail.custom"
    assert user.personal_email == "user.personal@mail.custom"
    challenge = session.query(OtpChallenge).filter_by(user_id=user.id, purpose="registration").one()

    code = _latest_code(app, "user@mail.custom")
    assert challenge.plaintext_code == code
    mismatch = client.post(
        "/api/auth/verify-registration",
        json={"phone_number": user.phone_number, "email": "someone@mail.custom", "otp": code},
    )
    assert mismatch.status_code == 401
    session.refresh(challenge)
    assert challenge.status == "active"

    verified = client.post(
        "/api/auth/verify-registration",
        json={"phone_number": user.phone_number, "email": " USER.PERSONAL@MAIL.CUSTOM ", "otp": code},
    )
    assert verified.status_code == 200


def test_login_sends_to_saved_email_and_confirmation_is_strict(
    client, app, session, capsys
):
    response = client.post(
        "/api/auth/login",
        json={"phone_number": "+254700000001", "password": "Admin@2026!"},
    )
    assert response.status_code == 200, response.get_json()
    assert {item["recipient"] for item in app.config["TEST_EMAIL_OUTBOX"][-2:]} == {
        "admin@okoa.local",
        "admin.personal@example.com",
    }
    code = _latest_code(app, "admin@okoa.local")
    wrong_email = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "+254700000001", "email": "other@okoa.local", "otp": code},
    )
    assert wrong_email.status_code == 401
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254700000001", purpose="login"
    ).one()
    assert challenge.plaintext_code == code
    console_output = capsys.readouterr().out
    assert "OKOA FLOAT VERIFICATION CODE" in console_output
    assert "PURPOSE: LOGIN" in console_output
    assert "PHONE:   +254700000001" in console_output
    assert f"OTP:     {code}" in console_output
    assert challenge.status == "active"

    verified = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "+254700000001", "otp": code},
    )
    assert verified.status_code == 200
    assert verified.get_json()["access_token"]


def test_password_and_phone_recovery_use_registered_email(client, app, session):
    requested = client.post(
        "/api/auth/request-password-reset", json={"email": "ADMIN.PERSONAL@EXAMPLE.COM"}
    )
    assert requested.status_code == 200, requested.get_json()
    assert app.config["TEST_EMAIL_OUTBOX"][-1]["recipient"] == "admin.personal@example.com"
    reset_code = _latest_code(app, "admin@okoa.local")
    mismatch = client.post(
        "/api/auth/reset-password",
        json={
            "email": "not-admin@okoa.local",
            "otp": reset_code,
            "new_password": "Changed@2026!",
        },
    )
    assert mismatch.status_code == 401
    reset = client.post(
        "/api/auth/reset-password",
        json={
            "email": " admin.personal@example.com ",
            "otp": reset_code,
            "new_password": "Changed@2026!",
        },
    )
    assert reset.status_code == 200
    assert session.query(User).filter_by(phone_number="+254700000001").one().check_password(
        "Changed@2026!"
    )

    requested = client.post(
        "/api/auth/request-phone-recovery", json={"email": "admin.personal@example.com"}
    )
    assert requested.status_code == 200
    recovery_code = _latest_code(app, "admin@okoa.local")
    recovered = client.post(
        "/api/auth/recover-phone",
        json={"email": "ADMIN.PERSONAL@EXAMPLE.COM", "otp": recovery_code},
    )
    assert recovered.status_code == 200
    assert recovered.get_json()["phone_number"] == "+254700000001"


def test_email_delivery_not_configured_keeps_local_otp_available(
    client, app, session, monkeypatch, capsys
):
    monkeypatch.setitem(app.config, "OTP_EMAIL_SENDER", None)
    monkeypatch.setitem(app.config, "SMTP_HOST", None)
    monkeypatch.setitem(app.config, "SMTP_FROM_EMAIL", None)
    response = client.post(
        "/api/auth/login",
        json={"phone_number": "+254700000001", "password": "Admin@2026!"},
    )
    assert response.status_code == 200
    assert response.get_json()["email_sent"] is False
    assert "development database and shown in the server console" in response.get_json()["message"]
    challenge = session.query(OtpChallenge).filter_by(purpose="login").one()
    assert challenge.plaintext_code is not None
    console_output = capsys.readouterr().out
    assert "OKOA FLOAT VERIFICATION CODE" in console_output
    assert "PURPOSE: LOGIN" in console_output
    assert "PHONE:   +254700000001" in console_output
    assert f"OTP:     {challenge.plaintext_code}" in console_output


def test_failed_work_email_does_not_skip_personal_email_attempt(
    client, app, monkeypatch
):
    attempted = []

    def send_email(recipient, purpose, phone_number, code, expires_at):
        attempted.append(recipient)
        if recipient == "admin@okoa.local":
            raise RuntimeError("work mailbox delivery failed")
        app.config["TEST_EMAIL_OUTBOX"].append(
            {
                "recipient": recipient,
                "subject": f"Okoa Float {purpose} OTP for {phone_number}",
                "body": f"OTP: {code}",
            }
        )

    monkeypatch.setattr("app.api.auth.send_otp_email", send_email)
    response = client.post(
        "/api/auth/login",
        json={"phone_number": "+254700000001", "password": "Admin@2026!"},
    )

    assert response.status_code == 200
    assert response.get_json()["email_sent"] is False
    assert attempted == ["admin@okoa.local", "admin.personal@example.com"]


def test_email_otp_message_identifies_purpose_and_phone(client, app):
    client.post(
        "/api/auth/login",
        json={"phone_number": "+254700000001", "password": "Admin@2026!"},
    )
    message = app.config["TEST_EMAIL_OUTBOX"][-2]
    assert message["subject"] == "Okoa Float login OTP for +254700000001"
    assert "Purpose: Login" in message["body"]
    assert "Phone number: +254700000001" in message["body"]
    assert "OTP: " in message["body"]


def test_admin_created_user_requires_and_saves_personal_email(client, admin_token, session):
    response = client.post(
        "/api/auth/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Admin Created User",
            "email": "created.work@example.com",
            "personal_email": "created.personal@example.com",
            "phone_number": "+254712300002",
            "password": "Password@2026",
            "department": "Sales",
        },
    )
    assert response.status_code == 200, response.get_json()
    user = session.query(User).filter_by(email="created.work@example.com").one()
    assert user.personal_email == "created.personal@example.com"


def test_otp_expires_two_hours_after_issue(client, session):
    response = client.post(
        "/api/auth/request-password-reset", json={"email": "admin@okoa.local"}
    )
    assert response.status_code == 200
    challenge = session.query(OtpChallenge).filter_by(purpose="password_reset").one()
    assert abs(
        (challenge.expires_at - challenge.created_at) - timedelta(hours=2)
    ) < timedelta(seconds=1)
    challenge.expires_at = datetime.utcnow() - timedelta(seconds=1)
    session.commit()
    expired = client.post(
        "/api/auth/reset-password",
        json={
            "email": "admin@okoa.local",
            "otp": _latest_code(client.application, "admin@okoa.local"),
            "new_password": "Changed@2026!",
        },
    )
    assert expired.status_code == 401
    assert "expired" in expired.get_json()["error"]["message"].lower()
