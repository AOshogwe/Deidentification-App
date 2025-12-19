"""
app/config.py
Environment-specific configuration
"""

import os
from datetime import timedelta


class Config:
    """Base configuration - shared across all environments"""

    # ─────────────────────────────────────────────────────────────────
    # DATABASE
    # ─────────────────────────────────────────────────────────────────

    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///app.db')

    # Fix PostgreSQL URI scheme (psycopg2 → postgresql)
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True
    }

    # ─────────────────────────────────────────────────────────────────
    # SECURITY & DEIDENTIFICATION
    # ─────────────────────────────────────────────────────────────────

    DEIDENTIFICATION_SECRET = os.getenv('DEIDENTIFICATION_SECRET')
    if not DEIDENTIFICATION_SECRET:
        raise ValueError(
            '❌ DEIDENTIFICATION_SECRET environment variable must be set. '
            'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    SECRET_KEY = os.getenv('SECRET_KEY', DEIDENTIFICATION_SECRET[:32])

    # ─────────────────────────────────────────────────────────────────
    # PRIVACY & LOGGING
    # ─────────────────────────────────────────────────────────────────

    ENABLE_AUDIT_LOGGING = os.getenv('ENABLE_AUDIT_LOGGING', 'True') == 'True'
    KEY_ROTATION_INTERVAL = timedelta(days=90)

    # ─────────────────────────────────────────────────────────────────
    # FLASK SETTINGS
    # ─────────────────────────────────────────────────────────────────

    JSON_SORT_KEYS = False
    PROPAGATE_EXCEPTIONS = True


class DevelopmentConfig(Config):
    """Development environment - with debugging enabled"""
    DEBUG = True
    TESTING = False
    JSONIFY_PRETTYPRINT_REGULAR = True


class ProductionConfig(Config):
    """Production environment - for Railway and live deployment"""
    DEBUG = False
    TESTING = False
    JSONIFY_PRETTYPRINT_REGULAR = False


class TestingConfig(Config):
    """Testing environment - for unit tests"""
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Mapping of environment names to config classes
config_by_env = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}