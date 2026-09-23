from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # Drop the existing table and recreate it according to the new schema
    db.session.execute(text("DROP TABLE IF EXISTS matches"))
    db.session.commit()
    db.create_all()
    print("Recreated matches table with correct schema.")
