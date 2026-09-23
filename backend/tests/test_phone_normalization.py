import pytest

from app.utils.phone import (
    PhoneNormalizationError,
    is_valid_ke_phone,
    normalize_ke_phone,
    normalize_ke_phone_strict,
)


@pytest.mark.parametrize("raw,expected", [
    ("0721143189", "+254721143189"),
    ("721143189", "+254721143189"),
    ("254721143189", "+254721143189"),
    ("+254721143189", "+254721143189"),
    ("+254 721 143 189", "+254721143189"),
    ("+254-721-143-189", "+254721143189"),
    ("(0721) 143 189", "+254721143189"),
    ("  0721143189  ", "+254721143189"),
    ("0721143189\n", "+254721143189"),
    ("０７２１１４３１８９", "+254721143189"),
    ("00254721143189", "+254721143189"),
    ("0111431890", "+254111431890"),
    ("+254111431890", "+254111431890"),
])
def test_normalize_valid(raw, expected):
    assert normalize_ke_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    None, "", "   ", "abc", "07abc143189", "0712345",
    "07123456789", "+255712345678", "+14155552671", "+254",
    "+2540", "254",
])
def test_normalize_invalid(raw):
    assert normalize_ke_phone(raw) is None
    assert is_valid_ke_phone(raw) is False


def test_strict_raises():
    with pytest.raises(PhoneNormalizationError):
        normalize_ke_phone_strict("not-a-phone")


def test_idempotent():
    once = normalize_ke_phone("0721143189")
    twice = normalize_ke_phone(once)
    assert once == twice == "+254721143189"
