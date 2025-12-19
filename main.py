"""
main.py
Flask application entry point with SSH tunnel support
Handles automatic SSH tunnel creation for remote MySQL databases
"""

import os
import logging
import time
from sshtunnel import SSHTunnelForwarder

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
        logger.info("SSH tunnel disabled - no SSH credentials provided")
        return None

    try:
        logger.info(f"Creating SSH tunnel to {ssh_host}:{ssh_port}...")

        ssh_tunnel = SSHTunnelForwarder(
            (ssh_host, int(ssh_port)),
            ssh_username=ssh_user,
            ssh_password=ssh_password,
            remote_bind_address=('127.0.0.1', 3306)
        )

        ssh_tunnel.start()
        time.sleep(1)  # Give tunnel time to establish

        local_port = ssh_tunnel.local_bind_port
        logger.info(f"✓ SSH tunnel established on 127.0.0.1:{local_port}")

        # Update DATABASE_URL to use tunnel
        db_user = os.getenv('DB_USER')
        db_password = os.getenv('DB_PASSWORD')
        db_name = os.getenv('DB_NAME')

        from urllib.parse import quote_plus
        encoded_password = quote_plus(db_password)
        encoded_user = quote_plus(db_user)

        tunnel_url = f'mysql+pymysql://{encoded_user}:{encoded_password}@127.0.0.1:{local_port}/{db_name}'
        os.environ['DATABASE_URL'] = tunnel_url
        logger.info("✓ DATABASE_URL updated to use SSH tunnel")

        return ssh_tunnel

    except Exception as e:
        logger.error(f"❌ Failed to create SSH tunnel: {e}")
        raise


def cleanup_ssh_tunnel():
    """Close SSH tunnel on shutdown"""
    global ssh_tunnel
    if ssh_tunnel:
        try:
            ssh_tunnel.stop()
            logger.info("✓ SSH tunnel closed")
        except Exception as e:
            logger.error(f"Error closing SSH tunnel: {e}")


# Create Flask app
from app import create_app

app = create_app()


if __name__ == '__main__':
    # Setup SSH tunnel if needed
    setup_ssh_tunnel()

    # Register cleanup on shutdown
    import atexit
    atexit.register(cleanup_ssh_tunnel)

    # Get environment
    env = os.getenv('FLASK_ENV', 'development')
    port = int(os.getenv('PORT', 5000))
    debug = env == 'development'

    logger.info(f"🚀 Starting Flask app")
    logger.info(f"Environment: {env}")
    logger.info(f"Port: {port}")
    logger.info(f"Debug: {debug}")

    # Run
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        use_reloader=False  # Disable reloader to prevent double tunnel creation
    )