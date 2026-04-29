from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from io import BytesIO
import pandas as pd
import json

from fastapi.responses import FileResponse
from app.db.session import get_db
from app.schemas.schemas import ExportRequest, ModelImport, ModelVersionImport, PromptImport, PromptMetricImport
from app.api.dependencies import get_engineer_or_admin
from app.models.database import Model, ModelVersion, Prompt, PromptMetric, User
from app.core.config import get_settings
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.schemas.schemas import NotificationCreate

router = APIRouter(prefix="/data", tags=["Import/Export"])
settings = get_settings()


def _ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/export")
def export_data(
    request: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Export data to CSV/JSON and return as file."""
    export_dir = _ensure_dir(settings.EXPORT_DIR)
    entity = request.entity_type

    if entity == "models":
        query = db.query(Model)
    elif entity == "versions":
        query = db.query(ModelVersion)
        if request.model_id:
            query = query.filter(ModelVersion.model_id == request.model_id)
    elif entity == "prompts":
        query = db.query(Prompt)
        if request.version_id:
            query = query.filter(Prompt.model_version_id == request.version_id)
        if request.date_from:
            query = query.filter(Prompt.submitted_at >= request.date_from)
        if request.date_to:
            query = query.filter(Prompt.submitted_at <= request.date_to)
    elif entity == "metrics":
        query = db.query(PromptMetric)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported entity type")

    rows = [row.__dict__ for row in query.all()]
    for row in rows:
        row.pop("_sa_instance_state", None)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{entity}_{timestamp}.{request.format}"
    file_path = export_dir / filename

    if request.format == "csv":
        pd.DataFrame(rows).to_csv(file_path, index=False)
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, default=str, indent=2)

    AuditService.log(
        db,
        current_user.id,
        "export",
        entity,
        None,
        None,
        {"format": request.format, "filename": filename}
    )

    return FileResponse(path=file_path, filename=filename)


@router.post("/import")
def import_data(
    entity_type: str = Query(..., pattern="^(models|versions|prompts|metrics)$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Import data from CSV/JSON."""
    if file.content_type not in {"text/csv", "application/json", "application/octet-stream"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    content = file.file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
            data = df.to_dict(orient="records")
        else:
            data = json.loads(content.decode("utf-8"))
            if not isinstance(data, list):
                raise ValueError("JSON must be an array of records")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse file: {exc}")

    created = 0
    errors = []

    def validate_record(idx: int, record: dict):
        try:
            if entity_type == "models":
                return ModelImport.model_validate(record).model_dump()
            if entity_type == "versions":
                return ModelVersionImport.model_validate(record).model_dump()
            if entity_type == "prompts":
                return PromptImport.model_validate(record).model_dump()
            if entity_type == "metrics":
                return PromptMetricImport.model_validate(record).model_dump()
            return None
        except Exception as exc:
            errors.append({"index": idx, "error": str(exc)})
            return None

    validated_records = []
    for idx, record in enumerate(data):
        validated = validate_record(idx, record)
        if validated is not None:
            validated_records.append(validated)

    if errors:
        NotificationService.create_notification(
            db,
            notification=NotificationCreate(
                title="Import validation failed",
                message=f"Import failed with {len(errors)} errors.",
                severity="error",
                recipients=None
            ),
            created_by_id=current_user.id
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errors})

    for record in validated_records:
        if entity_type == "models":
            db.add(Model(**record))
        elif entity_type == "versions":
            db.add(ModelVersion(**record))
        elif entity_type == "prompts":
            db.add(Prompt(**record))
        elif entity_type == "metrics":
            db.add(PromptMetric(**record))
        created += 1

    db.commit()
    AuditService.log(
        db,
        current_user.id,
        "import",
        entity_type,
        None,
        None,
        {"imported": created, "filename": file.filename}
    )
    return {"status": "ok", "imported": created}
