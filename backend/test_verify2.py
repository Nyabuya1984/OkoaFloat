from app import create_app
from app.models.user import User

app = create_app()
with app.app_context():
    user = User.query.filter_by(phone_number='0721143189').first()
    print("User deleted?", user.deleted)
