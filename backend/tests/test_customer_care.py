from datetime import date, timedelta

from app.models import CallFollowUp, CallLog, Customer


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _call_payload(**updates):
    payload = {
        "customer_name": "Amina Wanjiku",
        "phone_number": "+254711223344",
        "email": "amina@example.com",
        "company": "Amina Foods",
        "call_type": "Incoming",
        "category": "Billing",
        "priority": "Urgent",
        "summary": "Customer asked about an unexpected service charge.",
        "status": "Pending Follow-up",
        "follow_up_date": (date.today() + timedelta(days=1)).isoformat(),
        "follow_up_notes": "Call back after checking the invoice.",
    }
    payload.update(updates)
    return payload


def test_create_call_creates_customer_and_follow_up(client, rbac_tokens):
    response = client.post(
        "/api/customer-care/logs",
        headers=_headers(rbac_tokens["customer_care"]),
        json=_call_payload(),
    )

    assert response.status_code == 201, response.get_json()
    call = response.get_json()["data"]
    assert call["customer"]["name"] == "Amina Wanjiku"
    assert call["staff_name"] == "RBAC customer_care"
    assert len(call["follow_ups"]) == 1
    assert call["follow_ups"][0]["notes"] == "Call back after checking the invoice."
    assert Customer.query.filter_by(phone_number="+254711223344").count() == 1
    assert CallLog.query.count() == 1
    assert CallFollowUp.query.count() == 1


def test_call_log_search_filters_customers_and_paginates(client, rbac_tokens):
    created = client.post(
        "/api/customer-care/logs",
        headers=_headers(rbac_tokens["customer_care"]),
        json=_call_payload(follow_up_date=""),
    )
    assert created.status_code == 201

    response = client.get(
        "/api/customer-care/logs?q=711223344&category=Billing&page=1&per_page=1",
        headers=_headers(rbac_tokens["customer_care"]),
    )

    assert response.status_code == 200
    assert response.get_json()["pagination"] == {
        "page": 1,
        "per_page": 1,
        "total": 1,
        "pages": 1,
    }
    assert response.get_json()["data"][0]["customer"]["phone_number"] == "+254711223344"


def test_existing_customer_profile_and_call_updates(client, rbac_tokens):
    first = client.post(
        "/api/customer-care/logs",
        headers=_headers(rbac_tokens["customer_care"]),
        json=_call_payload(follow_up_date=""),
    )
    second = client.post(
        "/api/customer-care/logs",
        headers=_headers(rbac_tokens["customer_care"]),
        json=_call_payload(
            customer_name="Ignored replacement name",
            category="Technical",
            call_type="Outgoing",
            follow_up_date="",
        ),
    )
    assert first.status_code == second.status_code == 201
    assert Customer.query.count() == 1

    call_id = second.get_json()["data"]["id"]
    updated = client.patch(
        f"/api/customer-care/logs/{call_id}",
        headers=_headers(rbac_tokens["customer_care"]),
        json={"summary": "Revised note.", "status": "Resolved", "category": "General Inquiry"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["summary"] == "Revised note."
    assert updated.get_json()["data"]["status"] == "Resolved"

    directory = client.get(
        "/api/customer-care/customers",
        headers=_headers(rbac_tokens["customer_care"]),
    )
    customer = directory.get_json()["data"][0]
    assert customer["interaction_count"] == 2

    profile = client.get(
        f"/api/customer-care/customers/{customer['id']}",
        headers=_headers(rbac_tokens["customer_care"]),
    )
    assert profile.status_code == 200
    assert len(profile.get_json()["data"]["call_logs"]) == 2

    detail = client.get(
        f"/api/customer-care/logs/{call_id}",
        headers=_headers(rbac_tokens["customer_care"]),
    )
    assert detail.status_code == 200
    assert detail.get_json()["data"]["customer"]["phone_number"] == "+254711223344"


def test_follow_up_can_be_completed_and_disappears_from_pending_list(
    client, rbac_tokens
):
    created = client.post(
        "/api/customer-care/logs",
        headers=_headers(rbac_tokens["customer_care"]),
        json=_call_payload(),
    )
    follow_up_id = created.get_json()["data"]["follow_ups"][0]["id"]

    pending = client.get(
        "/api/customer-care/follow-ups",
        headers=_headers(rbac_tokens["customer_care"]),
    )
    assert pending.status_code == 200
    assert len(pending.get_json()["data"]) == 1

    completed = client.patch(
        f"/api/customer-care/follow-ups/{follow_up_id}",
        headers=_headers(rbac_tokens["customer_care"]),
        json={"is_completed": True},
    )
    assert completed.status_code == 200
    assert completed.get_json()["data"]["is_completed"] is True
    assert client.get(
        "/api/customer-care/follow-ups",
        headers=_headers(rbac_tokens["customer_care"]),
    ).get_json()["data"] == []


def test_invalid_call_values_are_rejected_without_creating_records(
    client, rbac_tokens
):
    response = client.post(
        "/api/customer-care/logs",
        headers=_headers(rbac_tokens["customer_care"]),
        json=_call_payload(call_type="Text message", follow_up_date=""),
    )

    assert response.status_code == 400
    assert "Incoming or Outgoing" in response.get_json()["error"]["message"]
    assert Customer.query.count() == 0
    assert CallLog.query.count() == 0
