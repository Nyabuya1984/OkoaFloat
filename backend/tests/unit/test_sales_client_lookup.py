from datetime import date

import pytest
from flask import Flask
from flask_jwt_extended import create_access_token

from app.api.sales import sales_bp
from app.extensions import db, jwt
from app.models import Customer, DebtCollectionDebtor, SalesDailyReport, User
from app.utils.rbac import assign_user_role
from app.utils.rbac_seed import seed_rbac


@pytest.fixture()
def sales_client():
    app = Flask("sales_client_lookup_test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="sales-lookup-test-key-long-enough",
        TESTING=True,
    )
    db.init_app(app)
    jwt.init_app(app)
    app.register_blueprint(sales_bp)
    with app.app_context():
        db.create_all()
        seed_rbac()
        staff = User(
            employee_id="SALES-1",
            full_name="Sales Test User",
            email="sales-test@example.invalid",
            role="EMPLOYEE",
            is_active=True,
            account_status="approved",
        )
        staff.set_password("test-only")
        db.session.add(staff)
        db.session.flush()
        assign_user_role(staff, "sales")
        db.session.add(
            SalesDailyReport(
                employee_id=staff.id,
                department="Sales & Marketing",
                agent_name="Bahari Test Agent",
                agent_number="AG-LOOKUP-1",
                store_number="STORE-LOOKUP-1",
                business_location="Nairobi",
                date_visited=date.today(),
                customer_type="sub_agent",
                outcome="existing",
                documents={"business_permit": True},
            )
        )
        db.session.add(
            Customer(
                name="Bahari Care Profile",
                phone_number="+254700000001",
                caller_type="agent",
                agent_name="Bahari Test Agent",
                agent_number="AG-LOOKUP-1",
                store_number="STORE-LOOKUP-1",
                location="Nairobi",
            )
        )
        care_staff = User(
            employee_id="CARE-LOOKUP-1",
            full_name="Customer Care Test User",
            email="care-test@example.invalid",
            role="EMPLOYEE",
            is_active=True,
            account_status="approved",
        )
        debt_staff = User(
            employee_id="DEBT-LOOKUP-1",
            full_name="Debt Collection Test User",
            email="debt-test@example.invalid",
            role="EMPLOYEE",
            is_active=True,
            account_status="approved",
        )
        care_staff.set_password("test-only")
        debt_staff.set_password("test-only")
        db.session.add_all([care_staff, debt_staff])
        db.session.flush()
        assign_user_role(care_staff, "customer_care")
        assign_user_role(debt_staff, "debt_collection")
        db.session.add(
            DebtCollectionDebtor(
                first_name="Bahari",
                other_names="Test Agent",
                agent_msisdn="+254700000002",
                owner_msisdn="+254700000003",
                agent_no="AG-LOOKUP-2",
                store_number="STORE-LOOKUP-2",
                business_name="Bahari Test Agent",
                location="Mombasa",
            )
        )
        db.session.commit()
        token = create_access_token(identity=str(staff.id))
        care_token = create_access_token(identity=str(care_staff.id))
        debt_token = create_access_token(identity=str(debt_staff.id))
        yield app.test_client(), {
            "sales": {"Authorization": f"Bearer {token}"},
            "care": {"Authorization": f"Bearer {care_token}"},
            "debt": {"Authorization": f"Bearer {debt_token}"},
        }
        db.session.remove()
        db.drop_all()


def test_lookup_autofills_sales_details_and_respects_department_permissions(
    sales_client,
):
    client, auth = sales_client
    response = client.get(
        "/api/sales/clients/lookup?field=agent_number&q=AG-LOOKUP-1",
        headers=auth["sales"],
    )

    assert response.status_code == 200, response.get_json()
    matches = response.get_json()["data"]["matches"]
    assert len(matches) == 1
    assert matches[0]["agent_name"] == "Bahari Test Agent"
    assert matches[0]["store_number"] == "STORE-LOOKUP-1"
    assert matches[0]["business_location"] == "Nairobi"
    assert matches[0]["category"] == "mpesa_sub_agent"
    assert matches[0]["documents"]["business_permit"] is True
    assert matches[0]["source"] == "Sales report"


def test_lookup_rejects_unknown_identifier_type(sales_client):
    client, auth = sales_client
    response = client.get(
        "/api/sales/clients/lookup?field=email&q=test@example.invalid",
        headers=auth["sales"],
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("department", "agent_number", "expected_source"),
    [
        ("care", "AG-LOOKUP-1", "Customer Care"),
        ("debt", "AG-LOOKUP-2", "Debt Collection"),
    ],
)
def test_department_agents_can_lookup_clients_without_sales_access(
    sales_client, department, agent_number, expected_source
):
    client, auth = sales_client
    response = client.get(
        f"/api/sales/clients/lookup?field=agent_number&q={agent_number}",
        headers=auth[department],
    )

    assert response.status_code == 200, response.get_json()
    matches = response.get_json()["data"]["matches"]
    assert len(matches) == 1
    assert expected_source in matches[0]["source"]
    assert matches[0]["agent_number"] == agent_number


def test_lookup_permission_does_not_grant_sales_report_access(sales_client):
    client, auth = sales_client

    response = client.get("/api/sales/reports", headers=auth["care"])

    assert response.status_code == 403


def test_customer_care_can_persist_only_ready_to_register_new_client(sales_client):
    client, auth = sales_client
    registration = {
        "agent_name": "Prospective Agent",
        "agent_number": "AG-CARE-1",
        "store_number": "STORE-CARE-1",
        "business_location": "Nairobi",
        "date_visited": "2026-10-26",
        "registration_date": "2026-10-26",
        "customer_type": "sub_agent",
        "outcome": "ready_to_register",
        "new_client": "true",
        "notes": "Caller submitted initial registration details.",
        "witness_name": "Witness",
        "witness_id_number": "ID-100",
        "witness_phone": "0712345678",
    }

    saved = client.post(
        "/api/sales/reports",
        headers=auth["care"],
        data=registration,
    )

    assert saved.status_code == 201, saved.get_json()
    report = saved.get_json()["data"]
    assert report["outcome"] == "ready_to_register"
    assert report["new_client"] is True
    assert report["registration_status"] == "INCOMPLETE"
    assert report["agent_name"] == "Prospective Agent"
    assert report["notes"] == "Caller submitted initial registration details."

    other_outcome = client.post(
        "/api/sales/reports",
        headers=auth["care"],
        data={**registration, "outcome": "interested"},
    )
    assert other_outcome.status_code == 403

    existing_client_write = client.post(
        "/api/sales/reports",
        headers=auth["care"],
        data={**registration, "new_client": "false"},
    )
    assert existing_client_write.status_code == 403

    import_write = client.post(
        "/api/sales/reports/import",
        headers=auth["care"],
    )
    assert import_write.status_code == 403


@pytest.mark.parametrize(
    ("customer_type", "document_fields"),
    [
        (
            "sub_agent",
            [
                "business_permit",
                "individual_kra_pin",
                "six_months_commission",
                "subagent_agent_contract",
                "owner_national_id",
                "sign_contract",
            ],
        ),
        (
            "agent",
            [
                "certificate_of_incorporation",
                "company_kra_pin",
                "six_months_commission",
                "owners_directors_national_ids",
                "cr12_directors",
            ],
        ),
    ],
)
def test_registration_is_complete_only_when_every_category_document_is_selected(
    sales_client, customer_type, document_fields
):
    client, auth = sales_client
    response = client.post(
        "/api/sales/reports",
        headers=auth["care"],
        data={
            "agent_name": "Complete Registration",
            "agent_number": f"AG-COMPLETE-{customer_type}",
            "store_number": f"STORE-COMPLETE-{customer_type}",
            "business_location": "Nairobi",
            "date_visited": "2026-10-26",
            "registration_date": "2026-10-26",
            "customer_type": customer_type,
            "outcome": "ready_to_register",
            "new_client": "true",
            "witness_name": "Witness",
            "witness_id_number": "ID-200",
            "witness_phone": "0712345678",
            **{field: "true" for field in document_fields},
        },
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["registration_status"] == "COMPLETE"
