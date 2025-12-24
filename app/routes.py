"""
app/routes.py
Complete Flask routes for deidentification system
"""

from flask import Blueprint, render_template, request, jsonify
from app.db import db
from app.models import MemberRaw, MemberDeidentified, MemberActivity, AuditLog
from app.deidentify import get_deidentifier
from datetime import datetime
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# Create blueprints
api_bp = Blueprint('api', __name__)
monitor_bp = Blueprint('monitor', __name__)

logger.info("Routes module loaded - blueprints created")

# ─────────────────────────────────────────────────────────────────────────
# MONITOR ROUTES (HTML Frontend)
# ─────────────────────────────────────────────────────────────────────────

@monitor_bp.route('/')
def dashboard():
    """Serve the monitor dashboard HTML"""
    try:
        logger.info("Serving dashboard")
        return render_template('monitor.html')
    except Exception as e:
        logger.error(f"Failed to render dashboard: {e}")
        return jsonify({'error': 'Dashboard not found'}), 404


@monitor_bp.route('/monitor')
def monitor():
    """Alias for dashboard"""
    return dashboard()


@monitor_bp.route('/deidentify')
def deidentify_panel():
    """Serve the deidentification control panel"""
    try:
        logger.info("Serving deidentify panel")
        return render_template('deidentify.html')
    except Exception as e:
        logger.error(f"Failed to render deidentify panel: {e}")
        return jsonify({'error': 'Panel not found'}), 404


@monitor_bp.route('/worker')
def worker_status():
    """Serve the worker status monitoring dashboard"""
    try:
        logger.info("Serving worker status page")
        return render_template('worker_status.html')
    except Exception as e:
        logger.error(f"Failed to render worker status page: {e}")
        return jsonify({'error': 'Page not found'}), 404


# ─────────────────────────────────────────────────────────────────────────
# API ROUTES (Backend Endpoints)
# ─────────────────────────────────────────────────────────────────────────

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    logger.info("Health check called")
    return jsonify({
        'status': 'healthy',
        'message': 'API is working',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@api_bp.route('/worker/status', methods=['GET'])
def worker_status_api():
    """Get current worker status and statistics from real database"""
    try:
        logger.info("Getting worker status...")

        # Get actual counts from database
        raw_count = 0
        deidentified_count = 0
        financial_raw = 0
        financial_deident = 0
        health_raw = 0
        health_deident = 0

        try:
            raw_count = db.session.query(MemberRaw).count()
            logger.info(f"members_raw count: {raw_count}")
        except Exception as e:
            logger.error(f"Error counting members_raw: {e}")
            raw_count = 0

        try:
            deidentified_count = db.session.query(MemberDeidentified).count()
            logger.info(f"members_deidentified count: {deidentified_count}")
        except Exception as e:
            logger.error(f"Error counting members_deidentified: {e}")
            deidentified_count = 0

        try:
            with db.engine.connect() as conn:
                result = conn.execute(text('SELECT COUNT(*) as cnt FROM member_financial_data'))
                financial_raw = result.scalar() or 0
                logger.info(f"member_financial_data count: {financial_raw}")
        except Exception as e:
            logger.debug(f"Table member_financial_data not found or error: {e}")
            financial_raw = 0

        try:
            with db.engine.connect() as conn:
                result = conn.execute(text('SELECT COUNT(*) as cnt FROM member_financial_data_deidentified'))
                financial_deident = result.scalar() or 0
                logger.info(f"member_financial_data_deidentified count: {financial_deident}")
        except Exception as e:
            logger.debug(f"Table member_financial_data_deidentified not found or error: {e}")
            financial_deident = 0

        try:
            with db.engine.connect() as conn:
                result = conn.execute(text('SELECT COUNT(*) as cnt FROM member_health_data'))
                health_raw = result.scalar() or 0
                logger.info(f"member_health_data count: {health_raw}")
        except Exception as e:
            logger.debug(f"Table member_health_data not found or error: {e}")
            health_raw = 0

        try:
            with db.engine.connect() as conn:
                result = conn.execute(text('SELECT COUNT(*) as cnt FROM member_health_data_deidentified'))
                health_deident = result.scalar() or 0
                logger.info(f"member_health_data_deidentified count: {health_deident}")
        except Exception as e:
            logger.debug(f"Table member_health_data_deidentified not found or error: {e}")
            health_deident = 0

        # Get latest logs from audit table
        latest_logs = []
        try:
            latest_logs = db.session.query(AuditLog)\
                .order_by(AuditLog.timestamp.desc())\
                .limit(10)\
                .all()
        except Exception as e:
            logger.warning(f"Could not fetch audit logs: {e}")
            latest_logs = []

        # Calculate totals
        total_deidentified = deidentified_count + financial_deident + health_deident
        total_raw = raw_count + financial_raw + health_raw
        progress = round((total_deidentified / total_raw * 100)) if total_raw > 0 else 0

        logger.info(f"Total: {total_raw} raw, {total_deidentified} deidentified, {progress}% progress")

        response_data = {
            'worker_status': 'active',
            'last_heartbeat': datetime.utcnow().isoformat(),
            'total_deidentified': total_deidentified,
            'tables_monitored': 3,
            'processing_rate': 12.5,
            'tables': [
                {
                    'source': 'members_raw',
                    'deidentified': 'members_raw_deidentified',
                    'source_records': raw_count,
                    'deidentified_records': deidentified_count,
                    'status': 'synced' if raw_count == deidentified_count else 'syncing',
                    'last_synced': datetime.utcnow().isoformat()
                },
                {
                    'source': 'member_financial_data',
                    'deidentified': 'member_financial_data_deidentified',
                    'source_records': financial_raw,
                    'deidentified_records': financial_deident,
                    'status': 'synced' if financial_raw == financial_deident else 'syncing',
                    'last_synced': datetime.utcnow().isoformat()
                },
                {
                    'source': 'member_health_data',
                    'deidentified': 'member_health_data_deidentified',
                    'source_records': health_raw,
                    'deidentified_records': health_deident,
                    'status': 'synced' if health_raw == health_deident else 'syncing',
                    'last_synced': datetime.utcnow().isoformat()
                }
            ],
            'progress_percent': progress,
            'recent_logs': [
                {
                    'timestamp': log.timestamp.isoformat(),
                    'action': log.action,
                    'details': log.details
                } for log in latest_logs
            ]
        }

        logger.info(f"Returning worker status successfully")
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"CRITICAL - Failed to get worker status: {e}", exc_info=True)
        return jsonify({
            'error': str(e),
            'worker_status': 'error'
        }), 500


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get deidentification statistics"""
    try:
        raw_count = db.session.query(MemberRaw).count()
        deidentified_count = db.session.query(MemberDeidentified).count()
        pending_count = raw_count - deidentified_count
        progress_percent = round((deidentified_count / raw_count * 100)) if raw_count > 0 else 0

        return jsonify({
            'raw_count': raw_count,
            'deidentified_count': deidentified_count,
            'pending_count': pending_count,
            'progress_percent': progress_percent
        }), 200

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/test-connection', methods=['POST'])
def test_connection():
    """Test database connection with optional SSH tunnel"""
    ssh_tunnel = None

    try:
        data = request.get_json()

        # Extract credentials
        from urllib.parse import quote_plus

        db_type = data.get('dbType', 'postgresql')
        db_host = data.get('dbHost')
        db_port = data.get('dbPort')
        db_user = data.get('dbUser')
        db_password = data.get('dbPassword')
        db_name = data.get('dbName')
        use_ssh_tunnel = data.get('useSshTunnel', False)

        # Validate input
        if not all([db_host, db_port, db_user, db_name]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required database credentials'
            }), 400

        # Handle SSH Tunnel
        if use_ssh_tunnel:
            from sshtunnel import SSHTunnelForwarder
            import time

            ssh_host = data.get('sshHost')
            ssh_port = int(data.get('sshPort', 22))
            ssh_user = data.get('sshUser')
            ssh_password = data.get('sshPassword')

            if not all([ssh_host, ssh_user, ssh_password]):
                return jsonify({
                    'status': 'error',
                    'message': 'Missing SSH tunnel credentials'
                }), 400

            try:
                logger.info(f"Creating SSH tunnel to {ssh_host}:{ssh_port}...")

                ssh_tunnel = SSHTunnelForwarder(
                    (ssh_host, int(ssh_port)),
                    ssh_username=ssh_user,
                    ssh_password=ssh_password,
                    remote_bind_address=('127.0.0.1', 3306)
                )

                ssh_tunnel.start()
                time.sleep(1)

                tunnel_host = '127.0.0.1'
                tunnel_port = ssh_tunnel.local_bind_port
                logger.info(f"✓ SSH tunnel established on {tunnel_host}:{tunnel_port}")

            except Exception as e:
                logger.error(f"SSH tunnel failed: {e}")
                return jsonify({
                    'status': 'error',
                    'message': f'SSH tunnel failed: {str(e)}'
                }), 500
        else:
            tunnel_host = db_host
            tunnel_port = db_port

        # URL-encode credentials
        encoded_password = quote_plus(db_password)
        encoded_user = quote_plus(db_user)

        # Build connection string
        if db_type == 'postgresql':
            conn_str = f'postgresql://{encoded_user}:{encoded_password}@{tunnel_host}:{tunnel_port}/{db_name}'
        elif db_type == 'mysql':
            conn_str = f'mysql+pymysql://{encoded_user}:{encoded_password}@{tunnel_host}:{tunnel_port}/{db_name}'
        else:
            return jsonify({
                'status': 'error',
                'message': 'Invalid database type. Use "postgresql" or "mysql"'
            }), 400

        # Test connection
        from sqlalchemy import create_engine, text

        engine = create_engine(conn_str, pool_pre_ping=True)

        with engine.connect() as conn:
            result = conn.execute(text('SELECT 1'))
            logger.info(f"✓ Query executed: {result.fetchone()}")

        logger.info(f"✓ Connection test successful: {db_host}:{db_port}/{db_name}")

        return jsonify({
            'status': 'connected',
            'message': f'Successfully connected to {db_host}:{db_port}/{db_name}',
            'host': db_host,
            'database': db_name,
            'type': db_type.upper(),
            'via_ssh': use_ssh_tunnel
        }), 200

    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Connection failed: {str(e)}'
        }), 500

    finally:
        if ssh_tunnel:
            try:
                ssh_tunnel.stop()
                logger.info("✓ SSH tunnel closed")
            except Exception as e:
                logger.error(f"Error closing SSH tunnel: {e}")


@api_bp.route('/audit-logs', methods=['GET'])
def get_audit_logs():
    """Get audit logs"""
    try:
        limit = request.args.get('limit', 100, type=int)
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

        return jsonify([{
            'id': log.id,
            'action': log.action,
            'timestamp': log.timestamp.isoformat(),
            'details': log.details
        } for log in logs]), 200

    except Exception as e:
        logger.error(f"Audit log retrieval failed: {e}")
        return jsonify({'error': str(e)}), 500


logger.info("All routes defined successfully")