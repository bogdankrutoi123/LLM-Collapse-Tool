from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import NotificationResponse, NotificationUpdate, NotificationCreate
from app.services.notification_service import NotificationService
from app.api.dependencies import get_current_user, get_admin_user
from app.models.database import User, NotificationStatus
from app.services.audit_service import AuditService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _to_dict(obj):
    data = obj.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data


@router.get("/", response_model=List[NotificationResponse])
def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[NotificationStatus] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List notifications."""
    return NotificationService.get_notifications(db, skip=skip, limit=limit, status=status, severity=severity)


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get notification by ID."""
    notification = NotificationService.get_notification_by_id(db, notification_id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.post("/", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(
    notification: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Create notification manually (admin)."""
    created = NotificationService.create_notification(db, notification, created_by_id=current_user.id)
    AuditService.log(db, current_user.id, "create", "notification", created.id, None, _to_dict(created))
    return created


@router.put("/{notification_id}", response_model=NotificationResponse)
def update_notification(
    notification_id: int,
    notification_update: NotificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update notification status/comment."""
    existing = NotificationService.get_notification_by_id(db, notification_id)
    old_value = _to_dict(existing) if existing else None
    updated = NotificationService.update_notification(
        db,
        notification_id,
        notification_update,
        acknowledged_by=current_user.id
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    AuditService.log(db, current_user.id, "update", "notification", updated.id, old_value, _to_dict(updated))
    return updated


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Delete notification (admin)."""
    existing = NotificationService.get_notification_by_id(db, notification_id)
    if not NotificationService.delete_notification(db, notification_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    AuditService.log(db, current_user.id, "delete", "notification", notification_id, _to_dict(existing) if existing else None, None)
