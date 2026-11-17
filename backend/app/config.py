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
    # Keep these defaults aligned with docker-compose.yml so local startup works
    # even when a developer has not created backend/.env yet.
    DB_NAME = os.environ.get('DB_NAME', 'Okoa_Float_DB')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'admin123')
    DB_USER = os.environ.get('DB_USER', 'okoa_user')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
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
    TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
    TIMEZONE = os.environ.get("TIMEZONE", "Africa/Nairobi")

    OTP_STORE_PLAINTEXT = False

    # SMS API Settings (Onfon Media)
    SMS_ENABLED = os.environ.get("SMS_ENABLED", "true").lower() in ("true", "1", "yes")
    ONFON_SMS_URL = os.environ.get("ONFON_SMS_URL", "https://api.onfonmedia.com/v1/sms/SendBulkSMS")
    ONFON_ACCESS_KEY = os.environ.get("ONFON_ACCESS_KEY")
    ONFON_API_KEY = os.environ.get("ONFON_API_KEY")
    ONFON_CLIENT_ID = os.environ.get("ONFON_CLIENT_ID")
    ONFON_SENDER_ID = os.environ.get("ONFON_SENDER_ID") or "OkoaFloat"

    # SMTP settings for OTP email fallback.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
    
    # CORS settings
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    OTP_STORE_PLAINTEXT = True
    SQLALCHEMY_ECHO = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"


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
    SMS_ENABLED = False
    OTP_STORE_PLAINTEXT = True
    RATELIMIT_ENABLED = False


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}