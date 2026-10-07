"""Email delivery used for authentication one-time passwords."""

import smtplib
from email.message import EmailMessage

from flask import current_app


class EmailDeliveryConfigurationError(RuntimeError):
    """Raised when OTP email delivery has not been configured."""


def send_otp_email(recipient, purpose, phone_number, code, expires_at):
    """Send an OTP using configured SMTP, or an injected test sender."""
    test_sender = current_app.config.get("OTP_EMAIL_SENDER")
    readable_purpose = purpose.replace("_", " ")
    subject = f"Okoa Float {readable_purpose} OTP for {phone_number}"
    body = (
        "Okoa Float account verification\n\n"
        f"Purpose: {readable_purpose.title()}\n"
        f"Phone number: {phone_number}\n"
        f"OTP: {code}\n\n"
        f"This code expires at {expires_at:%Y-%m-%d %H:%M UTC}. "
        "If you did not request this code, you can ignore this email."
    )
    if test_sender is not None:
        test_sender(recipient, subject, body)
        return

    config = current_app.config
    host = config.get("SMTP_HOST")
    sender = config.get("SMTP_FROM_EMAIL")
    if not host or not sender:
        missing = [
            name for name, value in (("SMTP_HOST", host), ("SMTP_FROM_EMAIL", sender))
            if not value
        ]
        raise EmailDeliveryConfigurationError(
            "Email OTP delivery is not configured; set " + " and ".join(missing)
        )
    if bool(config.get("SMTP_USERNAME")) != bool(config.get("SMTP_PASSWORD")):
        raise EmailDeliveryConfigurationError(
            "SMTP_USERNAME and SMTP_PASSWORD must both be set for authenticated SMTP; "
            "Gmail requires a Google App Password, not the regular account password"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    smtp_class = smtplib.SMTP_SSL if config.get("SMTP_USE_SSL") else smtplib.SMTP
    try:
        with smtp_class(host, int(config.get("SMTP_PORT", 587)), timeout=15) as client:
            if config.get("SMTP_USE_TLS") and not config.get("SMTP_USE_SSL"):
                client.starttls()
            username = config.get("SMTP_USERNAME")
            if username:
                client.login(username, config.get("SMTP_PASSWORD"))
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        current_app.logger.exception("SMTP delivery failed for authentication OTP")
        raise RuntimeError("Email OTP delivery failed; verify SMTP configuration and connectivity") from exc
