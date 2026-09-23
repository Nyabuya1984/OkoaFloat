import sqlite3

# Try to find the sqlite DB. It might be in instance/ or app.db
# Let's use SQLAlchemy in a flask app context
from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app('default')
with app.app_context():
    users = User.query.filter(User.profile_picture_url.like('%localhost:5000%')).all()
    for u in users:
        print(f"Fixing {u.phone_number}: {u.profile_picture_url}")
        u.profile_picture_url = u.profile_picture_url.replace('http://localhost:5000', '')
    db.session.commit()
    print("Done")
