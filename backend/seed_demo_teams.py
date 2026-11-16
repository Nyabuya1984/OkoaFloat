"""Seed synthetic development teams, assignments, and clearly marked GPS trails."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_

from app import create_app
from app.extensions import db
from app.models import (
    AgentLocation,
    Department,
    Role,
    User,
)
from app.utils.rbac import is_system_admin
from app.utils.organization import transition_department


DEMO_PASSWORD = "Demo-Only-2026!"

TEAMS = (
    {
        "key": "sales_manager",
        "employee_id": "DEMO-SM-MGR",
        "name": "Nia Wekesa",
        "email": "nia.wekesa@example.test",
        "phone": "+254700800001",
        "department": "Sales & Marketing",
        "department_role": "sales",
        "organizational_role": "team_leader",
        "title": "Sales & Marketing Team Leader",
        "city": "Nairobi",
        "address": "Westlands, Nairobi",
    },
    {
        "key": "sales_nairobi",
        "employee_id": "DEMO-SM-NAI",
        "name": "Naomi Atieno",
        "email": "naomi.atieno@example.test",
        "phone": "+254700800002",
        "department": "Sales & Marketing",
        "department_role": "sales",
        "organizational_role": "field_agent",
        "title": "Field Sales Representative",
        "city": "Nairobi",
        "address": "Kilimani, Nairobi",
        "coordinates": (-1.2864, 36.8172),
    },
    {
        "key": "sales_mombasa",
        "employee_id": "DEMO-SM-MSA",
        "name": "Baraka Mumo",
        "email": "baraka.mumo@example.test",
        "phone": "+254700800003",
        "department": "Sales & Marketing",
        "department_role": "sales",
        "organizational_role": "field_agent",
        "title": "Field Sales Representative",
        "city": "Mombasa",
        "address": "Nyali, Mombasa",
        "coordinates": (-4.0435, 39.6682),
    },
    {
        "key": "sales_kisumu",
        "employee_id": "DEMO-SM-KSM",
        "name": "Achieng Onyango",
        "email": "achieng.onyango@example.test",
        "phone": "+254700800004",
        "department": "Sales & Marketing",
        "department_role": "sales",
        "organizational_role": "field_agent",
        "title": "Field Sales Representative",
        "city": "Kisumu",
        "address": "Milimani, Kisumu",
        "coordinates": (-0.0917, 34.7680),
    },
    {
        "key": "sales_nakuru",
        "employee_id": "DEMO-SM-NAK",
        "name": "Kamau Kibet",
        "email": "kamau.kibet@example.test",
        "phone": "+254700800005",
        "department": "Sales & Marketing",
        "department_role": "sales",
        "organizational_role": "field_agent",
        "title": "Field Sales Representative",
        "city": "Nakuru",
        "address": "Milimani, Nakuru",
        "coordinates": (-0.3031, 36.0800),
    },
    {
        "key": "sales_eldoret",
        "employee_id": "DEMO-SM-ELD",
        "name": "Wanjiku Cherono",
        "email": "wanjiku.cherono@example.test",
        "phone": "+254700800006",
        "department": "Sales & Marketing",
        "department_role": "sales",
        "organizational_role": "field_agent",
        "title": "Field Sales Representative",
        "city": "Eldoret",
        "address": "Kapsoya, Eldoret",
        "coordinates": (0.5143, 35.2698),
    },
    {
        "key": "debt_manager",
        "employee_id": "DEMO-DC-MGR",
        "name": "Taji Mwangi",
        "email": "taji.mwangi@example.test",
        "phone": "+254700800007",
        "department": "Debt Collection",
        "department_role": "debt_collection",
        "organizational_role": "department_manager",
        "title": "Debt Collection Department Manager",
        "city": "Nairobi",
        "address": "Upper Hill, Nairobi",
    },
    {
        "key": "debt_nairobi",
        "employee_id": "DEMO-DC-NAI",
        "name": "Zuri Kamau",
        "email": "zuri.kamau@example.test",
        "phone": "+254700800008",
        "department": "Debt Collection",
        "department_role": "debt_collection",
        "organizational_role": "field_agent",
        "title": "Debt Collection Field Agent",
        "city": "Nairobi",
        "address": "Embakasi, Nairobi",
    },
    {
        "key": "debt_mombasa",
        "employee_id": "DEMO-DC-MSA",
        "name": "Jabali Barasa",
        "email": "jabali.barasa@example.test",
        "phone": "+254700800009",
        "department": "Debt Collection",
        "department_role": "debt_collection",
        "organizational_role": "field_agent",
        "title": "Debt Collection Field Agent",
        "city": "Mombasa",
        "address": "Likoni, Mombasa",
    },
    {
        "key": "debt_kisumu",
        "employee_id": "DEMO-DC-KSM",
        "name": "Imani Auma",
        "email": "imani.auma@example.test",
        "phone": "+254700800010",
        "department": "Debt Collection",
        "department_role": "debt_collection",
        "organizational_role": "field_agent",
        "title": "Debt Collection Field Agent",
        "city": "Kisumu",
        "address": "Kondele, Kisumu",
    },
    {
        "key": "care_manager",
        "employee_id": "DEMO-CC-MGR",
        "name": "Malaika Njeri",
        "email": "malaika.njeri@example.test",
        "phone": "+254700800011",
        "department": "Customer Care",
        "department_role": "customer_care",
        "organizational_role": "team_leader",
        "title": "Customer Care Team Leader",
        "city": "Nairobi",
        "address": "Kileleshwa, Nairobi",
    },
    {
        "key": "care_nairobi",
        "employee_id": "DEMO-CC-NAI",
        "name": "Pendo Wanjala",
        "email": "pendo.wanjala@example.test",
        "phone": "+254700800012",
        "department": "Customer Care",
        "department_role": "customer_care",
        "organizational_role": "field_agent",
        "title": "Customer Care Representative",
        "city": "Nairobi",
        "address": "Kasarani, Nairobi",
    },
    {
        "key": "care_nakuru",
        "employee_id": "DEMO-CC-NAK",
        "name": "Kito Kiptoo",
        "email": "kito.kiptoo@example.test",
        "phone": "+254700800013",
        "department": "Customer Care",
        "department_role": "customer_care",
        "organizational_role": "field_agent",
        "title": "Customer Care Representative",
        "city": "Nakuru",
        "address": "Section 58, Nakuru",
    },
    {
        "key": "care_thika",
        "employee_id": "DEMO-CC-THI-AGENT",
        "name": "Salma Muthoni",
        "email": "salma.muthoni@example.test",
        "phone": "+254700800015",
        "department": "Customer Care",
        "department_role": "customer_care",
        "organizational_role": "field_agent",
        "title": "Customer Care Representative",
        "city": "Thika",
        "address": "Town Centre, Thika",
    },
)

MANAGER_KEYS = {
    "sales_nairobi": "sales_manager",
    "sales_mombasa": "sales_manager",
    "sales_kisumu": "sales_manager",
    "sales_nakuru": "sales_manager",
    "sales_eldoret": "sales_manager",
    "debt_nairobi": "debt_manager",
    "debt_mombasa": "debt_manager",
    "debt_kisumu": "debt_manager",
    "care_nairobi": "care_manager",
    "care_nakuru": "care_manager",
    "care_thika": "care_manager",
}


def seed_demo_teams():
    app = create_app("development")
    if not app.debug:
        raise RuntimeError("Demo team data can only be seeded in development.")

    with app.app_context():
        admin = User.query.filter_by(phone_number="+254721143189").one()
        if not is_system_admin(admin):
            raise RuntimeError("A valid system administrator is required to seed demo teams.")

        departments = {}
        for spec in TEAMS:
            department_name = spec["department"]
            if department_name not in departments:
                department = Department.query.filter_by(name=department_name).one_or_none()
                if department is None:
                    department = Department(name=department_name)
                    db.session.add(department)
                    db.session.flush()
                departments[department_name] = department

        users = {}
        for spec in TEAMS:
            user = User.query.filter_by(employee_id=spec["employee_id"]).one_or_none()
            if user is None:
                identity_match = User.query.filter(
                    or_(
                        User.email == spec["email"],
                        User.phone_number == spec["phone"],
                    )
                ).first()
                if identity_match:
                    raise RuntimeError(
                        f"Demo identity conflicts with existing employee {spec['employee_id']}."
                    )
                user = User(
                    employee_id=spec["employee_id"],
                    full_name=spec["name"],
                    email=spec["email"],
                    password_hash="",
                )
                db.session.add(user)

            department = departments[spec["department"]]
            user.full_name = spec["name"]
            user.employee_name = spec["name"]
            user.email = spec["email"]
            user.personal_email = spec["email"]
            user.contact_email = spec["email"]
            user.phone_number = spec["phone"]
            user.contact_phone = spec["phone"]
            user.job_position_title = spec["title"]
            user.employer = "Okoa Float Ltd (Development Demo)"
            user.department = department.name
            user.department_id = department.id
            user.address_line1 = spec["address"]
            user.city = spec["city"]
            user.country = "Kenya"
            user.role = (
                "manager"
                if spec["organizational_role"] in {"department_manager", "team_leader"}
                else "employee"
            )
            user.is_active = True
            user.is_archived = False
            user.is_deleted = False
            user.is_superuser = False
            user.account_status = "approved"
            user.approved_at = user.approved_at or datetime.now(timezone.utc).replace(tzinfo=None)
            user.must_change_password = False
            user.hire_date = user.hire_date or date(2025, 1, 6)
            user.set_password(DEMO_PASSWORD)
            users[spec["key"]] = user

        db.session.flush()
        for spec in TEAMS:
            user = users[spec["key"]]
            manager_key = MANAGER_KEYS.get(spec["key"])
            user.manager_id = users[manager_key].id if manager_key else admin.id

            operational_role = Role.query.filter_by(
                name=spec["department_role"]
            ).one_or_none()
            if operational_role is None:
                raise RuntimeError(
                    "RBAC policies are not seeded; run the RBAC seed before demo teams."
                )
            transition_department(
                user=user,
                department=departments[spec["department"]],
                role_name=spec["department_role"],
                organizational_role=spec["organizational_role"],
                actor=admin,
            )
            user.job_position_title = spec["title"]

        db.session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        offsets = (
            (-0.0010, -0.0012),
            (0.0003, 0.0006),
            (0.0010, 0.0011),
        )
        for spec in TEAMS:
            coordinates = spec.get("coordinates")
            if not coordinates:
                continue
            user = users[spec["key"]]
            AgentLocation.query.filter_by(
                user_id=user.id,
                is_simulated=True,
            ).delete(synchronize_session=False            )
            for index, (latitude_delta, longitude_delta) in enumerate(offsets):
                db.session.add(
                    AgentLocation(
                        user_id=user.id,
                        department_id=user.department_id,
                        latitude=coordinates[0] + latitude_delta,
                        longitude=coordinates[1] + longitude_delta,
                        accuracy_meters=60,
                        is_simulated=True,
                        recorded_at=now - timedelta(minutes=(120 - index * 55)),
                    )
                )

        db.session.commit()
        print(f"Seeded {len(TEAMS)} synthetic test users across {len(departments)} departments.")
        print("Departments: Sales & Marketing, Debt Collection, Customer Care")
        print("Sales & Marketing field agents have simulated, clearly labeled GPS trails.")
        print(f"Shared development-only password: {DEMO_PASSWORD}")
        print("Demo users can sign in with their listed test email or phone and verify via backend OTP logs.")
        for spec in TEAMS:
            print(f"{spec['employee_id']}: {spec['name']} — {spec['email']} — {spec['phone']}")


if __name__ == "__main__":
    seed_demo_teams()
