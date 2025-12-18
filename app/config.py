import os
from datetime import timedelta


class Config:
    """Base configuration"""
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///app.db'
    )
    # Fix PostgreSQL URI if needed
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            'postgres://', 'postgresql://', 1
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEIDENTIFICATION_SECRET = os.getenv('DEIDENTIFICATION_SECRET')
    if not DEIDENTIFICATION_SECRET:
        raise ValueError('DEIDENTIFICATION_SECRET must be set')

    ENABLE_AUDIT_LOGGING = os.getenv('ENABLE_AUDIT_LOGGING', 'True') == 'True'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_env = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}