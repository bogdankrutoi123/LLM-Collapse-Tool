from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import os
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
from app.models.database import Model, ModelVersion, ModelStatus
from app.schemas.schemas import ModelCreate, ModelUpdate, ModelVersionCreate, ModelVersionUpdate
from app.core.config import get_settings


class ModelService:
    """Service for model management operations."""
    
    @staticmethod
    def get_model_by_id(db: Session, model_id: int) -> Optional[Model]:
        """Get model by ID."""
        return db.query(Model).filter(Model.id == model_id).first()
    
    @staticmethod
    def get_model_by_name(db: Session, name: str) -> Optional[Model]:
        """Get model by name."""
        return db.query(Model).filter(Model.name == name).first()
    
    @staticmethod
    def get_models(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ModelStatus] = None
    ) -> List[Model]:
        """Get list of models with filters."""
        query = db.query(Model)
        
        if status:
            query = query.filter(Model.status == status)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create_model(db: Session, model: ModelCreate) -> Model:
        """Create new model."""
        db_model = Model(
            name=model.name,
            description=model.description,
            source=model.source,
            status=model.status
        )
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model
    
    @staticmethod
    def update_model(db: Session, model_id: int, model_update: ModelUpdate) -> Optional[Model]:
        """Update model."""
        db_model = db.query(Model).filter(Model.id == model_id).first()
        if not db_model:
            return None
        
        update_data = model_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_model, field, value)
        
        db.commit()
        db.refresh(db_model)
        return db_model
    
    @staticmethod
    def delete_model(db: Session, model_id: int) -> bool:
        """Delete model."""
        db_model = db.query(Model).filter(Model.id == model_id).first()
        if not db_model:
            return False
        
        db.delete(db_model)
        db.commit()
        return True


class ModelVersionService:
    """Service for model version operations."""
    
    @staticmethod
    def get_version_by_id(db: Session, version_id: int) -> Optional[ModelVersion]:
        """Get version by ID."""
        return db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
    
    @staticmethod
    def get_versions_by_model(
        db: Session,
        model_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[ModelVersion]:
        """Get versions for a model."""
        return db.query(ModelVersion).filter(
            ModelVersion.model_id == model_id
        ).order_by(ModelVersion.deployment_date.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_current_version(db: Session, model_id: int) -> Optional[ModelVersion]:
        """Get current active version of a model."""
        return db.query(ModelVersion).filter(
            ModelVersion.model_id == model_id,
            ModelVersion.is_current == True
        ).first()
    
    @staticmethod
    def create_version(db: Session, version: ModelVersionCreate) -> ModelVersion:
        """Create new model version."""
        if hasattr(version, 'is_current') and version.is_current:
            db.query(ModelVersion).filter(
                ModelVersion.model_id == version.model_id,
                ModelVersion.is_current == True
            ).update({"is_current": False})
        
        db_version = ModelVersion(
            model_id=version.model_id,
            version=version.version,
            description=version.description,
            previous_version_id=version.previous_version_id,
            model_metadata=version.model_metadata,
            weights_path=version.weights_path,
            is_current=getattr(version, 'is_current', False)
        )
        db.add(db_version)
        db.commit()
        db.refresh(db_version)
        return db_version
    
    @staticmethod
    def update_version(
        db: Session,
        version_id: int,
        version_update: ModelVersionUpdate
    ) -> Optional[ModelVersion]:
        """Update model version."""
        db_version = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
        if not db_version:
            return None
        
        update_data = version_update.model_dump(exclude_unset=True)
        
        if 'is_current' in update_data and update_data['is_current']:
            db.query(ModelVersion).filter(
                ModelVersion.model_id == db_version.model_id,
                ModelVersion.is_current == True,
                ModelVersion.id != version_id
            ).update({"is_current": False})
        
        for field, value in update_data.items():
            setattr(db_version, field, value)
        
        db.commit()
        db.refresh(db_version)
        return db_version
    
    @staticmethod
    def delete_version(db: Session, version_id: int) -> bool:
        """Delete model version."""
        db_version = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
        if not db_version:
            return False
        
        db.delete(db_version)
        db.commit()
        return True
    
    @staticmethod
    def get_version_history(db: Session, version_id: int) -> List[ModelVersion]:
        """Get version history chain."""
        versions = []
        current = ModelVersionService.get_version_by_id(db, version_id)
        
        while current:
            versions.append(current)
            if current.previous_version_id:
                current = ModelVersionService.get_version_by_id(db, current.previous_version_id)
            else:
                break
        
        return versions

    @staticmethod
    def validate_model_runtime_compatibility(
        model_source: Optional[str],
        model_metadata: Optional[dict],
        weights_path: Optional[str],
    ) -> None:
        """Validate that model source has usable tokenizer and causal-LM-compatible config."""
        model_id: Optional[str] = None
        if model_metadata and isinstance(model_metadata, dict):
            model_id = model_metadata.get("hf_model_id")
        if not model_id and model_source and model_source.startswith("hf:"):
            model_id = model_source.replace("hf:", "", 1)

        source = (weights_path or model_id or "").strip()
        if not source:
            raise ValueError("Provide either weights_path or hf_model_id/model source (hf:...).")

        settings = get_settings()
        hf_token = settings.HUGGINGFACE_HUB_TOKEN or None
        if hf_token:
            os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", hf_token)
            os.environ.setdefault("HF_TOKEN", hf_token)

        use_local = bool(weights_path and weights_path.strip())
        token = None if use_local else hf_token
        if use_local:
            path = Path(source).expanduser()
            if not path.exists():
                raise ValueError(f"Local weights_path does not exist: {weights_path}")
            source = str(path)

        try:
            AutoTokenizer.from_pretrained(
                source,
                use_fast=False,
                trust_remote_code=True,
                token=token,
            )
        except Exception as exc:
            raise ValueError(f"Tokenizer is not available/compatible for source '{source}': {exc}") from exc

        try:
            config = AutoConfig.from_pretrained(
                source,
                trust_remote_code=True,
                token=token,
            )
            if type(config) not in AutoModelForCausalLM._model_mapping:
                raise ValueError(
                    f"Model config '{type(config).__name__}' is not supported by AutoModelForCausalLM."
                )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Model config is not readable/compatible for source '{source}': {exc}") from exc
