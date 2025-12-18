from flask import Flask
from config import config_by_env
from db import init_db
from deidentify import init_deidentifier
import os


def create_app():
    app = Flask(__name__, template_folder='templates')

    # Config
    env = os.getenv('FLASK_ENV', 'development')
    app.config.from_object(config_by_env[env])

    # Register blueprints
    from routes import api_bp, monitor_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(monitor_bp)

    return app