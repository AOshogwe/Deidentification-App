"""
app/deidentify.py
Core deidentification logic with audit logging
"""

import hmac
import hashlib
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class DeidentificationManager:
    """
    Centralized deidentification logic with audit logging.
    Generates stable, non-reversible anonymous IDs from email addresses.
    """

    def __init__(self, secret_key: str):
        """
        Initialize with HMAC secret key

        Args:
            secret_key: Secret for HMAC hashing (from environment variable)
        """
        if not secret_key:
            raise ValueError("Secret key cannot be empty")
        self.secret = secret_key.encode()

    @staticmethod
    def _hmac_hash(secret: bytes, value: str) -> str:
        """
        Generate HMAC-SHA256 hash (one-way, non-reversible).
        Key-based, so rainbow tables are useless.

        Args:
            secret: Secret key as bytes
            value: Value to hash

        Returns:
            Hexadecimal hash string
        """
        return hmac.new(
            secret,
            value.encode(),
            hashlib.sha256
        ).hexdigest()

    def generate_anon_id(self, email: str) -> str:
        """
        Stable, non-reversible anonymous ID from email.

        Same email always produces same anon_id (deterministic).
        Different people can't collide (email uniqueness).

        Args:
            email: User's email address

        Returns:
            64-character hex string (HMAC-SHA256)
        """
        if not email:
            raise ValueError("Email cannot be empty")
        return self._hmac_hash(self.secret, email.lower().strip())

    @staticmethod
    def fingerprint_name(name: str) -> str:
        """
        Weak fingerprint for internal reference only.
        Non-reversible, weak collision resistance.
        DO NOT use this as sole identifier.

        Args:
            name: User's full name

        Returns:
            16-character hex string (SHA1 truncated)
        """
        if not name:
            return "unknown"
        normalized = name.lower().strip()
        return hashlib.sha1(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def signup_cohort(created_at: datetime) -> str:
        """
        Temporal bucketing for privacy.
        Prevents exact reidentification via signup time.
        Granularity: Month-Year (e.g., '2025-01')

        Args:
            created_at: User signup datetime

        Returns:
            String in format 'YYYY-MM'
        """
        if not created_at:
            created_at = datetime.utcnow()
        return created_at.strftime("%Y-%m")

    def deidentify_member(self, member_raw) -> dict:
        """
        MASTER FUNCTION: Convert raw member to deidentified profile.

        This is the main function you call to deidentify a member.

        Args:
            member_raw: MemberRaw ORM instance with: id, email, full_name, created_at

        Returns:
            dict with deidentified attributes:
            {
                "anon_id": "a7f3d0c8...",  # 64-char hash
                "name_fingerprint": "b1c9d2e3f4g5h6i7",  # 16-char hash
                "signup_cohort": "2025-01"  # Month-year
            }
        """
        if not member_raw:
            raise ValueError("member_raw cannot be None")

        anon_id = self.generate_anon_id(member_raw.email)
        name_fp = self.fingerprint_name(member_raw.full_name)
        cohort = self.signup_cohort(member_raw.created_at)

        result = {
            "anon_id": anon_id,
            "name_fingerprint": name_fp,
            "signup_cohort": cohort,
        }

        logger.info(f"✓ Deidentified member {member_raw.id} → anon_id: {anon_id[:8]}...")

        return result

    def log_audit(self, action: str, source_id: int = None, anon_id: str = None, details: dict = None):
        """
        Log deidentification actions for compliance.
        Never logs PII.

        Args:
            action: Action name (e.g., 'deidentified', 'batch_deidentified', 'key_rotated')
            source_id: Original member ID (from members_raw table)
            anon_id: Anonymous ID (from members_deidentified table)
            details: Additional metadata as dict (will be JSON-serialized)
        """
        # Import here to avoid circular imports
        from app.models import AuditLog
        from app.db import db

        try:
            log_entry = AuditLog(
                action=action,
                source_member_id=source_id,
                anon_id=anon_id,
                details=json.dumps(details) if details else None
            )
            db.session.add(log_entry)
            db.session.commit()
            logger.info(f"✓ Audit log: {action}")
        except Exception as e:
            logger.error(f"❌ Failed to log audit: {e}")


# Global instance (singleton pattern)
deidentifier = None


def init_deidentifier(secret_key: str):
    """
    Initialize the global deidentification manager

    Call this once during app startup.

    Args:
        secret_key: Secret key from environment variable DEIDENTIFICATION_SECRET

    Returns:
        DeidentificationManager instance
    """
    global deidentifier
    try:
        deidentifier = DeidentificationManager(secret_key)
        logger.info("✓ Deidentifier initialized")
        return deidentifier
    except Exception as e:
        logger.error(f"❌ Failed to initialize deidentifier: {e}")
        raise


def get_deidentifier() -> DeidentificationManager:
    """
    Get the global deidentifier instance

    Use this to access deidentification functions anywhere in the app.

    Returns:
        DeidentificationManager instance

    Raises:
        RuntimeError: If deidentifier not yet initialized
    """
    global deidentifier
    if not deidentifier:
        raise RuntimeError("Deidentifier not initialized. Call init_deidentifier() first.")
    return deidentifier