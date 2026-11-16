import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    DebtCollectionAssignment,
    DebtCollectionAuditLog,
    DebtCollectionDebtor,
    DebtCollectionDutyAssignment,
    DebtCollectionLoan,
    Department,
    User,
)
from app.utils.rbac import assign_user_role


def grant_department_manager(session, user):
    admin = User.query.filter_by(phone_number="+254721143189").one()
    session.add(DebtCollectionDutyAssignment(
        user_id=user.id,
        duty="departmental_manager",
        assigned_by=admin.id,
    ))


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


def test_debtor_and_loan_crud_feed_summary(client, rbac_tokens):
    admin_token = rbac_tokens["debt_collection"]
    with client.application.app_context():
        grant_department_manager(db.session, User.query.filter_by(
            email="rbac.debt_collection@example.test"
        ).one())
        db.session.commit()
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
    compact_summary_response = client.get(
        "/api/debt-collection/summary?include_records=false",
        headers=headers,
    )
    assert compact_summary_response.status_code == 200
    compact_summary = compact_summary_response.get_json()["data"]
    assert compact_summary["records"] == []
    assert compact_summary["total_outstanding"] == summary["total_outstanding"]
    assert compact_summary["permissions"] == summary["permissions"]

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


def test_debt_collection_role_can_archive_restore_and_bulk_manage_loans(
    client, rbac_tokens
):
    admin_token = rbac_tokens["debt_collection"]
    with client.application.app_context():
        grant_department_manager(db.session, User.query.filter_by(
            email="rbac.debt_collection@example.test"
        ).one())
        db.session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}
    loan_ids = []
    for index in range(2):
        debtor_response = client.post(
            "/api/debt-collection/debtors",
            headers=headers,
            json={
                "first_name": f"Archive{index}",
                "agent_msisdn": f"25471234000{index}",
                "agent_no": f"AG-ARCHIVE-{index}",
                "business_name": f"Archive Shop {index}",
            },
        )
        assert debtor_response.status_code == 201, debtor_response.get_json()
        loan_response = client.post(
            "/api/debt-collection/loans",
            headers=headers,
            json={
                "debtor_id": debtor_response.get_json()["data"]["id"],
                "loan_amount": "1000.00",
                "amount_paid": "100.00",
                "loan_date": date.today().isoformat(),
            },
        )
        assert loan_response.status_code == 201, loan_response.get_json()
        loan_ids.append(loan_response.get_json()["data"]["id"])

    first_loan, second_loan = loan_ids
    archived = client.post(
        f"/api/debt-collection/loans/{first_loan}/archive",
        headers=headers,
        json={},
    )
    assert archived.status_code == 200, archived.get_json()
    assert archived.get_json()["data"]["is_archived"] is True
    active_ids = {
        row["id"] for row in client.get("/api/debt-collection/loans", headers=headers).get_json()["data"]
    }
    assert first_loan not in active_ids
    archived_list = client.get(
        "/api/debt-collection/loans?archived=true",
        headers=headers,
    )
    assert [row["id"] for row in archived_list.get_json()["data"]] == [first_loan]
    archived_view = client.get(
        "/api/debt-collection/loans/archived",
        headers=headers,
    )
    assert [row["id"] for row in archived_view.get_json()["data"]] == [first_loan]

    restored_one = client.post(
        f"/api/debt-collection/loans/{first_loan}/restore",
        headers=headers,
        json={},
    )
    assert restored_one.status_code == 200, restored_one.get_json()
    assert restored_one.get_json()["data"]["is_archived"] is False

    bulk_archived = client.post(
        "/api/debt-collection/loans/archive/bulk",
        headers=headers,
        json={"loan_ids": loan_ids},
    )
    assert bulk_archived.status_code == 200, bulk_archived.get_json()
    assert {row["id"] for row in bulk_archived.get_json()["data"]} == set(loan_ids)

    restored = client.post(
        "/api/debt-collection/loans/restore/bulk",
        headers=headers,
        json={"loan_ids": loan_ids},
    )
    assert restored.status_code == 200, restored.get_json()
    assert {row["id"] for row in restored.get_json()["data"]} == set(loan_ids)
    active_ids = {
        row["id"] for row in client.get("/api/debt-collection/loans", headers=headers).get_json()["data"]
    }
    assert set(loan_ids) <= active_ids


def test_debt_collector_cannot_list_or_change_archived_accounts(
    client, session, login_with_otp
):
    collector = User(
        employee_id="DC-ARCHIVE-001",
        full_name="Archive Collector",
        email="archive.collector@example.test",
        phone_number="+254700000099",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    collector.set_password("Collector@2026!")
    session.add(collector)
    session.flush()
    assign_user_role(collector, "debt_collection")
    admin = User.query.filter_by(phone_number="+254721143189").one()
    session.add(DebtCollectionDutyAssignment(
        user_id=collector.id,
        duty="debt_collector_agent",
        assigned_by=admin.id,
    ))
    debtor = DebtCollectionDebtor(
        first_name="Private",
        agent_msisdn="254712349999",
        agent_no="AG-ARCHIVE-PRIVATE",
        business_name="Private Shop",
    )
    session.add(debtor)
    session.flush()
    loan = DebtCollectionLoan(
        debtor_id=debtor.id,
        loan_amount=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        loan_date=date.today(),
    )
    session.add(loan)
    session.commit()
    loan_id = loan.id
    collector_token = login_with_otp(collector.phone_number, "Collector@2026!")
    collector_headers = {"Authorization": f"Bearer {collector_token}"}

    archived_list = client.get(
        "/api/debt-collection/loans?archived=true",
        headers=collector_headers,
    )
    assert archived_list.status_code == 403, archived_list.get_json()
    assert client.post(
        f"/api/debt-collection/loans/{loan_id}/archive",
        headers=collector_headers,
        json={},
    ).status_code == 403


def test_debt_collection_role_can_access_assigned_loans_and_record_payment(
    client, rbac_tokens, session, login_with_otp
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
    assign_user_role(employee, "debt_collection")
    admin_token = rbac_tokens["debt_collection"]
    admin = User.query.filter_by(phone_number="+254721143189").one()
    grant_department_manager(session, User.query.filter_by(
        email="rbac.debt_collection@example.test"
    ).one())
    session.add(DebtCollectionDutyAssignment(
        user_id=employee.id,
        duty="debt_collector_agent",
        assigned_by=admin.id,
    ))
    debtor = DebtCollectionDebtor(
        first_name="Brian",
        other_names="Otieno",
        agent_msisdn="254720000001",
        owner_msisdn="254720000002",
        operator_msisdn="254720000003",
        agent_no="AG-ASSIGNED-1",
        store_number="ST-001",
        business_name="Brian Shop",
        location="Nairobi",
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
    portfolio_loan = portfolio.get_json()["data"][0]
    assert history_call["debtor_name"] == "Brian"
    assert history_call["collector_name"] == "Debt Collector"
    assert history_call["promised_amount"] == "500.00"
    assert history_call["contact_date"] == date.today().isoformat()
    assert portfolio.get_json()["data"][0]["next_payment_date"] == "2026-10-07"
    assert portfolio_loan["first_name"] == "Brian"
    assert portfolio_loan["other_names"] == "Otieno"
    assert portfolio_loan["agent_number"] == "254720000001"
    assert portfolio_loan["owner_msisdn"] == "254720000002"
    assert portfolio_loan["operator_msisdn"] == "254720000003"
    assert portfolio_loan["agent_no"] == "AG-ASSIGNED-1"
    assert portfolio_loan["store_number"] == "ST-001"
    assert portfolio_loan["business_name"] == "Brian Shop"
    assert portfolio_loan["business_location"] == "Nairobi"
    assert portfolio_loan["loans_borrowed"] == 1
    assert portfolio_loan["assigned_at"]

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


def test_departmental_manager_reviews_full_portfolio_filters_and_reassigns(
    client, session, login_with_otp
):
    admin = User.query.filter_by(phone_number="+254721143189").one()
    manager = User(
        employee_id="DC-MANAGER-001",
        full_name="Department Manager",
        email="debt.manager@example.test",
        phone_number="+254700000089",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    first_collector = User(
        employee_id="DC-COLLECTOR-002",
        full_name="Collector One",
        email="collector.one@example.test",
        phone_number="+254700000090",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    second_collector = User(
        employee_id="DC-COLLECTOR-003",
        full_name="Collector Two",
        email="collector.two@example.test",
        phone_number="+254700000091",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    for user, password in (
        (manager, "Manager@2026!"),
        (first_collector, "Collector@2026!"),
        (second_collector, "Collector@2026!"),
    ):
        user.set_password(password)
        session.add(user)
    session.flush()
    for user in (manager, first_collector, second_collector):
        assign_user_role(user, "debt_collection")
    session.add_all([
        DebtCollectionDutyAssignment(user_id=manager.id, duty="departmental_manager", assigned_by=admin.id),
        DebtCollectionDutyAssignment(user_id=first_collector.id, duty="debt_collector_agent", assigned_by=admin.id),
        DebtCollectionDutyAssignment(user_id=second_collector.id, duty="debt_collector_agent", assigned_by=admin.id),
    ])
    debtors = [
        DebtCollectionDebtor(
            first_name="Assigned",
            agent_msisdn="254720000101",
            agent_no="AG-MANAGED-1",
            store_number="STORE-A",
            business_name="Assigned Shop",
            location="Nairobi",
        ),
        DebtCollectionDebtor(
            first_name="Unassigned",
            agent_msisdn="254720000102",
            agent_no="AG-MANAGED-2",
            store_number="STORE-B",
            business_name="Unassigned Shop",
            location="Mombasa",
        ),
    ]
    session.add_all(debtors)
    session.flush()
    loans = [
        DebtCollectionLoan(
            debtor_id=debtors[0].id,
            loan_amount=Decimal("100.00"),
            amount_paid=Decimal("20.00"),
            loan_date=date.today() - timedelta(days=60),
            status="overdue",
        ),
        DebtCollectionLoan(
            debtor_id=debtors[1].id,
            loan_amount=Decimal("250.00"),
            amount_paid=Decimal("0.00"),
            loan_date=date.today() - timedelta(days=90),
            status="overdue",
        ),
    ]
    session.add_all(loans)
    session.flush()
    session.add(DebtCollectionAssignment(
        debtor_id=debtors[0].id,
        loan_id=loans[0].id,
        collector_id=first_collector.id,
        assigned_by=admin.id,
    ))
    session.commit()
    collector_id = first_collector.id
    second_collector_id = second_collector.id
    assigned_loan_id, unassigned_loan_id = (loan.id for loan in loans)

    manager_token = login_with_otp(manager.phone_number, "Manager@2026!")
    manager_headers = {"Authorization": f"******"}
    manager_update = client.patch(
        f"/api/debt-collection/loans/{unassigned_loan_id}",
        headers=manager_headers,
        json={"no_of_days": 91},
    )
    assert manager_update.status_code == 200, manager_update.get_json()
    assert manager_update.get_json()["data"]["no_of_days"] == 91
    master_list = client.get("/api/debt-collection/loans", headers=manager_headers)
    assert master_list.status_code == 200
    assert {row["id"] for row in master_list.get_json()["data"]} == {assigned_loan_id, unassigned_loan_id}
    manager_debtors = client.get("/api/debt-collection/debtors", headers=manager_headers)
    assert {row["id"] for row in manager_debtors.get_json()["data"]} == {debtor.id for debtor in debtors}
    assert client.get("/api/debt-collection/summary", headers=manager_headers).get_json()["data"]["permissions"]["can_manage"] is True

    by_collector = client.get(
        f"/api/debt-collection/loans?collector_id={collector_id}",
        headers=manager_headers,
    )
    assert [row["id"] for row in by_collector.get_json()["data"]] == [assigned_loan_id]
    by_store = client.get("/api/debt-collection/loans?store_number=STORE-B", headers=manager_headers)
    assert [row["id"] for row in by_store.get_json()["data"]] == [unassigned_loan_id]
    by_agent = client.get(
        "/api/debt-collection/loans?agent_name=Assigned&agent_number=254720000101",
        headers=manager_headers,
    )
    assert [row["id"] for row in by_agent.get_json()["data"]] == [assigned_loan_id]
    by_business = client.get(
        "/api/debt-collection/loans?business_name=Assigned%20Shop",
        headers=manager_headers,
    )
    assert [row["id"] for row in by_business.get_json()["data"]] == [assigned_loan_id]
    by_collector = client.get(
        "/api/debt-collection/loans?collector_name=Collector%20One&collector_number=254700000090",
        headers=manager_headers,
    )
    assert [row["id"] for row in by_collector.get_json()["data"]] == [assigned_loan_id]
    csv_export = client.get(
        "/api/debt-collection/export.csv", headers=manager_headers
    )
    assert csv_export.status_code == 200
    assert csv_export.get_data(as_text=True).splitlines()[0].lstrip("\ufeff") == (
        "first_name,other_names,agent_msisdn,owner_msisdn,operator_msisdn,"
        "agent_no,store_number,business_name,location,loan_amount,amount_paid,"
        "loan_balance,loan_date,last_interest_calc_date,no_of_days,"
        "days_outstanding,status,collector_name,created_at,record_created_at"
    )
    excel_export = client.get(
        "/api/debt-collection/export.xlsx", headers=manager_headers
    )
    assert excel_export.status_code == 200
    assert "spreadsheetml" in excel_export.content_type
    by_location_and_balance = client.get(
        "/api/debt-collection/loans?location=Nairobi&min_balance=79&max_balance=81",
        headers=manager_headers,
    )
    assert [row["id"] for row in by_location_and_balance.get_json()["data"]] == [assigned_loan_id]
    assert by_location_and_balance.get_json()["data"][0]["days_outstanding"] >= 60
    by_overdue_age = client.get("/api/debt-collection/loans?overdue_days=80", headers=manager_headers)
    assert [row["id"] for row in by_overdue_age.get_json()["data"]] == [unassigned_loan_id]
    by_capacity = client.get("/api/debt-collection/loans?collector_capacity=0", headers=manager_headers)
    assert [row["id"] for row in by_capacity.get_json()["data"]] == [unassigned_loan_id]

    collector_token = login_with_otp(first_collector.phone_number, "Collector@2026!")
    collector_headers = {"Authorization": f"******"}
    collector_loans = client.get("/api/debt-collection/loans", headers=collector_headers)
    assert {row["id"] for row in collector_loans.get_json()["data"]} == {assigned_loan_id}
    collector_debtors = client.get(
        "/api/debt-collection/debtors",
        headers=collector_headers,
    )
    assert {row["id"] for row in collector_debtors.get_json()["data"]} == {
        debtors[0].id
    }
    assert client.get(
        f"/api/debt-collection/loans/{unassigned_loan_id}",
        headers=collector_headers,
    ).status_code == 404

    missing_reason = client.post(
        f"/api/debt-collection/loans/{assigned_loan_id}/assignments",
        headers=manager_headers,
        json={"collector_id": second_collector_id},
    )
    assert missing_reason.status_code == 422
    reassignment = client.post(
        f"/api/debt-collection/loans/{assigned_loan_id}/assignments",
        headers=manager_headers,
        json={"collector_id": second_collector_id, "reason": "Balance coverage"},
    )
    assert reassignment.status_code == 201

    missing_bulk_reason = client.post(
        "/api/debt-collection/assignments/bulk",
        headers=manager_headers,
        json={"collector_id": collector_id, "loan_ids": [assigned_loan_id, unassigned_loan_id]},
    )
    assert missing_bulk_reason.status_code == 422
    bulk = client.post(
        "/api/debt-collection/assignments/bulk",
        headers=manager_headers,
        json={
            "collector_id": collector_id,
            "loan_ids": [assigned_loan_id, unassigned_loan_id],
            "reason": "Rebalance collector workload",
        },
    )
    assert bulk.status_code == 201
    active_assignments = client.get("/api/debt-collection/assignments", headers=manager_headers).get_json()["data"]
    active = {row["loan_id"]: row for row in active_assignments}
    assert active[assigned_loan_id]["collector_id"] == collector_id
    assert active[assigned_loan_id]["reason"] == "Rebalance collector workload"
    assert active[unassigned_loan_id]["reason"] == "Rebalance collector workload"
    first_collector_token = login_with_otp(first_collector.phone_number, "Collector@2026!")
    first_collector_headers = {"Authorization": f"Bearer {first_collector_token}"}
    collector_portfolio = client.get("/api/collector/my-portfolio", headers=first_collector_headers)
    assert collector_portfolio.status_code == 200
    collector_records = collector_portfolio.get_json()["data"]
    assert {row["id"] for row in collector_records} == {assigned_loan_id, unassigned_loan_id}
    assert all(row["assigned_at"] for row in collector_records)

    progress = client.get("/api/debt-collection/analytics", headers=manager_headers).get_json()["data"]["collectors"]
    first_progress = next(item for item in progress if item["collector_id"] == collector_id)
    assert first_progress["assigned_accounts"] == 2
    assert first_progress["contacted_accounts"] == 0
    assert first_progress["pending_accounts"] == 2


def test_team_leader_can_allocate_only_to_direct_reports(
    client, session, login_with_otp
):
    admin = User.query.filter_by(phone_number="+254721143189").one()
    department = Department(name="Debt Collection")
    session.add(department)
    session.flush()

    team_leader = User(
        employee_id="DC-TEAM-LEAD-001",
        full_name="Team Lead",
        job_position_title="Group Leader",
        email="debt.teamlead@example.test",
        phone_number="+254700000092",
        role="employee",
        department=department.name,
        department_id=department.id,
        is_active=True,
        account_status="approved",
    )
    agent = User(
        employee_id="DC-TEAM-AGENT-001",
        full_name="Team Agent",
        job_position_title="Debt Collection Agent",
        email="debt.teamagent@example.test",
        phone_number="+254700000093",
        role="employee",
        department=department.name,
        department_id=department.id,
        is_active=True,
        account_status="approved",
    )
    other_agent = User(
        employee_id="DC-OTHER-AGENT-001",
        full_name="Other Agent",
        job_position_title="Debt Collection Agent",
        email="debt.otheragent@example.test",
        phone_number="+254700000094",
        role="employee",
        department=department.name,
        department_id=department.id,
        is_active=True,
        account_status="approved",
    )
    for user in (team_leader, agent, other_agent):
        user.set_password("Collector@2026!")
        session.add(user)
    session.flush()
    team_leader.manager_id = None
    agent.manager_id = team_leader.id
    for user in (team_leader, agent, other_agent):
        assign_user_role(user, "debt_collection")
    session.add_all([
        DebtCollectionDutyAssignment(
            user_id=agent.id, duty="debt_collector_agent", assigned_by=admin.id
        ),
        DebtCollectionDutyAssignment(
            user_id=other_agent.id, duty="debt_collector_agent", assigned_by=admin.id
        ),
    ])

    debtor_rows = [
        DebtCollectionDebtor(
            first_name=name,
            agent_msisdn=f"25470000010{index}",
            agent_no=f"AG-TEAM-{index}",
            business_name=f"{name} Shop",
        )
        for index, name in enumerate(("Assigned", "Outside", "Unassigned"), start=1)
    ]
    session.add_all(debtor_rows)
    session.flush()
    loan_rows = [
        DebtCollectionLoan(
            debtor_id=debtor_rows[index].id,
            loan_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            loan_date=date.today(),
        )
        for index in range(3)
    ]
    session.add_all(loan_rows)
    session.flush()
    session.add_all([
        DebtCollectionAssignment(
            debtor_id=debtor_rows[0].id,
            loan_id=loan_rows[0].id,
            collector_id=agent.id,
            assigned_by=admin.id,
        ),
        DebtCollectionAssignment(
            debtor_id=debtor_rows[1].id,
            loan_id=loan_rows[1].id,
            collector_id=other_agent.id,
            assigned_by=admin.id,
        ),
    ])
    session.commit()

    token = login_with_otp(team_leader.phone_number, "Collector@2026!")
    headers = {"Authorization": f"Bearer {token}"}
    summary = client.get("/api/debt-collection/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.get_json()["data"]["permissions"]["can_view_team"] is True
    assert summary.get_json()["data"]["permissions"]["can_manage"] is False
    visible = client.get("/api/debt-collection/loans", headers=headers)
    assert [row["id"] for row in visible.get_json()["data"]] == [loan_rows[0].id]
    allocation_list = client.get(
        "/api/debt-collection/loans?include_unassigned=true", headers=headers
    )
    assert allocation_list.status_code == 403
    team_collectors = client.get("/api/debt-collection/collectors", headers=headers)
    assert [row["id"] for row in team_collectors.get_json()["data"]] == [agent.id]
    assert client.post(
        f"/api/debt-collection/loans/{loan_rows[2].id}/assignments",
        headers=headers,
        json={"collector_id": agent.id},
    ).status_code == 403
    assert client.post(
        f"/api/debt-collection/loans/{loan_rows[2].id}/assignments",
        headers=headers,
        json={"collector_id": other_agent.id, "reason": "Not on my team"},
    ).status_code == 403
    representative_report = client.get(
        f"/api/debt-collection/analytics?collector_id={agent.id}",
        headers=headers,
    )
    assert representative_report.status_code == 200
    report_data = representative_report.get_json()["data"]
    assert report_data["collector_id"] == agent.id
    assert len(report_data["collectors"]) == 1
    assert report_data["collectors"][0]["assigned_accounts"] == 2
    exported = client.get("/api/debt-collection/export.csv", headers=headers)
    assert exported.status_code == 200
    exported_lines = exported.get_data(as_text=True).splitlines()
    assert exported_lines[0].lstrip("\ufeff") == (
        "first_name,other_names,agent_msisdn,owner_msisdn,operator_msisdn,"
        "agent_no,store_number,business_name,location,loan_amount,amount_paid,"
        "loan_balance,loan_date,last_interest_calc_date,no_of_days,"
        "days_outstanding,status,collector_name,created_at,record_created_at"
    )
    assert len(exported_lines) == 2
    imported = client.post(
        "/api/debt-collection/import",
        headers=headers,
        data={"file": (io.BytesIO(b""), "team-list.csv")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 403
    updated = client.patch(
        f"/api/debt-collection/loans/{loan_rows[0].id}",
        headers=headers,
        json={"loan_amount": "120"},
    )
    assert updated.status_code == 403
    outside_team_edit = client.patch(
        f"/api/debt-collection/loans/{loan_rows[1].id}",
        headers=headers,
        json={"loan_amount": "200"},
    )
    assert outside_team_edit.status_code == 404
    deleted = client.delete(
        f"/api/debt-collection/loans/{loan_rows[0].id}",
        headers=headers,
    )
    assert deleted.status_code == 403
    debtor_update = client.patch(
        f"/api/debt-collection/debtors/{debtor_rows[0].id}",
        headers=headers,
        json={"location": "Updated by group leader"},
    )
    assert debtor_update.status_code == 403
    assert deleted.get_json()["data"]["deleted"] is True
    portfolio = client.get("/api/collector/my-portfolio", headers=headers)
    portfolio_rows = portfolio.get_json()["data"]
    assert {row["id"] for row in portfolio_rows} == {
        loan_rows[0].id,
        loan_rows[2].id,
    }
    assert all(row["is_assigned_to_me"] is False for row in portfolio_rows)


def test_general_manager_can_manage_debt_collection(client, session, rbac_tokens):
    headers = {"Authorization": f"Bearer {rbac_tokens['general_manager']}"}
    admin = User.query.filter_by(phone_number="+254721143189").one()
    collector = User(
        employee_id="DC-GM-COLLECTOR-001",
        full_name="General Manager Collector",
        email="gm.collector@example.test",
        phone_number="+254700000095",
        role="employee",
        department="Debt Collection",
        job_position_title="Debt Collection Agent",
        is_active=True,
        account_status="approved",
    )
    collector.set_password("Collector@2026!")
    session.add(collector)
    session.flush()
    assign_user_role(collector, "debt_collection")
    session.add(DebtCollectionDutyAssignment(
        user_id=collector.id,
        duty="debt_collector_agent",
        assigned_by=admin.id,
    ))
    session.commit()

    response = client.post(
        "/api/debt-collection/debtors",
        headers=headers,
        json={
            "first_name": "General",
            "other_names": "Manager",
            "agent_msisdn": "254711111112",
            "agent_no": "AG-GM-1",
            "business_name": "GM Shop",
        },
    )
    assert response.status_code == 201, response.get_json()
    debtor_id = response.get_json()["data"]["id"]
    loan = client.post(
        "/api/debt-collection/loans",
        headers=headers,
        json={
            "debtor_id": debtor_id,
            "loan_amount": "100",
            "amount_paid": "0",
            "loan_date": date.today().isoformat(),
        },
    )
    assert loan.status_code == 201, loan.get_json()
    loan_id = loan.get_json()["data"]["id"]
    updated = client.patch(
        f"/api/debt-collection/loans/{loan_id}",
        headers=headers,
        json={"first_name": "General Updated", "loan_amount": "125"},
    )
    assert updated.status_code == 200, updated.get_json()
    assert updated.get_json()["data"]["agent_name"] == "General Updated Manager"
    allocation = client.post(
        "/api/debt-collection/assignments/bulk",
        headers=headers,
        json={"collector_id": collector.id, "loan_ids": [loan_id]},
    )
    assert allocation.status_code == 201, allocation.get_json()
    deleted = client.delete(f"/api/debt-collection/loans/{loan_id}", headers=headers)
    assert deleted.status_code == 200, deleted.get_json()


def test_admins_and_debt_managers_can_permanently_delete_uploaded_records(
    client, session, admin_token, login_with_otp
):
    admin = User.query.filter_by(phone_number="+254721143189").one()
    manager_users = {}
    for index, (name, role, duty) in enumerate(
        (
            ("Department Manager", "departmental_manager", "departmental_manager"),
            ("Group Leader", "group_leader", "group_leader"),
        ),
        start=1,
    ):
        user = User(
            employee_id=f"DC-DELETE-{index}",
            full_name=name,
            email=f"dc.delete{index}@example.test",
            phone_number=f"+25470000010{index}",
            role="employee",
            department="Debt Collection",
            job_position_title=name,
            is_active=True,
            account_status="approved",
        )
        user.set_password("Debt-Delete-Password!")
        session.add(user)
        session.flush()
        assign_user_role(user, "debt_collection")
        session.add(DebtCollectionDutyAssignment(
            user_id=user.id,
            duty=duty,
            assigned_by=admin.id,
        ))
        manager_users[role] = user

    loans_by_role = {}
    for index, (role, user) in enumerate(manager_users.items(), start=1):
        debtor = DebtCollectionDebtor(
            first_name="Duplicate",
            other_names=role,
            agent_msisdn=f"25470000020{index}",
            agent_no=f"DC-DUPLICATE-{index}",
            business_name=f"Duplicate Shop {index}",
        )
        single_debtor = DebtCollectionDebtor(
            first_name="Unique",
            other_names=role,
            agent_msisdn=f"25470000030{index}",
            agent_no=f"DC-UNIQUE-{index}",
            business_name=f"Unique Shop {index}",
        )
        session.add_all((debtor, single_debtor))
        session.flush()
        duplicate_loans = [
            DebtCollectionLoan(
                debtor_id=debtor.id,
                loan_amount=Decimal("100.00"),
                amount_paid=Decimal("0.00"),
                imported_balance=Decimal("100.00"),
                loan_date=date.today(),
            )
            for _ in range(2)
        ]
        single_loan = DebtCollectionLoan(
            debtor_id=single_debtor.id,
            loan_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            imported_balance=Decimal("100.00"),
            loan_date=date.today(),
        )
        session.add_all([*duplicate_loans, single_loan])
        session.flush()
        if role == "group_leader":
            session.add_all([
                DebtCollectionAssignment(
                    debtor_id=loan.debtor_id,
                    loan_id=loan.id,
                    collector_id=user.id,
                    assigned_by=admin.id,
                )
                for loan in [*duplicate_loans, single_loan]
            ])
        loans_by_role[role] = (duplicate_loans, single_loan, user)

    admin_debtor = DebtCollectionDebtor(
        first_name="Imported",
        agent_msisdn="254700000399",
        agent_no="DC-ADMIN-IMPORT",
        business_name="Admin Imported Shop",
    )
    session.add(admin_debtor)
    session.flush()
    admin_loan = DebtCollectionLoan(
        debtor_id=admin_debtor.id,
        loan_amount=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        imported_balance=Decimal("100.00"),
        loan_date=date.today(),
    )
    session.add(admin_loan)
    session.commit()

    admin_deleted = client.delete(
        f"/api/debt-collection/loans/{admin_loan.id}/permanent",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_deleted.status_code == 200, admin_deleted.get_json()

    bulk_debtor = DebtCollectionDebtor(
        first_name="Bulk",
        agent_msisdn="254700000398",
        agent_no="DC-ADMIN-BULK",
        business_name="Bulk Delete Shop",
    )
    session.add(bulk_debtor)
    session.flush()
    bulk_loans = [
        DebtCollectionLoan(
            debtor_id=bulk_debtor.id,
            loan_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            imported_balance=Decimal("100.00"),
            loan_date=date.today(),
        )
        for _ in range(2)
    ]
    session.add_all(bulk_loans)
    session.commit()
    bulk_deleted = client.delete(
        "/api/debt-collection/loans/permanent/bulk",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"loan_ids": [loan.id for loan in bulk_loans]},
    )
    assert bulk_deleted.status_code == 200, bulk_deleted.get_json()
    assert bulk_deleted.get_json()["data"]["permanently_deleted"] == 2

    for role, (duplicate_loans, single_loan, user) in loans_by_role.items():
        token = login_with_otp(user.phone_number, "Debt-Delete-Password!")
        headers = {"Authorization": f"Bearer {token}"}
        deleted = client.delete(
            f"/api/debt-collection/loans/{duplicate_loans[0].id}/permanent",
            headers=headers,
        )
        assert deleted.status_code == 200, (role, deleted.get_json())
        not_duplicate = client.delete(
            f"/api/debt-collection/loans/{single_loan.id}/permanent",
            headers=headers,
        )
        assert not_duplicate.status_code == 403, (role, not_duplicate.get_json())


def debt_collection_status(loan):
    return loan.status
