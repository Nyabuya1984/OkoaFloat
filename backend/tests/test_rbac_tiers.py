import pytest

from app.models import User
from app.utils.rbac import ROLE_TIERS, SUPERUSER_TIER, user_tier


def make_user(role, is_superuser=False):
    return User(
        role=role,
        is_superuser=is_superuser,
        is_active=True,
        is_archived=False,
        is_deleted=False,
    )


@pytest.mark.parametrize(
    ("role", "is_superuser", "expected"),
    [
        ("employee", False, 1),
        ("manager", False, 2),
        ("hr_admin", False, 3),
        ("hr_admin", True, SUPERUSER_TIER),
    ],
)
def test_user_tier_matches_frozen_roles(role, is_superuser, expected):
    assert user_tier(make_user(role, is_superuser)) == expected


def test_invalid_role_has_no_tier():
    assert user_tier(make_user("invalid")) == 0
    assert ROLE_TIERS == {"employee": 1, "manager": 2, "hr_admin": 3}


def test_superuser_flag_does_not_create_a_new_role():
    user = make_user("manager", is_superuser=True)
    assert user_tier(user) == ROLE_TIERS["manager"]
