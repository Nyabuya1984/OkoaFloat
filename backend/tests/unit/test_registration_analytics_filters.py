from datetime import date, timedelta
from types import SimpleNamespace

from flask import Flask

from app.api.sales import _analytics_filters


def _report(outcome, appointment_date=None):
    return SimpleNamespace(
        date_visited=date.today(),
        employee_id=10,
        customer_type="agent",
        outcome=outcome,
        business_location="Nairobi",
        agent_name="Shop",
        agent_number=None,
        store_number=None,
        business_owner_name=None,
        notes=None,
        report_data={"appointment_date": appointment_date} if appointment_date else {},
        documents={},
        witness_name=None,
        witness_id_number=None,
        witness_phone=None,
        registration_date=None,
        completion_date=None,
    )


def _filtered(query, reports):
    app = Flask(__name__)
    with app.test_request_context(f"/?{query}"):
        return list(_analytics_filters(reports))


def test_appointment_filter_supports_upcoming_past_and_boolean_values():
    today = date.today()
    future = _report("appointment", (today + timedelta(days=1)).isoformat())
    past = _report("appointment", (today - timedelta(days=1)).isoformat())
    no_date = _report("appointment")

    assert _filtered("appointment=upcoming", [future, past, no_date]) == [future]
    assert _filtered("appointment=past", [future, past, no_date]) == [past]
    assert _filtered("appointment=true", [future, no_date]) == [future, no_date]
    assert _filtered("outcome=appointment", [future, _report("interested")]) == [future]


def test_unconverted_definition_is_eligible_not_started():
    complete = {
        "customer_type": "agent",
        "outcome": "ready_to_register",
        "documents": {
            "certificate_of_incorporation": True,
            "company_kra_pin": True,
            "six_months_commission": True,
            "owners_directors_national_ids": True,
            "cr12_directors": True,
        },
        "witness_name": "Witness",
        "witness_id_number": "ID",
        "witness_phone": "Phone",
        "report_data": {},
    }
    not_started = {
        **complete,
        "outcome": "appointment",
        "documents": {},
        "report_data": {},
    }
    from app.services.registration_analytics import calculate_registration_analytics

    totals = calculate_registration_analytics([complete, not_started])["daily"]["totals"]
    assert totals["unconverted"] == 1
    assert totals["visited"] - totals["started"] == totals["unconverted"]


def test_completion_date_filters_do_not_fall_back_to_visit_dates():
    completed_in_range = _report("registered")
    completed_in_range.completion_date = date(2026, 4, 5)
    completed_outside_range = _report("registered")
    completed_outside_range.completion_date = date(2026, 4, 8)
    missing_completion_date = _report("registered")

    matches = _filtered(
        "completion_from=2026-04-01&completion_to=2026-04-07",
        [completed_in_range, completed_outside_range, missing_completion_date],
    )

    assert matches == [completed_in_range]
