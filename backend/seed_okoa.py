"""
One-time seed for Okoa Float Leave Management System.
Creates an HR admin user and baseline leave types + policies.
Safe to re-run — skips anything that already exists.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_

from app import create_app
from app.extensions import db
from app.models import Department, User, LeaveType, LeavePolicy


HR_ADMIN = {
    "employee_id": "HR-0001",
    "full_name": "System Administrator",
    "email": "admin@okoa.local",
    "phone_number": "+254700000001",
    "password": "Admin@2026!",
    "role": "hr_admin",
    "department": "HR",
    "employee_name": "System Administrator",
    "job_position_title": "HR Administrator",
    "employer": "Okoa Float Ltd",
    "hire_date": date.today(),
    "is_superuser": True,
}

DEV_EMPLOYEE = {
    "employee_id": "EMP-DEV-0001",
    "full_name": "Development Employee",
    "email": "employee.dev@okoa.local",
    "phone_number": "+254721143189",
    "password": "Nyabuy@1984",
    "role": "employee",
    "department": "Operations",
    "job_position_title": "Employee",
    "employer": "Okoa Float Ltd",
    "hire_date": date(2020, 1, 1),
}

LEAVE_TYPES = [
    # code, name, is_paid, requires_document, default_days, accrual, max_carryover, notice, gender_restriction, min_service_months
    ("ANNUAL",       "Annual Leave",       True,  False, 21, 1.75, 5,  14, None,     0),
    ("SICK",         "Sick Leave",         True,  True,  14, 1.17, 0,  0,  None,     0),
    ("MATERNITY",    "Maternity Leave",    True,  True,  90, 0,    0,  30, "Female", 12),
    ("PATERNITY",    "Paternity Leave",    True,  False, 14, 0,    0,  14, "Male",   0),
    ("COMPASSIONATE","Compassionate Leave",True,  False, 7,  0,    0,  0,  None,     0),
    ("STUDY",        "Study Leave",        True,  True,  10, 0,    0,  30, None,     12),
    ("UNPAID",       "Unpaid Leave",       False, False, 0, 0,    0,  0,  None,     0),
]


def seed():
    app = create_app()
    with app.app_context():
        # ---- HR admin ----
        existing = User.query.filter_by(email=HR_ADMIN["email"]).first()
        if existing:
            existing.is_superuser = True
            existing.role = "hr_admin"
            existing.is_active = True
            existing.account_status = "approved"
            existing.must_change_password = True
            if not existing.password_hash:
                existing.set_password(HR_ADMIN["password"])
            db.session.commit()
            print(f"[ok]   Updated HR admin to super-user: {HR_ADMIN['email']}")
        else:
            department = Department.query.filter_by(name=HR_ADMIN["department"]).first()
            if not department:
                department = Department(name=HR_ADMIN["department"])
                db.session.add(department)
                db.session.flush()
            admin = User(
                employee_id=HR_ADMIN["employee_id"],
                full_name=HR_ADMIN["full_name"],
                email=HR_ADMIN["email"],
                phone_number=HR_ADMIN["phone_number"],
                role=HR_ADMIN["role"],
                department=HR_ADMIN["department"],
                department_id=department.id,
                employee_name=HR_ADMIN["employee_name"],
                job_position_title=HR_ADMIN["job_position_title"],
                employer=HR_ADMIN["employer"],
                contact_phone=HR_ADMIN["phone_number"] if "phone_number" in HR_ADMIN else None,
                contact_email=HR_ADMIN["email"],
                hire_date=HR_ADMIN["hire_date"],
                is_active=True,
                is_superuser=HR_ADMIN.get("is_superuser", False),
                account_status="approved",
                must_change_password=True,
            )
            admin.set_password(HR_ADMIN["password"])
            db.session.add(admin)
            db.session.commit()
            print(f"[ok]   Created HR admin: {HR_ADMIN['email']} / {HR_ADMIN['password']}")

        # ---- Development employee ----
        dev = User.query.filter(
            or_(
                User.email == DEV_EMPLOYEE["email"],
                User.phone_number == DEV_EMPLOYEE["phone_number"],
            )
        ).first()
        department = Department.query.filter_by(name=DEV_EMPLOYEE["department"]).first()
        if not department:
            department = Department(name=DEV_EMPLOYEE["department"])
            db.session.add(department)
            db.session.flush()
        if not dev:
            dev = User(
                employee_id=DEV_EMPLOYEE["employee_id"],
                full_name=DEV_EMPLOYEE["full_name"],
                email=DEV_EMPLOYEE["email"],
                phone_number=DEV_EMPLOYEE["phone_number"],
                role=DEV_EMPLOYEE["role"],
                department=DEV_EMPLOYEE["department"],
                department_id=department.id,
                job_position_title=DEV_EMPLOYEE["job_position_title"],
                employer=DEV_EMPLOYEE["employer"],
                hire_date=DEV_EMPLOYEE["hire_date"],
            )
            db.session.add(dev)
        dev.phone_number = DEV_EMPLOYEE["phone_number"]
        dev.set_password(DEV_EMPLOYEE["password"])
        dev.hire_date = DEV_EMPLOYEE["hire_date"]
        dev.is_active = True
        dev.account_status = "approved"
        dev.approved_at = dev.approved_at or datetime.utcnow()
        dev.department_id = department.id
        db.session.commit()
        print(f"[ok]   Development employee ready: {DEV_EMPLOYEE['phone_number']}")

        # ---- Leave types + policies ----
        for (code, name, is_paid, req_doc, days,
             accrual, carryover, notice, gender, min_months) in LEAVE_TYPES:

            lt = LeaveType.query.filter_by(code=code).first()
            if lt:
                print(f"[skip] Leave type exists: {code}")
            else:
                lt = LeaveType(
                    name=name, code=code, is_paid=is_paid,
                    requires_document=req_doc,
                    default_days_per_year=Decimal(str(days)),
                )
                db.session.add(lt)
                db.session.flush()
                print(f"[ok]   Leave type: {code} ({name})")

            policy_exists = LeavePolicy.query.filter_by(leave_type_id=lt.id).first()
            if policy_exists:
                print(f"[skip] Policy exists for {code}")
            else:
                db.session.add(LeavePolicy(
                    leave_type_id=lt.id,
                    accrual_rate=Decimal(str(accrual)),
                    max_carryover=Decimal(str(carryover)),
                    notice_days_required=notice,
                    gender_restriction=gender,
                    min_service_months=min_months,
                ))
                print(f"[ok]   Policy for: {code}")

        db.session.commit()
        print()
        print("=" * 60)
        print("SEED COMPLETE")
        print("=" * 60)
        print(f"  Login:    {HR_ADMIN['email']}")
        print(f"  Password: {HR_ADMIN['password']}")
        print(f"  Role:     hr_admin")
        print(f"  NOTE: must_change_password=True — change it after first login.")
        print("=" * 60)


if __name__ == "__main__":
    seed()