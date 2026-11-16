"""
Flask Extensions
Shared across the application.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Database ORM - handles all database operations
db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)