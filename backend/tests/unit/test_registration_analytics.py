from datetime import date

from app.services.registration_analytics import (
    calculate_employee_performance,
    calculate_registration_analytics,
    registration_status,
)


def _report(**overrides):
    report = {
        "id": 1,
        "employee_id": 4,
        "agent_name": "Shop",
        "date_visited": "2026-04-03",
        "registration_date": None,
        "customer_type": "agent",
        "outcome": "ready_to_register",
        "documents": {
            "certificate_of_incorporation": "true",
            "company_kra_pin": True,
            "commission_statement": "yes",
            "owners_directors_national_ids": 1,
            "cr12_directors": "TRUE",
        },
        "witness_name": "Witness",
        "witness_id_number": "ID-1",
        "witness_phone": "0700000000",
        "report_data": {},
    }
    report.update(overrides)
    return report


def test_unknown_document_values_are_not_treated_as_submitted():
    incomplete = _report(documents={"certificate_of_incorporation": "unknown"})
    assert registration_status(incomplete) == "incomplete"


def test_registration_analytics_uses_eligible_visits_and_aggregate_rates():
    complete = _report(id=1)
    incomplete = _report(
        id=2,
        customer_type="sub_agent",
        documents={},
        witness_name="",
    )
    not_started = _report(
        id=3,
        outcome="appointment",
        registration_date=None,
        report_data={},
    )
    existing = _report(id=4, outcome="existing")

    result = calculate_registration_analytics([complete, incomplete, not_started, existing])
    totals = result["daily"]["totals"]

    assert totals["visited"] == 3
    assert totals["started"] == 2
    assert totals["complete"] == 1
    assert totals["incomplete"] == 1
    assert totals["not_started"] == 1
    assert totals["total_registrations"] == totals["complete"] + totals["incomplete"]
    assert totals["completion_rate"] == 50.0
    assert totals["visit_to_complete_rate"] == 33.33
    assert totals["unconverted"] == 1
    assert result["funnel"]["unconverted"] == 1
    assert result["statuses"]["rows"][2]["status"] == "not_started"
    document_row = next(
        row for row in result["documents"]
        if row["key"] == "certificate_of_incorporation"
    )
    assert document_row["category_label"] == "Agent"
    assert document_row["submission_rate"] == document_row["rate"]


def test_explicit_existing_client_forms_are_excluded_but_malformed_values_are_safe():
    explicit_existing = _report(
        id=1,
        outcome="interested",
        report_data={"new_client": "no"},
    )
    malformed_flag = _report(
        id=2,
        outcome="appointment",
        report_data={"new_client": "unknown"},
    )
    totals = calculate_registration_analytics([explicit_existing, malformed_flag])["daily"]["totals"]
    assert totals["visited"] == 1
    assert totals["not_started"] == 1


def test_employee_performance_uses_completion_dates_and_includes_zero_completion_peers():
    employees = [
        {"id": 4, "full_name": "Alex"},
        {"id": 5, "full_name": "Blair"},
    ]
    completed_agent = _report(id=1, employee_id=4, completion_date="2026-04-03")
    completed_sub_agent = _report(
        id=2,
        employee_id=4,
        customer_type="sub_agent",
        completion_date="2026-04-10",
        documents={
            "business_permit": True,
            "kra_pin": True,
            "commission_statement": True,
            "contract": True,
            "national_id": True,
            "sign_contract": True,
        },
    )
    outside_range = _report(id=3, employee_id=4, completion_date="2026-04-11")

    result = calculate_employee_performance(
        employees,
        [completed_agent, completed_sub_agent, outside_range],
        date(2026, 4, 1),
        date(2026, 4, 10),
    )

    assert result["total_complete"] == 2
    assert result["agent_complete"] == 1
    assert result["sub_agent_complete"] == 1
    assert result["team_average"] == 1.0
    assert result["rows"][0]["employee_name"] == "Alex"
    assert result["rows"][0]["performance"] == "above_average"
    assert result["rows"][1]["complete"] == 0
    assert result["rows"][1]["performance"] == "needs_support"
