from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import AlertThresholdResponse, AlertThresholdCreate, AlertThresholdUpdate
from app.services.notification_service import AlertThresholdService
from app.api.dependencies import get_admin_user
from app.models.database import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/thresholds", tags=["Alert Thresholds"])


def _to_dict(obj):
    data = obj.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data


@router.get("/", response_model=List[AlertThresholdResponse])
def list_thresholds(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """List alert thresholds."""
    return AlertThresholdService.get_thresholds(db, skip=skip, limit=limit, is_active=is_active)


@router.get("/{threshold_id}", response_model=AlertThresholdResponse)
def get_threshold(
    threshold_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Get threshold by ID."""
    threshold = AlertThresholdService.get_threshold_by_id(db, threshold_id)
    if not threshold:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found")
    return threshold


@router.post("/", response_model=AlertThresholdResponse, status_code=status.HTTP_201_CREATED)
def create_threshold(
    threshold: AlertThresholdCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Create alert threshold."""
    created = AlertThresholdService.create_threshold(db, threshold.model_dump())
    AuditService.log(db, current_user.id, "create", "alert_threshold", created.id, None, _to_dict(created))
    return created


@router.put("/{threshold_id}", response_model=AlertThresholdResponse)
def update_threshold(
    threshold_id: int,
    threshold_update: AlertThresholdUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Update alert threshold."""
    existing = AlertThresholdService.get_threshold_by_id(db, threshold_id)
    old_value = _to_dict(existing) if existing else None
    updated = AlertThresholdService.update_threshold(db, threshold_id, threshold_update.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found")
    AuditService.log(db, current_user.id, "update", "alert_threshold", updated.id, old_value, _to_dict(updated))
    return updated


@router.delete("/{threshold_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_threshold(
    threshold_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Delete alert threshold."""
    existing = AlertThresholdService.get_threshold_by_id(db, threshold_id)
    if not AlertThresholdService.delete_threshold(db, threshold_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Threshold not found")
    AuditService.log(db, current_user.id, "delete", "alert_threshold", threshold_id, _to_dict(existing) if existing else None, None)
