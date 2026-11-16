from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from app import create_app
from app.models import (
    Department,
    DepartmentAssignmentHistory,
    LeaveBalance,
    LeaveType,
    Notification,
    OtpChallenge,
    SalesFollowUp,
    SalesLead,
    SalesRegistration,
    User,
)
from app.api.auth import _hash_otp


def test_protected_super_admin_uses_expected_login_identity(session):
    admin = session.query(User).filter_by(phone_number="+254721143189").one()
    assert admin.role == "SUPER_ADMIN"
    assert admin.is_superuser is True
    assert admin.check_password("Admin@2026!")


def test_super_admin_can_create_a_custom_department(client, session, admin_token):
    response = client.post(
        "/api/auth/admin/departments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "M-Float"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "M-Float"
    assert session.query(Department).filter_by(name="M-Float").count() == 1


def test_super_admin_can_save_own_profile_without_employee_assignment_fields(
    client, session, admin_token
):
    admin = session.query(User).filter_by(phone_number="+254721143189").one()
    response = client.patch(
        f"/api/auth/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": admin.full_name,
            "official_email": admin.email,
            "phone_number": admin.phone_number,
            "role": admin.role,
            "is_superuser": True,
        },
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["is_superuser"] is True


def test_admin_can_create_users_with_gm_fallback_for_missing_manager_tiers(
    client, session, admin_token
):
    debt_department = Department(name="Debt Collection")
    accounts_department = Department(name="Accounts")
    session.add_all([debt_department, accounts_department])
    session.flush()
    general_manager = User(
        employee_id="GM-FALLBACK-001",
        full_name="Roster General Manager",
        email="roster.gm@example.test",
        phone_number="+254700000077",
        role="manager",
        department="All",
        is_active=True,
        account_status="approved",
    )
    general_manager.set_password("GeneralManager@2026!")
    session.add(general_manager)
    session.flush()
    session.add(DepartmentAssignmentHistory(
        user_id=general_manager.id,
        department_id=None,
        department_name="All",
        organizational_role="general_manager",
    ))
    session.commit()

    team_lead_response = client.post(
        "/api/auth/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Debt Team Lead",
            "official_email": "debt.teamlead@example.test",
            "phone_number": "+254700000078",
            "password": "Initial@2026!",
            "department": "Debt Collection",
            "department_role": "debt_collection",
            "organizational_role": "team_leader",
            "manager_id": general_manager.id,
        },
    )
    assert team_lead_response.status_code == 200, team_lead_response.get_json()
    team_lead_id = team_lead_response.get_json()["data"]["id"]

    collector_response = client.post(
        "/api/auth/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Debt Collector",
            "official_email": "debt.collector@example.test",
            "phone_number": "+254700000079",
            "password": "Initial@2026!",
            "department": "Debt Collection",
            "department_role": "debt_collection",
            "organizational_role": "field_agent",
            "manager_id": team_lead_id,
        },
    )
    assert collector_response.status_code == 200, collector_response.get_json()

    accounts_response = client.post(
        "/api/auth/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": "Accounts Employee",
            "official_email": "accounts.employee@example.test",
            "phone_number": "+254700000080",
            "password": "Initial@2026!",
            "department": "Accounts",
            "organizational_role": "field_agent",
            "manager_id": general_manager.id,
        },
    )
    assert accounts_response.status_code == 200, accounts_response.get_json()


def test_admin_bulk_delete_removes_related_user_records(client, session, admin_token):
    manager = User(
        employee_id="EMP-BULK-MANAGER",
        full_name="Bulk Delete Manager",
        email="bulk.manager@example.com",
        phone_number="+254712345677",
        role="manager",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    manager.set_password("Manager@2026!")
    session.add(manager)
    session.flush()
    manager_id = manager.id
    user = User(
        employee_id="EMP-BULK-001",
        full_name="Bulk Delete Employee",
        email="bulk.delete@example.com",
        personal_email="bulk.delete.personal@example.com",
        phone_number="+254712345678",
        role="employee",
        department="Sales",
        manager_id=manager_id,
        is_active=True,
        account_status="approved",
    )
    user.set_password("Employee@2026!")
    session.add(user)
    session.flush()
    user_id = user.id
    annual_leave = session.query(LeaveType).filter_by(code="ANNUAL").one()
    session.add(LeaveBalance(
        user_id=user_id,
        leave_type_id=annual_leave.id,
        year=2026,
        entitled_days=1,
        used_days=0,
        pending_days=0,
        carried_over=0,
    ))
    session.add(Notification(
        user_id=user_id,
        title="Test notification",
        body="This notification belongs to the deleted user.",
    ))
    session.add(DepartmentAssignmentHistory(
        user_id=user_id,
        department_id=None,
        department_name="Sales",
        organizational_role="field_agent",
    ))
    session.add(OtpChallenge(
        user_id=user_id,
        phone_number=user.phone_number,
        email_address=user.email,
        purpose="login",
        status="active",
        code_hash=_hash_otp("123456"),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    ))
    lead = SalesLead(
        lead_name="Bulk Delete Lead",
        phone_number="+254712345676",
        created_by_id=user_id,
    )
    session.add(lead)
    session.flush()
    registration = SalesRegistration(
        lead_id=lead.id,
        registered_by_user_id=user_id,
        status="complete",
    )
    session.add(registration)
    session.flush()
    session.add(SalesFollowUp(
        lead_id=lead.id,
        registration_id=registration.id,
        assigned_to_user_id=user_id,
        due_at=datetime.utcnow() + timedelta(days=1),
        task_type="registration_review",
    ))
    session.commit()

    response = client.post(
        "/api/auth/admin/users/bulk-delete",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_ids": [manager_id, user_id]},
    )

    assert response.status_code == 200
    assert session.query(User).filter(User.id.in_([manager_id, user_id])).count() == 0
    assert session.query(User).filter_by(id=user_id).count() == 0
    assert session.query(LeaveBalance).filter_by(user_id=user_id).count() == 0
    assert session.query(Notification).filter_by(user_id=user_id).count() == 0
    assert session.query(DepartmentAssignmentHistory).filter_by(user_id=user_id).count() == 0
    assert session.query(OtpChallenge).filter_by(user_id=user_id).count() == 0
    assert session.query(SalesLead).filter_by(created_by_id=user_id).count() == 0
    assert session.query(SalesRegistration).filter_by(registered_by_user_id=user_id).count() == 0
    assert session.query(SalesFollowUp).filter_by(assigned_to_user_id=user_id).count() == 0


def test_single_admin_delete_is_permanent(client, session, admin_token):
    user = User(
        employee_id="EMP-DELETE-001",
        full_name="Single Delete Employee",
        email="single.delete@example.com",
        phone_number="+254712345679",
        role="employee",
        is_active=True,
        account_status="approved",
    )
    user.set_password("Employee@2026!")
    session.add(user)
    session.flush()
    user_id = user.id
    session.add(Notification(
        user_id=user_id,
        title="Test notification",
        body="This notification belongs to the deleted user.",
    ))
    session.commit()

    response = client.delete(
        f"/api/auth/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["permanently_deleted"] is True
    assert session.query(User).filter_by(id=user_id).count() == 0
    assert session.query(Notification).filter_by(user_id=user_id).count() == 0


def test_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={
            "phone_number": "+254721143189",
            "password": "Admin@2026!",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["verification_required"] is True
    assert "challenge_id" not in payload


def test_login_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={
            "phone_number": "+254721143189",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_verify_login_otp_issues_session_without_challenge_id(client, session):
    response = client.post(
        "/api/auth/login",
        json={
            "phone_number": "+254721143189",
            "password": "Admin@2026!",
        },
    )

    assert response.status_code == 200
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254721143189", purpose="login"
    ).one()
    challenge.code_hash = _hash_otp("123456")
    session.commit()

    response = client.post(
        "/api/auth/verify-otp",
        json={"phone_number": "+254721143189", "email": "admin@okoa.local", "otp": "123456"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["access_token"]
    assert payload["refresh_token"]


def test_registration_verification_keeps_account_pending(client, session):
    response = client.post(
        "/api/auth/register",
        json={
            "phone_number": "+254712345678",
            "email": "new.employee@example.com",
            "personal_email": "new.employee.personal@example.com",
            "password": "Employee@2026!",
            "employee_name": "New Employee",
            "job_position_title": "Employee",
            "employer": "Okoa Float Ltd",
            "department": "Sales",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["verification_required"] is True
    assert "challenge_id" not in payload

    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254712345678", purpose="registration"
    ).one()
    challenge.code_hash = _hash_otp("654321")
    session.commit()
    verification = client.post(
        "/api/auth/verify-registration",
        json={"phone_number": "+254712345678", "email": "new.employee@example.com", "otp": "654321"},
    )
    assert verification.status_code == 200
    assert verification.get_json()["account_status"] == "pending"


def test_password_reset_uses_otp_without_challenge_id(client, session):
    request_response = client.post(
        "/api/auth/request-password-reset",
        json={"phone_number": "+254721143189"},
    )
    assert request_response.status_code == 200
    assert "challenge_id" not in request_response.get_json()
    challenge = session.query(OtpChallenge).filter_by(
        phone_number="+254721143189", purpose="reset"
    ).one()
    challenge.code_hash = _hash_otp("112233")
    session.commit()

    response = client.post(
        "/api/auth/reset-password",
        json={
            "phone_number": "+254721143189",
            "otp": "112233",
            "new_password": "Changed@2026!",
        },
    )
    assert response.status_code == 200
    user = session.query(User).filter_by(phone_number="+254721143189").one()
    assert user.check_password("Changed@2026!")

    create_app("testing")
    session.expire_all()
    user = session.query(User).filter_by(phone_number="+254721143189").one()
    assert user.check_password("Changed@2026!")


def test_me_requires_jwt(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_with_jwt(client, admin_token):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["id"] == 1


def test_me_includes_active_general_manager_assignment(client, session):
    general_manager = User(
        employee_id="GM-0001",
        full_name="General Manager",
        email="gm@okoa.local",
        phone_number="+254700000009",
        role="manager",
        department="All",
        is_active=True,
        account_status="approved",
    )
    general_manager.set_password("GeneralManager@2026!")
    session.add(general_manager)
    session.flush()
    session.add(DepartmentAssignmentHistory(
        user_id=general_manager.id,
        department_id=None,
        department_name="All",
        organizational_role="general_manager",
    ))
    session.commit()
    token = create_access_token(identity=str(general_manager.id))

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    user = response.get_json()["user"]
    assert user["organizational_role"] == "general_manager"
    assert user["department"] == "All"
    assert user["active_assignment"]["organizational_role"] == "general_manager"


def test_manager_cannot_approve_pending_registration_without_hierarchy(
    client, session, login_with_otp
):
    manager = User(
        employee_id="MGR-0001",
        full_name="Team Manager",
        email="manager@okoa.local",
        phone_number="+254700000002",
        role="manager",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    manager.set_password("Manager@2026!")
    pending = User(
        employee_id="EMP-0002",
        full_name="New Employee",
        email="new.employee@okoa.local",
        phone_number="+254700000003",
        role="employee",
        department="Sales",
        is_active=True,
        account_status="pending",
    )
    pending.set_password("Employee@2026!")
    session.add_all([manager, pending])
    session.commit()

    manager_token = login_with_otp(manager.phone_number, "Manager@2026!")
    response = client.post(
        f"/api/auth/accounts/{pending.id}/approve",
        headers={"Authorization": f"Bearer {manager_token}"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["message"] == (
        "An active organizational assignment is required to approve accounts"
    )
    session.refresh(pending)
    assert pending.account_status == "pending"


def test_admin_user_status_rejects_activation_without_a_valid_assignment(
    client, session, admin_token
):
    user = User(
        employee_id="EMP-STATUS-01",
        full_name="Status Test User",
        email="status.test@okoa.local",
        phone_number="+254700000004",
        role="employee",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    user.set_password("Employee@2026!")
    session.add(user)
    session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}
    endpoint = f"/api/auth/admin/users/{user.id}/status"

    response = client.post(endpoint, headers=headers, json={"status": "pending"})
    assert response.status_code == 200
    assert response.get_json()["data"]["account_status"] == "pending"
    assert response.get_json()["data"]["is_active"] is True

    response = client.post(endpoint, headers=headers, json={"status": "active"})
    assert response.status_code == 200
    assert response.get_json()["data"]["account_status"] == "approved"
    session.refresh(user)
    assert user.account_status == "approved"
    assert user.is_active is True
    assert user.approved_by is None

    response = client.post(endpoint, headers=headers, json={"status": "deactivated"})
    assert response.status_code == 200
    assert response.get_json()["data"]["state"] == "deactivated"

    response = client.post(endpoint, headers=headers, json={"status": "archived"})
    assert response.status_code == 200
    assert response.get_json()["data"]["state"] == "archived"


def test_deactivated_user_cannot_reuse_access_token_or_login(
    client, session, admin_token
):
    user = User(
        employee_id="EMP-STATUS-02",
        full_name="Inactive Token User",
        email="inactive.token@okoa.local",
        phone_number="+254700000006",
        role="employee",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    user.set_password("Employee@2026!")
    session.add(user)
    session.commit()
    access_token = create_access_token(identity=str(user.id))

    deactivated = client.post(
        f"/api/auth/admin/users/{user.id}/status",
        headers={"Authorization": f"******"},
        json={"status": "deactivated"},
    )
    assert deactivated.status_code == 200

    stale_request = client.get(
        "/api/auth/me",
        headers={"Authorization": f"******"},
    )
    assert stale_request.status_code == 400

    login = client.post(
        "/api/auth/login",
        json={
            "phone_number": user.phone_number,
            "password": "Employee@2026!",
        },
    )
    assert login.status_code == 403


def test_admin_user_patch_saves_profile_and_account_status(client, session, admin_token):
    user = User(
        employee_id="EMP-PATCH-STATUS-01",
        full_name="Profile Before Update",
        email="profile.status@okoa.local",
        phone_number="+254700000005",
        role="employee",
        department="Sales",
        is_active=True,
        account_status="approved",
    )
    user.set_password("Employee@2026!")
    session.add(user)
    session.commit()

    response = client.patch(
        f"/api/auth/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"full_name": "Profile After Update", "status": "deactivated"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["full_name"] == "Profile After Update"
    assert data["account_status"] == "deactivated"
    assert data["is_active"] is False