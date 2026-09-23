from app.models import User
from app.utils.rbac import is_super_admin


def test_user_state_precedence_and_active_helper():
    user = User(is_active=True, is_archived=False, is_deleted=False)
    assert user.state() == "active"
    assert user.is_currently_active() is True

    user.is_active = False
    assert user.state() == "deactivated"
    assert user.is_currently_active() is False

    user.is_archived = True
    assert user.state() == "archived"

    user.is_deleted = True
    assert user.state() == "deleted"


def test_user_defaults_are_defined_for_lifecycle_flags():
    assert User.is_active.default.arg is True
    assert User.is_archived.default.arg is False
    assert User.is_deleted.default.arg is False


def test_only_superuser_accounts_are_classified_as_super_admin():
    regular_user = User(role="hr_admin", is_superuser=False)
    super_admin = User(role="hr_admin", is_superuser=True)

    assert is_super_admin(regular_user) is False
    assert is_super_admin(super_admin) is True
    assert is_super_admin(None) is False
