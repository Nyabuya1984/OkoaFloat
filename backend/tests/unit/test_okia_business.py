import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.utils.okia_business import (
    ESCALATION_CATEGORIES,
    compute_shift,
    generate_reference_number,
    should_escalate,
    validate_caller_fields,
)


TZ = ZoneInfo("Africa/Nairobi")


@pytest.mark.parametrize(
    ("local_time", "expected"),
    [
        ((2026, 10, 12, 7, 59), "C"),   # Monday before A
        ((2026, 10, 12, 8, 0), "A"),
        ((2026, 10, 14, 11, 59), "A"),
        ((2026, 10, 14, 12, 0), "B"),
        ((2026, 10, 16, 15, 59), "B"),
        ((2026, 10, 16, 16, 0), "C"),
        ((2026, 10, 18, 23, 59), "C"),
        ((2026, 10, 19, 7, 59), "C"),
    ],
)
def test_compute_shift_boundaries(local_time, expected):
    assert compute_shift(datetime(*local_time, tzinfo=TZ)) == expected


@pytest.mark.parametrize("category", sorted(ESCALATION_CATEGORIES))
def test_each_escalation_trigger_category_is_escalated(category):
    required, department = should_escalate(category, "Normal", None)
    assert required is True
    assert department == ("it_support" if category == "USSD_ISSUE" else "general_manager")


def test_urgent_escalates_and_non_trigger_does_not():
    assert should_escalate("GENERAL_INQUIRY", "Urgent", None) == (True, "general_manager")
    assert should_escalate("GENERAL_INQUIRY", "Normal", None) == (False, None)
    assert should_escalate("GENERAL_INQUIRY", "Normal", "USSD downtime") == (True, "it_support")


def test_reference_numbers_have_required_format_and_are_unique():
    first = generate_reference_number()
    second = generate_reference_number()
    assert re.fullmatch(r"OF-\d{4}-\d{6}", first)
    assert first != second


def test_caller_fields_required_for_agent_and_sub_agent():
    with pytest.raises(ValueError, match="agent_name"):
        validate_caller_fields("agent", {})
    with pytest.raises(ValueError, match="store_number"):
        validate_caller_fields(
            "sub_agent",
            {"agent_name": "Wanjiku", "agent_number": "A12", "location": "Nairobi"},
        )
    validate_caller_fields(
        "agent",
        {"agent_name": "Wanjiku", "agent_number": "A12", "store_number": "S5", "location": "Nairobi"},
    )
