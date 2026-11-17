"""SMTP delivery for one-time password codes."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from app.services.sms import compose_otp_message

logger = logging.getLogger(__name__)


def send_otp_email(email_address, code, purpose="verification"):
    """Send an OTP email, returning ``(sent, error)``."""
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")
    sender = current_app.config.get("MAIL_DEFAULT_SENDER") or username
    if not username or not password or not sender:
        return False, "SMTP credentials or sender are not configured"

    use_tls = bool(current_app.config.get("MAIL_USE_TLS", True))
    use_ssl = bool(current_app.config.get("MAIL_USE_SSL", False))
    if use_tls == use_ssl:
        return False, "Enable exactly one of MAIL_USE_TLS or MAIL_USE_SSL"

    action = (purpose or "verification").replace("_", " ").strip().title()
    message = EmailMessage()
    message["Subject"] = f"Okoa Float {action} code"
    message["From"] = sender
    message["To"] = email_address
    message.set_content(compose_otp_message(code, purpose))

    host = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(current_app.config.get("MAIL_PORT", 587))
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with smtp_class(host, port, timeout=12) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)
        return True, None
    except Exception as error:
        logger.exception("Failed to send OTP email to %s", email_address)
        return False, str(error)