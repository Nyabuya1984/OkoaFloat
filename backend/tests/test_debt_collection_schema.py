from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import DebtCollectionDebtor, DebtCollectionDutyAssignment, DebtCollectionLoan, User


@pytest.mark.usefixtures("session")
def test_debt_collection_models_support_loan_balance_and_assignment():
    debtor = DebtCollectionDebtor(
        first_name="Alice",
        other_names="Wanjiku",
        agent_msisdn="254712345678",
        owner_msisdn="254700000001",
        operator_msisdn="254700000002",
        agent_no="AG-1001",
        store_number="ST-1001",
        business_name="Alicia Shop",
        location="Nairobi",
    )
    db.session.add(debtor)
    db.session.flush()

    loan = DebtCollectionLoan(
        debtor_id=debtor.id,
        loan_amount=Decimal("150000.00"),
        amount_paid=Decimal("20000.00"),
        status="Active",
        loan_date=date(2026, 1, 1),
    )
    db.session.add(loan)
    db.session.flush()

    assert loan.loan_balance == Decimal("130000.00")
    assert debtor.agent_no == "AG-1001"
    assert debt_collection_status(loan) == "Active"


def test_debtor_and_loan_crud_feed_summary(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    debtor_response = client.post(
        "/api/debt-collection/debtors",
        headers=headers,
        json={
            "first_name": "Amina",
            "other_names": "Wanjiku",
            "agent_msisdn": "254712345678",
            "agent_no": "AG-API-1",
            "store_number": "ST-API-1",
            "business_name": "Amina Grocery",
            "location": "Nairobi",
        },
    )
    assert debtor_response.status_code == 201, debtor_response.get_json()
    debtor_id = debtor_response.get_json()["data"]["id"]

    loan_response = client.post(
        "/api/debt-collection/loans",
        headers=headers,
        json={
            "debtor_id": debtor_id,
            "loan_amount": "1000.00",
            "amount_paid": "250.00",
            "loan_date": "2026-01-01",
            "status": "overdue",
        },
    )
    assert loan_response.status_code == 201, loan_response.get_json()
    loan_id = loan_response.get_json()["data"]["id"]

    summary = client.get("/api/debt-collection/summary", headers=headers).get_json()["data"]
    assert summary["total_outstanding"] == "750.00"
    assert summary["active_accounts"] == 1
    assert summary["overdue_accounts"] == 1
    assert summary["recovered_to_date"] == "250.00"
    assert summary["records"][0]["agent_name"] == "Amina Wanjiku"

    debtor_detail = client.get(f"/api/debt-collection/debtors/{debtor_id}", headers=headers)
    assert debtor_detail.status_code == 200
    debtor_update = client.patch(
        f"/api/debt-collection/debtors/{debtor_id}",
        headers=headers,
        json={"location": "Nairobi West"},
    )
    assert debtor_update.status_code == 200
    assert debtor_update.get_json()["data"]["location"] == "Nairobi West"

    update_response = client.patch(
        f"/api/debt-collection/loans/{loan_id}",
        headers=headers,
        json={"status": "active"},
    )
    assert update_response.status_code == 200
    delete_response = client.delete(f"/api/debt-collection/loans/{loan_id}", headers=headers)
    assert delete_response.status_code == 200
    debtor_delete = client.delete(f"/api/debt-collection/debtors/{debtor_id}", headers=headers)
    assert debtor_delete.status_code == 200


def test_employee_only_sees_assigned_loans_and_can_record_payment(
    client, admin_token, session, login_with_otp
):
    employee = User(
        employee_id="DC-EMP-001",
        full_name="Debt Collector",
        email="debt.collector@example.test",
        phone_number="+254700000088",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Collector@2026!")
    session.add(employee)
    session.flush()
    admin = User.query.filter_by(phone_number="+254700000001").one()
    session.add(DebtCollectionDutyAssignment(
        user_id=employee.id,
        duty="debt_collector_agent",
        assigned_by=admin.id,
    ))
    debtor = DebtCollectionDebtor(
        first_name="Brian",
        agent_msisdn="254720000001",
        agent_no="AG-ASSIGNED-1",
        business_name="Brian Shop",
    )
    session.add(debtor)
    session.flush()
    loan = DebtCollectionLoan(
        debtor_id=debtor.id,
        loan_amount="1000.00",
        amount_paid="0.00",
        loan_date=date(2026, 1, 1),
        status="active",
    )
    session.add(loan)
    session.commit()
    loan_id = loan.id
    employee_id = employee.id

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assignment = client.post(
        f"/api/debt-collection/loans/{loan_id}/assignments",
        headers=admin_headers,
        json={"collector_id": employee_id},
    )
    assert assignment.status_code == 201, assignment.get_json()

    employee_token = login_with_otp(employee.phone_number, "Collector@2026!")
    employee_headers = {"Authorization": f"Bearer {employee_token}"}
    visible = client.get("/api/debt-collection/loans", headers=employee_headers)
    assert [row["id"] for row in visible.get_json()["data"]] == [loan_id]
    call = client.post(
        f"/api/debt-collection/loans/{loan_id}/calls",
        headers=employee_headers,
        json={
            "outcome": "promise_to_pay",
            "promised_date": "2026-10-07",
            "promised_time": "09:30",
            "promised_amount": "500.00",
        },
    )
    assert call.status_code == 201, call.get_json()
    portfolio = client.get("/api/collector/my-portfolio", headers=employee_headers)
    history_call = portfolio.get_json()["data"][0]["interactions"][0]
    assert history_call["debtor_name"] == "Brian"
    assert history_call["collector_name"] == "Debt Collector"
    assert history_call["promised_amount"] == "500.00"
    assert history_call["contact_date"] == date.today().isoformat()
    assert portfolio.get_json()["data"][0]["next_payment_date"] == "2026-10-07"

    filtered_calls = client.get(
        f"/api/collector/analytics?from={date.today().isoformat()}&outcome=promise_to_pay",
        headers=employee_headers,
    )
    assert filtered_calls.status_code == 200
    assert [row["outcome"] for row in filtered_calls.get_json()["data"]["interactions"]] == ["promise_to_pay"]

    invalid_filter = client.get(
        "/api/collector/analytics?outcome=not-an-outcome",
        headers=employee_headers,
    )
    assert invalid_filter.status_code == 422
    follow_ups = client.get("/api/debt-collection/follow-ups", headers=employee_headers)
    assert follow_ups.status_code == 200
    assert follow_ups.get_json()["data"][0]["follow_up_type"] == "PTP"
    partial = client.post(
        f"/api/debt-collection/loans/{loan_id}/calls",
        headers=employee_headers,
        json={
            "outcome": "partial_payment",
            "amount_paid": "200.00",
            "promised_date": "2026-10-10",
            "promised_time": "11:00",
        },
    )
    assert partial.status_code == 201, partial.get_json()
    assert partial.get_json()["data"]["loan"]["loan_balance"] == "800.00"
    assert partial.get_json()["data"]["loan"]["status"] == "active"
    payment = client.post(
        f"/api/debt-collection/loans/{loan_id}/payments",
        headers=employee_headers,
        json={"amount": "800.00", "payment_date": "2026-10-06"},
    )
    assert payment.status_code == 201, payment.get_json()
    assert payment.get_json()["data"]["loan"]["status"] == "settled"


def debt_collection_status(loan):
    return loan.status
