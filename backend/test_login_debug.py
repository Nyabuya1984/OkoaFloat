from app.models.user import User
from app.extensions import db
from app import create_app
from werkzeug.security import check_password_hash

app = create_app()
with app.app_context():
    user = User.query.filter_by(phone_number='0721143189').first()
    print("User found:", user is not None)
    if user:
        print("Hash in DB:", user.password_hash)
        print("Check Nyabuy@1984:", check_password_hash(user.password_hash, 'Nyabuy@1984'))
        print("Check penzi123:", check_password_hash(user.password_hash, 'penzi123'))
