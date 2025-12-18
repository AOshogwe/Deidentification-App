import hmac
import hashlib
from datetime import datetime
from config import Config
import json
import logging

logger = logging.getLogger(__name__)


class DeidentificationManager:
    """
    Centralized deidentification logic with audit logging.
    """

    def __init__(self, secret_key: str):
        self.secret = secret_key.encode()

    @staticmethod
    def _hmac_hash(secret: bytes, value: str) -> str:
        """
        Generate HMAC-SHA256 hash (one-way, non-reversible).
        Key-based, so rainbow tables are useless.
        """
        return hmac.new(
            secret,
            value.encode(),
            hashlib.sha256
        ).hexdigest()

    def generate_anon_id(self, email: str) -> str:
        """
        Stable, non-reversible anonymous ID.
        Same email always produces same anon_id.
        Different people can't collide (email uniqueness).
        """
        return self._hmac_hash(self.secret, email)

    @staticmethod
    def fingerprint_name(name: str) -> str:
        """
        Weak fingerprint for internal reference only.
        Non-reversible, weak collision resistance.
        DO NOT use this as sole identifier.
        """
        normalized = name.lower().strip()
        return hashlib.sha1(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def signup_cohort(created_at: datetime) -> str:
        """
        Temporal bucketing for privacy.
        Prevents exact reidentification via signup time.
        Granularity: Month-Year (e.g., '2025-01')
        """
        return created_at.strftime("%Y-%m")

    def deidentify_member(self, member_raw) -> dict:
        """
        MASTER FUNCTION: Convert raw member to deidentified profile.

        Args:
            member_raw: MemberRaw instance

        Returns:
            dict with deidentified attributes
        """
        anon_id = self.generate_anon_id(member_raw.email)
        name_fp = self.fingerprint_name(member_raw.full_name)
        cohort = self.signup_cohort(member_raw.created_at)

        result = {
            "anon_id": anon_id,
            "name_fingerprint": name_fp,
            "signup_cohort": cohort,
        }

        logger.info(f"Deidentified member {member_raw.id} → anon_id: {anon_id[:8]}...")

        return result

    def log_audit(self, action: str, source_id: int = None, anon_id: str = None, details: dict = None):
        """
        Log deidentification actions for compliance.
        Never logs PII.
        """
        from models import AuditLog
        from db import get_db_session

        try:
            log_entry = AuditLog(
                action=action,
                source_member_id=source_id,
                anon_id=anon_id,
                details=json.dumps(details) if details else None
            )
            session = get_db_session()
            session.add(log_entry)
            session.commit()
            logger.info(f"Audit log: {action}")
        except Exception as e:
            logger.error(f"Failed to log audit: {e}")


# Global instance
deidentifier = None


def init_deidentifier(secret_key: str):
    """Initialize the deidentification manager"""
    global deidentifier
    deidentifier = DeidentificationManager(secret_key)
    return deidentifier


def get_deidentifier() -> DeidentificationManager:
    """Get the global deidentifier instance"""
    if not deidentifier:
        raise RuntimeError("Deidentifier not initialized. Call init_deidentifier() first.")
    return deidentifier