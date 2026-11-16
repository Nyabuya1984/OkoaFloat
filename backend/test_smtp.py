"""Send a one-off SMTP test email using the backend environment."""

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))


def main():
    host = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    sender = os.environ.get("MAIL_DEFAULT_SENDER") or username
    recipient = os.environ.get("MAIL_TEST_RECIPIENT") or sender
    use_ssl = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"

    if not username or not password or not sender or not recipient:
        print(
            "SMTP test not run: set MAIL_USERNAME, MAIL_PASSWORD, "
            "and MAIL_DEFAULT_SENDER in backend/.env."
        )
        return 2
    if use_ssl == use_tls:
        print("SMTP test not run: enable exactly one of MAIL_USE_TLS or MAIL_USE_SSL.")
        return 2

    message = EmailMessage()
    message["Subject"] = "Okoa Float SMTP connectivity test"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("This is a test message verifying Gmail SMTP delivery.")

    try:
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as server:
            if use_tls and not use_ssl:
                server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)
    except smtplib.SMTPResponseException as exc:
        response = exc.smtp_error.decode("utf-8", errors="replace")
        print(f"SMTP test failed: SMTP {exc.smtp_code}: {response}")
        return 1
    except (OSError, smtplib.SMTPException) as exc:
        print(f"SMTP test failed: {type(exc).__name__}: {exc}")
        return 1

    print("SMTP test succeeded; test email sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
