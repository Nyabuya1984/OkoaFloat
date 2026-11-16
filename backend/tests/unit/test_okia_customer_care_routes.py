from datetime import date

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token

from app.extensions import db, jwt
from app.models import (
    ConcernCategory,
    DebtCollectionCallLog,
    DebtCollectionDebtor,
    DebtCollectionLoan,
    DepartmentAssignmentHistory,
    Role,
    SalesDailyReport,
    User,
    UserRole,
)
from app.utils.rbac import assign_user_role
from app.utils.rbac_seed import seed_rbac
from app.api.okoa_customer_care import okoa_customer_care_bp
from app.api.customer_care import customer_care_bp
from app.utils.okia_seed import seed_reference_data


@pytest.fixture()
def isolated_client():
    app = Flask("okoa_customer_care_test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="test-only-key",
        TIMEZONE="Africa/Nairobi",
        TESTING=True,
    )
    db.init_app(app)
    jwt.init_app(app)
    app.register_blueprint(okoa_customer_care_bp)
    app.register_blueprint(customer_care_bp)
    with app.app_context():
        db.create_all()
        seed_rbac()
        staff = User(
            employee_id="TEST-1",
            full_name="Test Manager",
            email="test-manager@example.invalid",
            role="EMPLOYEE",
            is_active=True,
            is_superuser=False,
            account_status="approved",
        )
        staff.set_password("test-only")
        db.session.add(staff)
        db.session.flush()
        assign_user_role(staff, "customer_care")
        db.session.commit()
        token = create_access_token(identity=str(staff.id))
        yield app.test_client(), {"Authorization": f"Bearer {token}"}
        db.session.remove()
        db.drop_all()


def test_call_route_creates_reference_shift_and_reconciliation_escalation(isolated_client):
    client, headers = isolated_client
    response = client.post(
        "/api/calls",
        headers=headers,
        json={
            "call_type": "inbound",
            "caller_type": "agent",
            "customer_name": "Customer One",
            "phone_number": "+254711000001",
            "agent_name": "Agent One",
            "agent_number": "A-100",
            "store_number": "S-100",
            "location": "Nairobi",
            "concern_category": "RECONCILIATION",
            "summary": "Payment made but balance still owing.",
            "call_started_at": "2026-10-12T08:00:00+03:00",
        },
    )
    assert response.status_code == 201, response.get_json()
    call = response.get_json()["data"]
    assert call["reference_number"].startswith("OF-")
    assert call["shift_code"] == "A"
    assert call["requires_escalation"] is True
    assert call["escalated_to"] == "general_manager"
    assert client.get("/api/calls?shift=A&escalated=true", headers=headers).get_json()["data"][0]["id"] == call["id"]
    resolution = client.get("/api/reports/gm/resolution?from=2026-10-12&to=2026-10-12", headers=headers)
    assert resolution.status_code == 200
    assert resolution.get_json()["data"]["total"] == 1
    attention = client.get("/api/reports/gm/attention", headers=headers)
    assert attention.status_code == 200
    assert len(attention.get_json()["data"]["open_escalations"]) == 1
    escalation_id = attention.get_json()["data"]["open_escalations"][0]["id"]
    gm_report = client.get(
        f"/api/reports/gm/escalations/{escalation_id}", headers=headers
    )
    assert gm_report.status_code == 200, gm_report.get_json()
    report_sections = {
        section["id"]: section for section in gm_report.get_json()["data"]["sections"]
    }
    assert report_sections["client"]["client"]["agent_number"] == "A-100"
    assert report_sections["client"]["call_history"][0]["direction"] == "Incoming"
    assert report_sections["shift"]["shift"]["shift_id"] == "A"
    assert report_sections["agent_activity"]["shift_activity"] == {
        "clients_served": 1,
        "total_calls": 1,
        "resolved_on_spot": 0,
        "escalated_or_pending": 1,
    }
    assert report_sections["escalation"]["reason"] == "Payment made but balance still owing."
    matrix = client.get("/api/reports/gm/agent-shift-matrix?from=2026-10-12&to=2026-10-12", headers=headers)
    assert matrix.status_code == 200
    assert matrix.get_json()["data"][0]["shift"] == "A"
    assert client.patch(
        f"/api/escalations/{escalation_id}/resolve", headers=headers, json={}
    ).status_code == 200


def test_new_customer_care_routes_require_jwt(isolated_client):
    client, _ = isolated_client
    assert client.get("/api/escalations").status_code == 401


def test_removed_concern_categories_are_deleted_from_reference_data(isolated_client):
    client, headers = isolated_client
    for code, label in (
        ("REGISTRATION_HOW", "How do I register?"),
        ("REPAYMENT_HOW", "How do I repay Okoa Float?"),
    ):
        db.session.add(ConcernCategory(code=code, label=label, direction="inbound"))
    db.session.commit()

    seed_reference_data()
    response = client.get("/api/concerns", headers=headers)

    assert response.status_code == 200
    codes = {category["code"] for category in response.get_json()["data"]}
    assert "REGISTRATION_HOW" not in codes
    assert "REPAYMENT_HOW" not in codes


def test_general_manager_can_view_escalation_briefing_without_customer_care_access(
    isolated_client,
):
    client, headers = isolated_client
    call_response = client.post(
        "/api/calls",
        headers=headers,
        json={
            "call_type": "inbound",
            "caller_type": "agent",
            "customer_name": "Customer One",
            "phone_number": "+254711000001",
            "agent_name": "Agent One",
            "agent_number": "A-100",
            "store_number": "S-100",
            "location": "Nairobi",
            "concern_category": "RECONCILIATION",
            "summary": "Payment made but balance still owing.",
            "call_started_at": "2026-10-12T08:00:00+03:00",
        },
    )
    assert call_response.status_code == 201, call_response.get_json()
    escalation_id = client.get("/api/escalations", headers=headers).get_json()["data"][0]["id"]

    gm = User(
        employee_id="GM-1",
        full_name="General Manager",
        email="general-manager@example.invalid",
        role="MANAGER",
        is_active=True,
        account_status="approved",
    )
    gm.set_password("test-only")
    db.session.add(gm)
    db.session.flush()
    sales_role = Role.query.filter_by(name="sales").one()
    db.session.add(UserRole(user_id=gm.id, role_id=sales_role.id))
    db.session.add(
        DepartmentAssignmentHistory(
            user_id=gm.id,
            department_name="All",
            organizational_role="general_manager",
        )
    )
    sales_report = SalesDailyReport(
        employee_id=gm.id,
        department="Sales & Marketing",
        agent_name="Sales Agent",
        agent_number="SA-1",
        store_number="STORE-1",
        date_visited=date.today(),
        customer_type="agent",
        outcome="ready_to_register",
        report_data={"registration_status": "INCOMPLETE"},
    )
    debtor = DebtCollectionDebtor(
        first_name="Debt",
        agent_msisdn="+254711000099",
        agent_no="DEBT-1",
        business_name="Test Debt Business",
    )
    db.session.add_all([sales_report, debtor])
    db.session.flush()
    loan = DebtCollectionLoan(
        debtor_id=debtor.id,
        loan_amount=1000,
        amount_paid=0,
        loan_date=date.today(),
        status="legal",
    )
    db.session.add(loan)
    db.session.flush()
    db.session.add(
        DebtCollectionCallLog(
            debtor_id=debtor.id,
            loan_id=loan.id,
            collector_id=gm.id,
            outcome="promise_to_pay",
        )
    )
    db.session.commit()
    gm_headers = {
        "Authorization": f"Bearer {create_access_token(identity=str(gm.id))}"
    }

    report = client.get(
        f"/api/reports/gm/escalations/{escalation_id}",
        headers=gm_headers,
    )

    assert report.status_code == 200, report.get_json()
    assert {section["id"] for section in report.get_json()["data"]["sections"]} == {
        "client",
        "shift",
        "agent_activity",
        "escalation",
    }
    queue = client.get("/api/escalations", headers=gm_headers)
    assert queue.status_code == 200
    overview = client.get("/api/reports/gm/shift-overview", headers=gm_headers)
    assert overview.status_code == 200, overview.get_json()
    assert client.get("/api/shifts", headers=gm_headers).status_code == 200
    assert client.get(
        "/api/customer-care/logs?page=1&per_page=25", headers=gm_headers
    ).status_code == 200
    assert client.get(
        "/api/debt-collection/summary", headers=gm_headers
    ).status_code == 200
    assert client.get(
        "/api/debt-collection/collectors", headers=gm_headers
    ).status_code == 200
    assert client.get(
        "/api/debt-collection/assignments", headers=gm_headers
    ).status_code == 200
    assert client.post(
        "/api/debt-collection/debtors", headers=gm_headers, json={}
    ).status_code == 403
    snapshots = overview.get_json()["data"]["department_snapshots"]
    assert snapshots["sales_marketing"]["pending_documents"] == 1
    assert snapshots["debt_collection"]["promises_to_pay"] == 1
    assert snapshots["debt_collection"]["default_escalations"] == 1
    assert "proxy" in snapshots["debt_collection"]["default_escalations_basis"]
    assert snapshots["customer_care"]["open_tickets"] == 1
    assert client.get("/api/calls", headers=gm_headers).status_code == 403


def test_existing_customer_care_flow_persists_and_returns_okoa_fields(isolated_client):
    client, headers = isolated_client
    response = client.post(
        "/api/customer-care/logs",
        headers=headers,
        json={
            "customer_name": "Customer Two",
            "phone_number": "+254711000002",
            "call_type": "Incoming",
            "category": "RECONCILIATION",
            "caller_type": "agent",
            "location": "Nairobi",
            "agent_name": "Agent Two",
            "agent_number": "A-200",
            "store_number": "S-200",
            "priority": "Normal",
            "summary": "Paid but still showing owing.",
            "call_started_at": "2026-10-12T08:00:00+03:00",
            "follow_up_date": "",
        },
    )
    assert response.status_code == 201, response.get_json()
    call = response.get_json()["data"]
    assert call["concern_category"] == "RECONCILIATION"
    assert call["outbound_reason"] is None
    assert call["shift_code"] == "A"
    assert call["reference_number"].startswith("OF-")
    assert call["requires_escalation"] is True
    assert call["customer"]["caller_type"] == "agent"
    assert call["customer"]["location"] == "Nairobi"
    assert call["customer"]["agent_name"] == "Agent Two"
    assert call["customer"]["agent_number"] == "A-200"
    assert call["customer"]["store_number"] == "S-200"

    call_id = call["id"]
    detail = client.get(f"/api/customer-care/logs/{call_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["reference_number"] == call["reference_number"]
    history = client.get("/api/customer-care/customers/1", headers=headers).get_json()["data"]
    assert history["caller_type"] == "agent"
    assert history["call_logs"][0]["concern_category"] == "RECONCILIATION"
    assert history["call_logs"][0]["escalated_to"] == "general_manager"
    assert history["call_logs"][0]["escalation_id"] is not None
    directory = client.get(
        "/api/customer-care/customers?caller_type=agent&store_number=S-200", headers=headers
    )
    assert directory.status_code == 200
    assert directory.get_json()["data"][0]["store_number"] == "S-200"
    escalations = client.get("/api/escalations?status=open", headers=headers)
    assert escalations.status_code == 200
    assert escalations.get_json()["data"][0]["call_id"] == call_id
    resolved = client.patch(
        f"/api/customer-care/logs/{call_id}",
        headers=headers,
        json={"status": "Resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["escalation_resolved"] is True
    assert client.get("/api/escalations?status=open", headers=headers).get_json()["data"] == []


def test_ready_to_register_caller_is_a_valid_inbound_customer_care_concern(isolated_client):
    client, headers = isolated_client
    response = client.post(
        "/api/customer-care/logs",
        headers=headers,
        json={
            "customer_name": "Prospective Client",
            "phone_number": "+254711000003",
            "call_type": "Incoming",
            "caller_type": "potential_client",
            "concern_category": "CALLER_READY_TO_REGISTER",
            "priority": "Normal",
            "summary": "Caller is ready to register as a new client.",
            "call_started_at": "2026-10-12T08:00:00+03:00",
        },
    )

    assert response.status_code == 201, response.get_json()
    call = response.get_json()["data"]
    assert call["concern_category"] == "CALLER_READY_TO_REGISTER"
    assert call["customer"]["caller_type"] == "potential_client"
