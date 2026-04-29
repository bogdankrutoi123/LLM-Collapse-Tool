from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import UserResponse, UserCreate, UserUpdate
from app.services.user_service import UserService
from app.api.dependencies import get_admin_user
from app.models.database import User, UserRole
from app.services.audit_service import AuditService

router = APIRouter(prefix="/users", tags=["Users"])


def _to_dict(obj):
    data = obj.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data


@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """List users (admin only)."""
    return UserService.get_users(db, skip=skip, limit=limit, role=role, is_active=is_active)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Get user by ID."""
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Create user (admin only)."""
    if UserService.get_user_by_username(db, user.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    if UserService.get_user_by_email(db, user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    db_user = UserService.create_user(db, user)
    AuditService.log(db, current_user.id, "create", "user", db_user.id, None, _to_dict(db_user))
    return db_user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Update user (admin only)."""
    existing = UserService.get_user_by_id(db, user_id)
    old_value = _to_dict(existing) if existing else None
    updated = UserService.update_user(db, user_id, user_update)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    AuditService.log(db, current_user.id, "update", "user", updated.id, old_value, _to_dict(updated))
    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Delete user (admin only)."""
    existing = UserService.get_user_by_id(db, user_id)
    if not UserService.delete_user(db, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    AuditService.log(db, current_user.id, "delete", "user", user_id, _to_dict(existing) if existing else None, None)
