import sqlite3
from app import create_app
from app.extensions import db
from app.models.user import User

app = create_app('default')
with app.app_context():
    users = User.query.filter(User.profile_picture_url.like('/static/uploads%')).all()
    for u in users:
        print(f"Fixing {u.phone_number}: {u.profile_picture_url}")
        u.profile_picture_url = "http://localhost:5000" + u.profile_picture_url
    db.session.commit()
    print("Done")
