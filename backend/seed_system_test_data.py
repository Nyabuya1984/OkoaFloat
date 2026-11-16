"""Seed repeatable, clearly marked synthetic records for department system testing."""

import argparse
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.engine import make_url

from app import create_app
from app.extensions import db
from app.models import (
    CallFollowUp,
    CallLog,
    Client,
    Customer,
    DebtCollectionAssignment,
    DebtCollectionCallLog,
    DebtCollectionCreditRating,
    DebtCollectionDebtor,
    DebtCollectionFollowUpSchedule,
    DebtCollectionLoan,
    DebtCollectionLoanStatusHistory,
    DebtCollectionPayment,
    Department,
    DepartmentAssignmentHistory,
    Escalation,
    LoanSnapshot,
    Role,
    SalesDailyReport,
    User,
    UserRole,
)
from app.utils.okia_business import compute_shift, generate_reference_number
from app.utils.organization import get_active_assignment
from app.utils.okia_seed import seed_reference_data


MARKER = "SYSTEM TEST"
SALES_DEPARTMENT_NAMES = {"sales & marketing", "sales and marketing"}
SYSTEM_TEST_CLIENT_PHONES = (
    "SYS-TEST-SALES-CLIENT-001",
    "SYS-TEST-SALES-CLIENT-002",
    "SYS-TEST-CARE-CLIENT-001",
    "SYS-TEST-DEBT-CLIENT-001",
)
SYSTEM_TEST_CARE_PHONES = tuple(
    f"+254700810{suffix}" for suffix in ("001", "002", "003", "004")
)
SYSTEM_TEST_DEBT_AGENT_NUMBERS = tuple(
    f"SYS-TEST-DC-{suffix}" for suffix in ("001", "002", "003")
)
SYSTEM_TEST_SALES_REPORT_KEYS = tuple(
    f"SYS-TEST-SALES-REPORT-{suffix}" for suffix in ("001", "002", "003")
)
TODAY = date.today()


def _department(name):
    normalized = name.casefold()
    candidates = (
        SALES_DEPARTMENT_NAMES
        if normalized in SALES_DEPARTMENT_NAMES
        else {normalized}
    )
    departments = Department.query.all()
    for department in departments:
        if department.name.casefold() in candidates:
            return department
    raise RuntimeError(f"Required department does not exist: {name}")


def _department_user(department, role_name, organizational_role=None):
    candidates = (
        User.query.join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .join(
            DepartmentAssignmentHistory,
            DepartmentAssignmentHistory.user_id == User.id,
        )
        .filter(
            Role.name == role_name,
            User.department_id == department.id,
            User.is_active.is_(True),
            User.is_archived.is_(False),
            User.is_deleted.is_(False),
            User.account_status == "approved",
            DepartmentAssignmentHistory.ended_at.is_(None),
            DepartmentAssignmentHistory.department_id == department.id,
            DepartmentAssignmentHistory.role_name == role_name,
        )
        .order_by(User.id)
        .all()
    )
    for user in candidates:
        assignment = get_active_assignment(user.id)
        if assignment and (
            organizational_role is None
            or assignment.organizational_role == organizational_role
        ):
            return user
    raise RuntimeError(
        f"No active approved {role_name} user found in {department.name}"
    )


def _seed_clients(departments, staff):
    specs = (
        (
            "sales",
            "SYS-TEST-SALES-CLIENT-001",
            "SYSTEM TEST - Bahari Mobile Shop",
            "agent",
            "new",
            "Bahari Mobile Shop",
            "Westlands, Nairobi",
            -1.2676,
            36.8108,
        ),
        (
            "sales",
            "SYS-TEST-SALES-CLIENT-002",
            "SYSTEM TEST - Lakeview Mini Mart",
            "sub_agent",
            "existing",
            "Lakeview Mini Mart",
            "Milimani, Kisumu",
            -0.0917,
            34.7680,
        ),
        (
            "care",
            "SYS-TEST-CARE-CLIENT-001",
            "SYSTEM TEST - Thika Family Stores",
            "business",
            "existing",
            "Thika Family Stores",
            "Town Centre, Thika",
            -1.0333,
            37.0693,
        ),
        (
            "debt",
            "SYS-TEST-DEBT-CLIENT-001",
            "SYSTEM TEST - Coastline Traders",
            "agent",
            "existing",
            "Coastline Traders",
            "Nyali, Mombasa",
            -4.0435,
            39.6682,
        ),
    )
    created = 0
    for key, phone, name, client_type, status, business, location, lat, lon in specs:
        existing = Client.query.filter_by(phone_number=phone).one_or_none()
        if existing:
            if not existing.name.startswith(f"{MARKER} -"):
                raise RuntimeError(f"Refusing to reuse non-test client phone {phone}")
            continue
        db.session.add(
            Client(
                name=name,
                phone_number=phone,
                email=f"{phone[-3:]}@example.test",
                client_type=client_type,
                client_status=status,
                business_name=business,
                business_location=location,
                latitude=lat,
                longitude=lon,
                location_accuracy_meters=25,
                department_id=departments[key].id,
                created_by_id=staff[key].id,
            )
        )
        created += 1
    return created


def _seed_sales(department, sales_staff):
    specs = (
        {
            "key": "SYS-TEST-SALES-REPORT-001",
            "days_ago": 1,
            "customer_type": "agent",
            "outcome": "interested",
            "business": "SYSTEM TEST - Bahari Mobile Shop",
            "location": "Westlands, Nairobi",
            "visited": 12,
            "notes": "Interested in agent onboarding; follow-up requested.",
        },
        {
            "key": "SYS-TEST-SALES-REPORT-002",
            "days_ago": 2,
            "customer_type": "sub_agent",
            "outcome": "appointment",
            "business": "SYSTEM TEST - Green Hills Grocers",
            "location": "Kilimani, Nairobi",
            "visited": 8,
            "notes": "Appointment booked to review sub-agent onboarding.",
        },
        {
            "key": "SYS-TEST-SALES-REPORT-003",
            "days_ago": 3,
            "customer_type": "agent",
            "outcome": "registered",
            "business": "SYSTEM TEST - Lakeview Mini Mart",
            "location": "Milimani, Kisumu",
            "visited": 15,
            "notes": "Synthetic registration completed with sample documents.",
        },
    )
    documents = {
        "certificate_of_incorporation": True,
        "company_kra_pin": True,
        "six_months_commission": True,
        "owners_directors_national_ids": True,
        "cr12_directors": True,
    }
    created = 0
    for spec in specs:
        existing = SalesDailyReport.query.filter_by(
            agent_number=spec["key"]
        ).first()
        if existing:
            if not (existing.notes or "").startswith(f"{MARKER} |"):
                raise RuntimeError(
                    f"Refusing to reuse non-test sales report {spec['key']}"
                )
            continue
        is_registered = spec["outcome"] == "registered"
        report_data = {
            "customers_visited": spec["visited"],
            "registered_count": 1 if is_registered else 0,
            "appointment_count": 1 if spec["outcome"] == "appointment" else 0,
            "client_type": "new",
        }
        if not is_registered:
            report_data["new_client"] = True
        if spec["outcome"] == "appointment":
            report_data.update(
                {
                    "appointment_date": (
                        TODAY + timedelta(days=5)
                    ).isoformat(),
                    "appointment_time": "10:00",
                }
            )
        report = SalesDailyReport(
            employee_id=sales_staff.id,
            department=department.name,
            agent_name=sales_staff.full_name,
            agent_number=spec["key"],
            store_number=spec["key"].replace("REPORT", "STORE"),
            business_owner_name=f"{MARKER} Business Owner",
            contact_phone="+254700820001",
            id_number="TEST-ID-SALES-001",
            business_location=spec["location"],
            date_visited=TODAY - timedelta(days=spec["days_ago"]),
            registration_date=TODAY - timedelta(days=spec["days_ago"])
            if is_registered
            else None,
            admin_name=sales_staff.full_name,
            witness_name=f"{MARKER} Witness" if is_registered else None,
            witness_id_number="TEST-WITNESS-001" if is_registered else None,
            witness_phone="+254700820002" if is_registered else None,
            customer_type=spec["customer_type"],
            outcome=spec["outcome"],
            visit_mode="field_visit",
            notes=f"{MARKER} | {spec['notes']}",
            documents=documents if is_registered else {},
            uploaded_files=[],
            report_data={
                **report_data,
            },
        )
        db.session.add(report)
        created += 1
    return created


def _seed_customer_care(staff):
    specs = (
        ("001", "Amina Test Client", "agent", "TEST-AGENT-CC-001", "TEST-STORE-CC-001", "Kasarani, Nairobi"),
        ("002", "Baraka Test Client", "potential_client", None, None, "Nakuru Town"),
        ("003", "Pendo Test Client", "agent", "TEST-AGENT-CC-003", "TEST-STORE-CC-003", "Thika Town"),
        ("004", "Kito Test Client", "sales_rep", None, None, "Kisumu Central"),
    )
    customers = {}
    for suffix, name, caller_type, agent_number, store_number, location in specs:
        phone = f"+254700810{suffix}"
        customer = Customer.query.filter_by(phone_number=phone).one_or_none()
        if customer is None:
            customer = Customer(
                name=f"{MARKER} - {name}",
                phone_number=phone,
                email=f"customer-{suffix}@example.test",
                company=f"{MARKER} Test Portfolio",
                caller_type=caller_type,
                location=location,
                agent_name=f"{MARKER} Field Agent" if agent_number else None,
                agent_number=agent_number,
                store_number=store_number,
            )
            db.session.add(customer)
            db.session.flush()
        elif not customer.name.startswith(f"{MARKER} -"):
            raise RuntimeError(f"Refusing to reuse non-test care customer {phone}")
        customers[suffix] = customer

    call_specs = (
        ("001", "LOAN_BALANCE", "Normal", "Resolved", False, "Balance explained; customer confirmed understanding."),
        ("002", "INFORMATION_INQUIRY", "Normal", "Pending Follow-up", False, "Potential client requested a product call-back."),
        ("003", "RECONCILIATION", "Urgent", "Escalated", True, "Synthetic payment reconciliation issue for escalation testing."),
        ("004", "VERIFY_REGISTRATION", "Low", "Resolved", False, "Registration documents verified with the test caller."),
    )
    created_calls = 0
    for suffix, category, priority, status, escalated, summary in call_specs:
        marked_summary = f"{MARKER} | {summary}"
        call = CallLog.query.filter_by(summary=marked_summary).one_or_none()
        if call is None:
            started = datetime.utcnow() - timedelta(days=int(suffix))
            call = CallLog(
                customer_id=customers[suffix].id,
                staff_id=staff.id,
                call_type="Outgoing" if suffix == "004" else "Incoming",
                category=category,
                concern_category=category if suffix != "004" else None,
                outbound_reason="VERIFY_REGISTRATION" if suffix == "004" else None,
                priority=priority,
                summary=marked_summary,
                status=status,
                requires_escalation=escalated,
                escalated_to="general_manager" if escalated else None,
                escalation_reason=marked_summary if escalated else None,
                escalated_at=started if escalated else None,
                escalation_resolved=False,
                call_started_at=started,
                shift_code=compute_shift(started),
                outcome="Escalated" if escalated else status,
            )
            db.session.add(call)
            db.session.flush()
            call.reference_number = generate_reference_number(call.id)
            created_calls += 1
        if suffix == "003" and not Escalation.query.filter_by(call_id=call.id).first():
            db.session.add(
                Escalation(
                    call_id=call.id,
                    to_dept="general_manager",
                    reason=f"{MARKER} reconciliation escalation scenario",
                    status="open",
                )
            )
        if suffix == "002" and not CallFollowUp.query.filter_by(call_log_id=call.id).first():
            db.session.add(
                CallFollowUp(
                    call_log_id=call.id,
                    assigned_to=staff.id,
                    due_date=TODAY + timedelta(days=2),
                    notes=f"{MARKER} follow-up for product inquiry",
                )
            )

    for suffix, limit, balance in (
        ("001", "25000.00", "3800.00"),
        ("003", "40000.00", "12500.00"),
    ):
        if not LoanSnapshot.query.filter_by(
            customer_id=customers[suffix].id,
            source="system_test_seed",
        ).first():
            db.session.add(
                LoanSnapshot(
                    customer_id=customers[suffix].id,
                    mpesa_number=customers[suffix].phone_number,
                    loan_limit=Decimal(limit),
                    outstanding_balance=Decimal(balance),
                    commission_status="SYSTEM TEST - current",
                    source="system_test_seed",
                )
            )
    return len(customers), created_calls


def _seed_debt_collection(department, collector, manager):
    specs = (
        {
            "suffix": "001",
            "first": "TEST Amina",
            "other": "Sample",
            "agent_no": "SYS-TEST-DC-001",
            "store": "SYS-TEST-DC-STORE-001",
            "business": "SYSTEM TEST - Sunrise General Store",
            "location": "Embakasi, Nairobi",
            "amount": Decimal("85000.00"),
            "paid": Decimal("25000.00"),
            "days": 90,
            "status": "overdue",
        },
        {
            "suffix": "002",
            "first": "TEST Baraka",
            "other": "Sample",
            "agent_no": "SYS-TEST-DC-002",
            "store": "SYS-TEST-DC-STORE-002",
            "business": "SYSTEM TEST - Coastline Traders",
            "location": "Nyali, Mombasa",
            "amount": Decimal("62000.00"),
            "paid": Decimal("0.00"),
            "days": 35,
            "status": "promise_to_pay",
        },
        {
            "suffix": "003",
            "first": "TEST Pendo",
            "other": "Sample",
            "agent_no": "SYS-TEST-DC-003",
            "store": "SYS-TEST-DC-STORE-003",
            "business": "SYSTEM TEST - Lakeview Hardware",
            "location": "Milimani, Kisumu",
            "amount": Decimal("34000.00"),
            "paid": Decimal("0.00"),
            "days": 18,
            "status": "active",
        },
    )
    created = {key: 0 for key in ("debtors", "loans", "assignments", "calls", "payments", "follow_ups", "ratings")}
    for spec in specs:
        debtor = DebtCollectionDebtor.query.filter_by(agent_no=spec["agent_no"]).one_or_none()
        if debtor is None:
            debtor = DebtCollectionDebtor(
                first_name=spec["first"],
                other_names=spec["other"],
                agent_msisdn=f"+254700811{spec['suffix']}",
                owner_msisdn=f"+254700812{spec['suffix']}",
                operator_msisdn=f"+254700813{spec['suffix']}",
                agent_no=spec["agent_no"],
                store_number=spec["store"],
                business_name=spec["business"],
                location=spec["location"],
            )
            db.session.add(debtor)
            db.session.flush()
            created["debtors"] += 1
        elif not debtor.business_name.startswith(f"{MARKER} -"):
            raise RuntimeError(f"Refusing to reuse non-test debtor {spec['agent_no']}")

        loan = DebtCollectionLoan.query.filter_by(debtor_id=debtor.id).order_by(
            DebtCollectionLoan.id
        ).first()
        if loan is None:
            loan = DebtCollectionLoan(
                debtor_id=debtor.id,
                loan_amount=spec["amount"],
                amount_paid=spec["paid"],
                loan_date=TODAY - timedelta(days=spec["days"]),
                last_interest_calc_date=TODAY,
                no_of_days=spec["days"],
                status=spec["status"],
            )
            db.session.add(loan)
            db.session.flush()
            created["loans"] += 1
            if spec["status"] == "overdue":
                db.session.add(
                    DebtCollectionLoanStatusHistory(
                        loan_id=loan.id,
                        old_status="active",
                        new_status="overdue",
                        changed_by=manager.id,
                        reason=f"{MARKER} seeded overdue scenario",
                    )
                )
        if not loan.assignments.filter_by(is_active=True).first():
            db.session.add(
                DebtCollectionAssignment(
                    debtor_id=debtor.id,
                    loan_id=loan.id,
                    collector_id=collector.id,
                    assigned_by=manager.id,
                    reason=f"{MARKER} initial collector assignment",
                    is_active=True,
                )
            )
            created["assignments"] += 1

        if spec["paid"] and not DebtCollectionPayment.query.filter_by(loan_id=loan.id).first():
            db.session.add(
                DebtCollectionPayment(
                    loan_id=loan.id,
                    collector_id=collector.id,
                    amount=spec["paid"],
                    payment_date=TODAY - timedelta(days=3),
                    payment_type="partial",
                    notes=f"{MARKER} sample partial repayment",
                )
            )
            created["payments"] += 1

        outcome = {
            "001": "no_answer",
            "002": "promise_to_pay",
            "003": "callback_requested",
        }[spec["suffix"]]
        marked_notes = f"{MARKER} | {outcome} workflow sample"
        call = DebtCollectionCallLog.query.filter_by(
            debtor_id=debtor.id, notes=marked_notes
        ).first()
        if call is None:
            due_date = TODAY + timedelta(days=4 if spec["suffix"] == "002" else 2)
            call = DebtCollectionCallLog(
                debtor_id=debtor.id,
                loan_id=loan.id,
                collector_id=collector.id,
                outcome=outcome,
                notes=marked_notes,
                promised_date=due_date if outcome == "promise_to_pay" else None,
                promised_time="10:00" if outcome == "promise_to_pay" else None,
                promised_amount=Decimal("10000.00") if outcome == "promise_to_pay" else None,
                callback_date=due_date if outcome == "callback_requested" else None,
                callback_time="14:00" if outcome == "callback_requested" else None,
                amount_paid=Decimal("0.00"),
            )
            db.session.add(call)
            db.session.flush()
            created["calls"] += 1
            if outcome in {"promise_to_pay", "callback_requested"}:
                follow_up_type = "PTP" if outcome == "promise_to_pay" else "Callback"
                if not DebtCollectionFollowUpSchedule.query.filter_by(
                    source_call_log_id=call.id
                ).first():
                    db.session.add(
                        DebtCollectionFollowUpSchedule(
                            debtor_id=debtor.id,
                            loan_id=loan.id,
                            collector_id=collector.id,
                            follow_up_type=follow_up_type,
                            due_at=datetime.combine(
                                due_date, time(10 if follow_up_type == "PTP" else 14)
                            ),
                            status="Pending",
                            source_call_log_id=call.id,
                        )
                    )
                    created["follow_ups"] += 1
        if not DebtCollectionCreditRating.query.filter(
            DebtCollectionCreditRating.debtor_id == debtor.id,
            DebtCollectionCreditRating.reason.like(f"{MARKER}%"),
        ).first():
            db.session.add(
                DebtCollectionCreditRating(
                    debtor_id=debtor.id,
                    loan_id=loan.id,
                    grade={"001": "C", "002": "B", "003": "A"}[spec["suffix"]],
                    score={"001": 48, "002": 68, "003": 82}[spec["suffix"]],
                    reason=f"{MARKER} synthetic test rating",
                )
            )
            created["ratings"] += 1
    return created


def _assert_safe_database(app):
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if (
        not app.debug
        or url.host not in {"mysql", "localhost", "127.0.0.1"}
        or not url.database
        or "prod" in url.database.casefold()
    ):
        raise RuntimeError(
            "System-test data actions are restricted to a local development database."
        )


def seed_records(app):
    _assert_safe_database(app)
    with app.app_context():
        departments = {
            "sales": _department("Sales & Marketing"),
            "care": _department("Customer Care"),
            "debt": _department("Debt Collection"),
        }
        staff = {
            "sales": _department_user(departments["sales"], "sales"),
            "care": _department_user(departments["care"], "customer_care"),
            "debt": _department_user(departments["debt"], "debt_collection", "field_agent"),
        }
        debt_manager = _department_user(
            departments["debt"], "debt_collection", "department_manager"
        )

        try:
            seed_reference_data()
            counts = {
                "clients": _seed_clients(departments, staff),
                "sales_reports": _seed_sales(departments["sales"], staff["sales"]),
            }
            care_counts = _seed_customer_care(staff["care"])
            counts["care_customers"], counts["care_calls"] = care_counts
            counts["debt_collection"] = _seed_debt_collection(
                departments["debt"], staff["debt"], debt_manager
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return counts


def delete_records(app):
    _assert_safe_database(app)
    with app.app_context():
        deleted = {"sales_reports": 0, "care_calls": 0, "care_customers": 0, "clients": 0}
        try:
            for report in SalesDailyReport.query.filter(
                SalesDailyReport.agent_number.in_(SYSTEM_TEST_SALES_REPORT_KEYS),
                SalesDailyReport.notes.like(f"{MARKER} |%"),
            ).all():
                db.session.delete(report)
                deleted["sales_reports"] += 1

            care_calls = CallLog.query.filter(
                CallLog.summary.like(f"{MARKER} |%")
            ).all()
            for call in care_calls:
                db.session.delete(call)
                deleted["care_calls"] += 1

            for snapshot in LoanSnapshot.query.filter_by(source="system_test_seed").all():
                db.session.delete(snapshot)

            for phone in SYSTEM_TEST_CARE_PHONES:
                customer = Customer.query.filter_by(phone_number=phone).one_or_none()
                if (
                    customer
                    and customer.name.startswith(f"{MARKER} -")
                    and not CallLog.query.filter_by(customer_id=customer.id).first()
                    and not LoanSnapshot.query.filter_by(customer_id=customer.id).first()
                ):
                    db.session.delete(customer)
                    deleted["care_customers"] += 1

            for phone in SYSTEM_TEST_CLIENT_PHONES:
                client = Client.query.filter_by(phone_number=phone).one_or_none()
                if client and client.name.startswith(f"{MARKER} -"):
                    db.session.delete(client)
                    deleted["clients"] += 1

            debtors = DebtCollectionDebtor.query.filter(
                DebtCollectionDebtor.agent_no.in_(SYSTEM_TEST_DEBT_AGENT_NUMBERS),
                DebtCollectionDebtor.business_name.like(f"{MARKER} -%"),
            ).all()
            debtor_ids = [debtor.id for debtor in debtors]
            loans = (
                DebtCollectionLoan.query.filter(
                    DebtCollectionLoan.debtor_id.in_(debtor_ids)
                ).all()
                if debtor_ids
                else []
            )
            loan_ids = [loan.id for loan in loans]

            def delete_matching(model, column, values):
                if values:
                    db.session.query(model).filter(column.in_(values)).delete(
                        synchronize_session=False
                    )

            delete_matching(
                DebtCollectionFollowUpSchedule,
                DebtCollectionFollowUpSchedule.debtor_id,
                debtor_ids,
            )
            delete_matching(
                DebtCollectionAssignment,
                DebtCollectionAssignment.debtor_id,
                debtor_ids,
            )
            delete_matching(
                DebtCollectionCallLog,
                DebtCollectionCallLog.debtor_id,
                debtor_ids,
            )
            delete_matching(
                DebtCollectionPayment,
                DebtCollectionPayment.loan_id,
                loan_ids,
            )
            delete_matching(
                DebtCollectionCreditRating,
                DebtCollectionCreditRating.debtor_id,
                debtor_ids,
            )
            delete_matching(
                DebtCollectionLoanStatusHistory,
                DebtCollectionLoanStatusHistory.loan_id,
                loan_ids,
            )
            for loan in loans:
                db.session.delete(loan)
            for debtor in debtors:
                db.session.delete(debtor)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    deleted["debt_collection_debtors"] = len(debtors)
    deleted["debt_collection_loans"] = len(loans)
    return deleted


def seed(apply):
    app = create_app("development")
    _assert_safe_database(app)
    if not apply:
        raise RuntimeError("Pass --apply to write synthetic system-test records.")

    counts = seed_records(app)
    print(f"Seeded or retained synthetic records in {make_url(app.config['SQLALCHEMY_DATABASE_URI']).database}:")
    print(f"  Clients: {counts['clients']} new")
    print(f"  Sales reports: {counts['sales_reports']} new")
    print(f"  Customer Care customers: {counts['care_customers']} total")
    print(f"  Customer Care calls: {counts['care_calls']} new")
    for name, count in counts["debt_collection"].items():
        print(f"  Debt Collection {name.replace('_', ' ')}: {count} new")
    print("All seeded records are marked SYSTEM TEST and use example.test contacts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write records to the guarded local development database",
    )
    seed(parser.parse_args().apply)
