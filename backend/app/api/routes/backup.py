from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
import json
from datetime import datetime

from app.db.session import get_db
from app.api.dependencies import get_admin_user
from app.core.config import get_settings
from app.schemas.schemas import BackupRestoreRequest
from app.models.database import (
    User, Model, ModelVersion, Prompt, PromptMetric,
    AlertThreshold, AlertRule, AlertRuleItem,
    Notification, AuditLog, SystemSetting, AggregatedMetric, CollapseEvent
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/backup", tags=["Backup"])
settings = get_settings()


def _backup_dir() -> Path:
    path = Path(settings.EXPORT_DIR) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _serialize(query):
    rows = [row.__dict__ for row in query]
    for row in rows:
        row.pop("_sa_instance_state", None)
    return rows


@router.post("/create")
def create_backup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    data = {
        "users": _serialize(db.query(User).all()),
        "models": _serialize(db.query(Model).all()),
        "model_versions": _serialize(db.query(ModelVersion).all()),
        "prompts": _serialize(db.query(Prompt).all()),
        "prompt_metrics": _serialize(db.query(PromptMetric).all()),
        "aggregated_metrics": _serialize(db.query(AggregatedMetric).all()),
        "alert_thresholds": _serialize(db.query(AlertThreshold).all()),
        "alert_rules": _serialize(db.query(AlertRule).all()),
        "alert_rule_items": _serialize(db.query(AlertRuleItem).all()),
        "notifications": _serialize(db.query(Notification).all()),
        "audit_logs": _serialize(db.query(AuditLog).all()),
        "system_settings": _serialize(db.query(SystemSetting).all()),
        "collapse_events": _serialize(db.query(CollapseEvent).all())
    }

    filename = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path = _backup_dir() / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str, indent=2)

    AuditService.log(db, current_user.id, "backup", "system", None, None, {"filename": filename})
    return {"status": "ok", "filename": filename}


@router.get("/list", response_model=List[str])
def list_backups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    path = _backup_dir()
    return sorted([p.name for p in path.glob("backup_*.json")], reverse=True)


@router.post("/restore")
def restore_backup(
    request: BackupRestoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    path = _backup_dir() / request.filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if request.replace:
        db.query(CollapseEvent).delete()
        db.query(AuditLog).delete()
        db.query(Notification).delete()
        db.query(AlertRuleItem).delete()
        db.query(AlertRule).delete()
        db.query(AlertThreshold).delete()
        db.query(AggregatedMetric).delete()
        db.query(PromptMetric).delete()
        db.query(Prompt).delete()
        db.query(ModelVersion).delete()
        db.query(Model).delete()
        db.query(SystemSetting).delete()
        db.query(User).delete()
        db.commit()

    def load(model, records):
        for record in records:
            db.add(model(**record))

    load(User, data.get("users", []))
    load(Model, data.get("models", []))
    load(ModelVersion, data.get("model_versions", []))
    load(Prompt, data.get("prompts", []))
    load(PromptMetric, data.get("prompt_metrics", []))
    load(AggregatedMetric, data.get("aggregated_metrics", []))
    load(AlertThreshold, data.get("alert_thresholds", []))
    load(AlertRule, data.get("alert_rules", []))
    load(AlertRuleItem, data.get("alert_rule_items", []))
    load(Notification, data.get("notifications", []))
    load(AuditLog, data.get("audit_logs", []))
    load(SystemSetting, data.get("system_settings", []))
    load(CollapseEvent, data.get("collapse_events", []))

    db.commit()
    AuditService.log(db, current_user.id, "restore", "system", None, None, {"filename": request.filename, "replace": request.replace})
    return {"status": "ok", "restored": request.filename}
