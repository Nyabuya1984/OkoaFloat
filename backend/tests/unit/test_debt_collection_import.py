import csv
import io
from datetime import date

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token

from app.api.debt_collection import debt_collection_bp
from app.extensions import db, jwt
from app.models import (
    DebtCollectionAssignment,
    DebtCollectionAuditLog,
    DebtCollectionCallLog,
    DebtCollectionDebtor,
    DebtCollectionDutyAssignment,
    DebtCollectionLoan,
    DepartmentAssignmentHistory,
    User,
)
from app.utils.rbac import assign_user_role
from app.utils.rbac_seed import seed_rbac


@pytest.fixture(autouse=True)
def reset_test_data():
    yield


@pytest.fixture()
def debt_collection_client():
    app = Flask("debt_collection_import_test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="debt-collection-import-test-key",
        TESTING=True,
    )
    db.init_app(app)
    jwt.init_app(app)
    app.register_blueprint(debt_collection_bp)
    with app.app_context():
        db.create_all()
        seed_rbac()
        admin = User(
            employee_id="ADMIN-IMPORT-TEST",
            full_name="Import Test Admin",
            email="import-admin@example.invalid",
            phone_number="+254700000001",
            role="super_admin",
            is_active=True,
            is_superuser=True,
            account_status="approved",
        )
        manager = User(
            employee_id="MANAGER-IMPORT-TEST",
            full_name="Import Test Manager",
            email="import-manager@example.invalid",
            phone_number="+254700000002",
            role="EMPLOYEE",
            is_active=True,
            account_status="approved",
        )
        leader = User(
            employee_id="LEADER-IMPORT-TEST",
            full_name="Import Test Team Leader",
            email="import-leader@example.invalid",
            phone_number="+254700000003",
            role="EMPLOYEE",
            is_active=True,
            account_status="approved",
        )
        general_manager = User(
            employee_id="GM-IMPORT-TEST",
            full_name="Import Test General Manager",
            email="import-gm@example.invalid",
            phone_number="+254700000004",
            role="MANAGER",
            is_active=True,
            account_status="approved",
        )
        for user in (admin, manager, leader, general_manager):
            user.set_password("test-only")
        db.session.add_all([admin, manager, leader, general_manager])
        db.session.flush()
        assign_user_role(manager, "debt_collection")
        assign_user_role(leader, "debt_collection")
        assign_user_role(general_manager, "debt_collection")
        db.session.add(DebtCollectionDutyAssignment(
            user_id=manager.id,
            duty="departmental_manager",
            assigned_by=admin.id,
        ))
        db.session.add(DebtCollectionDutyAssignment(
            user_id=leader.id,
            duty="group_leader",
            assigned_by=admin.id,
        ))
        db.session.add(DepartmentAssignmentHistory(
            user_id=general_manager.id,
            department_name="All",
            organizational_role="general_manager",
        ))
        db.session.commit()
        headers = {
            key: {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}
            for key, user in (
                ("admin", admin),
                ("manager", manager),
                ("leader", leader),
                ("general_manager", general_manager),
            )
        }
        yield app.test_client(), headers
        db.session.remove()
        db.drop_all()


def test_import_accepts_more_than_one_thousand_rows(debt_collection_client):
    client, headers = debt_collection_client
    content = io.StringIO()
    writer = csv.writer(content)
    writer.writerow([
        "first_name",
        "other_names",
        "agent_msisdn",
        "owner_msisdn",
        "operator_msisdn",
        "agent_no",
        "store_number",
        "business_name",
        "location",
        "loan_amount",
    ])
    for row_number in range(1001):
        writer.writerow([
            "Test",
            "Client",
            f"254700{row_number:06d}",
            "",
            "",
            f"IMPORT-TEST-{row_number}",
            "",
            "Test Business",
            "Nairobi",
            "100",
        ])

    response = client.post(
        "/api/debt-collection/import",
        headers=headers["manager"],
        data={"file": (io.BytesIO(content.getvalue().encode()), "large-list.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["total_rows"] == 1001
    assert response.get_json()["data"]["accepted_rows"] == 1001
    assert DebtCollectionDebtor.query.count() == 1001


def test_import_preserves_payment_above_principal_with_reported_balance(
    debt_collection_client,
):
    client, headers = debt_collection_client
    content = (
        "first_name,agent_msisdn,agent_no,business_name,loan_amount,"
        "amount_paid,loan_balance\n"
        "Test,254700000001,IMPORT-PAID-OVER-PRINCIPAL,Test Business,100,150,75\n"
    )

    response = client.post(
        "/api/debt-collection/import",
        headers=headers["manager"],
        data={"file": (io.BytesIO(content.encode()), "legacy-balance.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["accepted_rows"] == 1
    assert response.get_json()["data"]["rejected_rows"] == 0
    loan = DebtCollectionLoan.query.one()
    assert loan.amount_paid == 150
    assert loan.loan_balance == 75


def _create_client(first_name, agent_no, agent_msisdn, business_name):
    debtor = DebtCollectionDebtor(
        first_name=first_name,
        agent_msisdn=agent_msisdn,
        agent_no=agent_no,
        business_name=business_name,
    )
    db.session.add(debtor)
    db.session.flush()
    return debtor


def _create_loan(debtor):
    loan = DebtCollectionLoan(
        debtor_id=debtor.id,
        loan_amount=100,
        amount_paid=0,
        loan_date=date(2026, 1, 1),
        status="active",
    )
    db.session.add(loan)
    db.session.flush()
    return loan


def test_department_manager_can_view_and_update_portfolio_records(debt_collection_client):
    client, headers = debt_collection_client
    debtor = _create_client(
        "Managed", "MANAGED-1", "254700000022", "Managed Shop"
    )
    loan = _create_loan(debtor)
    db.session.commit()

    summary = client.get(
        "/api/debt-collection/summary",
        headers=headers["manager"],
    ).get_json()["data"]
    assert summary["permissions"]["can_manage"] is True
    assert [row["id"] for row in client.get(
        "/api/debt-collection/loans",
        headers=headers["manager"],
    ).get_json()["data"]] == [loan.id]

    updated = client.patch(
        f"/api/debt-collection/loans/{loan.id}",
        headers=headers["manager"],
        json={"no_of_days": 14},
    )
    assert updated.status_code == 200, updated.get_json()
    assert updated.get_json()["data"]["no_of_days"] == 14


def test_group_leader_can_view_all_debtors_but_cannot_write(debt_collection_client):
    client, headers = debt_collection_client
    leader = User.query.filter_by(employee_id="LEADER-IMPORT-TEST").one()
    admin = User.query.filter_by(employee_id="ADMIN-IMPORT-TEST").one()
    collector = User(
        employee_id="LEADER-TEAM-COLLECTOR",
        full_name="Team Collector",
        email="team-collector@example.invalid",
        phone_number="+254700000005",
        role="EMPLOYEE",
        is_active=True,
        account_status="approved",
        manager_id=leader.id,
    )
    collector.set_password("test-only")
    db.session.add(collector)
    db.session.flush()
    assign_user_role(collector, "debt_collection")
    db.session.add(DebtCollectionDutyAssignment(
        user_id=collector.id,
        duty="debt_collector_agent",
        assigned_by=admin.id,
    ))
    other_collector = User(
        employee_id="OTHER-TEAM-COLLECTOR",
        full_name="Other Team Collector",
        email="other-team-collector@example.invalid",
        phone_number="+254700000006",
        role="EMPLOYEE",
        is_active=True,
        account_status="approved",
    )
    other_collector.set_password("test-only")
    db.session.add(other_collector)
    db.session.flush()
    assign_user_role(other_collector, "debt_collection")
    db.session.add(DebtCollectionDutyAssignment(
        user_id=other_collector.id,
        duty="debt_collector_agent",
        assigned_by=admin.id,
    ))
    team_debtor = _create_client(
        "Team", "TEAM-1", "254700000020", "Team Shop"
    )
    team_loan = _create_loan(team_debtor)
    unassigned_debtor = _create_client(
        "Unassigned", "UNASSIGNED-1", "254700000021", "Unassigned Shop"
    )
    unassigned_loan = _create_loan(unassigned_debtor)
    other_team_debtor = _create_client(
        "Other Team", "OTHER-TEAM-1", "254700000023", "Other Team Shop"
    )
    other_team_loan = _create_loan(other_team_debtor)
    db.session.add(DebtCollectionAssignment(
        debtor_id=team_debtor.id,
        loan_id=team_loan.id,
        collector_id=collector.id,
        assigned_by=admin.id,
    ))
    db.session.add(DebtCollectionAssignment(
        debtor_id=other_team_debtor.id,
        loan_id=other_team_loan.id,
        collector_id=other_collector.id,
        assigned_by=admin.id,
    ))
    db.session.commit()

    response = client.get(
        "/api/debt-collection/loans",
        headers=headers["leader"],
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.get_json()["data"]} == {
        team_loan.id, unassigned_loan.id, other_team_loan.id,
    }
    debtors = client.get(
        "/api/debt-collection/debtors",
        headers=headers["leader"],
    )
    assert debtors.status_code == 200
    assert {row["id"] for row in debtors.get_json()["data"]} == {
        team_debtor.id, unassigned_debtor.id, other_team_debtor.id,
    }
    summary = client.get(
        "/api/debt-collection/summary",
        headers=headers["leader"],
    ).get_json()["data"]
    assert summary["permissions"]["can_view_all"] is False
    assert summary["permissions"]["can_view_all_debtors"] is True
    assert client.get(
        f"/api/debt-collection/loans/{other_team_loan.id}",
        headers=headers["leader"],
    ).status_code == 404
    assert client.get(
        "/api/debt-collection/loans?include_unassigned=true",
        headers=headers["leader"],
    ).status_code == 403
    assert client.patch(
        f"/api/debt-collection/loans/{team_loan.id}",
        headers=headers["leader"],
        json={"loan_amount": 200},
    ).status_code == 403
    assert client.patch(
        f"/api/debt-collection/debtors/{team_debtor.id}",
        headers=headers["leader"],
        json={"location": "Changed"},
    ).status_code == 403
    assert client.delete(
        f"/api/debt-collection/loans/{team_loan.id}",
        headers=headers["leader"],
    ).status_code == 403
    assert client.post(
        "/api/debt-collection/assignments/bulk",
        headers=headers["leader"],
        json={"collector_id": collector.id, "loan_ids": [team_loan.id]},
    ).status_code == 403


def test_team_leader_cannot_delete_duplicate_loan_entries(
    debt_collection_client,
):
    client, headers = debt_collection_client
    debtor = _create_client("Duplicate", "DUP-1", "254700000010", "Duplicate Shop")
    duplicate = _create_loan(debtor)
    keep = _create_loan(debtor)
    unique = _create_client("Unique", "UNIQUE-1", "254700000011", "Unique Shop")
    unique_loan = _create_loan(unique)
    db.session.commit()

    response = client.get(
        "/api/debt-collection/loans",
        headers=headers["manager"],
    )

    assert response.status_code == 200
    records = {record["id"]: record for record in response.get_json()["data"]}
    assert records[duplicate.id]["is_duplicate"] is True
    assert records[keep.id]["is_duplicate"] is True
    assert records[unique_loan.id]["is_duplicate"] is False

    deleted = client.delete(
        f"/api/debt-collection/loans/{duplicate.id}/permanent",
        headers=headers["leader"],
    )
    assert deleted.status_code == 403
    assert db.session.get(DebtCollectionLoan, duplicate.id) is not None
    assert db.session.get(DebtCollectionLoan, keep.id) is not None
    assert DebtCollectionAuditLog.query.filter_by(
        entity="DebtCollectionLoan",
        action="permanently_deleted",
    ).count() == 0

    denied = client.delete(
        f"/api/debt-collection/loans/{unique_loan.id}/permanent",
        headers=headers["leader"],
    )
    assert denied.status_code == 403
    assert db.session.get(DebtCollectionLoan, unique_loan.id) is not None


def test_only_super_admin_or_general_manager_can_permanently_delete_nonduplicates(
    debt_collection_client,
):
    client, headers = debt_collection_client
    debtor = _create_client("Delete", "DELETE-1", "254700000012", "Delete Shop")
    loan = _create_loan(debtor)
    second_debtor = _create_client(
        "Delete Two", "DELETE-2", "254700000013", "Delete Two Shop"
    )
    second_loan = _create_loan(second_debtor)
    third_debtor = _create_client(
        "Delete Three", "DELETE-3", "254700000014", "Delete Three Shop"
    )
    third_loan = _create_loan(third_debtor)
    db.session.add(DebtCollectionCallLog(
        debtor_id=debtor.id,
        loan_id=loan.id,
        collector_id=next(
            user_id for (user_id,) in db.session.query(User.id)
            .filter(User.employee_id == "MANAGER-IMPORT-TEST").all()
        ),
        outcome="no_answer",
    ))
    db.session.add(DebtCollectionCallLog(
        debtor_id=third_debtor.id,
        loan_id=third_loan.id,
        collector_id=next(
            user_id for (user_id,) in db.session.query(User.id)
            .filter(User.employee_id == "MANAGER-IMPORT-TEST").all()
        ),
        outcome="no_answer",
    ))
    db.session.commit()

    denied = client.delete(
        f"/api/debt-collection/loans/{loan.id}/permanent",
        headers=headers["manager"],
    )
    assert denied.status_code == 403

    removed_loan = client.delete(
        f"/api/debt-collection/loans/{loan.id}/permanent",
        headers=headers["general_manager"],
    )
    assert removed_loan.status_code == 200, removed_loan.get_json()
    call = DebtCollectionCallLog.query.filter_by(debtor_id=debtor.id).one()
    assert call.loan_id is None

    removed_admin_loan = client.delete(
        f"/api/debt-collection/loans/{second_loan.id}/permanent",
        headers=headers["admin"],
    )
    assert removed_admin_loan.status_code == 200, removed_admin_loan.get_json()

    removed_debtor = client.delete(
        f"/api/debt-collection/debtors/{debtor.id}/permanent",
        headers=headers["admin"],
    )
    assert removed_debtor.status_code == 200, removed_debtor.get_json()
    assert db.session.get(DebtCollectionDebtor, debtor.id) is None
    assert DebtCollectionCallLog.query.count() == 1

    removed_gm_debtor = client.delete(
        f"/api/debt-collection/debtors/{third_debtor.id}/permanent",
        headers=headers["general_manager"],
    )
    assert removed_gm_debtor.status_code == 200, removed_gm_debtor.get_json()
    assert db.session.get(DebtCollectionDebtor, third_debtor.id) is None
    assert db.session.get(DebtCollectionLoan, third_loan.id) is None
    assert DebtCollectionCallLog.query.count() == 0
