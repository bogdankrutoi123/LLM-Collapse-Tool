from sqlalchemy.orm import Session
from typing import Optional, Any
from datetime import datetime, date
from app.models.database import AuditLog


class AuditService:
    """Service for audit logging."""

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: AuditService._json_safe(val) for key, val in value.items()}
        if isinstance(value, list):
            return [AuditService._json_safe(item) for item in value]
        return value

    @staticmethod
    def log(
        db: Session,
        user_id: Optional[int],
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=AuditService._json_safe(old_value) if old_value is not None else None,
            new_value=AuditService._json_safe(new_value) if new_value is not None else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
