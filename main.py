import os
from app import create_app, init_db, init_deidentifier

app = create_app()

if __name__ == '__main__':
    # Get environment
    env = os.getenv('FLASK_ENV', 'development')
    debug = env == 'development'

    # Initialize database
    with app.app_context():
        init_db(app)
        init_deidentifier(app.config['DEIDENTIFICATION_SECRET'])

    # Run on 0.0.0.0 (required for Railway)
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=debug
    )