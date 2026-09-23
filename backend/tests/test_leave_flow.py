from datetime import date

from app.extensions import db
from app.models import User


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _submit(client, token, start="2026-10-01", end="2026-10-07"):
    return client.post(
        "/api/leave/requests",
        headers=_headers(token),
        json={
            "leave_type_id": 1,
            "start_date": start,
            "end_date": end,
            "reason": "Annual rest",
            "contact_phone": "+254700000001",
            "contact_email": "admin@example.com",
        },
    )


def test_list_types(client, admin_token):
    response = client.get("/api/leave/types", headers=_headers(admin_token))

    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 6


def test_submit_annual(client, admin_token):
    response = _submit(client, admin_token)

    assert response.status_code == 201
    assert response.get_json()["data"]["days_requested"] == 5.0


def test_submit_insufficient_notice(client, admin_token):
    response = _submit(
        client,
        admin_token,
        start="2026-09-21",
        end="2026-09-25",
    )

    assert response.status_code in (400, 409)
    assert "notice" in response.get_json()["error"].lower()


def test_approve_moves_balance(client, admin_token):
    submitted = _submit(client, admin_token)
    request_id = submitted.get_json()["data"]["id"]

    approved = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(admin_token),
        json={"decision_comment": "Approved"},
    )
    balances = client.get(
        "/api/leave/balances",
        headers=_headers(admin_token),
    )

    assert approved.status_code == 200
    assert balances.status_code == 200
    annual = next(item for item in balances.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["pending_days"] == 0.0
    assert annual["used_days"] == 5.0


def test_reject_releases_balance(client, admin_token):
    submitted = _submit(client, admin_token)
    request_id = submitted.get_json()["data"]["id"]

    rejected = client.post(
        f"/api/leave/requests/{request_id}/reject",
        headers=_headers(admin_token),
        json={"decision_comment": "Not approved"},
    )
    balances = client.get(
        "/api/leave/balances",
        headers=_headers(admin_token),
    )

    assert rejected.status_code == 200
    assert balances.status_code == 200
    annual = next(item for item in balances.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["pending_days"] == 0.0
    assert annual["used_days"] == 0.0


def test_cancel_releases_balance(client, admin_token):
    submitted = _submit(client, admin_token)
    request_id = submitted.get_json()["data"]["id"]

    cancelled = client.post(
        f"/api/leave/requests/{request_id}/cancel",
        headers=_headers(admin_token),
    )
    balances = client.get(
        "/api/leave/balances",
        headers=_headers(admin_token),
    )

    assert cancelled.status_code == 200
    assert balances.status_code == 200
    annual = next(item for item in balances.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["pending_days"] == 0.0
    assert annual["used_days"] == 0.0


def test_submit_sales_report_accepts_field_sales_department(client):
    user = User(
        employee_id="SALES-1001",
        full_name="Jane Sales Rep",
        email="jane.sales@okoa.local",
        phone_number="+254700000101",
        role="employee",
        department="Field Sales",
        hire_date=date(2024, 1, 1),
        is_active=True,
        account_status="approved",
    )
    user.set_password("Pass@word1")
    db.session.add(user)
    db.session.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "jane.sales@okoa.local", "password": "Pass@word1"},
    )
    assert login.status_code == 200
    token = login.get_json()["access_token"]

    response = client.post(
        "/api/sales/reports",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "agent_name": "Grace Njeri",
            "agent_number": "AG-102",
            "store_number": "ST-204",
            "business_owner_name": "Grace Njeri",
            "contact_phone": "+254712345678",
            "id_number": "12345678",
            "business_location": "Nairobi CBD",
            "date_visited": "2026-09-21",
            "registration_date": "2026-09-21",
            "admin_name": "Asha Admin",
            "witness_name": "John Witness",
            "witness_id_number": "87654321",
            "witness_phone": "+254787654321",
            "customer_type": "agent",
            "outcome": "registered",
            "visit_mode": "field_visit",
            "commission_statement": "true",
            "kra_pin": "true",
            "national_id": "true",
            "business_permit": "true",
            "contract": "false",
            "incorporation_certificate": "true",
            "company_kra_pin": "true",
            "cr12": "true",
        },
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["department"] == "Field Sales"


def test_cannot_approve_missing_request(client, admin_token):
    response = client.post(
        "/api/leave/requests/99999/approve",
        headers=_headers(admin_token),
        json={"decision_comment": "Missing"},
    )

    assert response.status_code == 404


def test_manager_can_view_and_approve_pending_leave_for_any_employee(client, admin_token, session):
    manager = User(
        employee_id="MGR-1001",
        full_name="Operations Manager",
        email="manager@okoa.local",
        phone_number="+254700000201",
        role="manager",
        department="Operations",
        hire_date=date(2020, 1, 1),
        is_active=True,
        account_status="approved",
    )
    manager.set_password("Manager@2026!")
    session.add(manager)
    session.commit()

    submitted = _submit(client, admin_token, start="2026-10-01", end="2026-10-02")
    request_id = submitted.get_json()["data"]["id"]
    login = client.post(
        "/api/auth/login",
        json={"email": "manager@okoa.local", "password": "Manager@2026!"},
    )
    assert login.status_code == 200
    manager_token = login.get_json()["access_token"]

    pending = client.get("/api/leave/requests/pending", headers=_headers(manager_token))
    calendar = client.get("/api/leave/team-calendar", headers=_headers(manager_token))
    approved = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(manager_token),
        json={"decision_comment": "Approved for team coverage"},
    )

    assert pending.status_code == 200
    assert any(item["id"] == request_id for item in pending.get_json()["data"])
    assert calendar.status_code == 200
    assert any(item["id"] == request_id for item in calendar.get_json()["data"])
    assert approved.status_code == 200