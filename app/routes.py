"""
app/routes.py
All Flask routes: Dashboard HTML + API endpoints
"""

from flask import Blueprint, render_template, request, jsonify
from app.db import db
from app.models import MemberRaw, MemberDeidentified, MemberActivity, AuditLog
from app.deidentify import get_deidentifier
import logging

logger = logging.getLogger(__name__)

# Create blueprints
api_bp = Blueprint('api', __name__, url_prefix='/api')
monitor_bp = Blueprint('monitor', __name__)

# ─────────────────────────────────────────────────────────────────────────
# MONITOR ROUTES (HTML Frontend)
# ─────────────────────────────────────────────────────────────────────────

@monitor_bp.route('/', methods=['GET'])
def dashboard():
    """Serve the monitor dashboard HTML"""
    try:
        return render_template('monitor.html')
    except Exception as e:
        logger.error(f"Failed to render dashboard: {e}")
        return jsonify({'error': 'Dashboard not found'}), 404


@monitor_bp.route('/monitor', methods=['GET'])
def monitor():
    """Alias for dashboard"""
    return dashboard()


# ─────────────────────────────────────────────────────────────────────────
# API ROUTES (Backend Endpoints)
# ─────────────────────────────────────────────────────────────────────────

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Liveness probe for Railway/Docker"""
    try:
        # Test database connection
        result = db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy',
            'message': 'Application is running'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@api_bp.route('/test-connection', methods=['POST'])
def test_connection():
    """
    Test database connection with provided credentials

    Expected JSON:
    {
        "dbType": "postgresql" | "mysql",
        "dbHost": "localhost",
        "dbPort": 5432,
        "dbUser": "admin",
        "dbPassword": "password",
        "dbName": "dbname"
    }
    """
    try:
        data = request.get_json()

        # Extract credentials
        db_type = data.get('dbType', 'postgresql')
        db_host = data.get('dbHost')
        db_port = data.get('dbPort')
        db_user = data.get('dbUser')
        db_password = data.get('dbPassword')
        db_name = data.get('dbName')

        # Validate input
        if not all([db_host, db_port, db_user, db_name]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required database credentials'
            }), 400

        # Build connection string
        if db_type == 'postgresql':
            conn_str = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
        elif db_type == 'mysql':
            conn_str = f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
        else:
            return jsonify({
                'status': 'error',
                'message': 'Invalid database type. Use "postgresql" or "mysql"'
            }), 400

        # Test connection
        from sqlalchemy import create_engine, text
        engine = create_engine(conn_str)

        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))

        logger.info(f"✓ Connection test successful: {db_host}:{db_port}/{db_name}")

        return jsonify({
            'status': 'connected',
            'message': f'Successfully connected to {db_host}:{db_port}/{db_name}',
            'host': db_host,
            'database': db_name,
            'type': db_type.upper()
        }), 200

    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Connection failed: {str(e)}'
        }), 500


@api_bp.route('/health-check', methods=['POST'])
def continuous_health_check():
    """
    Continuous health check endpoint for monitoring dashboard
    Called every 10 seconds by dashboard
    """
    try:
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy'}), 200
    except Exception as e:
        logger.error(f"Continuous health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@api_bp.route('/members/deidentify/<int:member_id>', methods=['POST'])
def deidentify_member(member_id):
    """Deidentify a single member by ID"""
    try:
        deidentifier = get_deidentifier()

        member = MemberRaw.query.get_or_404(member_id)
        data = deidentifier.deidentify_member(member)

        # Check if already deidentified
        existing = MemberDeidentified.query.filter_by(anon_id=data['anon_id']).first()
        if not existing:
            deidentified = MemberDeidentified(**data)
            db.session.add(deidentified)
            db.session.commit()
            deidentifier.log_audit(
                'deidentified',
                source_id=member_id,
                anon_id=data['anon_id']
            )

        return jsonify({
            'status': 'success',
            'member_id': member_id,
            'anon_id': data['anon_id'],
            'signup_cohort': data['signup_cohort']
        }), 200

    except Exception as e:
        logger.error(f"Deidentification failed: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/members/deidentify-batch', methods=['POST'])
def deidentify_batch():
    """Batch deidentify all members"""
    try:
        deidentifier = get_deidentifier()

        members = MemberRaw.query.all()
        results = []

        for member in members:
            data = deidentifier.deidentify_member(member)

            existing = MemberDeidentified.query.filter_by(anon_id=data['anon_id']).first()
            if not existing:
                deidentified = MemberDeidentified(**data)
                db.session.add(deidentified)
                results.append({
                    'member_id': member.id,
                    'anon_id': data['anon_id'],
                    'status': 'created'
                })
            else:
                results.append({
                    'member_id': member.id,
                    'anon_id': data['anon_id'],
                    'status': 'exists'
                })

        db.session.commit()
        deidentifier.log_audit('batch_deidentified', details={'count': len(results)})

        logger.info(f"Batch deidentified {len(results)} members")

        return jsonify({
            'status': 'success',
            'total': len(results),
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Batch deidentification failed: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/members/activity/<anon_id>', methods=['POST'])
def log_activity(anon_id):
    """Log member activity using anonymous ID"""
    try:
        data = request.get_json()

        # Verify anon_id exists
        member = MemberDeidentified.query.filter_by(anon_id=anon_id).first_or_404()

        activity = MemberActivity(
            anon_id=anon_id,
            activity_type=data.get('activity_type'),
            activity_score=data.get('activity_score', 0.0)
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({
            'status': 'logged',
            'anon_id': anon_id
        }), 201

    except Exception as e:
        logger.error(f"Activity logging failed: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/audit-logs', methods=['GET'])
def get_audit_logs():
    """Get audit trail for compliance"""
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