from app import create_app
from app.extensions import db
from sqlalchemy import text
import traceback

app = create_app()
with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN profile_picture_url VARCHAR(255) NULL"))
        db.session.commit()
        print("Added profile_picture_url to users table.")
    except Exception as e:
        db.session.rollback()
        print(f"Failed to alter users: {e}")
        
    try:
        db.session.execute(text("ALTER TABLE messages ADD COLUMN media_url VARCHAR(255) NULL"))
        db.session.commit()
        print("Added media_url to messages table.")
    except Exception as e:
        db.session.rollback()
        print(f"Failed to alter messages: {e}")
