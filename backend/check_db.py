from app import create_app, db
from app.models.user import User

app = create_app()
with app.app_context():
    users = User.query.all()
    for u in users:
        print(f"ID: {u.user_id}, Phone: {u.phone_number}, Name: {u.full_name}, Gender: {u.gender}, Age: {u.age}, Town: {u.town_name}, County: {u.county_name}")
