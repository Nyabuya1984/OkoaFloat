import csv
import io
from datetime import date

from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models import SalesDailyReport, User


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _report(employee, category, outcome, name, documents=None):
    return SalesDailyReport(
        employee_id=employee.id,
        created_by_id=employee.id,
        department=employee.department,
        agent_name=name,
        business_location="Nairobi",
        date_visited=date(2026, 10, 20),
        registration_date=date(2026, 10, 20) if outcome == "ready_to_register" else None,
        customer_type=category,
        outcome=outcome,
        visit_mode="field_visit",
        witness_name="Witness" if outcome == "ready_to_register" else None,
        witness_id_number="W-100" if outcome == "ready_to_register" else None,
        witness_phone="0711000000" if outcome == "ready_to_register" else None,
        documents=documents or {},
        report_data={
            "new_client": True,
            "registration_status": "INCOMPLETE" if outcome == "ready_to_register" else None,
        },
    )


def test_field_agent_analytics_is_date_filtered_and_scope_limited(client, app, rbac_tokens):
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        db.session.add_all([
            _report(employee, "agent", "ready_to_register", "Incomplete Shop"),
            _report(
                employee, "sub_agent", "ready_to_register", "Complete Shop",
                documents={
                    "business_permit": True,
                    "individual_kra_pin": True,
                    "six_months_commission": True,
                    "subagent_agent_contract": True,
                    "owner_national_id": True,
                    "sign_contract": True,
                },
            ),
            SalesDailyReport(
                employee_id=employee.id,
                agent_name="Outside date",
                business_location="Nairobi",
                date_visited=date(2026, 9, 1),
                customer_type="agent",
                outcome="interested",
                visit_mode="field_visit",
                documents={},
                report_data={"new_client": True},
            ),
        ])
        db.session.commit()

    response = client.get(
        "/api/sales/analytics/field-agents?from=2026-10-01&to=2026-10-31",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert response.status_code == 200, response.get_json()
    result = response.get_json()["data"]
    assert result["scope"] == "mine"
    assert result["totals"] == {
        "visits": 2,
        "eligible_visits": 2,
        "registrations_started": 2,
        "complete": 1,
        "incomplete": 1,
    }
    agent = result["agents"][0]
    assert agent["by_category"]["agent"]["incomplete"] == 1
    assert agent["by_category"]["sub_agent"]["complete"] == 1
    assert agent["completion_rate"] == 50
    assert result["incomplete_visits"][0]["missing_requirements"]
    csv_export = client.get(
        "/api/sales/analytics/field-agents/export.csv?from=2026-10-01&to=2026-10-31",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert csv_export.status_code == 200
    assert "employee_id,employee_name,category,visits" in csv_export.get_data(as_text=True)
    assert "sub_agent" in csv_export.get_data(as_text=True)

    xlsx_export = client.get(
        "/api/sales/analytics/field-agents/export.xlsx?from=2026-10-01&to=2026-10-31",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert xlsx_export.status_code == 200
    export_book = load_workbook(io.BytesIO(xlsx_export.data), read_only=True, data_only=True)
    export_rows = list(export_book.active.iter_rows(values_only=True))
    export_book.close()
    assert export_rows[0][0:3] == ("employee_id", "employee_name", "category")
    assert any(row[2] == "sub_agent" and row[3] == 1 for row in export_rows[1:])

    team_response = client.get(
        "/api/sales/analytics/field-agents?from=2026-10-01&to=2026-10-31",
        headers=_headers(rbac_tokens["department_manager"]),
    )
    assert team_response.status_code == 200
    assert team_response.get_json()["data"]["scope"] == "team"
    assert team_response.get_json()["data"]["totals"]["visits"] == 2

    org_response = client.get(
        "/api/sales/analytics/field-agents?from=2026-10-01&to=2026-10-31",
        headers=_headers(rbac_tokens["general_manager"]),
    )
    assert org_response.status_code == 200
    assert org_response.get_json()["data"]["scope"] == "org"
    assert org_response.get_json()["data"]["totals"]["visits"] == 2


def test_incomplete_registration_recovery_completes_and_notifies_scope(
    client, app, rbac_tokens
):
    with app.app_context():
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        report = _report(employee, "agent", "ready_to_register", "Recovery Shop")
        db.session.add(report)
        db.session.commit()
        report_id = report.id

    employee_headers = _headers(rbac_tokens["sales"])
    tasks = client.get(
        "/api/sales/reports/recovery-follow-ups", headers=employee_headers
    )
    assert tasks.status_code == 200
    assert tasks.get_json()["data"][0]["report_id"] == report_id
    assert "certificate_of_incorporation" in tasks.get_json()["data"][0]["missing_requirements"]

    update = client.patch(
        f"/api/sales/reports/{report_id}/recovery-follow-up",
        headers=employee_headers,
        json={
            "documents": {
                "certificate_of_incorporation": True,
                "company_kra_pin": True,
                "six_months_commission": True,
                "owners_directors_national_ids": True,
                "cr12_directors": True,
            },
            "notes": "Documents verified at the outlet.",
        },
    )
    assert update.status_code == 200, update.get_json()
    assert update.get_json()["data"]["status"] == "COMPLETE"
    assert update.get_json()["data"]["follow_up"]["status"] == "completed"
    assert client.get(
        "/api/sales/reports/recovery-follow-ups", headers=employee_headers
    ).get_json()["data"] == []


def test_xlsx_template_export_and_import_use_the_report_contract(
    client, app, rbac_tokens
):
    headers = _headers(rbac_tokens["sales"])
    template = client.get("/api/sales/reports/template.xlsx", headers=headers)
    assert template.status_code == 200
    workbook = load_workbook(io.BytesIO(template.data), read_only=True, data_only=True)
    columns = list(next(workbook.active.iter_rows(values_only=True)))
    assert {"agent_name", "date_visited", "customer_type", "outcome"} <= set(columns)
    workbook.close()

    output = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["agent_name", "date_visited", "customer_type", "outcome", "visit_mode"])
    sheet.append(["Imported Agent", "2026-10-25", "agent", "interested", "field_visit"])
    workbook.save(output)
    output.seek(0)
    imported = client.post(
        "/api/sales/reports/import",
        headers=headers,
        data={"file": (output, "reports.xlsx")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 201, imported.get_json()
    assert imported.get_json()["data"]["created"] == 1

    exported = client.get("/api/sales/reports/export.xlsx", headers=headers)
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.data), read_only=True, data_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    workbook.close()
    assert rows[0] == tuple(columns)
    assert any("Imported Agent" in row for row in rows[1:])


def test_invalid_report_import_is_atomic(client, rbac_tokens):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["agent_name", "date_visited", "customer_type", "outcome"])
    writer.writeheader()
    writer.writerow({"agent_name": "Valid Agent", "date_visited": "2026-10-25", "customer_type": "agent", "outcome": "interested"})
    writer.writerow({"agent_name": "Invalid Agent", "date_visited": "not-a-date", "customer_type": "agent", "outcome": "interested"})
    response = client.post(
        "/api/sales/reports/import",
        headers=_headers(rbac_tokens["sales"]),
        data={"file": (io.BytesIO(output.getvalue().encode()), "reports.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["data"]["created"] == 0
