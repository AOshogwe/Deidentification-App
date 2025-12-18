"""
app/__init__.py
Flask application factory with correct relative imports
"""

from flask import Flask
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # Import config AFTER Flask is initialized
    from app.config import config_by_env

    # Load environment-specific config
    env = os.getenv('FLASK_ENV', 'development')
    logger.info(f"Loading config for environment: {env}")

    try:
        config_class = config_by_env.get(env, config_by_env['development'])
        app.config.from_object(config_class)
        logger.info(f"Config loaded: {config_class.__name__}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise

    # Initialize database
    try:
        from app.db import init_db
        init_db(app)
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize deidentifier
    try:
        from app.deidentify import init_deidentifier
        init_deidentifier(app.config['DEIDENTIFICATION_SECRET'])
        logger.info("Deidentifier initialized")
    except Exception as e:
        logger.error(f"Failed to initialize deidentifier: {e}")
        raise

    # Register blueprints
    try:
        from app.routes import api_bp, monitor_bp
        app.register_blueprint(api_bp, url_prefix='/api')
        app.register_blueprint(monitor_bp)
        logger.info("Blueprints registered")
    except Exception as e:
        logger.error(f"Failed to register blueprints: {e}")
        raise

    return app