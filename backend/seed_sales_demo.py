"""Seed clearly marked telesales sample data for exercising the call workflow."""

from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    AuditLog,
    DepartmentAssignmentHistory,
    SalesCallLog,
    SalesFollowUp,
    SalesLead,
    SalesRegistration,
    User,
)


DEMO_SOURCE = "DEMO TELESALES SAMPLE"
SAMPLES = [
    ("Northstar Mini Mart", "Miriam Njeri", "new_or_existing"),
    ("Kifaru Wholesale", "Peter Mwangi", "interested"),
    ("Lakeside Grocers", "Asha Wanjiku", "not_interested"),
    ("Mwangaza Traders", "Samuel Otieno", "ready_to_register"),
    ("Horizon Retail", "Grace Achieng", "appointment"),
    ("Jirani Supermarket", "David Kamau", "registered"),
    ("Twiga Supplies", "Linet Wambui", "unreachable"),
    ("Tumaini Stores", "Brian Kiptoo", "wrong_number"),
    ("Demo Fresh Foods", "Mercy Atieno", "registered"),
    ("Demo Town Agencies", "Kevin Maina", "interested"),
]


def _is_sales_department(name):
    return "sales" in (name or "").casefold() or "marketing" in (name or "").casefold()


def seed_sales_demo():
    existing = SalesLead.query.filter_by(source=DEMO_SOURCE).count()
    if existing:
        print(f"Found {existing} existing demo telesales leads; no duplicates created.")
        return existing

    users = User.query.filter(
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
        User.account_status == "approved",
    ).order_by(User.id).all()
    assignments = {
        row.user_id: row
        for row in DepartmentAssignmentHistory.query.filter(
            DepartmentAssignmentHistory.ended_at.is_(None)
        ).all()
    }
    sales_users = [
        user for user in users
        if _is_sales_department(
            assignments[user.id].department_name if user.id in assignments else user.department
        )
    ]
    managers = [
        user for user in sales_users
        if user.id in assignments
        and assignments[user.id].organizational_role in {
            "general_manager", "department_manager", "team_leader"
        }
    ]
    representatives = [
        user for user in sales_users
        if user.id not in {manager.id for manager in managers}
    ]
    if not managers or not representatives:
        raise RuntimeError(
            "Create an active Sales & Marketing manager and at least one approved "
            "Sales & Marketing representative before seeding demo telesales leads."
        )

    manager = managers[0]
    now = datetime.utcnow().replace(microsecond=0)
    sample_count = len(SAMPLES)
    for index, (company, director, response) in enumerate(SAMPLES):
        assignee = representatives[index % len(representatives)]
        phone = f"+254799000{index + 101:03d}"
        lead = SalesLead(
            lead_name=director,
            business_name=company,
            company_name=company,
            director_name=director,
            phone_number=phone,
            location=f"{('Nairobi', 'Mombasa', 'Kisumu', 'Nakuru')[index % 4]} CBD",
            head_office_location=f"{('Nairobi', 'Mombasa', 'Kisumu', 'Nakuru')[index % 4]}",
            business_location=f"Demo Business Premises {index + 1}",
            mpesa_agent_name=f"{director} Agent",
            mpesa_agent_number=f"AGT{index + 101:06d}",
            mpesa_store_number=f"STR{index + 101:04d}",
            source=DEMO_SOURCE,
            department_id=assignee.department_id,
            status=response,
            assigned_to_id=assignee.id,
            allocated_by_id=manager.id,
            created_by_id=manager.id,
            updated_by_id=manager.id,
            allocated_at=now - timedelta(days=sample_count - index),
            created_at=now - timedelta(days=sample_count - index),
            updated_at=now - timedelta(days=sample_count - index),
            is_archived=response == "wrong_number",
            archived_at=now if response == "wrong_number" else None,
        )
        db.session.add(lead)
        db.session.flush()

        contact_time = now - timedelta(days=sample_count - index, hours=index % 5)
        reason = "Already using another float provider" if response == "not_interested" else None
        appointment = now + timedelta(days=2, hours=index) if response == "appointment" else None
        call = SalesCallLog(
            lead_id=lead.id,
            contacted_by_user_id=assignee.id,
            contact_datetime=contact_time,
            contact_date=contact_time.date(),
            contact_day=contact_time.strftime("%A"),
            contact_time=contact_time.strftime("%H:%M:%S"),
            response=response,
            reason_for_decline=reason,
            appointment_datetime=appointment,
            notes=f"Seeded demo call for {company}.",
            reached=response not in {"unreachable", "wrong_number"},
            created_at=contact_time,
        )
        db.session.add(call)
        db.session.flush()

        registration = None
        if response == "registered":
            is_complete = company == "Jirani Supermarket"
            documents = {
                "director_id": True,
                "business_permit": is_complete,
                "tax_certificate": True,
                "till_store_number": True,
            }
            registration = SalesRegistration(
                lead_id=lead.id,
                registered_by_user_id=assignee.id,
                status="COMPLETE" if is_complete else "INCOMPLETE",
                documents=documents,
                reason_for_incompleteness=(
                    None if is_complete else "Awaiting business permit photo via WhatsApp"
                ),
                created_at=contact_time,
                updated_at=contact_time,
            )
            db.session.add(registration)
            db.session.flush()
            if not is_complete:
                db.session.add(SalesFollowUp(
                    lead_id=lead.id,
                    call_log_id=call.id,
                    registration_id=registration.id,
                    assigned_to_user_id=assignee.id,
                    due_at=now + timedelta(days=1),
                    task_type="registration_documents",
                    notes=registration.reason_for_incompleteness,
                ))
        elif response == "appointment":
            db.session.add(SalesFollowUp(
                lead_id=lead.id,
                call_log_id=call.id,
                assigned_to_user_id=assignee.id,
                due_at=appointment,
                task_type="appointment",
                notes="Seeded demo appointment.",
            ))
        elif response == "unreachable":
            db.session.add(SalesFollowUp(
                lead_id=lead.id,
                call_log_id=call.id,
                assigned_to_user_id=assignee.id,
                due_at=now + timedelta(days=1),
                task_type="retry_call",
                notes="Retry seeded unreachable demo lead.",
            ))

        db.session.add(AuditLog(
            actor_id=assignee.id,
            action="sales_call_logged",
            entity="SalesLead",
            entity_id=str(lead.id),
            event_metadata={
                "call_log_id": call.id,
                "response": response,
                "seeded_demo": True,
            },
            timestamp=contact_time,
        ))

    db.session.commit()
    print(
        f"Seeded {sample_count} {DEMO_SOURCE} leads across "
        f"{len(representatives)} Sales representatives."
    )
    return sample_count


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed_sales_demo()
