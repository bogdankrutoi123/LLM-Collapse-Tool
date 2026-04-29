from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import CollapseEventResponse
from app.api.dependencies import get_current_user
from app.models.database import User, CollapseEvent

router = APIRouter(prefix="/collapse-events", tags=["Collapse Events"])


@router.get("/", response_model=List[CollapseEventResponse])
def list_collapse_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    model_version_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CollapseEvent)
    if model_version_id:
        query = query.filter(CollapseEvent.model_version_id == model_version_id)
    return query.order_by(CollapseEvent.created_at.desc()).offset(skip).limit(limit).all()
