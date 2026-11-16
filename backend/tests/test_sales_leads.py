from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import Workbook

from app.extensions import db
from app.models import (
    AuditLog,
    DepartmentAssignmentHistory,
    Role,
    SalesCallLog,
    SalesFollowUp,
    SalesLead,
    SalesRegistration,
    User,
)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _prepare_sales_scope(app):
    with app.app_context():
        sales_role = Role.query.filter_by(name="sales").one()
        manager = User.query.filter_by(email="leave.manager3@example.test").one()
        employee = User.query.filter_by(email="rbac.sales@example.test").one()
        from app.utils.rbac import assign_user_role
        for user in (manager, employee):
            assign_user_role(user, "sales")
            assignment = DepartmentAssignmentHistory.query.filter_by(
                user_id=user.id, ended_at=None
            ).one()
            assignment.role_id = sales_role.id
            assignment.role_name = sales_role.name
        db.session.commit()
        return manager.id, employee.id


def test_lead_upload_allocation_and_conditional_telesales_fields(
    app, client, rbac_tokens
):
    manager_id, employee_id = _prepare_sales_scope(app)
    upload = client.post(
        "/api/sales/leads/import",
        headers=_headers(rbac_tokens["team_leader"]),
        data={"file": (BytesIO(
            b"lead_name,phone_number,business_name,location,source\n"
            b"Jane Owner,+254700000077,Jane Shop,Nairobi,Campaign\n"
        ), "leads.csv")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201, upload.get_json()
    assert upload.get_json()["data"]["created"] == 1
    manager_leads = client.get(
        "/api/sales/leads", headers=_headers(rbac_tokens["team_leader"])
    )
    lead_id = manager_leads.get_json()["data"][0]["id"]
    assigned = client.patch(
        f"/api/sales/leads/{lead_id}/allocation",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"employee_id": employee_id},
    )
    assert assigned.status_code == 200, assigned.get_json()
    assert assigned.get_json()["data"]["assigned_to_id"] == employee_id
    filtered_leads = client.get(
        f"/api/sales/leads?from=2026-01-01&to=2027-01-01&employee_id={employee_id}",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert filtered_leads.status_code == 200
    assert [row["id"] for row in filtered_leads.get_json()["data"]] == [lead_id]
    invalid_filter = client.get(
        "/api/sales/leads/analytics?from=not-a-date",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert invalid_filter.status_code == 422

    lead_rows = client.get(
        "/api/sales/leads", headers=_headers(rbac_tokens["sales"])
    )
    assert lead_rows.status_code == 200
    assert lead_rows.get_json()["data"][0]["lead_name"] == "Jane Owner"
    employee_analytics = client.get(
        "/api/sales/leads/analytics?from=2026-01-01&to=2027-01-01",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert employee_analytics.status_code == 200, employee_analytics.get_json()
    assert employee_analytics.get_json()["data"]["call_attempts"] == 2
    forbidden_employee_analytics = client.get(
        f"/api/sales/leads/analytics?employee_id={manager_id}",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert forbidden_employee_analytics.status_code == 403

    missing_callback = client.patch(
        f"/api/sales/leads/{lead_id}",
        headers=_headers(rbac_tokens["sales"]),
        json={"status": "callback_requested"},
    )
    assert missing_callback.status_code == 422

    callback = client.patch(
        f"/api/sales/leads/{lead_id}",
        headers=_headers(rbac_tokens["sales"]),
        json={
            "status": "callback_requested",
            "callback_date": "2026-11-02",
            "callback_time": "10:30",
            "notes": "Call back about new outlet",
        },
    )
    assert callback.status_code == 200, callback.get_json()
    assert callback.get_json()["data"]["callback_time"] == "10:30"

    missing_reason = client.patch(
        f"/api/sales/leads/{lead_id}",
        headers=_headers(rbac_tokens["sales"]),
        json={"status": "not_interested"},
    )
    assert missing_reason.status_code == 422
    rejected = client.patch(
        f"/api/sales/leads/{lead_id}",
        headers=_headers(rbac_tokens["sales"]),
        json={
            "status": "not_interested",
            "outcome_reason": "No current need",
            "notes": "Client declined for now",
        },
    )
    assert rejected.status_code == 200
    history = client.get(
        "/api/sales/leads/call-history/export.csv?from=2026-01-01"
        f"&to=2027-01-01&employee_id={employee_id}",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert history.status_code == 200
    assert "text/csv" in history.content_type
    assert "sales-call-history.csv" in history.headers["Content-Disposition"]
    assert "Jane Owner" in history.get_data(as_text=True)
    assert "Call back about new outlet" in history.get_data(as_text=True)
    assert "No current need" in history.get_data(as_text=True)
    lead_sheet = client.get(
        "/api/sales/leads/export.csv",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert lead_sheet.status_code == 200
    assert lead_sheet.get_data(as_text=True).splitlines()[0].startswith(
        "Business Name,Head Office Location,Director's Name,Phone Number,"
        "M-Pesa Agent Name,M-Pesa Agent Number,M-Pesa Store Number"
    )
    excel_sheet = client.get(
        "/api/sales/leads/export.xlsx",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert excel_sheet.status_code == 200
    workbook = load_workbook(BytesIO(excel_sheet.data), read_only=True)
    assert next(workbook.active.iter_rows(values_only=True))[:7] == (
        "Business Name",
        "Head Office Location",
        "Director's Name",
        "Phone Number",
        "M-Pesa Agent Name",
        "M-Pesa Agent Number",
        "M-Pesa Store Number",
    )
    own_call_history = client.get(
        "/api/sales/leads/call-history/export.csv",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert own_call_history.status_code == 200
    assert "Jane Owner" in own_call_history.get_data(as_text=True)
    own_call_history_xlsx = client.get(
        "/api/sales/leads/call-history/export.csv?format=xlsx",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert own_call_history_xlsx.status_code == 200
    assert "spreadsheetml" in own_call_history_xlsx.content_type
    own_call_history_pdf = client.get(
        "/api/sales/leads/call-history/export.csv?format=pdf",
        headers=_headers(rbac_tokens["sales"]),
    )
    assert own_call_history_pdf.status_code == 200
    assert own_call_history_pdf.content_type == "application/pdf"
    assert own_call_history_pdf.data.startswith(b"%PDF")
    manager_lead_pdf = client.get(
        "/api/sales/leads/export.pdf",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert manager_lead_pdf.status_code == 200
    assert manager_lead_pdf.data.startswith(b"%PDF")
    with app.app_context():
        lead = db.session.get(SalesLead, lead_id)
        assert lead.updated_by_id == employee_id
        assert lead.allocated_by_id == manager_id
        assert AuditLog.query.filter_by(entity="SalesLead", entity_id=str(lead_id)).count() == 4


def test_lead_allocation_and_upload_are_rejected_outside_manager_scope(
    app, client, rbac_tokens
):
    _prepare_sales_scope(app)
    forbidden_upload = client.post(
        "/api/sales/leads/import",
        headers=_headers(rbac_tokens["sales"]),
        data={"file": (BytesIO(b"lead_name,phone_number\nA,+254700000001\n"), "leads.csv")},
        content_type="multipart/form-data",
    )
    assert forbidden_upload.status_code == 403
    assert client.get(
        "/api/sales/leads/assignees",
        headers=_headers(rbac_tokens["sales"]),
    ).status_code == 403


def test_manager_can_edit_and_archive_lead_without_removing_call_history(
    app, client, rbac_tokens
):
    _, employee_id = _prepare_sales_scope(app)
    upload = client.post(
        "/api/sales/leads/import",
        headers=_headers(rbac_tokens["team_leader"]),
        data={"file": (BytesIO(
            b"Business Name,Head Office Location,Director's Name,Phone Number,"
            b"M-Pesa Agent Name,M-Pesa Agent Number,M-Pesa Store Number\n"
            b"Editable Shop,Nairobi,A Owner,+254700000084,A Agent,AGT0084,STR0084\n"
        ), "leads.csv")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201, upload.get_json()
    lead_id = client.get(
        "/api/sales/leads",
        headers=_headers(rbac_tokens["team_leader"]),
    ).get_json()["data"][0]["id"]
    assert client.patch(
        f"/api/sales/leads/{lead_id}/allocation",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"employee_id": employee_id},
    ).status_code == 200
    call = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={"response": "interested", "notes": "Asked for details"},
    )
    assert call.status_code == 201, call.get_json()

    denied_edit = client.patch(
        f"/api/sales/leads/{lead_id}/details",
        headers=_headers(rbac_tokens["sales"]),
        json={"business_name": "Unauthorized Edit"},
    )
    assert denied_edit.status_code == 403
    edited = client.patch(
        f"/api/sales/leads/{lead_id}/details",
        headers=_headers(rbac_tokens["team_leader"]),
        json={
            "business_name": "Updated Shop",
            "business_location": "Westlands",
            "phone_number": "+254700000085",
        },
    )
    assert edited.status_code == 200, edited.get_json()
    assert edited.get_json()["data"]["company_name"] == "Updated Shop"
    assert edited.get_json()["data"]["business_location"] == "Westlands"

    archived = client.delete(
        f"/api/sales/leads/{lead_id}",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert archived.status_code == 200, archived.get_json()
    assert archived.get_json()["data"]["is_archived"] is True
    assert client.get(
        "/api/sales/leads",
        headers=_headers(rbac_tokens["team_leader"]),
    ).get_json()["data"] == []
    archived_list = client.get(
        "/api/sales/leads?include_archived=true",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert archived_list.status_code == 200
    assert archived_list.get_json()["data"][0]["call_logs"][0]["notes"] == "Asked for details"
    with app.app_context():
        assert SalesCallLog.query.filter_by(lead_id=lead_id).count() == 1
        assert AuditLog.query.filter_by(
            entity="SalesLead",
            entity_id=str(lead_id),
            action="sales_lead_updated",
        ).count() == 1
        assert AuditLog.query.filter_by(
            entity="SalesLead",
            entity_id=str(lead_id),
            action="sales_lead_archived",
        ).count() == 1


def test_excel_lead_upload_distributes_rows_across_sales_representatives(
    app, client, rbac_tokens
):
    _, employee_id = _prepare_sales_scope(app)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([
        "Business Name", "Head Office Location", "Director's Name", "Phone Number",
        "M-Pesa Agent Name", "M-Pesa Agent Number", "M-Pesa Store Number",
    ])
    sheet.append([
        "Excel Sample Shop", "Nairobi", "Amina Owner", "+254700000092",
        "Amina Agent", "AGT0092", "STR0092",
    ])
    content = BytesIO()
    workbook.save(content)
    content.seek(0)
    upload = client.post(
        "/api/sales/leads/import",
        headers=_headers(rbac_tokens["team_leader"]),
        data={
            "file": (content, "leads.xlsx"),
            "distribute_evenly": "true",
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201, upload.get_json()
    assert upload.get_json()["data"]["created"] == 1
    assert upload.get_json()["data"]["assigned"] == 1
    with app.app_context():
        lead = SalesLead.query.filter_by(phone_number="+254700000092").one()
        assert lead.company_name == "Excel Sample Shop"
        assert lead.director_name == "Amina Owner"
        assert lead.assigned_to_id == employee_id


def test_bulk_lead_sharing_and_even_distribution_require_reassignment_reason(
    app, client, rbac_tokens
):
    _, employee_id = _prepare_sales_scope(app)
    upload = client.post(
        "/api/sales/leads/import",
        headers=_headers(rbac_tokens["team_leader"]),
        data={"file": (BytesIO(
            b"Business Name,Head Office Location,Director's Name,Phone Number,"
            b"M-Pesa Agent Name,M-Pesa Agent Number,M-Pesa Store Number\n"
            b"First Shop,Nairobi,A Owner,+254700000081,A Agent,AGT0081,STR0081\n"
            b"Second Shop,Nairobi,B Owner,+254700000082,B Agent,AGT0082,STR0082\n"
        ), "leads.csv")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201, upload.get_json()
    lead_ids = [
        lead["id"]
        for lead in client.get(
            "/api/sales/leads",
            headers=_headers(rbac_tokens["team_leader"]),
        ).get_json()["data"]
    ]

    assigned = client.post(
        "/api/sales/leads/assignments/bulk",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"lead_ids": lead_ids, "employee_id": employee_id},
    )
    assert assigned.status_code == 201, assigned.get_json()
    assert assigned.get_json()["data"]["assigned"] == 2

    missing_reason = client.post(
        "/api/sales/leads/assignments/bulk",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"lead_ids": lead_ids, "employee_id": employee_id},
    )
    assert missing_reason.status_code == 422
    reassigned = client.post(
        "/api/sales/leads/assignments/bulk",
        headers=_headers(rbac_tokens["team_leader"]),
        json={
            "lead_ids": lead_ids,
            "employee_id": employee_id,
            "reason": "Balancing the calling workload",
        },
    )
    assert reassigned.status_code == 201, reassigned.get_json()

    missing_distribution_reason = client.post(
        "/api/sales/leads/distribute",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"lead_ids": lead_ids},
    )
    assert missing_distribution_reason.status_code == 422
    split = client.post(
        "/api/sales/leads/distribute",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"lead_ids": lead_ids, "reason": "Share the refreshed list"},
    )
    assert split.status_code == 200, split.get_json()
    assert split.get_json()["data"]["assigned"] == 2

    with app.app_context():
        assert all(
            lead.assigned_to_id == employee_id
            for lead in SalesLead.query.filter(SalesLead.id.in_(lead_ids)).all()
        )


def test_telesales_call_audit_registration_and_retry_workflow(app, client, rbac_tokens):
    manager_id, employee_id = _prepare_sales_scope(app)
    upload = client.post(
        "/api/sales/leads/import",
        headers=_headers(rbac_tokens["team_leader"]),
        data={"file": (BytesIO(
            b"Company_Name,Director_Name,Phone_Number,Head_Office_Location,"
            b"Business_Location,M_Pesa_Agent_Name,M_Pesa_Agent_Number,M_Pesa_Store_Number\n"
            b"Sample Shop,Jane Owner,+254700000091,Nairobi CBD,Westlands,Jane Agent,12345,STORE-12\n"
        ), "leads.csv")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201, upload.get_json()
    lead = client.get(
        "/api/sales/leads", headers=_headers(rbac_tokens["team_leader"])
    ).get_json()["data"][0]
    assert lead["company_name"] == "Sample Shop"
    assert lead["director_name"] == "Jane Owner"
    lead_id = lead["id"]
    assert client.patch(
        f"/api/sales/leads/{lead_id}/allocation",
        headers=_headers(rbac_tokens["team_leader"]),
        json={"employee_id": employee_id},
    ).status_code == 200
    new_response = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={"response": "New"},
    )
    assert new_response.status_code == 201, new_response.get_json()
    new_call = new_response.get_json()["data"]["call"]
    assert new_call["response"] == "new"
    assert new_call["contacted_by_user_id"] == employee_id
    assert new_call["contact_date"] and new_call["contact_day"]
    assert len(new_call["contact_time"]) == 8

    wrong_number = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={"response": "wrong_number"},
    )
    assert wrong_number.status_code == 201, wrong_number.get_json()
    wrong_call = wrong_number.get_json()["data"]["call"]
    assert wrong_call["contacted_by_user_id"] == employee_id
    assert wrong_call["contact_date"]
    assert wrong_call["contact_day"]
    assert len(wrong_call["contact_time"]) == 8
    assert wrong_call["reached"] is False
    assert client.get(
        "/api/sales/leads", headers=_headers(rbac_tokens["sales"])
    ).get_json()["data"] == []

    with app.app_context():
        archived_lead = db.session.get(SalesLead, lead_id)
        archived_lead.is_archived = False
        archived_lead.archived_at = None
        archived_lead.status = "new_or_existing"
        db.session.commit()

    incomplete = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={
            "response": "registered",
            "registration_documents": {
                "director_id": True,
                "business_permit": False,
                "tax_certificate": True,
                "till_store_number": True,
            },
            "reason_for_incompleteness": "Awaiting permit image on WhatsApp",
        },
    )
    assert incomplete.status_code == 201, incomplete.get_json()
    assert incomplete.get_json()["data"]["registration"]["status"] == "INCOMPLETE"
    assert incomplete.get_json()["data"]["follow_up"]["task_type"] == "registration_documents"

    missing_decline_reason = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={"response": "not_interested"},
    )
    assert missing_decline_reason.status_code == 422
    missing_appointment = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={"response": "appointment"},
    )
    assert missing_appointment.status_code == 422
    future_appointment = (datetime.utcnow() + timedelta(days=2)).replace(microsecond=0).isoformat()
    appointment = client.post(
        f"/api/sales/leads/{lead_id}/calls",
        headers=_headers(rbac_tokens["sales"]),
        json={"response": "appointment", "appointment_datetime": future_appointment},
    )
    assert appointment.status_code == 201, appointment.get_json()
    assert appointment.get_json()["data"]["follow_up"]["task_type"] == "appointment"

    manager_analytics = client.get(
        "/api/sales/leads/analytics",
        headers=_headers(rbac_tokens["team_leader"]),
    )
    assert manager_analytics.status_code == 200, manager_analytics.get_json()
    analytics = manager_analytics.get_json()["data"]
    assert analytics["call_attempts"] == 4
    assert analytics["reached_calls"] == 3
    assert analytics["funnel"]["registered"] == 1
    assert analytics["incomplete_bottlenecks"][0]["reason"] == "Awaiting permit image on WhatsApp"

    with app.app_context():
        assert SalesCallLog.query.filter_by(lead_id=lead_id).count() == 4
        assert SalesRegistration.query.filter_by(lead_id=lead_id).one().status == "INCOMPLETE"
        assert SalesFollowUp.query.filter_by(lead_id=lead_id, is_completed=False).count() == 2
