from db import db
from datetime import datetime


class MemberRaw(db.Model):
    """
    IDENTIFYING DATA TABLE (Restricted Access)
    Only administrators and the deidentification layer touch this.
    """
    __tablename__ = "members_raw"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<MemberRaw(id={self.id}, email={self.email})>"


class MemberDeidentified(db.Model):
    """
    AI-ACCESSIBLE DATA TABLE (Safe for ML/AI)
    No identifying information. Only stable anonymous identifiers and features.
    """
    __tablename__ = "members_deidentified"

    id = db.Column(db.Integer, primary_key=True)
    anon_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name_fingerprint = db.Column(db.String(32), nullable=True)  # Non-reversible reference
    signup_cohort = db.Column(db.String(20), nullable=False)  # Month-year grouping
    member_score = db.Column(db.Float, default=0.0)  # Engagement/trust metric
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<MemberDeidentified(anon_id={self.anon_id})>"


class MemberActivity(db.Model):
    """
    BEHAVIORAL DATA TABLE (AI-ready, already non-identifying)
    Tracks behavior tied only to anon_id, not raw identifiers.
    """
    __tablename__ = "member_activity"

    id = db.Column(db.Integer, primary_key=True)
    anon_id = db.Column(db.String(64), db.ForeignKey("members_deidentified.anon_id"), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # 'post', 'like', 'follow', 'comment'
    activity_score = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MemberActivity(anon_id={self.anon_id}, type={self.activity_type})>"


class AuditLog(db.Model):
    """
    AUDIT TRAIL (Privacy & Compliance)
    Tracks deidentification operations (not the data itself).
    """
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100), nullable=False)  # 'deidentified', 'key_rotated', 'access_denied'
    source_member_id = db.Column(db.Integer, nullable=True)  # Raw ID only, no PII
    anon_id = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text, nullable=True)  # Structured log info (JSON string)

    def __repr__(self):
        return f"<AuditLog(action={self.action}, timestamp={self.timestamp})>"