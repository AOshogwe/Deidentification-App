from flask import Flask, jsonify, request
from config import config_by_env
from db import init_db, db
from models import MemberRaw, MemberDeidentified, MemberActivity, AuditLog
from deidentify import init_deidentifier, get_deidentifier
import logging
import os

app = Flask(__name__)

# Configuration
env = os.getenv("FLASK_ENV", "development")
app.config.from_object(config_by_env[env])

# Initialize
init_db(app)
init_deidentifier(app.config["DEIDENTIFICATION_SECRET"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health_check():
    """Liveness probe for Railway"""
    return jsonify({"status": "healthy"}), 200


@app.route("/api/members/deidentify/<int:member_id>", methods=["POST"])
def deidentify_member_route(member_id):
    """
    Deidentify a single member by ID.

    Flow:
    1. Fetch raw member
    2. Deidentify (HMAC-hash email → anon_id)
    3. Store in deidentified table
    4. Log audit trail
    """
    try:
        deidentifier = get_deidentifier()

        member = MemberRaw.query.get_or_404(member_id)
        data = deidentifier.deidentify_member(member)

        # Check if already deidentified
        existing = MemberDeidentified.query.filter_by(anon_id=data["anon_id"]).first()
        if not existing:
            deidentified = MemberDeidentified(**data)
            db.session.add(deidentified)
            db.session.commit()
            deidentifier.log_audit(
                "deidentified",
                source_id=member_id,
                anon_id=data["anon_id"]
            )

        return jsonify({
            "status": "success",
            "member_id": member_id,
            "anon_id": data["anon_id"],
            "signup_cohort": data["signup_cohort"]
        }), 200

    except Exception as e:
        logger.error(f"Deidentification failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/members/deidentify-batch", methods=["POST"])
def deidentify_batch():
    """
    Deidentify multiple members in bulk.
    Use for initial migration or batch processing.
    """
    try:
        deidentifier = get_deidentifier()

        members = MemberRaw.query.all()
        results = []

        for member in members:
            data = deidentifier.deidentify_member(member)

            existing = MemberDeidentified.query.filter_by(anon_id=data["anon_id"]).first()
            if not existing:
                deidentified = MemberDeidentified(**data)
                db.session.add(deidentified)
                results.append({"member_id": member.id, "anon_id": data["anon_id"], "status": "created"})
            else:
                results.append({"member_id": member.id, "anon_id": data["anon_id"], "status": "exists"})

        db.session.commit()
        deidentifier.log_audit("batch_deidentified", details={"count": len(results)})

        return jsonify({
            "status": "success",
            "total": len(results),
            "results": results
        }), 200

    except Exception as e:
        logger.error(f"Batch deidentification failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/members/activity/<anon_id>", methods=["POST"])
def log_member_activity(anon_id):
    """
    Record member activity using anon_id (no raw identifiers).
    Safe for streaming to AI engines.
    """
    try:
        data = request.get_json()
        activity_type = data.get("activity_type")
        activity_score = data.get("activity_score", 0.0)

        # Verify anon_id exists in deidentified table
        member = MemberDeidentified.query.filter_by(anon_id=anon_id).first_or_404()

        activity = MemberActivity(
            anon_id=anon_id,
            activity_type=activity_type,
            activity_score=activity_score
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({"status": "logged", "anon_id": anon_id}), 201

    except Exception as e:
        logger.error(f"Activity logging failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/audit-logs", methods=["GET"])
def get_audit_logs():
    """
    Retrieve audit trail for compliance review.
    Non-sensitive information only.
    """
    try:
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
        return jsonify([{
            "id": log.id,
            "action": log.action,
            "timestamp": log.timestamp.isoformat(),
            "details": log.details
        } for log in logs]), 200

    except Exception as e:
        logger.error(f"Audit log retrieval failed: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)