"""
main.py
Flask application entry point for gunicorn and local development
Run: python main.py (local) or gunicorn main:app (production/Railway)
"""

import os
import logging
from app import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app using factory
app = create_app()

# Log startup info
if __name__ == '__main__':
    env = os.getenv('FLASK_ENV', 'development')
    port = int(os.getenv('PORT', 5000))
    debug = env == 'development'

    logger.info(f"🚀 Starting Flask app")
    logger.info(f"Environment: {env}")
    logger.info(f"Port: {port}")
    logger.info(f"Debug: {debug}")
    logger.info(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")

    # Run development server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        use_reloader=True
    )