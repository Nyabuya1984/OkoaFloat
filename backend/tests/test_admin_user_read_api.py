from app.api.admin import VALID_STATUSES


def test_admin_user_list_supports_all_lifecycle_statuses():
    assert VALID_STATUSES == {
        "active",
        "deactivated",
        "archived",
        "deleted",
        "all",
    }
