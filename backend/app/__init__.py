"""
Application Factory Pattern
Creates and configures the Flask application.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from sqlalchemy import text
from flask_migrate import Migrate
from flask_cors import CORS

from app.config import config
from app.extensions import db, jwt
from app.utils.rbac import normalize_role

# Import models so Alembic can detect them
from app.models import Department, HandoverReport, SalesDailyReport, User


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
    
    # Initialize extensions
    db.init_app(app)
    Migrate(app, db, directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations_okoa'))
    jwt.init_app(app)
    CORS(app, origins=app.config.get('CORS_ORIGINS', '*'))
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.leave import leave_bp
    from app.api.chat import chat_bp
    from app.api.admin import admin_bp
    from app.api.sales import sales_bp
    from app.api.debt_collection import collector_bp, debt_collection_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(leave_bp, url_prefix='/api/leave')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(admin_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(debt_collection_bp)
    app.register_blueprint(collector_bp)
    
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
                is_protected_super_admin = user.email == 'admin@okoa.local' or user.phone_number == '+254700000001'
                if is_protected_super_admin:
                    user.role = 'SUPER_ADMIN'
                    user.is_superuser = True
                else:
                    user.is_superuser = False
                    user.role = 'EMPLOYEE' if normalized_role == 'SUPER_ADMIN' else normalized_role

            default_admin = User.query.filter(
                (User.email == 'admin@okoa.local') | (User.phone_number == '+254700000001')
            ).order_by(User.id.asc()).first()
            if not default_admin:
                default_admin = User(
                    employee_id='HR-0001',
                    full_name='System Administrator',
                    employee_name='System Administrator',
                    job_position_title='Super Administrator',
                    employer='Okoa Float Ltd',
                    email='admin@okoa.local',
                    phone_number='+254700000001',
                    department='HR',
                    role='SUPER_ADMIN',
                    is_active=True,
                    is_superuser=True,
                    account_status='approved',
                    must_change_password=True,
                )
                db.session.add(default_admin)
            else:
                default_admin.full_name = 'System Administrator'
                default_admin.employee_name = 'System Administrator'
                default_admin.job_position_title = 'Super Administrator'
                default_admin.employer = 'Okoa Float Ltd'
                default_admin.email = 'admin@okoa.local'
                default_admin.phone_number = '+254700000001'
                default_admin.department = 'HR'
                default_admin.role = 'SUPER_ADMIN'
                default_admin.is_active = True
                default_admin.is_superuser = True
                default_admin.account_status = 'approved'
                default_admin.must_change_password = True
                default_admin.employee_id = default_admin.employee_id or 'HR-0001'

            default_admin.set_password('Admin@2026!')
            db.session.commit()
            app.logger.info('Ensured default super-admin account is canonicalized and protected')
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