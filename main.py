"""
main.py
Flask application entry point with SSH tunnel support
Handles automatic SSH tunnel creation for remote MySQL databases
"""

import os
import logging
import time
from urllib.parse import quote_plus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global SSH tunnel
ssh_tunnel = None


def setup_ssh_tunnel():
    """
    Create SSH tunnel to cPanel server if SSH credentials are provided
    This allows secure connection to MySQL on remote server
    """
    global ssh_tunnel

    ssh_host = os.getenv('SSH_HOST')
    ssh_port = os.getenv('SSH_PORT', '22')
    ssh_user = os.getenv('SSH_USER')
    ssh_password = os.getenv('SSH_PASSWORD')

    # Only create tunnel if SSH credentials are provided
    if not all([ssh_host, ssh_user, ssh_password]):
        logger.info("ℹ️ SSH tunnel disabled - no SSH credentials provided")
        return None

    try:
        from sshtunnel import SSHTunnelForwarder

        logger.info(f"🔧 Creating SSH tunnel to {ssh_host}:{ssh_port}...")

        ssh_tunnel = SSHTunnelForwarder(
            (ssh_host, int(ssh_port)),
            ssh_username=ssh_user,
            ssh_password=ssh_password,
            remote_bind_address=('127.0.0.1', 3306)
        )

        ssh_tunnel.start()
        time.sleep(2)  # Give tunnel time to fully establish

        local_port = ssh_tunnel.local_bind_port
        logger.info(f"✓ SSH tunnel established on 127.0.0.1:{local_port}")

        # Build connection string using tunnel
        db_user = os.getenv('DB_USER', 'root')
        db_password = os.getenv('DB_PASSWORD', '')
        db_name = os.getenv('DB_NAME', 'test')

        encoded_password = quote_plus(db_password)
        encoded_user = quote_plus(db_user)

        tunnel_url = f'mysql+pymysql://{encoded_user}:{encoded_password}@127.0.0.1:{local_port}/{db_name}'
        os.environ['DATABASE_URL'] = tunnel_url
        logger.info(f"✓ DATABASE_URL configured to use SSH tunnel")
        logger.info(f"✓ Connecting to: {db_user}@127.0.0.1:{local_port}/{db_name}")

        return ssh_tunnel

    except Exception as e:
        logger.error(f"❌ Failed to create SSH tunnel: {e}")
        logger.info("ℹ️ Falling back to direct DATABASE_URL")
        return None


def cleanup_ssh_tunnel():
    """Close SSH tunnel on shutdown"""
    global ssh_tunnel
    if ssh_tunnel:
        try:
            ssh_tunnel.stop()
            logger.info("✓ SSH tunnel closed")
        except Exception as e:
            logger.error(f"Error closing SSH tunnel: {e}")


# Setup SSH tunnel BEFORE importing Flask app
logger.info("=" * 60)
logger.info("DEIDENTIFICATION SYSTEM STARTUP")
logger.info("=" * 60)

setup_ssh_tunnel()

# NOW create Flask app (models will use the tunneled DATABASE_URL)
from app import create_app

app = create_app()

logger.info("=" * 60)
logger.info("✓ APPLICATION READY")
logger.info("=" * 60)


if __name__ == '__main__':
    # Register cleanup on shutdown
    import atexit
    atexit.register(cleanup_ssh_tunnel)

    # Get environment
    env = os.getenv('FLASK_ENV', 'development')
    port = int(os.getenv('PORT', 5000))
    debug = env == 'development'

    logger.info(f"🚀 Starting Flask server")
    logger.info(f"Environment: {env}")
    logger.info(f"Port: {port}")
    logger.info(f"Debug mode: {debug}")

    # Run
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        use_reloader=False
    )