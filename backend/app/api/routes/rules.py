from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse, AlertRuleItemCreate
from app.services.alert_rule_service import AlertRuleService
from app.api.dependencies import get_admin_user
from app.models.database import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/rules", tags=["Alert Rules"])


def _to_dict(obj):
    data = obj.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data


@router.get("/", response_model=List[AlertRuleResponse])
def list_rules(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    return AlertRuleService.get_rules(db, skip=skip, limit=limit, is_active=is_active)


@router.get("/{rule_id}", response_model=AlertRuleResponse)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    rule = AlertRuleService.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


@router.post("/", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    rule: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    created = AlertRuleService.create_rule(db, rule)
    AuditService.log(db, current_user.id, "create", "alert_rule", created.id, None, _to_dict(created))
    return created


@router.put("/{rule_id}", response_model=AlertRuleResponse)
def update_rule(
    rule_id: int,
    rule_update: AlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    existing = AlertRuleService.get_rule_by_id(db, rule_id)
    old_value = _to_dict(existing) if existing else None
    updated = AlertRuleService.update_rule(db, rule_id, rule_update)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    AuditService.log(db, current_user.id, "update", "alert_rule", updated.id, old_value, _to_dict(updated))
    return updated


@router.put("/{rule_id}/items", response_model=AlertRuleResponse)
def replace_rule_items(
    rule_id: int,
    items: List[AlertRuleItemCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    updated = AlertRuleService.replace_rule_items(
        db,
        rule_id,
        [item.model_dump() for item in items]
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    AuditService.log(db, current_user.id, "update", "alert_rule_items", rule_id, None, {"items": len(items)})
    return updated


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    existing = AlertRuleService.get_rule_by_id(db, rule_id)
    if not AlertRuleService.delete_rule(db, rule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    AuditService.log(db, current_user.id, "delete", "alert_rule", rule_id, _to_dict(existing) if existing else None, None)
