import hashlib
import secrets
from datetime import date, datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import Department, OtpChallenge, User


DEFAULT_PASSWORD = "Password123!"

SYSTEM_USERS = [
    {
        "employee_id": "HR-1001",
        "full_name": "Mary Wanjiku Njeri",
        "employee_name": "Mary Wanjiku Njeri",
        "email": "hr.manager@okoa.local",
        "phone_number": "+254712345010",
        "job_position_title": "HR Manager",
        "employer": "Okoa Float Ltd",
        "department": "Human Resources",
        "role": "hr_admin",
        "is_superuser": True,
        "account_status": "approved",
        "must_change_password": False,
    },
    {
        "employee_id": "MN-2001",
        "full_name": "Daniel Kiprotich Koech",
        "employee_name": "Daniel Kiprotich Koech",
        "email": "ops.manager@okoa.local",
        "phone_number": "+254712345011",
        "job_position_title": "Operations Manager",
        "employer": "Okoa Float Ltd",
        "department": "Operations",
        "role": "manager",
        "is_superuser": False,
        "account_status": "approved",
        "must_change_password": False,
    },
]

EMPLOYEES = [
    {"employee_id": "EMP-0001", "full_name": "Achieng Adhiambo Otieno", "email": "achieng.otieno@okoa.local", "phone_number": "+254712345001", "department": "Operations", "job_position_title": "Customer Support Associate", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0002", "full_name": "Brian Otieno Muthoni", "email": "brian.otieno@okoa.local", "phone_number": "+254712345002", "department": "Operations", "job_position_title": "Operations Analyst", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0003", "full_name": "Catherine Wairimu Kariuki", "email": "catherine.kariuki@okoa.local", "phone_number": "+254712345003", "department": "Finance", "job_position_title": "Finance Officer", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0004", "full_name": "David Njoroge Kamau", "email": "david.kamau@okoa.local", "phone_number": "+254712345004", "department": "IT", "job_position_title": "Software Engineer", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0005", "full_name": "Esther Nyambura Wambui", "email": "esther.wambui@okoa.local", "phone_number": "+254712345005", "department": "HR", "job_position_title": "HR Assistant", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0006", "full_name": "Felix Kibet Langat", "email": "felix.langat@okoa.local", "phone_number": "+254712345006", "department": "Field Sales", "job_position_title": "Sales Executive", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0007", "full_name": "Grace Muthoni Kamande", "email": "grace.kamande@okoa.local", "phone_number": "+254712345007", "department": "Customer Success", "job_position_title": "Customer Success Lead", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0008", "full_name": "Harrison Mugo Njenga", "email": "harrison.njenga@okoa.local", "phone_number": "+254712345008", "department": "Logistics", "job_position_title": "Logistics Coordinator", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0009", "full_name": "Irene Auma Wekesa", "email": "irene.wekesa@okoa.local", "phone_number": "+254712345009", "department": "Operations", "job_position_title": "Quality Assurance Officer", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0010", "full_name": "Joseph Mwangi Karanja", "email": "joseph.karanja@okoa.local", "phone_number": "+254712345012", "department": "IT", "job_position_title": "DevOps Engineer", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0011", "full_name": "Kevin Mumo Mutua", "email": "kevin.mutua@okoa.local", "phone_number": "+254712345013", "department": "Sales", "job_position_title": "Account Executive", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0012", "full_name": "Linda Akinyi Oduor", "email": "linda.oduor@okoa.local", "phone_number": "+254712345014", "department": "Marketing", "job_position_title": "Marketing Coordinator", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0013", "full_name": "Martin Karanja Kimani", "email": "martin.kimani@okoa.local", "phone_number": "+254712345015", "department": "Finance", "job_position_title": "Accounts Clerk", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0014", "full_name": "Naomi Chepkemoi Rono", "email": "naomi.rono@okoa.local", "phone_number": "+254712345016", "department": "Operations", "job_position_title": "Operations Coordinator", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0015", "full_name": "Owen Mwenda Gichuru", "email": "owen.gichuru@okoa.local", "phone_number": "+254712345017", "department": "IT", "job_position_title": "Frontend Developer", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0016", "full_name": "Patricia Njeri Ngugi", "email": "patricia.ngugi@okoa.local", "phone_number": "+254712345018", "department": "Customer Success", "job_position_title": "Support Specialist", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0017", "full_name": "Quincy Kiplagat Ngeno", "email": "quincy.ngeno@okoa.local", "phone_number": "+254712345019", "department": "Logistics", "job_position_title": "Fleet Coordinator", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0018", "full_name": "Ruth Njeri Mbugua", "email": "ruth.mbugua@okoa.local", "phone_number": "+254712345020", "department": "HR", "job_position_title": "Recruitment Officer", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0019", "full_name": "Samuel Kinyua Wanjiku", "email": "samuel.wanjiku@okoa.local", "phone_number": "+254712345021", "department": "Sales", "job_position_title": "Sales Manager", "employer": "Okoa Float Ltd"},
    {"employee_id": "EMP-0020", "full_name": "Teresia Achieng Okoth", "email": "teresia.okoth@okoa.local", "phone_number": "+254712345022", "department": "Operations", "job_position_title": "Field Operations Officer", "employer": "Okoa Float Ltd"},
]


def ensure_department(name):
    department = Department.query.filter_by(name=name).first()
    if not department:
        department = Department(name=name)
        db.session.add(department)
        db.session.flush()
    return department


def upsert_user(payload):
    existing = User.query.filter((User.email == payload["email"]) | (User.phone_number == payload["phone_number"])).first()
    if existing:
        existing.full_name = payload["full_name"]
        existing.employee_name = payload.get("employee_name", payload["full_name"])
        existing.email = payload["email"]
        existing.phone_number = payload["phone_number"]
        existing.role = payload.get("role", "employee")
        existing.is_superuser = payload.get("is_superuser", False)
        existing.account_status = payload.get("account_status", "approved")
        existing.is_active = True
        existing.must_change_password = payload.get("must_change_password", False)
        existing.job_position_title = payload.get("job_position_title")
        existing.employer = payload.get("employer")
        existing.department = payload.get("department")
        existing.department_id = ensure_department(payload.get("department", "Operations")).id
        existing.hire_date = existing.hire_date or date.today()
        existing.contact_phone = existing.phone_number
        existing.contact_email = existing.email
        existing.set_password(DEFAULT_PASSWORD)
        return existing

    department = ensure_department(payload.get("department", "Operations"))
    user = User(
        employee_id=payload["employee_id"],
        full_name=payload["full_name"],
        employee_name=payload.get("employee_name", payload["full_name"]),
        email=payload["email"],
        phone_number=payload["phone_number"],
        job_position_title=payload.get("job_position_title", "Employee"),
        employer=payload.get("employer", "Okoa Float Ltd"),
        department=payload.get("department", "Operations"),
        department_id=department.id,
        role=payload.get("role", "employee"),
        is_superuser=payload.get("is_superuser", False),
        is_active=True,
        account_status=payload.get("account_status", "approved"),
        must_change_password=payload.get("must_change_password", False),
        hire_date=date.today(),
        contact_phone=payload["phone_number"],
        contact_email=payload["email"],
    )
    user.set_password(DEFAULT_PASSWORD)
    db.session.add(user)
    return user


def create_seed_otp_for_user(user, purpose="login", code=None):
    if not user or not user.phone_number:
        return None

    existing = OtpChallenge.query.filter_by(user_id=user.id, purpose=purpose, verified_at=None).order_by(OtpChallenge.created_at.desc()).first()
    if existing and existing.expires_at > datetime.utcnow():
        return existing

    otp_code = code or f"{secrets.randbelow(1_000_000):06d}"
    challenge = OtpChallenge(
        challenge_id=secrets.token_urlsafe(32),
        user_id=user.id,
        phone_number=user.phone_number,
        purpose=purpose,
        code_hash=hashlib.sha256(otp_code.encode("utf-8")).hexdigest(),
        debug_code=otp_code,
        expires_at=datetime.utcnow() + timedelta(hours=2),
        attempts=0,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def main():
    app = create_app()
    with app.app_context():
        for item in SYSTEM_USERS + EMPLOYEES:
            upsert_user(item)

        users = User.query.order_by(User.id.asc()).all()
        otp_count = 0
        for user in users:
            if user.phone_number:
                otp = create_seed_otp_for_user(user, purpose="login")
                if otp:
                    otp_count += 1

        db.session.commit()
        print("Seeded system users, employee test accounts, and login OTP challenges.")
        print(f"Created/updated {len(SYSTEM_USERS) + len(EMPLOYEES)} users with default password: {DEFAULT_PASSWORD}")
        print(f"Inserted {otp_count} OTP records into the OTP table.")
        for item in SYSTEM_USERS + EMPLOYEES:
            print(f"- {item['full_name']} | {item['email']} | {item['phone_number']} | {item.get('role', 'employee')}")


if __name__ == "__main__":
    main()
