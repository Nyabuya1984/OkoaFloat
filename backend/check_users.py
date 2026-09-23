from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app()
with app.app_context():
    w = User.query.filter_by(phone_number='0721143189').first()
    h = User.query.filter_by(phone_number='0721153487').first()
    print("Wycliffe:", w.full_name if w else None, w.gender if w else None)
    print("Hilda:", h.full_name if h else None, h.gender if h else None)
