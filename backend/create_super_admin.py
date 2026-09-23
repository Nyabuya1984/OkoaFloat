from datetime import date

from app import create_app
from app.extensions import db
from app.models import User


DEFAULT_EMAIL = "admin@okoa.local"
DEFAULT_PASSWORD = "Admin@2026!"
DEFAULT_PHONE = "+254700000001"


def ensure_super_admin(email=DEFAULT_EMAIL, password=DEFAULT_PASSWORD, phone_number=DEFAULT_PHONE):
    app = create_app()
    with app.app_context():
        try:
            user = User.query.filter((User.email == email) | (User.phone_number == phone_number)).first()
            if not user:
                user = User(
                    employee_id="HR-0001",
                    full_name="System Administrator",
                    employee_name="System Administrator",
                    job_position_title="HR Administrator",
                    employer="Okoa Float Ltd",
                    email=email,
                    phone_number=phone_number,
                    department="HR",
                    role="hr_admin",
                    hire_date=date.today(),
                    is_active=True,
                    is_superuser=True,
                    account_status="approved",
                    must_change_password=True,
                )
                db.session.add(user)
            user.email = email
            user.phone_number = phone_number
            user.role = "hr_admin"
            user.department = "HR"
            user.is_active = True
            user.is_superuser = True
            user.account_status = "approved"
            user.must_change_password = True
            user.full_name = user.full_name or "System Administrator"
            user.employee_name = user.employee_name or user.full_name
            user.set_password(password)
            db.session.commit()
            print("Super admin ready:")
            print(f"  email:    {user.email}")
            print(f"  password: {password}")
            print(f"  role:     {user.role}")
            print(f"  superuser: {user.is_superuser}")
        except Exception as exc:
            print(f"Super admin bootstrap deferred until the schema is migrated: {exc}")


if __name__ == "__main__":
    ensure_super_admin()
