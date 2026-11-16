"""
Application Factory Pattern
Creates and configures the Flask application.
"""
import os
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from flask import Flask
from sqlalchemy import text
from flask_migrate import Migrate
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import config
from app.extensions import db, jwt, limiter
from app.utils.rbac import normalize_role

SUPER_ADMIN_PHONE = '+254721143189'
SUPER_ADMIN_PASSWORD = 'Admin@2026!'

# Import models so Alembic can detect them
from app.models import (
    Department,
    HandoverReport,
    Permission,
    Role,
    RolePermission,
    SalesDailyReport,
    User,
    UserRole,
)


def create_app(config_name='default'):
    """
    Application factory function.
    
    Args:
        config_name: Configuration environment (development, production, testing)
    
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    config_class = config[config_name]
    validate_config = getattr(config_class, "validate", None)
    if validate_config:
        validate_config()
    trusted_proxy_hops = app.config.get("TRUSTED_PROXY_HOPS", 0)
    if trusted_proxy_hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxy_hops)
    
    # Initialize extensions
    db.init_app(app)
    Migrate(app, db, directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations_okoa'))
    jwt.init_app(app)

    @jwt.token_verification_loader
    def active_approved_user_token(_jwt_header, jwt_payload):
        """Invalidate existing access and refresh tokens after account deactivation."""
        try:
            user_id = int(jwt_payload.get("sub"))
        except (TypeError, ValueError):
            return False
        user = db.session.get(User, user_id)
        return bool(
            user
            and user.is_currently_active()
            and user.account_status == "approved"
        )

    limiter.init_app(app)
    CORS(app, origins=app.config.get('CORS_ORIGINS', '*'))

    # Setup logging
    setup_logging(app)
    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(error):
        return {
            "error": {
                "code": "TOO_MANY_REQUESTS",
                "message": "Too many code requests. Please wait before trying again.",
            }
        }, 429
    
    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.leave import leave_bp
    from app.api.chat import chat_bp
    from app.api.customer_care import customer_care_bp
    from app.api.okoa_customer_care import okoa_customer_care_bp
    from app.api.admin import admin_bp
    from app.api.sales import sales_bp
    from app.api.organization import (
        organization_bp,
        organization_compat_bp,
        reports_bp,
    )
    from app.utils.organization import cleanup_expired_locations
    from app.api.debt_collection import collector_bp, debt_collection_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(leave_bp, url_prefix='/api/leave')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(customer_care_bp)
    app.register_blueprint(okoa_customer_care_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(organization_bp)
    app.register_blueprint(organization_compat_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(debt_collection_bp)
    app.register_blueprint(collector_bp)

    @app.cli.command("seed-okia")
    def seed_okia_command():
        """Seed Okoa customer-care shifts and concern categories."""
        from app.utils.okia_seed import seed_reference_data

        seed_reference_data()
        app.logger.info("Seeded Okoa customer-care reference data")

    @app.cli.command("seed-rbac")
    def seed_rbac_command():
        """Load the RBAC policy file into the role and permission tables."""
        from app.utils.rbac_seed import seed_rbac

        seed_rbac()
        app.logger.info("Seeded RBAC roles and permission rules")

    @app.cli.command("cleanup-agent-locations")
    def cleanup_agent_locations_command():
        """Delete agent GPS records that exceed the configured retention period."""
        deleted_count = cleanup_expired_locations()
        db.session.commit()
        app.logger.info("Deleted %s expired agent location records", deleted_count)
    
    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    @app.route('/', methods=['GET'])
    def index():
        return {
            'service': 'OKOA FLOAT LEAVE API',
            'version': '1.0.0',
            'health': '/health',
            'auth': '/api/auth',
            'leave': '/api/leave'
        }, 200

    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint for monitoring."""
        try:
            db.session.execute(text('SELECT 1'))
            database_status = 'connected'
        except Exception:
            db.session.rollback()
            database_status = 'disconnected'
        return {
            'status': 'healthy',
            'version': '1.0.0',
            'database': database_status,
        }, 200

    with app.app_context():
        configured_admin_email = app.config.get("ADMIN_EMAIL")
        if configured_admin_email:
            configured_admin_email = configured_admin_email.strip().lower()

        try:
            role_def = db.session.execute(text("SHOW COLUMNS FROM users LIKE 'role'" )).fetchone()
            if role_def and str(role_def[1]).lower().startswith('enum'):
                db.session.execute(text("ALTER TABLE users MODIFY COLUMN role VARCHAR(32) NOT NULL DEFAULT 'EMPLOYEE'"))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            app.logger.warning('Could not reconcile schema defaults: %s', exc)

        try:
            for user in User.query.all():
                normalized_role = normalize_role(user.role)
                is_protected_super_admin = (
                    user.email == 'admin@okoa.local'
                    or user.phone_number in {'+254700000001', SUPER_ADMIN_PHONE}
                )
                if is_protected_super_admin:
                    user.role = 'SUPER_ADMIN'
                    user.is_superuser = True
                else:
                    user.is_superuser = False
                    user.role = 'EMPLOYEE' if normalized_role == 'SUPER_ADMIN' else normalized_role

            default_admin = User.query.filter(
                (User.email == 'admin@okoa.local') | (User.phone_number.in_({'+254700000001', SUPER_ADMIN_PHONE}))
            ).order_by(User.id.asc()).first()
            needs_initial_admin_password = (
                default_admin is None
                or default_admin.phone_number != SUPER_ADMIN_PHONE
            )
            if not default_admin:
                default_admin = User(
                    employee_id='HR-0001',
                    full_name='System Administrator',
                    employee_name='System Administrator',
                    job_position_title='Super Administrator',
                    employer='Okoa Float Ltd',
                    email=configured_admin_email or 'admin@okoa.local',
                    phone_number=SUPER_ADMIN_PHONE,
                    department='HR',
                    role='SUPER_ADMIN',
                    is_active=True,
                    is_superuser=True,
                    account_status='approved',
                    approved_at=datetime.utcnow(),
                    must_change_password=True,
                )
                db.session.add(default_admin)
            else:
                default_admin.full_name = 'System Administrator'
                default_admin.employee_name = 'System Administrator'
                default_admin.job_position_title = 'Super Administrator'
                default_admin.employer = 'Okoa Float Ltd'
                if (
                    configured_admin_email
                    and default_admin.email.strip().lower() == 'admin@okoa.local'
                ):
                    default_admin.email = configured_admin_email
                default_admin.phone_number = SUPER_ADMIN_PHONE
                default_admin.department = 'HR'
                default_admin.role = 'SUPER_ADMIN'
                default_admin.is_active = True
                default_admin.is_superuser = True
                default_admin.account_status = 'approved'
                default_admin.approved_at = default_admin.approved_at or datetime.utcnow()
                default_admin.employee_id = default_admin.employee_id or 'HR-0001'

            if needs_initial_admin_password:
                default_admin.must_change_password = True
                default_admin.set_password(SUPER_ADMIN_PASSWORD)
            db.session.commit()
            app.logger.info('Ensured default super-admin account is canonicalized and protected')
            if (
                not app.testing
                and default_admin.email.strip().lower() == 'admin@okoa.local'
            ):
                app.logger.warning(
                    "The default super-admin still uses a placeholder email; set ADMIN_EMAIL "
                    "to configure the administrator contact address."
                )
        except Exception:
            db.session.rollback()
            app.logger.warning('Skipping default super-admin bootstrap until the database schema is migrated.')

    return app


def setup_logging(app):
    """Configure logging for the application."""
    if not app.debug:
        # Create logs directory if it doesn't exist
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Set up file handler
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'okoa_float.log'),
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.INFO)
        
        # Set up formatter
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        file_handler.setFormatter(formatter)
        
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Okoa Float Leave Management System started')