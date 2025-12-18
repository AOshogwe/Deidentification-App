from flask_sqlalchemy import SQLAlchemy
import logging

db = SQLAlchemy()
logger = logging.getLogger(__name__)


def init_db(app):
    """Initialize database with Flask app"""
    db.init_app(app)

    with app.app_context():
        db.create_all()
        logger.info("Database initialized successfully")

    return db


def get_db_session():
    """Get current database session (for non-request contexts)"""
    return db.session


def close_db_session():
    """Safely close database session"""
    db.session.close()