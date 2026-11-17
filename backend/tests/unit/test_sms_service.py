import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.api.auth import _otp_generated_message, _password_reset_message
from app.services.sms import (
    compose_otp_message,
    format_onfon_phone,
    get_sms_config,
    send_otp_sms,
    send_sms,
)


def test_format_onfon_phone():
    assert format_onfon_phone("+254712345678") == "254712345678"
    assert format_onfon_phone("0712345678") == "254712345678"
    assert format_onfon_phone("0112345678") == "254112345678"
    assert format_onfon_phone("+254112345678") == "254112345678"
    assert format_onfon_phone("254712345678") == "254712345678"
    assert format_onfon_phone("") is None
    assert format_onfon_phone(None) is None


def test_compose_otp_message():
    msg_login = compose_otp_message("123456", "login")
    assert "123456" in msg_login
    assert "sign-in" in msg_login
    assert "10 minutes" in msg_login

    msg_reg = compose_otp_message("654321", "registration")
    assert "654321" in msg_reg
    assert "registration" in msg_reg

    msg_reset = compose_otp_message("999888", "reset")
    assert "999888" in msg_reset
    assert "password reset" in msg_reset

    msg_recovery = compose_otp_message("111222", "account_recovery")
    assert "111222" in msg_recovery
    assert "account recovery" in msg_recovery


def test_send_sms_disabled(monkeypatch):
    monkeypatch.setenv("SMS_ENABLED", "false")
    success, detail = send_sms("+254712345678", "Test")
    assert success is False
    assert "disabled" in detail


def test_send_sms_missing_credentials(monkeypatch):
    monkeypatch.setenv("SMS_ENABLED", "true")
    monkeypatch.setenv("ONFON_ACCESS_KEY", "")
    monkeypatch.setenv("ONFON_API_KEY", "")
    monkeypatch.setenv("ONFON_CLIENT_ID", "")
    success, detail = send_sms("+254712345678", "Test")
    assert success is False
    assert "incomplete" in detail


def test_send_sms_success(monkeypatch):
    monkeypatch.setenv("SMS_ENABLED", "true")
    monkeypatch.setenv("ONFON_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("ONFON_API_KEY", "test-api-key")
    monkeypatch.setenv("ONFON_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ONFON_SENDER_ID", "OKOAFLOAT")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({
        "ErrorCode": 0,
        "ErrorDescription": "Success",
        "Data": [{"MessageErrorCode": 0, "MessageErrorDescription": "Success"}]
    }).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        success, detail = send_sms("+254712345678", "Your code is 123456")
        assert success is True
        assert detail is None
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.headers["Accesskey"] == "test-access-key"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["SenderId"] == "OKOAFLOAT"
        assert payload["MessageParameters"][0]["Number"] == "254712345678"
        assert payload["MessageParameters"][0]["Text"] == "Your code is 123456"


def test_send_sms_rejection(monkeypatch):
    monkeypatch.setenv("SMS_ENABLED", "true")
    monkeypatch.setenv("ONFON_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("ONFON_API_KEY", "test-api-key")
    monkeypatch.setenv("ONFON_CLIENT_ID", "test-client-id")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({
        "ErrorCode": 0,
        "ErrorDescription": "null",
        "Data": [{"MessageErrorCode": 401, "MessageErrorDescription": "source_address filter mismatch"}]
    }).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success, detail = send_sms("+254712345678", "Test")
        assert success is False
        assert "source_address filter mismatch" in detail


def test_send_sms_network_error(monkeypatch):
    monkeypatch.setenv("SMS_ENABLED", "true")
    monkeypatch.setenv("ONFON_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("ONFON_API_KEY", "test-api-key")
    monkeypatch.setenv("ONFON_CLIENT_ID", "test-client-id")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        success, detail = send_sms("+254712345678", "Test")
        assert success is False
        assert "Failed to deliver SMS" in detail


def test_otp_messages():
    msg = _otp_generated_message("verification", sms_sent=True)
    assert "accepted your 6-digit verification code request" in msg
    assert "Delivery to your phone is not confirmed" in msg

    msg_masked = _otp_generated_message("verification", sms_sent=True, phone_number="+254712345678")
    assert "phone number ending in ...5678" in msg_masked
    assert "Delivery to your phone is not confirmed" in msg_masked

    msg_dev = _otp_generated_message("verification", sms_sent=False)
    assert "couldn't send" in msg_dev

    reset_sms = _password_reset_message(sms_sent=True, phone_number="+254712345678")
    assert "sent to your phone number ending in ...5678" in reset_sms

    reset_dev = _password_reset_message(sms_sent=False)
    assert "couldn't send" in reset_dev


if __name__ == "__main__":
    test_format_onfon_phone()
    test_compose_otp_message()
    from unittest.mock import patch
    import os
    class MonkeyPatch:
        def setenv(self, k, v):
            os.environ[k] = v
    mp = MonkeyPatch()
    test_send_sms_disabled(mp)
    test_send_sms_missing_credentials(mp)
    test_send_sms_success(mp)
    test_send_sms_rejection(mp)
    test_send_sms_network_error(mp)
    test_otp_messages()
    print("ALL SMS SERVICE TESTS PASSED!")
