from datetime import datetime, timezone
from types import SimpleNamespace

from app.utils.location_tracking import next_schedule_boundary, schedule_is_active


def _policy(**overrides):
    values = {
        "is_enabled": True,
        "timezone": "Africa/Nairobi",
        "days": ["mon", "tue", "wed", "thu", "fri"],
        "start_time": "08:00",
        "end_time": "17:00",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_tracking_schedule_uses_local_weekdays_and_end_time():
    policy = _policy()

    monday_work_hours = datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)
    monday_after_hours = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 10, 24, 6, 0, tzinfo=timezone.utc)

    assert schedule_is_active(policy, monday_work_hours) is True
    assert schedule_is_active(policy, monday_after_hours) is False
    assert schedule_is_active(policy, saturday) is False


def test_tracking_schedule_supports_overnight_windows():
    policy = _policy(days=["fri"], start_time="22:00", end_time="02:00")

    saturday_early_morning = datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)

    assert schedule_is_active(policy, saturday_early_morning) is True


def test_next_transition_is_returned_as_utc():
    policy = _policy()
    now = datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)

    assert next_schedule_boundary(policy, now) == datetime(2026, 10, 26, 14, 0)


def test_disabled_schedule_never_tracks_or_has_a_next_boundary():
    policy = _policy(is_enabled=False)
    now = datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)

    assert schedule_is_active(policy, now) is False
    assert next_schedule_boundary(policy, now) is None
