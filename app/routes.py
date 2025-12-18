from flask import Blueprint, render_template, request, jsonify
from db import db
from models import MemberRaw, MemberDeidentified, MemberActivity, AuditLog
from deidentify import get_deidentifier
import logging

logger = logging.getLogger(__name__)

# Blueprints
api_bp = Blueprint('api', __name__)
monitor_bp = Blueprint('monitor', __name__)


# ─────────────────────────────────────────────────────────────────────────
# MONITOR ROUTES (HTML Frontend)
# ─────────────────────────────────────────────────────────────────────────

@monitor_bp.route('/')
def dashboard():
    """Serve the monitor dashboard"""
    return render_template('monitor.html')


@monitor_bp.route('/monitor')
def monitor():
    """Alias for dashboard"""
    return render_template('monitor.html')


# ─────────────────────────────────────────────────────────────────────────
# API ROUTES (Backend Endpoints)
# ─────────────────────────────────────────────────────────────────────────

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Liveness probe"""
    try:
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@api_bp.route('/test-connection', methods=['POST'])
def test_connection():
    """Test database connection with provided credentials"""
    try:
        data = request.get_json()

        db_type = data.get('dbType', 'postgresql')
        db_host = data.get('dbHost')
        db_port = data.get('dbPort')
        db_user = data.get('dbUser')
        db_password = data.get('dbPassword')
        db_name = data.get('dbName')

        # Build connection string
        if db_type == 'postgresql':
            conn_str = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
        else:  # mysql
            conn_str = f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'

        # Test connection
        from sqlalchemy import create_engine
        engine = create_engine(conn_str, connect_args={'timeout': 5})
        with engine.connect() as conn:
            conn.execute('SELECT 1')

        return jsonify({
            'status': 'connected',
            'message': f'Successfully connected to {db_host}:{db_port}/{db_name}'
        }), 200

    except Exception as e:
        logger.error(f'Connection test failed: {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/health-check', methods=['POST'])
def continuous_health_check():
    """Continuous health check with latency"""
    try:
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@api_bp.route('/members/deidentify/<int:member_id>', methods=['POST'])
def deidentify_member(member_id):
    """Deidentify a single member"""
    try:
        deidentifier = get_deidentifier()

        member = MemberRaw.query.get_or_404(member_id)
        data = deidentifier.deidentify_member(member)

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
        }), 200

    except Exception as e:
        logger.error(f'Deidentification failed: {e}')
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
                results.append({'member_id': member.id, 'anon_id': data['anon_id'], 'status': 'created'})
            else:
                results.append({'member_id': member.id, 'anon_id': data['anon_id'], 'status': 'exists'})

        db.session.commit()
        deidentifier.log_audit('batch_deidentified', details={'count': len(results)})

        return jsonify({'status': 'success', 'total': len(results), 'results': results}), 200

    except Exception as e:
        logger.error(f'Batch deidentification failed: {e}')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/members/activity/<anon_id>', methods=['POST'])
def log_activity(anon_id):
    """Log member activity"""
    try:
        data = request.get_json()
        member = MemberDeidentified.query.filter_by(anon_id=anon_id).first_or_404()

        activity = MemberActivity(
            anon_id=anon_id,
            activity_type=data.get('activity_type'),
            activity_score=data.get('activity_score', 0.0)
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({'status': 'logged', 'anon_id': anon_id}), 201

    except Exception as e:
        logger.error(f'Activity logging failed: {e}')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/audit-logs', methods=['GET'])
def get_audit_logs():
    """Get audit logs"""
    try:
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
        return jsonify([{
            'id': log.id,
            'action': log.action,
            'timestamp': log.timestamp.isoformat(),
        } for log in logs]), 200

    except Exception as e:
        logger.error(f'Audit log retrieval failed: {e}')
        return jsonify({'error': str(e)}), 500