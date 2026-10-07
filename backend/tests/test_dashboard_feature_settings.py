from app.models import User


def _create_employee(session):
    employee = User(
        employee_id="DF-EMP-001",
        full_name="Feature Test Employee",
        email="feature.employee@example.test",
        phone_number="+254700000099",
        role="employee",
        department="Sales and Marketing",
        is_active=True,
        account_status="approved",
    )
    employee.set_password("Employee@2026!")
    session.add(employee)
    session.commit()
    return employee.phone_number


def test_system_admin_can_manage_dashboard_features(client, session, login_with_otp):
    system_admin = User(
        employee_id="DF-SYS-001",
        full_name="Feature Test System Admin",
        email="feature.system-admin@example.test",
        phone_number="+254700000098",
        role="system_admin",
        department="IT",
        is_active=True,
        account_status="approved",
    )
    system_admin.set_password("SystemAdmin@2026!")
    session.add(system_admin)
    session.commit()
    token = login_with_otp(system_admin.phone_number, "SystemAdmin@2026!")
    headers = {"Authorization": f"Bearer {token}"}

    features_response = client.get("/api/admin/dashboard-features", headers=headers)
    assert features_response.status_code == 200
    assert "roles" in features_response.get_json()["data"]

    update_response = client.patch(
        "/api/admin/dashboard-features",
        headers=headers,
        json={"role": "manager", "feature": "sales_reports", "enabled": False},
    )
    assert update_response.status_code == 200


def test_super_admin_can_disable_sales_reports_for_a_role(client, admin_token, session, login_with_otp):
    response = client.patch(
        "/api/admin/dashboard-features",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "employee", "feature": "sales_reports", "enabled": False},
    )
    assert response.status_code == 200

    phone_number = _create_employee(session)
    employee_token = login_with_otp(phone_number, "Employee@2026!")
    headers = {"Authorization": f"Bearer {employee_token}"}

    features_response = client.get("/api/admin/dashboard-features", headers=headers)
    assert features_response.get_json()["data"]["features"]["sales_reports"] is False

    sales_response = client.get("/api/sales/reports", headers=headers)
    assert sales_response.status_code == 403
    assert "disabled" in sales_response.get_json()["error"]["message"].lower()


def test_super_admin_can_disable_sales_reports_for_self(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.patch(
        "/api/admin/dashboard-features",
        headers=headers,
        json={"role": "super_admin", "feature": "sales_reports", "enabled": False},
    )
    assert response.status_code == 200

    settings_response = client.get("/api/admin/dashboard-features", headers=headers)
    assert settings_response.get_json()["data"]["features"]["sales_reports"] is False
    assert "SUPER_ADMIN" in settings_response.get_json()["data"]["roles"]

    sales_response = client.get("/api/sales/reports", headers=headers)
    assert sales_response.status_code == 403


def test_super_admin_can_disable_debt_collection_for_a_role(client, admin_token, session, login_with_otp):
    response = client.patch(
        "/api/admin/dashboard-features",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "employee", "feature": "debt_collection", "enabled": False},
    )
    assert response.status_code == 200

    phone_number = _create_employee(session)
    employee_token = login_with_otp(phone_number, "Employee@2026!")
    headers = {"Authorization": f"Bearer {employee_token}"}

    features_response = client.get("/api/admin/dashboard-features", headers=headers)
    assert features_response.get_json()["data"]["features"]["debt_collection"] is False
    debt_response = client.get("/api/debt-collection/summary", headers=headers)
    assert debt_response.status_code == 403
    assert "disabled" in debt_response.get_json()["error"]["message"].lower()


def test_super_admin_assigns_employee_duties_and_personal_dashboard_features(
    client, admin_token, session, login_with_otp
):
    phone_number = _create_employee(session)
    employee = User.query.filter_by(phone_number=phone_number).one()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assign_response = client.put(
        f"/api/admin/users/{employee.id}/duties",
        headers=admin_headers,
        json={"duties": ["debt_collector_agent"]},
    )
    assert assign_response.status_code == 200, assign_response.get_json()
    assert assign_response.get_json()["data"]["duties"] == ["debt_collector_agent"]

    employee_token = login_with_otp(phone_number, "Employee@2026!")
    employee_headers = {"Authorization": f"Bearer {employee_token}"}
    features = client.get("/api/admin/dashboard-features", headers=employee_headers)
    assert features.status_code == 200
    assert features.get_json()["data"]["features"]["debt_collection"] is True
    assert features.get_json()["data"]["features"]["sales_reports"] is False
    assert client.get("/api/debt-collection/summary", headers=employee_headers).status_code == 200
    assert client.get("/api/sales/reports", headers=employee_headers).status_code == 403

    update_response = client.put(
        f"/api/admin/users/{employee.id}/duties",
        headers=admin_headers,
        json={"duties": ["sales_marketing_executive"]},
    )
    assert update_response.status_code == 200
    features = client.get("/api/admin/dashboard-features", headers=employee_headers)
    assert features.get_json()["data"]["features"]["sales_reports"] is True
    assert features.get_json()["data"]["features"]["debt_collection"] is False


def test_employee_cannot_change_dashboard_features(client, session, login_with_otp):
    phone_number = _create_employee(session)
    employee_token = login_with_otp(phone_number, "Employee@2026!")

    response = client.patch(
        "/api/admin/dashboard-features",
        headers={"Authorization": f"Bearer {employee_token}"},
        json={"role": "employee", "feature": "sales_reports", "enabled": False},
    )

    assert response.status_code == 403


def test_sales_api_cors_preflight_does_not_require_authentication(client):
    response = client.options(
        "/api/sales/v2/summary",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3001"