from datetime import datetime

from app.extensions import db


class OtpChallenge(db.Model):
    __tablename__ = "OTP"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    email_address = db.Column(db.String(255), nullable=False)
    personal_email_address = db.Column(db.String(255), nullable=True)
    plaintext_code = db.Column(db.String(6), nullable=True)
    purpose = db.Column(
        db.Enum("registration", "login", "password_reset", "account_recovery", name="otp_purpose"),
        nullable=False,
    )
    code_hash = db.Column(db.String(128), nullable=False)
    status = db.Column(
        db.Enum("active", "expired", "verified", name="otp_status"),
        nullable=False,
        default="active",
        index=True,
    )
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AuthSession(db.Model):
    __tablename__ = "auth_sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)