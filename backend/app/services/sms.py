"""
SMS Delivery Service using Onfon Media Bulk SMS API.
Dispatches OTP codes to users' mobile phones.
"""
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Optional, Tuple

from flask import current_app, has_app_context

from app.utils.phone import normalize_ke_phone

logger = logging.getLogger(__name__)


def format_onfon_phone(phone_number: str) -> Optional[str]:
    """
    Format phone number to Kenyan MSISDN standard expected by Onfon (e.g. 254712345678).
    """
    if not phone_number:
        return None
    normalized = normalize_ke_phone(phone_number)
    if normalized:
        # normalize_ke_phone returns +254..., strip leading '+'
        return normalized.lstrip("+")

    # Fallback cleanup
    digits = re.sub(r"\D", "", str(phone_number))
    if digits.startswith("0") and len(digits) == 10:
        return f"254{digits[1:]}"
    if digits.startswith("254") and len(digits) == 12:
        return digits
    return digits if digits else None


def _get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve config value from Flask current_app or environment variable."""
    if has_app_context() and current_app:
        val = current_app.config.get(key)
        if val is not None and str(val).strip() != "":
            return str(val)
    return os.environ.get(key, default)


def get_sms_config() -> dict:
    """Return configured Onfon Media SMS API parameters."""
    return {
        "enabled": _get_config_value("SMS_ENABLED", "true").lower() in ("true", "1", "yes"),
        "url": _get_config_value("ONFON_SMS_URL", "https://api.onfonmedia.com/v1/sms/SendBulkSMS"),
        "access_key": _get_config_value("ONFON_ACCESS_KEY", ""),
        "api_key": _get_config_value("ONFON_API_KEY", ""),
        "client_id": _get_config_value("ONFON_CLIENT_ID", ""),
        "sender_id": _get_config_value("ONFON_SENDER_ID", ""),
    }


def compose_otp_message(code: str, purpose: str = "verification") -> str:
    """Compose clear, professional SMS text for OTP verification."""
    purpose_clean = (purpose or "verification").lower().replace("_", " ").strip()
    if "login" in purpose_clean:
        action = "sign-in"
    elif "register" in purpose_clean or "registration" in purpose_clean:
        action = "registration"
    elif "reset" in purpose_clean or "password" in purpose_clean:
        action = "password reset"
    elif "recovery" in purpose_clean:
        action = "account recovery"
    else:
        action = "verification"

    return (
        f"Your Okoa Float {action} code is: {code}. "
        "Valid for 10 minutes. Do not share this code with anyone."
    )


def send_sms(phone_number: str, text: str) -> Tuple[bool, Optional[str]]:
    """
    Send an SMS message to a mobile number via Onfon Media Bulk SMS API.
    
    Returns:
        (success: bool, detail: Optional[str])
    """
    config = get_sms_config()

    if not config["enabled"]:
        msg = "SMS sending is disabled in configuration."
        logger.info(msg)
        return False, msg

    access_key = config["access_key"]
    api_key = config["api_key"]
    client_id = config["client_id"]
    sender_id = config["sender_id"] or ""
    url = config["url"]

    if not access_key or not api_key or not client_id:
        msg = "Onfon SMS credentials (ONFON_ACCESS_KEY, ONFON_API_KEY, ONFON_CLIENT_ID) are incomplete."
        logger.warning(msg)
        return False, msg

    formatted_number = format_onfon_phone(phone_number)
    if not formatted_number:
        msg = f"Invalid phone number for SMS dispatch: {phone_number}"
        logger.warning(msg)
        return False, msg

    payload = {
        "SenderId": sender_id,
        "MessageParameters": [
            {
                "Number": formatted_number,
                "Text": text,
            }
        ],
        "ApiKey": api_key,
        "ClientId": client_id,
    }

    headers = {
        "Accesskey": access_key,
        "Content-Type": "application/json",
        "User-Agent": "OkoaFloat-Backend/1.0",
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=12) as response:
            status_code = response.status
            body = response.read().decode("utf-8")

        response_json = json.loads(body)
        error_code = response_json.get("ErrorCode")
        error_desc = response_json.get("ErrorDescription")

        # In Onfon API, ErrorCode 0 or "0" indicates success at gateway
        data_list = response_json.get("Data") or []
        first_item = data_list[0] if data_list and isinstance(data_list, list) else {}
        item_error_code = first_item.get("MessageErrorCode")
        item_error_desc = first_item.get("MessageErrorDescription")

        # Check for message level rejection (e.g. 401 source address filter mismatch)
        if item_error_code not in (0, "0", "000", None, ""):
            err_msg = f"Onfon SMS dispatch rejected: {item_error_desc or item_error_code}"
            logger.error(err_msg)
            return False, err_msg

        if error_code in (0, "0", "000"):
            logger.info("SMS successfully dispatched to %s via Onfon Media.", formatted_number)
            return True, None

        err_msg = f"Onfon SMS returned error: {error_code} - {error_desc}"
        logger.error(err_msg)
        return False, err_msg

    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        err_msg = f"Onfon SMS HTTP error {exc.code}: {err_body}"
        logger.error(err_msg)
        return False, err_msg
    except Exception as exc:
        err_msg = f"Failed to deliver SMS to {phone_number}: {exc}"
        logger.exception(err_msg)
        return False, err_msg


def send_otp_sms(phone_number: str, code: str, purpose: str = "verification") -> Tuple[bool, Optional[str]]:
    """
    Format and send an OTP verification SMS to a mobile phone.
    
    Returns:
        (success: bool, detail: Optional[str])
    """
    message = compose_otp_message(code, purpose)
    return send_sms(phone_number, message)
