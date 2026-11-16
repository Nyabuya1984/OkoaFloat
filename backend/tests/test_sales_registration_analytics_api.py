from datetime import date, timedelta

from app.extensions import db
from app.models import (
    DepartmentAssignmentHistory,
    SalesDailyReport,
    User,
)
from app.utils.rbac import assign_user_role


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_registration_analytics_permission_filters_and_record_pagination(
    client, app, rbac_tokens
):
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        complete_documents = {
            "certificate_of_incorporation": True,
            "company_kra_pin": "yes",
            "six_months_commission": 1,
            "owners_directors_national_ids": "true",
            "cr12_directors": True,
        }
        db.session.add_all([
            SalesDailyReport(
                employee_id=employee.id,
                agent_name=f"Complete Shop {index}",
                business_location="Nairobi",
                date_visited=date(2026, 4, 3),
                registration_date=date(2026, 4, 3),
                completion_date=date(2026, 4, 4),
                customer_type="agent",
                outcome="ready_to_register",
                documents=complete_documents,
                witness_name="Witness",
                witness_id_number="SECRET-ID",
                witness_phone="SECRET-PHONE",
                report_data={"registration_status": "INCOMPLETE"},
            )
            for index in range(2)
        ])
        db.session.add(SalesDailyReport(
            employee_id=employee.id,
            agent_name="Existing Shop",
            business_location="Nairobi",
            date_visited=date(2026, 4, 3),
            customer_type="agent",
            outcome="existing",
            documents={},
            report_data={},
        ))
        db.session.commit()

    denied = client.get(
        "/api/sales/analytics/registrations",
        headers=_headers(rbac_tokens["customer_care"]),
    )
    assert denied.status_code == 403

    headers = _headers(rbac_tokens["sales"])
    analytics = client.get(
        "/api/sales/analytics/registrations?from=2026-04-01&to=2026-04-30"
        "&category=agent&year=2026&month=4",
        headers=headers,
    )
    assert analytics.status_code == 200, analytics.get_json()
    totals = analytics.get_json()["data"]["daily"]["totals"]
    assert totals["visited"] == 2
    assert totals["complete"] == 2
    assert totals["total_registrations"] == 2

    first_page = client.get(
        "/api/sales/analytics/registration-records?visit_date=2026-04-03"
        "&category=agent&status=complete&page=1&per_page=1",
        headers=headers,
    )
    payload = first_page.get_json()["data"]
    assert first_page.status_code == 200
    assert payload["total_rows"] == 2
    assert len(payload["rows"]) == 1
    assert "witness_id_number" in payload["rows"][0]
    assert payload["rows"][0]["completion_date"] == "2026-04-04"

    second_page = client.get(
        "/api/sales/analytics/registration-records?visit_date=2026-04-03"
        "&category=agent&status=complete&page=2&per_page=1",
        headers=headers,
    )
    assert second_page.get_json()["data"]["rows"][0]["id"] != payload["rows"][0]["id"]


def test_registration_analytics_rejects_invalid_filters(client, rbac_tokens):
    response = client.get(
        "/api/sales/analytics/registrations?month=13",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["message"]


def test_manager_performance_and_reports_are_scoped_to_sales_hierarchy(
    client, app, rbac_tokens, admin_token
):
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        department_manager = User.query.filter_by(
            email="leave.manager2@example.test"
        ).one()
        department_id = employee.department_id
        other_employee = User(
            employee_id="RBAC-SALES-OTHER",
            full_name="Other Sales Employee",
            email="rbac.sales.other@example.test",
            phone_number="+254700001099",
            role="employee",
            department="Sales & Marketing",
            department_id=department_id,
            manager_id=department_manager.id,
            is_active=True,
            account_status="approved",
        )
        other_employee.set_password("RBAC-Test-Password!")
        db.session.add(other_employee)
        db.session.flush()
        assign_user_role(other_employee, "sales")
        db.session.add(DepartmentAssignmentHistory(
            user_id=other_employee.id,
            department_id=department_id,
            department_name="Sales & Marketing",
            organizational_role="field_agent",
        ))
        db.session.add(SalesDailyReport(
            employee_id=employee.id,
            agent_name="Completed Shop",
            business_location="Nairobi",
            date_visited=date(2026, 4, 3),
            registration_date=date(2026, 4, 3),
            completion_date=date(2026, 4, 4),
            customer_type="agent",
            outcome="ready_to_register",
            documents={
                "certificate_of_incorporation": True,
                "company_kra_pin": True,
                "six_months_commission": True,
                "owners_directors_national_ids": True,
                "cr12_directors": True,
            },
            witness_name="Witness",
            witness_id_number="ID-1",
            witness_phone="0700000000",
            report_data={},
        ))
        db.session.add(SalesDailyReport(
            employee_id=other_employee.id,
            agent_name="Other Employee Shop",
            business_location="Nairobi",
            date_visited=date(2026, 4, 3),
            customer_type="agent",
            outcome="ready_to_register",
            documents={},
            report_data={},
        ))
        db.session.commit()
        employee_id = employee.id

    team_headers = _headers(rbac_tokens["team_leader"])
    employee_performance = client.get(
        "/api/sales/analytics/employee-performance",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert employee_performance.status_code == 403

    performance = client.get(
        "/api/sales/analytics/employee-performance"
        "?from=2026-04-01&to=2026-04-07&category=agent",
        headers=team_headers,
    )
    assert performance.status_code == 200, performance.get_json()
    performance_data = performance.get_json()["data"]
    assert performance_data["date_basis"] == "completion_date"
    assert performance_data["total_complete"] == 1
    assert len(performance_data["rows"]) == 1
    assert performance_data["rows"][0]["employee_id"] == employee_id

    team_reports = client.get("/api/sales/reports", headers=team_headers)
    assert team_reports.status_code == 200, team_reports.get_json()
    assert [row["agent_name"] for row in team_reports.get_json()["data"]] == [
        "Completed Shop"
    ]
    assert team_reports.get_json()["data"][0]["employee_name"] == "RBAC sales"
    team_name_filter = client.get(
        "/api/sales/reports?employee_name=rbac%20sales",
        headers=team_headers,
    )
    assert team_name_filter.status_code == 200
    assert [row["employee_name"] for row in team_name_filter.get_json()["data"]] == [
        "RBAC sales"
    ]
    team_v2_reports = client.get(
        "/api/sales/v2/reports?scope=team",
        headers=team_headers,
    )
    assert team_v2_reports.status_code == 200, team_v2_reports.get_json()
    assert [
        row["agent_name"] for row in team_v2_reports.get_json()["data"]["rows"]
    ] == ["Completed Shop"]
    assert team_v2_reports.get_json()["data"]["rows"][0]["employee_name"] == "RBAC sales"
    team_v2_name_filter = client.get(
        "/api/sales/v2/reports?scope=team&employee_name=rbac%20sales",
        headers=team_headers,
    )
    assert team_v2_name_filter.status_code == 200
    assert [
        row["employee_name"]
        for row in team_v2_name_filter.get_json()["data"]["rows"]
    ] == ["RBAC sales"]
    out_of_scope_name_filter = client.get(
        "/api/sales/v2/reports?scope=team&employee_name=Other",
        headers=team_headers,
    )
    assert out_of_scope_name_filter.status_code == 200
    assert out_of_scope_name_filter.get_json()["data"]["total_rows"] == 0
    team_v2_performance = client.get(
        "/api/sales/v2/performance/team?scope=team",
        headers=team_headers,
    )
    assert team_v2_performance.status_code == 200, team_v2_performance.get_json()
    assert [
        row["agent_id"]
        for row in team_v2_performance.get_json()["data"]["rows"]
    ] == [employee_id]

    employee_reports = client.get(
        "/api/sales/reports",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert employee_reports.status_code == 200, employee_reports.get_json()
    assert [
        row["agent_name"] for row in employee_reports.get_json()["data"]
    ] == ["Completed Shop"]
    employee_team_scope = client.get(
        "/api/sales/v2/reports?scope=team",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert employee_team_scope.status_code == 403

    department_performance = client.get(
        "/api/sales/analytics/employee-performance",
        headers=_headers(rbac_tokens["department_manager"]),
    )
    assert department_performance.status_code == 200, department_performance.get_json()
    department_rows = department_performance.get_json()["data"]["rows"]
    assert len(department_rows) == 2
    assert sum(row["complete"] == 0 for row in department_rows) == 1
    department_v2_reports = client.get(
        "/api/sales/v2/reports?scope=team",
        headers=_headers(rbac_tokens["department_manager"]),
    )
    assert department_v2_reports.status_code == 200, department_v2_reports.get_json()
    assert {
        row["agent_name"]
        for row in department_v2_reports.get_json()["data"]["rows"]
    } == {"Completed Shop", "Other Employee Shop"}
    assert {
        row["employee_name"]
        for row in department_v2_reports.get_json()["data"]["rows"]
    } == {"RBAC sales", "Other Sales Employee"}
    department_name_filter = client.get(
        "/api/sales/reports?employee_name=Other%20Sales",
        headers=_headers(rbac_tokens["department_manager"]),
    )
    assert department_name_filter.status_code == 200
    assert [
        row["employee_name"] for row in department_name_filter.get_json()["data"]
    ] == ["Other Sales Employee"]

    general_manager_org = client.get(
        "/api/sales/v2/registrations/org?scope=org",
        headers=_headers(rbac_tokens["general_manager"]),
    )
    assert general_manager_org.status_code == 200, general_manager_org.get_json()
    general_manager_performance = client.get(
        "/api/sales/analytics/employee-performance",
        headers=_headers(rbac_tokens["general_manager"]),
    )
    assert general_manager_performance.status_code == 200
    assert len(general_manager_performance.get_json()["data"]["rows"]) == 2
    general_manager_reports = client.get(
        "/api/sales/reports",
        headers=_headers(rbac_tokens["general_manager"]),
    )
    assert general_manager_reports.status_code == 200
    assert {
        row["employee_name"] for row in general_manager_reports.get_json()["data"]
    } == {"RBAC sales", "Other Sales Employee"}

    superadmin_performance = client.get(
        "/api/sales/analytics/employee-performance",
        headers=_headers(admin_token),
    )
    assert superadmin_performance.status_code == 200
    assert len(superadmin_performance.get_json()["data"]["rows"]) == 2

    drilldown = client.get(
        "/api/sales/analytics/registration-records"
        f"?metric=complete&employee_id={employee_id}"
        "&completion_from=2026-04-01&completion_to=2026-04-07",
        headers=team_headers,
    )
    assert drilldown.status_code == 200, drilldown.get_json()
    assert [row["agent_name"] for row in drilldown.get_json()["data"]["rows"]] == [
        "Completed Shop"
    ]


def test_record_detail_filters_weekday_outcome_and_unknown_document_state_is_pending(
    client, app, rbac_tokens
):
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        db.session.add_all([
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Explicitly Pending",
                business_location="Nairobi",
                date_visited=date(2026, 4, 3),  # Friday; Monday=0.
                registration_date=date(2026, 4, 3),
                customer_type="agent",
                outcome="ready_to_register",
                documents={"company_kra_pin": False},
                report_data={},
            ),
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Unknown State",
                business_location="Nairobi",
                date_visited=date(2026, 4, 3),
                registration_date=date(2026, 4, 3),
                customer_type="agent",
                outcome="ready_to_register",
                documents={"company_kra_pin": "unknown"},
                report_data={},
            ),
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Different Outcome",
                business_location="Nairobi",
                date_visited=date(2026, 4, 3),
                customer_type="agent",
                outcome="appointment",
                documents={},
                report_data={},
            ),
        ])
        db.session.commit()

    headers = _headers(rbac_tokens["sales"])
    query = (
        "/api/sales/analytics/registration-records?day=4"
        "&outcome=ready_to_register&metric=document_pending"
        "&document=company_kra_pin"
    )
    pending = client.get(query, headers=headers)
    assert pending.status_code == 200, pending.get_json()
    rows = pending.get_json()["data"]["rows"]
    assert {row["agent_name"] for row in rows} == {"Explicitly Pending", "Unknown State"}

    submitted = client.get(
        query.replace("document_pending", "document_submitted"),
        headers=headers,
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["data"]["total_rows"] == 0


def test_shared_appointment_filter_accepts_upcoming_and_past_and_outcome(
    client, app, rbac_tokens
):
    today = date.today()
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        db.session.add_all([
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Future Appointment",
                business_location="Nairobi",
                date_visited=today,
                customer_type="agent",
                outcome="appointment",
                documents={},
                report_data={"appointment_date": (today + timedelta(days=1)).isoformat()},
            ),
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Past Appointment",
                business_location="Nairobi",
                date_visited=today,
                customer_type="agent",
                outcome="appointment",
                documents={},
                report_data={"appointment_date": (today - timedelta(days=1)).isoformat()},
            ),
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Other Outcome",
                business_location="Nairobi",
                date_visited=today,
                customer_type="agent",
                outcome="interested",
                documents={},
                report_data={"appointment_date": (today + timedelta(days=1)).isoformat()},
            ),
        ])
        db.session.commit()

    headers = _headers(rbac_tokens["sales"])
    upcoming_params = "?appointment=upcoming&outcome=appointment"
    analytics = client.get(
        f"/api/sales/analytics/registrations{upcoming_params}",
        headers=headers,
    )
    assert analytics.status_code == 200, analytics.get_json()
    assert analytics.get_json()["data"]["daily"]["totals"]["visited"] == 1

    upcoming_records = client.get(
        f"/api/sales/analytics/registration-records{upcoming_params}&metric=visited",
        headers=headers,
    )
    assert upcoming_records.status_code == 200, upcoming_records.get_json()
    assert [row["agent_name"] for row in upcoming_records.get_json()["data"]["rows"]] == [
        "Future Appointment"
    ]

    past_records = client.get(
        "/api/sales/analytics/registration-records"
        "?appointment=past&outcome=appointment&metric=visited",
        headers=headers,
    )
    assert past_records.status_code == 200, past_records.get_json()
    assert [row["agent_name"] for row in past_records.get_json()["data"]["rows"]] == [
        "Past Appointment"
    ]


def test_view_only_registration_record_does_not_expose_witness_id_or_phone(
    client, app, rbac_tokens, monkeypatch
):
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        report = SalesDailyReport(
            employee_id=employee.id,
            agent_name="Protected Shop",
            business_location="Nairobi",
            date_visited=date(2026, 4, 4),
            customer_type="agent",
            outcome="ready_to_register",
            documents={},
            witness_name="Witness",
            witness_id_number="PRIVATE-ID",
            witness_phone="PRIVATE-PHONE",
            report_data={},
        )
        db.session.add(report)
        db.session.commit()

    import app.api.sales as sales_api

    monkeypatch.setattr(
        sales_api,
        "can",
        lambda _user, permission: permission == "sales_reports.view",
    )
    response = client.get(
        "/api/sales/analytics/registration-records?visit_date=2026-04-04",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert response.status_code == 200, response.get_json()
    record = response.get_json()["data"]["rows"][0]
    assert record["witness_name"] == "Witness"
    assert "witness_id_number" not in record
    assert "witness_phone" not in record
