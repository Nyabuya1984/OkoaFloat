"""
Configuration Settings
Loads from environment variables with fallback defaults.
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))


class Config:
    """Base configuration class."""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database settings. The application has exactly one supported database.
    DB_NAME = os.environ.get('DB_NAME')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_USER = os.environ.get('DB_USER')
    DB_HOST = os.environ.get('DB_HOST')
    DB_PORT = os.environ.get('DB_PORT')
    SQLALCHEMY_DATABASE_URI = (
        f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    )
    assert "Okoa_Float_DB" in SQLALCHEMY_DATABASE_URI, \
        "Refusing to start: wrong database — expected Okoa_Float_DB"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ['headers']
    
    # CORS settings
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    # Keep the terminal readable; enable explicitly with SQLALCHEMY_ECHO=true.
    SQLALCHEMY_ECHO = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"
    # Development-only convenience: print OTPs to the server console.
    # ProductionConfig does not enable this setting.
    STORE_PLAINTEXT_OTP = os.environ.get("STORE_PLAINTEXT_OTP", "true").lower() == "true"


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    SQLALCHEMY_ECHO = False

    @classmethod
    def validate(cls):
        insecure_defaults = {
            "SECRET_KEY": "dev-secret-key-change-in-production",
            "JWT_SECRET_KEY": "dev-secret-key-change-in-production",
        }
        for name, insecure_value in insecure_defaults.items():
            if getattr(cls, name) == insecure_value:
                raise RuntimeError(f"{name} must be configured in production")
        if not cls.CORS_ORIGINS or cls.CORS_ORIGINS.strip() == "*":
            raise RuntimeError("CORS_ORIGINS must be restricted in production")


class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}