from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask_jwt_extended import create_access_token
import pytest

from app.extensions import db
from app.models import (
    AgentLocation,
    AgentLocationOverride,
    AgentLocationPolicy,
    AgentLocationSharing,
    Department,
    DepartmentAssignmentHistory,
    SalesDailyReport,
    User,
    UserRole,
)
from app.utils.organization import (
    can_perform_actions,
    can_view_history,
    effective_organizational_roles,
    get_active_assignment,
    is_group_leader_substitute,
    validate_assignment_capacity,
)
from app.utils.rbac import assign_user_role


def _employee(department_name, role_name, title):
    department = Department.query.filter_by(name=department_name).one_or_none()
    if department is None:
        department = Department(name=department_name)
        db.session.add(department)
        db.session.flush()
    suffix = User.query.count() + 1
    employee = User(
        employee_id=f"ORG-{suffix}",
        full_name=f"Organization Test {suffix}",
        email=f"organization.{suffix}@example.test",
        phone_number=f"+254711000{suffix:04d}",
        role="employee",
        department=department.name,
        department_id=department.id,
        job_position_title=title,
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Organization-Test-Password!")
    db.session.add(employee)
    db.session.flush()
    assign_user_role(employee, role_name)
    return employee


def _active_tracking_policy():
    local_now = datetime.now(ZoneInfo("Africa/Nairobi"))
    policy = AgentLocationPolicy(
        id=1,
        is_enabled=True,
        timezone="Africa/Nairobi",
        days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        start_time=(local_now - timedelta(minutes=10)).strftime("%H:%M"),
        end_time=(local_now + timedelta(minutes=10)).strftime("%H:%M"),
    )
    db.session.add(policy)
    db.session.flush()
    return policy


def test_admin_creation_builds_the_reporting_hierarchy(client, admin_token, session):
    created = {}
    role_specs = [
        ("general_manager", "All", None, None),
        ("department_manager", "Sales and Marketing", "sales", "general_manager"),
        ("team_leader", "Sales and Marketing", "sales", "department_manager"),
        ("field_agent", "Sales and Marketing", "sales", "team_leader"),
    ]
    manager_id = None
    for index, (organizational_role, department, department_role, _) in enumerate(role_specs):
        response = client.post(
            "/api/auth/admin/users",
            headers={"Authorization": f"******"},
            json={
                "full_name": f"Hierarchy User {index}",
                "official_email": f"hierarchy.user.{index}@example.test",
                "phone_number": f"+25471100{index:04d}",
                "password": "Organization-Test-Password!",
                "department": department,
                "department_role": department_role,
                "organizational_role": organizational_role,
                **({"manager_id": manager_id} if manager_id is not None else {}),
            },
        )
        assert response.status_code == 200, response.get_json()
        employee_id = response.get_json()["data"]["id"]
        created[organizational_role] = session.get(User, employee_id)
        if organizational_role != "general_manager":
            assert created[organizational_role].manager_id == manager_id
        manager_id = employee_id

    assert created["field_agent"].email == created["field_agent"].personal_email
    assert get_active_assignment(created["field_agent"].id).organizational_role == "field_agent"
    duplicate_roles = [
        {
            "full_name": "Duplicate General Manager",
            "official_email": "duplicate.general.manager@example.test",
            "phone_number": "+254711009901",
            "department": "All",
            "organizational_role": "general_manager",
            "department_role": None,
        },
        {
            "full_name": "Duplicate Department Manager",
            "official_email": "duplicate.department.manager@example.test",
            "phone_number": "+254711009902",
            "department": "Sales and Marketing",
            "organizational_role": "department_manager",
            "department_role": "sales",
            "manager_id": created["general_manager"].id,
        },
        {
            "full_name": "Duplicate Team Leader",
            "official_email": "duplicate.team.leader@example.test",
            "phone_number": "+254711009903",
            "department": "Sales and Marketing",
            "organizational_role": "team_leader",
            "department_role": "sales",
            "manager_id": created["department_manager"].id,
        },
    ]
    for duplicate in duplicate_roles:
        response = client.post(
            "/api/auth/admin/users",
            headers={"Authorization": f"******"},
            json={
                **duplicate,
                "password": "Organization-Test-Password!",
            },
        )
        assert response.status_code == 422
        assert "already" in response.get_json()["error"]["message"]


def test_active_hierarchy_assignments_enforce_system_and_department_limits(session):
    department_manager = _employee(
        "Sales and Marketing", "sales", "Department Manager"
    )
    other_department_manager = _employee(
        "Sales and Marketing", "sales", "Field Agent"
    )
    team_leader = _employee("Sales and Marketing", "sales", "Team Leader")
    other_team_leader = _employee("Sales and Marketing", "sales", "Field Agent")
    general_manager = _employee("General Management", "sales", "General Manager")
    other_general_manager = _employee("General Management", "sales", "Field Agent")

    with pytest.raises(ValueError, match="already has a Department Manager"):
        validate_assignment_capacity(
            other_department_manager.id,
            other_department_manager.department_id,
            "department_manager",
        )
    with pytest.raises(ValueError, match="already has a Team Leader"):
        validate_assignment_capacity(
            other_team_leader.id,
            other_team_leader.department_id,
            "team_leader",
        )
    with pytest.raises(ValueError, match="General Manager is already assigned"):
        validate_assignment_capacity(
            other_general_manager.id,
            other_general_manager.department_id,
            "general_manager",
        )


def test_account_activation_requires_a_valid_reporting_manager(
    client, admin_token, session
):
    employee = _employee("Sales and Marketing", "sales", "Field Agent")
    employee.account_status = "pending"
    employee.manager_id = None
    session.commit()

    response = client.post(
        f"/api/auth/admin/users/{employee.id}/status",
        headers={"Authorization": f"******"},
        json={"status": "active"},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["message"] == (
        "A valid reporting manager is required before activation"
    )
    assert employee.account_status == "pending"


def test_department_transfer_revokes_old_writes_and_keeps_read_only_history(
    client, admin_token, session
):
    sales_manager = _employee("Sales and Marketing", "sales", "Department Manager")
    agent = _employee("Sales and Marketing", "sales", "Field Agent")
    agent.manager_id = sales_manager.id
    report = SalesDailyReport(
        employee_id=agent.id,
        department="Sales and Marketing",
        agent_name="M-Pesa Agent",
        date_visited=date(2026, 10, 21),
        customer_type="agent",
        outcome="interested",
    )
    debt_manager = _employee("Debt Collection", "debt_collection", "Department Manager")
    debt_team_leader = _employee("Debt Collection", "debt_collection", "Team Leader")
    debt_team_leader.manager_id = debt_manager.id
    db.session.add(report)
    db.session.commit()
    assert can_perform_actions(agent.id, agent.department_id) is True
    assert can_view_history(agent.id, agent.department_id) is True

    response = client.post(
        "/api/employees/transfer",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": agent.id,
            "department_id": debt_manager.department_id,
            "department_role": "debt_collection",
            "organizational_role": "field_agent",
            "manager_id": debt_team_leader.id,
        },
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["revoked_previous_department_access"] is True

    assignment = get_active_assignment(agent.id)
    assert assignment.department_name == "Debt Collection"
    assert assignment.role_name == "debt_collection"
    assert DepartmentAssignmentHistory.query.filter_by(
        user_id=agent.id, department_name="Sales and Marketing"
    ).one().ended_at is not None
    assert UserRole.query.filter_by(user_id=agent.id).one().role.name == "debt_collection"
    assert can_perform_actions(agent.id, sales_manager.department_id) is False
    assert can_view_history(agent.id, sales_manager.department_id) is True

    token = create_access_token(identity=str(agent.id))
    denied = client.post(
        "/api/sales/reports",
        headers={"Authorization": f"Bearer {token}"},
        data={},
    )
    assert denied.status_code == 403

    history = client.get(
        "/api/organization/reports/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.get_json()["data"][0]["id"] == report.id
    assert history.get_json()["data"][0]["read_only"] is True
    assert history.get_json()["data"][0]["can_edit"] is False
    department_history = client.get(
        f"/api/reports/{sales_manager.department_id}",
        headers={"Authorization": f"******"},
    )
    assert department_history.status_code == 200
    assert department_history.get_json()["data"]["read_only"] is True


def test_admin_profile_edit_updates_department_role_and_reporting_manager(
    client, admin_token, session
):
    sales_team_leader = _employee(
        "Sales and Marketing", "sales", "Team Leader"
    )
    agent = _employee("Sales and Marketing", "sales", "Field Agent")
    agent.manager_id = sales_team_leader.id
    collections_manager = _employee(
        "Debt Collection", "debt_collection", "Department Manager"
    )
    collections_team_leader = _employee(
        "Debt Collection", "debt_collection", "Team Leader"
    )
    collections_team_leader.manager_id = collections_manager.id
    db.session.commit()

    response = client.patch(
        f"/api/auth/admin/users/{agent.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": agent.full_name,
            "official_email": "updated.agent@example.test",
            "phone_number": agent.phone_number,
            "department": "Debt Collection",
            "organizational_role": "field_agent",
            "department_role": "debt_collection",
            "manager_id": collections_team_leader.id,
        },
    )

    assert response.status_code == 200, response.get_json()
    session.refresh(agent)
    assignment = get_active_assignment(agent.id)
    assert agent.email == "updated.agent@example.test"
    assert agent.department == "Debt Collection"
    assert agent.manager_id == collections_team_leader.id
    assert assignment.department_id == collections_manager.department_id
    assert assignment.role_name == "debt_collection"
    assert assignment.organizational_role == "field_agent"
    assert DepartmentAssignmentHistory.query.filter_by(
        user_id=agent.id, department_name="Sales and Marketing"
    ).one().ended_at is not None
    assert department_history.get_json()["data"]["reports"][0]["id"] == report.id


def test_admin_profile_edit_saves_details_when_existing_reporting_chain_is_stale(
    client, admin_token, session
):
    team_leader = _employee("Customer Care", "customer_care", "Team Leader")
    department_manager = _employee(
        "Customer Care", "customer_care", "Department Manager"
    )
    unrelated_agent = _employee("Customer Care", "customer_care", "Field Agent")
    team_leader.manager_id = department_manager.id
    department_manager.manager_id = unrelated_agent.id
    db.session.commit()

    response = client.patch(
        f"/api/auth/admin/users/{team_leader.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": team_leader.full_name,
            "official_email": "updated.team.leader@example.test",
            "phone_number": team_leader.phone_number,
            "department": "Customer Care",
            "organizational_role": "team_leader",
            "department_role": "customer_care",
            "manager_id": department_manager.id,
        },
    )

    assert response.status_code == 200, response.get_json()
    session.refresh(team_leader)
    assert team_leader.email == "updated.team.leader@example.test"
    assert team_leader.manager_id == department_manager.id


def test_admin_can_assign_team_leader_under_department_manager(
    client, admin_token, session
):
    general_manager = _employee(
        "Sales and Marketing", "sales", "General Manager"
    )
    department_manager = _employee(
        "Customer Care", "customer_care", "Department Manager"
    )
    team_leader = _employee(
        "Customer Care", "customer_care", "Field Agent"
    )
    department_manager.manager_id = general_manager.id
    team_leader.manager_id = department_manager.id
    db.session.commit()

    response = client.patch(
        f"/api/auth/admin/users/{team_leader.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "full_name": team_leader.full_name,
            "official_email": team_leader.email,
            "phone_number": team_leader.phone_number,
            "department": "Customer Care",
            "organizational_role": "team_leader",
            "department_role": "customer_care",
            "manager_id": department_manager.id,
        },
    )

    assert response.status_code == 200, response.get_json()
    session.refresh(team_leader)
    assert team_leader.manager_id == department_manager.id
    assert get_active_assignment(team_leader.id).organizational_role == "team_leader"


def test_client_registration_requires_gps_and_location_ping_is_rate_limited(
    client, session
):
    agent = _employee("Sales and Marketing", "sales", "Field Agent")
    other_agent = _employee("Sales and Marketing", "sales", "Field Agent")
    token = create_access_token(identity=str(agent.id))
    headers = {"Authorization": f"Bearer {token}"}

    missing_location = client.post(
        "/api/clients/register",
        headers=headers,
        json={
            "name": "GPS Required Client",
            "phone_number": "+254700123456",
            "client_type": "agent",
        },
    )
    assert missing_location.status_code == 400

    registered = client.post(
        "/api/clients/register",
        headers=headers,
        json={
            "name": "GPS Client",
            "phone_number": "+254700123457",
            "client_type": "agent",
            "client_status": "existing",
            "latitude": -1.2864,
            "longitude": 36.8172,
            "location_accuracy_meters": 12.5,
        },
    )
    assert registered.status_code == 201
    assert registered.get_json()["data"]["latitude"] == -1.2864
    assert registered.get_json()["data"]["created_by_id"] == agent.id
    assert registered.get_json()["data"]["client_status"] == "existing"
    assert registered.get_json()["data"]["client_type"] == "agent"

    invalid_status = client.post(
        "/api/clients/register",
        headers=headers,
        json={
            "name": "Invalid Status Client",
            "phone_number": "+254700123458",
            "client_type": "sub_agent",
            "client_status": "prospect",
            "latitude": -1.2864,
            "longitude": 36.8172,
        },
    )
    assert invalid_status.status_code == 400

    missing_status = client.post(
        "/api/clients/register",
        headers=headers,
        json={
            "name": "Missing Status Client",
            "phone_number": "+254700123459",
            "client_type": "sub_agent",
            "latitude": -1.2864,
            "longitude": 36.8172,
        },
    )
    assert missing_status.status_code == 400

    sharing_headers = {"Authorization": f"******"}
    initial_sharing_status = client.get(
        "/api/organization/agent/location-sharing",
        headers=sharing_headers,
    )
    assert initial_sharing_status.status_code == 200
    assert initial_sharing_status.get_json()["data"]["enabled"] is False
    _active_tracking_policy()
    invalid_sharing_status = client.put(
        "/api/organization/agent/location-sharing",
        headers=sharing_headers,
        json={"enabled": "yes"},
    )
    assert invalid_sharing_status.status_code == 403
    enabled_sharing_status = client.put(
        "/api/organization/agent/location-sharing",
        headers=sharing_headers,
        json={"enabled": True},
    )
    assert enabled_sharing_status.status_code == 403

    invalid_ping = client.post(
        "/api/agent/location",
        headers=headers,
        json={"latitude": 91, "longitude": 36.8172},
    )
    assert invalid_ping.status_code == 400

    first_ping = client.post(
        "/api/agent/location",
        headers=headers,
        json={
            "user_id": other_agent.id,
            "latitude": -1.2864,
            "longitude": 36.8172,
            "accuracy_meters": 12.5,
        },
    )
    assert first_ping.status_code == 201
    saved_location = AgentLocation.query.filter_by(user_id=agent.id).one()
    assert saved_location.user_id == agent.id
    assert saved_location.user_id != other_agent.id
    assert saved_location.is_simulated is False
    second_ping = client.post(
        "/api/agent/location",
        headers=sharing_headers,
        json={"latitude": -1.2863, "longitude": 36.8173},
    )
    assert second_ping.status_code == 429
    disabled_sharing_status = client.put(
        "/api/organization/agent/location-sharing",
        headers=sharing_headers,
        json={"enabled": False},
    )
    assert disabled_sharing_status.status_code == 403
    AgentLocationPolicy.query.filter_by(id=1).one().is_enabled = False
    ping_after_opt_out = client.post(
        "/api/agent/location",
        headers=sharing_headers,
        json={"latitude": -1.2863, "longitude": 36.8173},
    )
    assert ping_after_opt_out.status_code == 403


def test_active_visit_location_requires_explicit_session_and_stops_cleanly(
    client, session
):
    agent = _employee("Sales and Marketing", "sales", "Field Agent")
    headers = {"Authorization": f"******"}
    ping_payload = {
        "latitude": -1.2864,
        "longitude": 36.8172,
        "tracking_mode": "active_visit",
    }

    before_opt_in = client.post(
        "/api/agent/location", headers=headers, json=ping_payload
    )
    assert before_opt_in.status_code == 403
    assert before_opt_in.get_json()["error"]["code"] == "ACTIVE_VISIT_REQUIRED"

    started = client.post(
        "/api/organization/agent/active-visit",
        headers=headers,
        json={"action": "start"},
    )
    assert started.status_code == 200
    assert started.get_json()["data"]["active_visit"] is True

    allowed_ping = client.post(
        "/api/agent/location", headers=headers, json=ping_payload
    )
    assert allowed_ping.status_code == 201
    assert AgentLocation.query.filter_by(user_id=agent.id).count() == 1

    stopped = client.post(
        "/api/organization/agent/active-visit",
        headers=headers,
        json={"action": "stop"},
    )
    assert stopped.status_code == 200
    assert stopped.get_json()["data"]["active_visit"] is False
    assert AgentLocationSharing.query.filter_by(user_id=agent.id).one().is_enabled is False

    after_stop = client.post(
        "/api/agent/location", headers=headers, json=ping_payload
    )
    assert after_stop.status_code == 403
    assert after_stop.get_json()["error"]["code"] == "ACTIVE_VISIT_REQUIRED"


def test_manager_live_tracking_is_scoped_to_the_reporting_hierarchy(client, session):
    department_manager = _employee(
        "Sales and Marketing", "sales", "Department Manager"
    )
    team_leader = _employee("Sales and Marketing", "sales", "Team Leader")
    team_leader.manager_id = department_manager.id
    agent = _employee("Sales and Marketing", "sales", "Field Agent")
    agent.manager_id = team_leader.id
    another_team_leader = _employee(
        "Sales and Marketing", "sales", "Team Leader"
    )
    another_agent = _employee(
        "Sales and Marketing", "sales", "Field Agent"
    )
    another_agent.manager_id = another_team_leader.id
    _active_tracking_policy()
    session.add(AgentLocation(
        user_id=agent.id,
        department_id=agent.department_id,
        latitude=-1.2864,
        longitude=36.8172,
        accuracy_meters=8,
    ))
    session.add(AgentLocation(
        user_id=another_agent.id,
        department_id=another_agent.department_id,
        latitude=-1.2865,
        longitude=36.8173,
        accuracy_meters=9,
    ))
    session.add(AgentLocationSharing(
        user_id=agent.id,
        is_enabled=True,
        updated_at=datetime.utcnow() - timedelta(minutes=1),
    ))
    session.commit()

    department_manager_token = create_access_token(identity=str(department_manager.id))
    response = client.get(
        "/api/manager/agents/live-locations",
        headers={"Authorization": f"Bearer {department_manager_token}"},
    )
    assert response.status_code == 200
    locations = response.get_json()["data"]["agents"]
    assert {row["user_id"] for row in locations} == {
        agent.id,
        another_agent.id,
    }
    agent_status = {row["user_id"]: row for row in locations}
    assert agent_status[agent.id]["sharing_status"] == "on"
    assert agent_status[agent.id]["active_visit"] is True
    assert agent_status[another_agent.id]["sharing_status"] == "on"
    assert agent_status[another_agent.id]["active_visit"] is False
    assert all(len(row["trail"]) == 1 for row in locations)
    trail_response = client.get(
        f"/api/organization/manager/agents/{another_agent.id}/location-trail?hours=24",
        headers={"Authorization": f"Bearer {team_leader_token}"},
    )
    assert trail_response.status_code == 200
    assert trail_response.get_json()["data"]["trail"][0]["latitude"] == -1.2865
    location_stream = client.get(
        "/api/organization/locations/stream",
        headers={"Authorization": f"Bearer {team_leader_token}"},
        buffered=False,
    )
    assert location_stream.status_code == 200
    assert location_stream.mimetype == "text/event-stream"
    assert b"data:" in next(iter(location_stream.response))
    location_stream.close()
    team_leader_token = create_access_token(identity=str(team_leader.id))
    team_locations = client.get(
        "/api/manager/agents/live-locations",
        headers={"Authorization": f"Bearer {team_leader_token}"},
    )
    assert team_locations.status_code == 200
    assert {row["user_id"] for row in team_locations.get_json()["data"]["agents"]} == {
        agent.id,
    }
    assert team_locations.get_json()["data"]["agents"][0]["active_visit"] is True
    forbidden_other_team_trail = client.get(
        f"/api/organization/manager/agents/{another_agent.id}/location-trail?hours=24",
        headers={"Authorization": f"Bearer {team_leader_token}"},
    )
    assert forbidden_other_team_trail.status_code == 403
    range_response = client.get(
        f"/api/organization/manager/agents/{another_agent.id}/location-trail",
        headers={"Authorization": f"Bearer {team_leader_token}"},
        query_string={
            "start": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
            "end": datetime.utcnow().isoformat() + "Z",
        },
    )
    assert range_response.status_code == 200
    assert len(range_response.get_json()["data"]["trail"]) == 1
    invalid_range = client.get(
        f"/api/organization/manager/agents/{another_agent.id}/location-trail",
        headers={"Authorization": f"Bearer {team_leader_token}"},
        query_string={
            "start": datetime.utcnow().isoformat() + "Z",
            "end": (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z",
        },
    )
    assert invalid_range.status_code == 400
    invalid_window = client.get(
        f"/api/organization/manager/agents/{another_agent.id}/location-trail?hours=48",
        headers={"Authorization": f"Bearer {team_leader_token}"},
    )
    assert invalid_window.status_code == 400

    field_agent_token = create_access_token(identity=str(agent.id))
    forbidden = client.get(
        "/api/manager/agents/live-locations",
        headers={"Authorization": f"Bearer {field_agent_token}"},
    )
    assert forbidden.status_code == 403
    forbidden_stream = client.get(
        "/api/organization/locations/stream",
        headers={"Authorization": f"Bearer {field_agent_token}"},
    )
    assert forbidden_stream.status_code == 403
    forbidden_trail = client.get(
        f"/api/organization/manager/agents/{another_agent.id}/location-trail",
        headers={"Authorization": f"Bearer {field_agent_token}"},
    )
    assert forbidden_trail.status_code == 403


def test_admin_schedule_and_team_leader_override_control_automatic_tracking(
    client, admin_token, session
):
    department_manager = _employee(
        "Sales and Marketing", "sales", "Department Manager"
    )
    team_leader = _employee("Sales and Marketing", "sales", "Team Leader")
    team_leader.manager_id = department_manager.id
    agent = _employee("Sales and Marketing", "sales", "Field Agent")
    agent.manager_id = team_leader.id
    session.commit()

    local_now = datetime.now(ZoneInfo("Africa/Nairobi"))
    schedule = {
        "enabled": True,
        "timezone": "Africa/Nairobi",
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "start_time": (local_now - timedelta(minutes=10)).strftime("%H:%M"),
        "end_time": (local_now + timedelta(minutes=10)).strftime("%H:%M"),
    }
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    saved_schedule = client.put(
        "/api/organization/location-tracking/schedule",
        headers=admin_headers,
        json=schedule,
    )
    assert saved_schedule.status_code == 200
    assert saved_schedule.get_json()["data"]["enabled"] is True

    agent_token = create_access_token(identity=str(agent.id))
    agent_headers = {"Authorization": f"Bearer {agent_token}"}
    agent_status = client.get(
        "/api/organization/agent/location-sharing",
        headers=agent_headers,
    )
    assert agent_status.status_code == 200
    assert agent_status.get_json()["data"]["enabled"] is True
    forbidden_schedule_edit = client.put(
        "/api/organization/location-tracking/schedule",
        headers=agent_headers,
        json=schedule,
    )
    assert forbidden_schedule_edit.status_code == 403

    team_leader_token = create_access_token(identity=str(team_leader.id))
    team_headers = {"Authorization": f"Bearer {team_leader_token}"}
    manager_status = client.get(
        "/api/organization/location-tracking/control",
        headers=team_headers,
    )
    assert manager_status.status_code == 200
    assert manager_status.get_json()["data"]["scope"]["type"] == "team"
    assert manager_status.get_json()["data"]["enabled"] is True

    paused = client.put(
        "/api/organization/location-tracking/control",
        headers=team_headers,
        json={"enabled": False},
    )
    assert paused.status_code == 200
    assert paused.get_json()["data"]["enabled"] is False
    assert paused.get_json()["data"]["override_active"] is True
    assert client.get(
        "/api/organization/agent/location-sharing",
        headers=agent_headers,
    ).get_json()["data"]["enabled"] is False

    resumed = client.put(
        "/api/organization/location-tracking/control",
        headers=team_headers,
        json={"enabled": True},
    )
    assert resumed.status_code == 200
    assert resumed.get_json()["data"]["enabled"] is True
    assert AgentLocationOverride.query.filter_by(
        scope_type="team",
        scope_id=team_leader.id,
    ).one().expires_at > datetime.utcnow()

    disabled_schedule = client.put(
        "/api/organization/location-tracking/schedule",
        headers=admin_headers,
        json={**schedule, "enabled": False, "days": []},
    )
    assert disabled_schedule.status_code == 200
    assert client.get(
        "/api/organization/agent/location-sharing",
        headers=agent_headers,
    ).get_json()["data"]["enabled"] is False
    assert AgentLocationOverride.query.count() == 0


def test_department_manager_group_leader_fallback_is_department_scoped(session):
    department_manager = _employee(
        "Sales and Marketing", "sales", "Department Manager"
    )
    team_leader = _employee("Sales and Marketing", "sales", "Group Leader")
    team_leader.manager_id = department_manager.id
    other_manager = _employee(
        "Customer Care", "customer_care", "Department Manager"
    )
    other_leader = _employee("Customer Care", "customer_care", "Group Leader")
    other_leader.manager_id = other_manager.id
    session.flush()

    assert is_group_leader_substitute(
        department_manager, department_manager.department_id
    ) is False

    team_leader.is_active = False
    team_leader.account_status = "deactivated"
    session.flush()

    assert is_group_leader_substitute(
        department_manager, department_manager.department_id
    ) is True
    assert effective_organizational_roles(department_manager) == [
        "department_manager",
        "team_leader",
    ]
    assert is_group_leader_substitute(
        other_manager, other_manager.department_id
    ) is False
