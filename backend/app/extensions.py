"""
Flask Extensions
Shared across the application.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager

# Database ORM - handles all database operations
db = SQLAlchemy()
jwt = JWTManager()