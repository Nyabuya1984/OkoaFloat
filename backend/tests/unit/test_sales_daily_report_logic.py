from datetime import date
from types import SimpleNamespace

import pytest

from app.api.sales import DOCUMENT_REQUIREMENTS, _create_report


def _payload(category, outcome="ready_to_register", **overrides):
    customer_type = "sub_agent" if category == "sub_agent" else "agent"
    payload = {
        "agent_name": "Sample Agent",
        "agent_number": "AG-101",
        "store_number": "STORE-1",
        "business_owner_name": "Business Owner",
        "id_number": "ID-100",
        "contact_phone": "0712345678",
        "business_location": "Nairobi",
        "date_visited": "2026-10-22",
        "registration_date": "2026-10-23",
        "customer_type": customer_type,
        "outcome": outcome,
        "new_client": "true",
        "witness_name": "Witness Name",
        "witness_id_number": "ID-10",
        "witness_phone": "0712345678",
        "documents": {},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("category", ["agent", "sub_agent"])
def test_ready_to_register_status_uses_each_category_checklist(category):
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    incomplete, error, _ = _create_report(employee, _payload(category))
    assert error is None
    assert incomplete.report_data["registration_status"] == "INCOMPLETE"
    assert incomplete.business_owner_name == "Business Owner"
    assert incomplete.id_number == "ID-100"
    assert incomplete.contact_phone == "0712345678"

    complete_payload = _payload(
        category,
        **{field: "true" for field in DOCUMENT_REQUIREMENTS[category]},
    )
    complete, error, _ = _create_report(employee, complete_payload)

    assert error is None
    assert complete.report_data["registration_status"] == "COMPLETE"
    assert complete.report_data["client_type"] == "new"


def test_ready_to_register_does_not_trust_client_supplied_registration_status():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = _payload("sub_agent", registration_status="COMPLETE")
    report, error, _ = _create_report(employee, payload)

    assert error is None
    assert report.report_data["registration_status"] == "INCOMPLETE"


def test_existing_referral_contact_and_required_visit_fields_are_validated():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = {
        "agent_name": "Sample Agent",
        "agent_number": "AG-101",
        "store_number": "STORE-1",
        "business_owner_name": "Business Owner",
        "id_number": "ID-100",
        "contact_phone": "0712345678",
        "business_location": "Nairobi",
        "date_visited": date.today().isoformat(),
        "customer_type": "agent",
        "outcome": "existing",
        "new_client": "false",
        "referral_agreed": "yes",
        "referral_name": "Referral Contact",
        "notes": "Visited the outlet",
    }
    report, error, status = _create_report(employee, payload)
    assert report is None
    assert status == 422
    assert "referral contact number" in error

    payload["referral_contact_number"] = "0712345678"
    payload["referral_details"] = "Owner of the neighboring outlet"
    report, error, _ = _create_report(employee, payload)

    assert error is None
    assert report.report_data["referral_contact_number"] == "0712345678"
    assert report.report_data["referral_name"] == "Referral Contact"
    assert report.report_data["referral_details"] == "Owner of the neighboring outlet"


def test_existing_referral_name_is_required_when_referral_is_agreed():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = {
        "agent_name": "Sample Agent",
        "agent_number": "AG-101",
        "store_number": "STORE-1",
        "business_owner_name": "Business Owner",
        "id_number": "ID-100",
        "contact_phone": "0712345678",
        "business_location": "Nairobi",
        "date_visited": date.today().isoformat(),
        "customer_type": "agent",
        "outcome": "existing",
        "new_client": "false",
        "referral_agreed": "yes",
        "referral_contact_number": "0712345678",
        "notes": "Visited the outlet",
    }
    report, error, status = _create_report(employee, payload)

    assert report is None
    assert status == 422
    assert error == "A referral name is required when a referral is agreed"


def test_existing_client_interaction_does_not_require_reentering_owner_details():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    report, error, status = _create_report(
        employee,
        {
            "agent_name": "Existing Agent",
            "agent_number": "AG-202",
            "store_number": "STORE-202",
            "business_location": "Nairobi",
            "date_visited": date.today().isoformat(),
            "customer_type": "agent",
            "outcome": "existing",
            "new_client": "false",
            "notes": "Followed up on the previous issue.",
            "referral_agreed": "no",
        },
    )

    assert status == 201
    assert error is None
    assert report.business_owner_name is None
    assert report.report_data["referral_agreed"] == "no"


def test_appointment_accepts_valid_date_time_and_remarks():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = _payload(
        "agent",
        outcome="appointment",
        registration_date="",
        appointment_date="2026-11-01",
        appointment_time="14:30",
        notes="Return to complete registration",
    )
    report, error, status = _create_report(employee, payload)

    assert error is None
    assert status == 201
    assert report.report_data["appointment_date"] == "2026-11-01"

    payload["appointment_time"] = "not-a-time"
    report, error, status = _create_report(employee, payload)
    assert report is None
    assert status == 422
    assert error == "Appointment date and time must be valid"


def test_new_not_interested_outcome_accepts_required_client_details_and_remarks():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = _payload(
        "agent",
        outcome="not_interested",
        registration_date="",
        notes="Client declined at this time",
    )
    report, error, status = _create_report(employee, payload)

    assert error is None
    assert status == 201
    assert report.outcome == "not_interested"
    assert report.notes == "Client declined at this time"


def test_ready_to_register_requires_registration_date():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = _payload("agent", registration_date="")

    report, error, status = _create_report(employee, payload)

    assert report is None
    assert status == 422
    assert "registration_date" in error


def test_appointment_requires_a_date_as_well_as_a_valid_time():
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    payload = _payload(
        "agent",
        outcome="appointment",
        appointment_date="",
        appointment_time="14:30",
        notes="Return for registration",
    )

    report, error, status = _create_report(employee, payload)

    assert report is None
    assert status == 422
    assert error == "Appointment date and time must be valid"


@pytest.mark.parametrize(
    ("outcome", "fields"),
    [
        ("interested", {"notes": "Client is interested"}),
        ("not_interested", {"notes": "Client declined"}),
        (
            "appointment",
            {
                "notes": "Return for registration",
                "appointment_date": "2026-11-01",
                "appointment_time": "14:30",
            },
        ),
        (
            "ready_to_register",
            {
                "registration_date": "2026-10-23",
                "witness_name": "Witness",
                "witness_id_number": "ID-10",
                "witness_phone": "0712345678",
            },
        ),
    ],
)
def test_new_client_outcomes_do_not_require_owner_details(
    outcome, fields
):
    employee = SimpleNamespace(id=123, department="Sales and Marketing")
    overrides = {
        "business_owner_name": "",
        "id_number": "",
        "contact_phone": "",
        "registration_date": "",
        **fields,
    }
    payload = _payload(
        "agent",
        outcome=outcome,
        **overrides,
    )

    report, error, status = _create_report(employee, payload)

    assert error is None
    assert status == 201
    assert report.business_owner_name is None
    assert report.id_number is None
    assert report.contact_phone is None
    if outcome == "ready_to_register":
        assert report.report_data["registration_status"] == "INCOMPLETE"
