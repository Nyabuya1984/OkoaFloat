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

    # SMTP settings are deliberately optional at startup. OTP requests fail
    # explicitly until the mail transport and sender address are configured.
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"
    
    # CORS settings
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"
    STORE_PLAINTEXT_OTP = os.environ.get("STORE_PLAINTEXT_OTP", "true").lower() == "true"


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    STORE_PLAINTEXT_OTP = False

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
    STORE_PLAINTEXT_OTP = True


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}