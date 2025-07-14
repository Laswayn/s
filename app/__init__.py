from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

db = SQLAlchemy()
migrate = Migrate()

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    # Create Flask app dengan static_url_path untuk sensus
    app = Flask(__name__, static_url_path='/sensus/static')
    app.config.from_object(config[config_name])
    
    # Ensure database directory exists and is accessible
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'):
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        db_path = Path(db_path)
        db_dir = db_path.parent
        
        # Create directory with proper permissions
        try:
            db_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
            app.logger.info(f"Database directory ensured: {db_dir}")
            
            # If database file exists, ensure it has proper permissions
            if db_path.exists():
                db_path.chmod(0o644)
                app.logger.info(f"Database file permissions set: {db_path}")
                
        except Exception as e:
            app.logger.error(f"Failed to setup database directory: {e}")
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Set application root untuk sensus subdirectory
    if config_name == 'production':
        app.config['APPLICATION_ROOT'] = '/sensus'
        app.config['SESSION_COOKIE_PATH'] = '/sensus'
    
    # Setup logging
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Sensus app startup')
    
    # Create database tables and default users within app context
    with app.app_context():
        try:
            # Import models to ensure they're registered
            from app.models import User, Keluarga, Individu
            
            # Create all tables
            db.create_all()
            app.logger.info('Database tables created successfully')
            
            # Create default users if they don't exist
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                admin_user = User(username='admin', role='admin')
                admin_user.set_password(app.config['ADMIN_PASSWORD'])
                db.session.add(admin_user)
                app.logger.info('Created admin user')
            
            regular_user = User.query.filter_by(username='user').first()
            if not regular_user:
                regular_user = User(username='user', role='user')
                regular_user.set_password(app.config['USER_PASSWORD'])
                db.session.add(regular_user)
                app.logger.info('Created regular user')
            
            db.session.commit()
            app.logger.info('Default users setup completed')
            
            # Test database access
            family_count = Keluarga.query.count()
            individual_count = Individu.query.count()
            app.logger.info(f'Database accessible - Families: {family_count}, Individuals: {individual_count}')
            
        except Exception as e:
            app.logger.error(f'Database initialization error: {e}')
            db.session.rollback()
    
    # Register blueprints dengan prefix untuk sensus
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    # Create upload directory
    try:
        upload_dir = Path(app.config['UPLOAD_FOLDER'])
        upload_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        app.logger.info(f"Upload directory ensured: {upload_dir}")
    except Exception as e:
        app.logger.error(f"Failed to create upload directory: {e}")
    
    return app

from app import models
