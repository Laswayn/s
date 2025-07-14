import os
from datetime import timedelta
from pathlib import Path

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sensus-secret-key-pahlawan140'
    
    # Get absolute paths
    BASE_DIR = Path(__file__).parent.absolute()
    INSTANCE_DIR = BASE_DIR / 'instance'
    
    # Ensure instance directory exists with proper permissions
    INSTANCE_DIR.mkdir(exist_ok=True, mode=0o755)
    
    # Database configuration with absolute path
    DATABASE_PATH = INSTANCE_DIR / 'data_sensus.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    SESSION_TIMEOUT = 3600
    
    # Session cookie configuration untuk subdirectory
    SESSION_COOKIE_PATH = '/'
    SESSION_COOKIE_SECURE = False    # Set True jika HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # User credentials untuk sensus
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'pahlawan140'
    USER_PASSWORD = os.environ.get('USER_PASSWORD') or 'bps140'
    
    # Upload configuration
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    UPLOAD_FOLDER.mkdir(exist_ok=True, mode=0o755)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    
    # Konfigurasi khusus untuk folder sensus
    BASE_DIR = Path(__file__).parent.absolute()
    
    # Database path untuk folder sensus
    INSTANCE_DIR = BASE_DIR / 'instance'
    INSTANCE_DIR.mkdir(exist_ok=True, mode=0o755)
    
    DATABASE_PATH = INSTANCE_DIR / 'data_sensus.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{DATABASE_PATH}'
    
    # Upload folder untuk sensus
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    UPLOAD_FOLDER.mkdir(exist_ok=True, mode=0o755)
    
    # Application root untuk subdirectory sensus
    APPLICATION_ROOT = '/sensus'
    
    # Static files configuration untuk sensus
    STATIC_URL_PATH = '/sensus/static'
    
    # Session cookie path untuk subdirectory
    SESSION_COOKIE_PATH = '/sensus'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
