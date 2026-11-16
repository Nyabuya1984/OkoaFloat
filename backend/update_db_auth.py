from app import create_app
from app.extensions import db
from sqlalchemy import text
import traceback

app = create_app()
with app.app_context():
    # Update users table
    try:
        db.session.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50) UNIQUE NULL"))
        db.session.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL"))
        db.session.execute(text("ALTER TABLE users ADD COLUMN profile_status ENUM('Active', 'Inactive') DEFAULT 'Active'"))
        db.session.commit()
        print("Added username, password_hash, profile_status to users table.")
    except Exception as e:
        db.session.rollback()
        print(f"Failed to alter users: {e}")
