"""Kenyan phone number normalization to E.164 format."""
import re
from typing import Optional

KE_CC = "254"
_KE_NSN_RE = re.compile(r"^[71]\d{8}$")
_FULLWIDTH_MAP = str.maketrans("０１２３４５６７８９", "0123456789")


class PhoneNormalizationError(ValueError):
    """Raised when a phone number cannot be normalized."""


def normalize_ke_phone(raw: Optional[str]) -> Optional[str]:
    """Normalize a Kenyan mobile/fixed number to +254[71]XXXXXXXX."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raw = str(raw)
    value = raw.strip().translate(_FULLWIDTH_MAP)
    if not value:
        return None

    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    digits = digits.lstrip("0")
    if digits.startswith(KE_CC):
        digits = digits[len(KE_CC):]
    digits = digits.lstrip("0")
    if not _KE_NSN_RE.fullmatch(digits):
        return None
    return f"+{KE_CC}{digits}"


def normalize_ke_phone_strict(raw: Optional[str]) -> str:
    """Normalize a phone or raise a validation error."""
    result = normalize_ke_phone(raw)
    if result is None:
        raise PhoneNormalizationError(f"Invalid Kenyan phone number: {raw!r}")
    return result


def is_valid_ke_phone(raw: Optional[str]) -> bool:
    """Return whether raw is a valid Kenyan phone input."""
    return normalize_ke_phone(raw) is not None
