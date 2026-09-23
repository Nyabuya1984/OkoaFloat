"""Populate realistic, repeatable demo leave data.

This script only adds records identified by the ``[DEMO]`` marker and is safe
to run repeatedly against the configured Okoa Float database.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    AuditLog,
    CompanyHoliday,
    HandoverReport,
    HandoverTask,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
    User,
)


DEMO_MARKER = "[DEMO]"
ACKNOWLEDGMENT_TEXT = (
    "I have been hereby briefed on work to be undertaken and hereby agree to "
    "take responsibility of work to be executed."
)


def working_days(start, end):
    return sum(
        1
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
    )


def seed():
    app = create_app()
    with app.app_context():
        users = User.query.filter_by(is_active=True).order_by(User.id.asc()).all()
        leave_types = {item.code: item for item in LeaveType.query.all()}
        if not users or "ANNUAL" not in leave_types:
            raise RuntimeError("Run the base user and leave-type seeds first.")

        year = date.today().year
        for user in users:
            for code, entitled in (
                ("ANNUAL", Decimal("21.00")),
                ("SICK", Decimal("14.00")),
                ("MATERNITY", Decimal("90.00")),
                ("PATERNITY", Decimal("14.00")),
                ("COMPASSIONATE", Decimal("7.00")),
                ("STUDY", Decimal("10.00")),
            ):
                leave_type = leave_types.get(code)
                if leave_type is None:
                    continue
                balance = LeaveBalance.query.filter_by(
                    user_id=user.id, leave_type_id=leave_type.id, year=year
                ).first()
                if balance is None:
                    db.session.add(
                        LeaveBalance(
                            user_id=user.id,
                            leave_type_id=leave_type.id,
                            year=year,
                            entitled_days=entitled,
                            used_days=Decimal("0.00"),
                            pending_days=Decimal("0.00"),
                            carried_over=Decimal("0.00"),
                        )
                    )

        holidays = (
            ("Mashujaa Day", date(year, 10, 20)),
            ("Jamhuri Day", date(year, 12, 12)),
        )
        for name, holiday_date in holidays:
            if not CompanyHoliday.query.filter_by(
                date=holiday_date, country="Kenya"
            ).first():
                db.session.add(
                    CompanyHoliday(name=name, date=holiday_date, country="Kenya")
                )

        employees = [user for user in users if user.role == "employee"]
        manager = next((user for user in users if user.role == "manager"), users[0])
        admin = next((user for user in users if user.is_superuser), users[0])
        if len(employees) < 3:
            raise RuntimeError("At least three employee accounts are required.")

        request_specs = [
            (employees[0], "ANNUAL", 7, "pending", employees[1], None),
            (employees[1], "ANNUAL", 3, "approved", employees[2], None),
            (employees[2], "SICK", 2, "approved", None, None),
            (employees[3] if len(employees) > 3 else employees[0], "ANNUAL", 5, "pending", employees[4] if len(employees) > 4 else employees[1], "report"),
            (employees[5] if len(employees) > 5 else employees[0], "UNPAID", 4, "rejected", employees[6] if len(employees) > 6 else employees[1], None),
        ]

        for index, (employee, code, days, status, delegate, report_kind) in enumerate(request_specs):
            reason = f"{DEMO_MARKER} Sample {code.lower()} leave request {index + 1}"
            if LeaveRequest.query.filter_by(user_id=employee.id, reason=reason).first():
                continue
            leave_type = leave_types[code]
            start = date(year, 9, 21 + (index * 3))
            end = start + timedelta(days=days + 1)
            request_item = LeaveRequest(
                user_id=employee.id,
                leave_type_id=leave_type.id,
                start_date=start,
                end_date=end,
                days_requested=working_days(start, end),
                reason=reason,
                contact_phone=employee.phone_number,
                contact_email=employee.email,
                address_line1="Okoa Float Office",
                city="Nairobi",
                country="Kenya",
                handover_user_id=delegate.id if delegate else None,
                handover_name=delegate.full_name if delegate else None,
                handover_statement=ACKNOWLEDGMENT_TEXT if status == "approved" else None,
                handover_agreed_at=datetime.utcnow() if status == "approved" and delegate else None,
                status=status,
                approver_id=manager.id if status in {"approved", "rejected"} else None,
                decision_comment="Demo decision" if status in {"approved", "rejected"} else None,
                applied_at=datetime.utcnow(),
                decided_at=datetime.utcnow() if status in {"approved", "rejected"} else None,
            )
            db.session.add(request_item)
            db.session.flush()

            if report_kind == "report":
                report = HandoverReport(
                    leave_request_id=request_item.id,
                    version="v1",
                    summary=(
                        "This demonstration report covers active customer operations, "
                        "scheduled follow-ups, stakeholder communication, and escalation "
                        "steps required during the employee's planned absence."
                    ),
                    submitted_at=datetime.utcnow(),
                )
                report.tasks.append(
                    HandoverTask(
                        task_name="Review open customer cases",
                        description="Confirm ownership and next action for open cases.",
                        status="in_progress",
                        percent_complete=50,
                        next_action="Send the daily case summary to the manager.",
                        deadline=start,
                        priority="high",
                        sort_order=0,
                    )
                )
                db.session.add(report)

            db.session.add(
                Notification(
                    user_id=employee.id,
                    title="Demo leave update",
                    body=f"{DEMO_MARKER} Your {code.lower()} leave request is {status}.",
                    is_read=False,
                )
            )
            db.session.add(
                AuditLog(
                    actor_id=admin.id,
                    action="demo_leave_seeded",
                    entity="LeaveRequest",
                    entity_id=str(request_item.id),
                    event_metadata={"marker": DEMO_MARKER},
                )
            )

        db.session.commit()
        print("Demo leave data seeded successfully.")
        print(f"Users: {User.query.count()}")
        print(f"Leave requests: {LeaveRequest.query.count()}")
        print(f"Leave balances: {LeaveBalance.query.count()}")
        print(f"Public holidays: {CompanyHoliday.query.count()}")
        print(f"Handover reports: {HandoverReport.query.count()}")
        print(f"Notifications: {Notification.query.count()}")
        print(f"Audit logs: {AuditLog.query.count()}")


if __name__ == "__main__":
    seed()
