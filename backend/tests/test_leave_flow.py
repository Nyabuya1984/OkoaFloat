from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from flask_jwt_extended import create_access_token

from app import ensure_default_leave_types
from app.api.leave import _leave_reporting_chain
from app.extensions import db
from app.models import (
    AuditLog,
    Department,
    DepartmentAssignmentHistory,
    LeaveBalance,
    LeavePolicy,
    LeaveType,
    User,
)
from app.utils.organization import get_active_assignment
from app.utils.workflow import handover_gate


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


def test_ensure_default_leave_types_bootstraps_catalog(app):
    with app.app_context():
        LeaveBalance.query.delete()
        LeavePolicy.query.delete()
        LeaveType.query.delete()
        db.session.commit()

        ensure_default_leave_types()

        types = LeaveType.query.order_by(LeaveType.name.asc()).all()
        codes = {leave_type.code for leave_type in types}
        assert {"ANNUAL", "SICK", "MATERNITY", "UNPAID"}.issubset(codes)
        assert LeavePolicy.query.count() >= 1


def test_list_types(client, admin_token):
    response = client.get("/api/leave/types", headers=_headers(admin_token))

    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 7


def test_handover_users_lists_active_colleagues_without_current_user(client, session):
    admin = session.query(User).filter_by(phone_number="+254721143189").one()
    colleague = User(
        employee_id="EMP-HANDOVER-USER",
        full_name="Handover Colleague",
        email="handover.colleague@example.test",
        phone_number="+254700000297",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    inactive = User(
        employee_id="EMP-HANDOVER-INACTIVE",
        full_name="Inactive Colleague",
        email="handover.inactive@example.test",
        phone_number="+254700000298",
        role="employee",
        is_active=False,
        account_status="deactivated",
    )
    colleague.set_password("Pass@word1")
    inactive.set_password("Pass@word1")
    session.add_all([colleague, inactive])
    session.commit()
    with client.application.app_context():
        token = create_access_token(identity=str(admin.id))

    response = client.get(
        "/api/leave/handover-users", headers=_headers(token)
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == [
        {"id": colleague.id, "name": colleague.full_name}
    ]


def test_admin_can_configure_annual_leave_allocation(client, admin_token):
    response = client.patch(
        "/api/leave/admin/policies/1",
        headers=_headers(admin_token),
        json={
            "annual_entitlement_days": 25,
            "max_carryover": 5,
            "notice_days_required": 10,
            "min_service_months": 6,
            "gender_restriction": None,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["annual_entitlement_days"] == 25
    policy_list = client.get("/api/leave/admin/policies", headers=_headers(admin_token))
    annual = next(item for item in policy_list.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["annual_entitlement_days"] == 25
    assert annual["max_carryover"] == 5
    assert annual["notice_days_required"] == 10


def test_admin_can_filter_employee_leave_history(client, admin_token):
    response = client.get(
        "/api/leave/admin/requests?year=2026&status=pending",
        headers=_headers(admin_token),
    )

    assert response.status_code == 200
    assert response.get_json()["pagination"]["page"] == 1
    assert "pages" in response.get_json()["pagination"]


def test_employee_cannot_view_admin_leave_history(client, login_with_otp):
    employee = User(
        employee_id="EMP-LEAVE-HISTORY",
        full_name="History Employee",
        email="history.employee@okoa.local",
        phone_number="+254700000203",
        role="employee",
        department="Operations",
        hire_date=date(2020, 1, 1),
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Pass@word1")
    db.session.add(employee)
    db.session.commit()
    token = login_with_otp(employee.phone_number, "Pass@word1")

    response = client.get("/api/leave/admin/requests", headers=_headers(token))

    assert response.status_code == 403


def test_admin_balance_adjustment_is_audited_and_updates_remaining_balance(client, admin_token):
    employee = User(
        employee_id="EMP-LEAVE-001",
        full_name="Leave Balance Employee",
        email="leave.employee@okoa.local",
        phone_number="+254700000201",
        role="employee",
        department="Operations",
        hire_date=date(2020, 1, 1),
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Pass@word1")
    db.session.add(employee)
    db.session.commit()

    adjusted = client.patch(
        f"/api/leave/admin/balances/{employee.id}/1",
        headers=_headers(admin_token),
        json={
            "year": 2026,
            "entitled_days": 24,
            "used_days": 5,
            "reason": "Corrected HR allocation",
        },
    )

    assert adjusted.status_code == 200
    assert adjusted.get_json()["data"]["remaining_days"] == 19
    assert adjusted.get_json()["data"]["is_manual_override"] is True
    listed = client.get(
        "/api/leave/admin/balances?year=2026",
        headers=_headers(admin_token),
    )
    employee_balance = next(
        item for item in listed.get_json()["data"]
        if item["user_id"] == employee.id and item["leave_type_id"] == 1
    )
    assert employee_balance["used_days"] == 5
    assert employee_balance["remaining_days"] == 19
    audit = AuditLog.query.filter_by(action="employee_leave_balance_adjusted").one()
    assert audit.event_metadata["reason"] == "Corrected HR allocation"


def test_employee_cannot_manage_leave_policy(client, login_with_otp):
    employee = User(
        employee_id="EMP-LEAVE-002",
        full_name="Regular Employee",
        email="regular.employee@okoa.local",
        phone_number="+254700000202",
        role="employee",
        department="Operations",
        hire_date=date(2020, 1, 1),
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Pass@word1")
    db.session.add(employee)
    db.session.commit()
    token = login_with_otp(employee.phone_number, "Pass@word1")

    response = client.get("/api/leave/admin/policies", headers=_headers(token))

    assert response.status_code == 403


def test_handover_notes_do_not_satisfy_full_report_gate():
    leave_request = SimpleNamespace(
        id=123,
        days_requested=4,
        handover_user_id=2,
        handover_agreed_at=date.today(),
        handover_statement="Accepted",
        handover_report="Brief handover notes",
        leave_type=SimpleNamespace(code="ANNUAL"),
    )
    with patch("app.utils.workflow.HandoverReport") as report_model:
        report_model.query.filter_by.return_value.first.return_value = None
        gate = handover_gate(leave_request)

    assert gate["report_required"] is True
    assert gate["report_submitted"] is False


def test_sick_and_unpaid_leave_do_not_require_planned_handover_report():
    with patch("app.utils.workflow.HandoverReport") as report_model:
        report_model.query.filter_by.return_value.first.return_value = None
        for code in ("SICK", "UNPAID"):
            leave_request = SimpleNamespace(
                id=123,
                days_requested=4,
                handover_user_id=2,
                handover_agreed_at=date.today(),
                handover_statement="Accepted",
                leave_type=SimpleNamespace(code=code),
            )
            gate = handover_gate(leave_request)
            assert gate["report_required"] is False


def test_submit_annual(client, rbac_tokens):
    response = _submit(client, rbac_tokens["sales"])

    assert response.status_code == 201
    assert response.get_json()["data"]["days_requested"] == 5.0


def test_leave_submission_requires_a_valid_reporting_chain(client, rbac_tokens):
    response = _submit(client, rbac_tokens["debt_collection"])

    assert response.status_code == 409
    assert "complete, valid reporting chain" in response.get_json()["error"]


def test_custom_department_employee_can_apply_for_leave_without_operational_role(
    client, session
):
    department = Department(name="Accounts")
    general_manager = User(
        employee_id="GM-LEAVE-CUSTOM",
        full_name="Leave Test General Manager",
        email="leave.gm.custom@example.test",
        phone_number="+254700000281",
        role="manager",
        department="All",
        hire_date=date(2020, 1, 1),
        is_active=True,
        account_status="approved",
    )
    general_manager.set_password("GeneralManager@2026!")
    session.add_all([department, general_manager])
    session.flush()
    session.add(DepartmentAssignmentHistory(
        user_id=general_manager.id,
        department_id=None,
        department_name="All",
        organizational_role="general_manager",
    ))

    employee = User(
        employee_id="EMP-ACCOUNTS-LEAVE",
        full_name="Accounts Leave Employee",
        email="accounts.leave@example.test",
        phone_number="+254700000282",
        role="employee",
        department=department.name,
        department_id=department.id,
        manager_id=general_manager.id,
        hire_date=date(2020, 1, 1),
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Employee@2026!")
    session.add(employee)
    session.flush()
    session.add(DepartmentAssignmentHistory(
        user_id=employee.id,
        department_id=department.id,
        department_name=department.name,
        organizational_role="field_agent",
    ))
    session.commit()
    chain = _leave_reporting_chain(employee)
    employee_assignment = get_active_assignment(employee.id)
    manager_assignment = get_active_assignment(general_manager.id)
    assert chain is not None, {
        "employee_department": employee.department_id,
        "employee_manager": employee.manager_id,
        "employee_assignment": (
            employee_assignment.organizational_role,
            employee_assignment.department_id,
            employee_assignment.started_at,
        ) if employee_assignment else None,
        "manager_assignment": (
            manager_assignment.organizational_role,
            manager_assignment.department_id,
            manager_assignment.started_at,
        ) if manager_assignment else None,
        "manager_active": general_manager.is_currently_active(),
        "manager_status": general_manager.account_status,
    }
    token = create_access_token(identity=str(employee.id))
    start_date = date.today() + timedelta(days=30)

    response = client.post(
        "/api/leave/requests",
        headers=_headers(token),
        json={
            "leave_type_id": 1,
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=1)).isoformat(),
            "reason": "Annual rest",
            "contact_phone": employee.phone_number,
            "contact_email": employee.email,
        },
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["workflow_state"] == "general_manager_pending"
    assert chain["general_manager"].id == general_manager.id


def test_department_manager_substitutes_for_inactive_group_leader(
    session, rbac_tokens
):
    employee = session.query(User).filter_by(
        email="rbac.sales@example.test"
    ).one()
    inactive_leader = session.query(User).filter_by(
        email="leave.manager3@example.test"
    ).one()
    department_manager = session.query(User).filter_by(
        email="leave.manager2@example.test"
    ).one()
    general_manager = session.query(User).filter_by(
        email="leave.manager1@example.test"
    ).one()
    active_chain = _leave_reporting_chain(employee)
    assert active_chain["team_leader"].id == inactive_leader.id
    assert active_chain["department_manager"].id == department_manager.id
    assert active_chain["general_manager"].id == general_manager.id

    inactive_leader.is_active = False
    inactive_leader.account_status = "deactivated"
    session.flush()

    chain = _leave_reporting_chain(employee)
    assert chain["team_leader"].id == department_manager.id
    assert chain["department_manager"].id == department_manager.id
    assert chain["general_manager"].id == general_manager.id


def test_submit_insufficient_notice(client, rbac_tokens):
    response = _submit(
        client,
        rbac_tokens["sales"],
        start="2026-09-21",
        end="2026-09-25",
    )

    assert response.status_code in (400, 409)
    assert "notice" in response.get_json()["error"].lower()


def test_approve_moves_balance(client, admin_token, rbac_tokens):
    submitted = _submit(client, rbac_tokens["sales"])
    assert submitted.status_code == 201
    request_id = submitted.get_json()["data"]["id"]

    bypass_attempt = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(rbac_tokens["general_manager"]),
        json={"decision_comment": "Attempted to skip the approval chain"},
    )
    early_hr_verification = client.post(
        f"/api/leave/requests/{request_id}/verify-complete",
        headers=_headers(admin_token),
    )
    department_manager_queue = client.get(
        "/api/leave/requests/pending",
        headers=_headers(rbac_tokens["department_manager"]),
    )
    assert bypass_attempt.status_code == 403
    assert early_hr_verification.status_code == 409
    assert all(
        item["id"] != request_id
        for item in department_manager_queue.get_json()["data"]
    )

    team_leader_approval = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"decision_comment": "Approved for team coverage"},
    )
    assert team_leader_approval.status_code == 200
    assert team_leader_approval.get_json()["data"]["workflow_state"] == "department_manager_pending"
    department_manager_approval = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(rbac_tokens["department_manager"]),
        json={"decision_comment": "Approved for department coverage"},
    )
    assert department_manager_approval.status_code == 200
    assert department_manager_approval.get_json()["data"]["workflow_state"] == "general_manager_pending"
    general_manager_approval = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(rbac_tokens["general_manager"]),
        json={"decision_comment": "Approved for business coverage"},
    )
    assert general_manager_approval.status_code == 200
    assert general_manager_approval.get_json()["data"]["workflow_state"] == "hr_verification"
    assert [
        step["stage_role"]
        for step in general_manager_approval.get_json()["data"]["approval_steps"]
    ] == ["team_leader", "department_manager", "general_manager"]
    approved = client.post(
        f"/api/leave/requests/{request_id}/verify-complete",
        headers=_headers(admin_token),
    )
    balances = client.get(
        "/api/leave/balances",
        headers=_headers(rbac_tokens["sales"]),
    )

    assert approved.status_code == 200
    assert balances.status_code == 200
    annual = next(item for item in balances.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["pending_days"] == 0.0
    assert annual["used_days"] == 5.0


def test_reject_releases_balance(client, rbac_tokens):
    submitted = _submit(client, rbac_tokens["sales"])
    request_id = submitted.get_json()["data"]["id"]

    rejected = client.post(
        f"/api/leave/requests/{request_id}/reject",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"decision_comment": "Not approved"},
    )
    balances = client.get(
        "/api/leave/balances",
        headers=_headers(rbac_tokens["sales"]),
    )

    assert rejected.status_code == 200
    assert balances.status_code == 200
    annual = next(item for item in balances.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["pending_days"] == 0.0
    assert annual["used_days"] == 0.0


def test_cancel_releases_balance(client, rbac_tokens):
    submitted = _submit(client, rbac_tokens["sales"])
    request_id = submitted.get_json()["data"]["id"]

    cancelled = client.post(
        f"/api/leave/requests/{request_id}/cancel",
        headers=_headers(rbac_tokens["sales"]),
    )
    balances = client.get(
        "/api/leave/balances",
        headers=_headers(rbac_tokens["sales"]),
    )

    assert cancelled.status_code == 200
    assert balances.status_code == 200
    annual = next(item for item in balances.get_json()["data"] if item["leave_type_id"] == 1)
    assert annual["pending_days"] == 0.0
    assert annual["used_days"] == 0.0


def test_submit_sales_report_accepts_field_sales_department(client, login_with_otp):
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

    token = login_with_otp("+254700000101", "Pass@word1")

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


def test_manager_without_reporting_assignment_cannot_approve_leave(
    client, rbac_tokens, session, login_with_otp
):
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

    submitted = _submit(
        client,
        rbac_tokens["sales"],
        start="2026-10-01",
        end="2026-10-02",
    )
    request_id = submitted.get_json()["data"]["id"]
    manager_token = login_with_otp(manager.phone_number, "Manager@2026!")

    pending = client.get("/api/leave/requests/pending", headers=_headers(manager_token))
    calendar = client.get("/api/leave/team-calendar", headers=_headers(manager_token))
    approved = client.post(
        f"/api/leave/requests/{request_id}/approve",
        headers=_headers(manager_token),
        json={"decision_comment": "Approved for team coverage"},
    )

    assert pending.status_code == 403
    assert calendar.status_code == 403
    assert approved.status_code == 403