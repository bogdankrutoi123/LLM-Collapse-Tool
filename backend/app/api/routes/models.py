from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import (
    ModelCreate, ModelUpdate, ModelResponse,
    ModelVersionCreate, ModelVersionUpdate, ModelVersionResponse
)
from app.services.model_service import ModelService, ModelVersionService
from app.api.dependencies import get_current_user, get_engineer_or_admin
from app.models.database import User, ModelStatus
from app.services.audit_service import AuditService

router = APIRouter(prefix="/models", tags=["Models"])


def _to_dict(obj):
    data = obj.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data


@router.get("/", response_model=List[ModelResponse])
def list_models(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[ModelStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of models."""
    models = ModelService.get_models(db, skip=skip, limit=limit, status=status)
    return models


@router.get("/{model_id}", response_model=ModelResponse)
def get_model(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get model by ID."""
    model = ModelService.get_model_by_id(db, model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    return model


@router.post("/", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
def create_model(
    model: ModelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Create a new model."""
    existing = ModelService.get_model_by_name(db, model.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model with this name already exists"
        )
    
    db_model = ModelService.create_model(db, model)
    AuditService.log(db, current_user.id, "create", "model", db_model.id, None, _to_dict(db_model))
    return db_model


@router.put("/{model_id}", response_model=ModelResponse)
def update_model(
    model_id: int,
    model_update: ModelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Update a model."""
    existing = ModelService.get_model_by_id(db, model_id)
    old_value = _to_dict(existing) if existing else None
    db_model = ModelService.update_model(db, model_id, model_update)
    if not db_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    AuditService.log(db, current_user.id, "update", "model", db_model.id, old_value, _to_dict(db_model))
    return db_model


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Delete a model."""
    existing = ModelService.get_model_by_id(db, model_id)
    if not ModelService.delete_model(db, model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    AuditService.log(db, current_user.id, "delete", "model", model_id, _to_dict(existing) if existing else None, None)


@router.get("/{model_id}/versions", response_model=List[ModelVersionResponse])
def list_model_versions(
    model_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get versions for a model."""
    model = ModelService.get_model_by_id(db, model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    
    versions = ModelVersionService.get_versions_by_model(db, model_id, skip, limit)
    return versions


@router.get("/{model_id}/versions/current", response_model=ModelVersionResponse)
def get_current_version(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current active version of a model."""
    version = ModelVersionService.get_current_version(db, model_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No current version found for this model"
        )
    return version


@router.post("/{model_id}/versions", response_model=ModelVersionResponse, status_code=status.HTTP_201_CREATED)
def create_model_version(
    model_id: int,
    version: ModelVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Create a new version for a model."""
    model = ModelService.get_model_by_id(db, model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    
    if version.model_id != model_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model ID mismatch"
        )

    try:
        ModelVersionService.validate_model_runtime_compatibility(
            model_source=model.source,
            model_metadata=version.model_metadata,
            weights_path=version.weights_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    
    db_version = ModelVersionService.create_version(db, version)
    AuditService.log(db, current_user.id, "create", "model_version", db_version.id, None, _to_dict(db_version))
    return db_version


@router.get("/versions/{version_id}", response_model=ModelVersionResponse)
def get_model_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get version by ID."""
    version = ModelVersionService.get_version_by_id(db, version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found"
        )
    return version


@router.put("/versions/{version_id}", response_model=ModelVersionResponse)
def update_model_version(
    version_id: int,
    version_update: ModelVersionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Update a model version."""
    existing = ModelVersionService.get_version_by_id(db, version_id)
    old_value = _to_dict(existing) if existing else None
    if existing:
        parent_model = ModelService.get_model_by_id(db, existing.model_id)
    else:
        parent_model = None

    if existing and parent_model:
        update_data = version_update.model_dump(exclude_unset=True)
        merged_metadata = update_data.get("model_metadata", existing.model_metadata)
        merged_weights_path = update_data.get("weights_path", existing.weights_path)
        try:
            ModelVersionService.validate_model_runtime_compatibility(
                model_source=parent_model.source,
                model_metadata=merged_metadata,
                weights_path=merged_weights_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db_version = ModelVersionService.update_version(db, version_id, version_update)
    if not db_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found"
        )
    AuditService.log(db, current_user.id, "update", "model_version", db_version.id, old_value, _to_dict(db_version))
    return db_version


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_engineer_or_admin)
):
    """Delete a model version."""
    existing = ModelVersionService.get_version_by_id(db, version_id)
    if not ModelVersionService.delete_version(db, version_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found"
        )
    AuditService.log(db, current_user.id, "delete", "model_version", version_id, _to_dict(existing) if existing else None, None)


@router.get("/versions/{version_id}/history", response_model=List[ModelVersionResponse])
def get_version_history(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get version history chain."""
    history = ModelVersionService.get_version_history(db, version_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found"
        )
    return history
