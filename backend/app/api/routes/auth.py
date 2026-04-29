import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.schemas import LoginRequest, Token, UserCreate, UserResponse, RefreshTokenRequest, AuthBootstrapStatus, BootstrapAdminRequest
from app.services.user_service import UserService
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.config import get_settings
from app.services.audit_service import AuditService
from app.api.dependencies import get_current_user
from app.models.database import User, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    kw = dict(httponly=True, secure=settings.COOKIE_SECURE,
              samesite=settings.COOKIE_SAMESITE,
              domain=settings.COOKIE_DOMAIN or None)
    response.set_cookie(settings.ACCESS_COOKIE_NAME, access_token, path="/", **kw)
    response.set_cookie(settings.REFRESH_COOKIE_NAME, refresh_token, path="/api/v1/auth", **kw)


def _clear_auth_cookies(response: Response) -> None:
    kw = dict(domain=settings.COOKIE_DOMAIN or None)
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/", **kw)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth", **kw)


def _bootstrap_admin_available(db: Session) -> bool:
    return bool(settings.BOOTSTRAP_ADMIN_TOKEN) and not UserService.has_admin_user(db)


@router.get("/bootstrap-status", response_model=AuthBootstrapStatus)
def bootstrap_status(db: Session = Depends(get_db)):
    has_admin = UserService.has_admin_user(db)
    return {
        "has_admin": has_admin,
        "public_registration_enabled": settings.PUBLIC_REGISTRATION_ENABLED,
        "bootstrap_admin_available": bool(settings.BOOTSTRAP_ADMIN_TOKEN) and not has_admin,
    }


@router.post("/bootstrap-admin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_admin(payload: BootstrapAdminRequest, db: Session = Depends(get_db)):
    if UserService.has_admin_user(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Admin account already exists")
    if not settings.BOOTSTRAP_ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Bootstrap admin is not configured")
    if not secrets.compare_digest(payload.bootstrap_token, settings.BOOTSTRAP_ADMIN_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid bootstrap token")
    if UserService.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Username already registered")
    if UserService.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Email already registered")

    admin_user = UserService.create_user(db, UserCreate(
        email=payload.email, username=payload.username,
        full_name=payload.full_name, password=payload.password,
        role=UserRole.ADMIN,
    ))
    AuditService.log(db, admin_user.id, "bootstrap_admin", "user", admin_user.id,
                     None, {"username": admin_user.username})
    return admin_user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if not settings.PUBLIC_REGISTRATION_ENABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Public registration is disabled")
    if UserService.get_user_by_username(db, user.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Username already registered")
    if UserService.get_user_by_email(db, user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Email already registered")

    user = user.model_copy(update={"role": UserRole.OPERATOR})
    db_user = UserService.create_user(db, user)
    AuditService.log(db, db_user.id, "register", "user", db_user.id, None,
                     {"username": db_user.username})
    return db_user


@router.post("/login", response_model=UserResponse)
def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = UserService.authenticate_user(db, login_data.username, login_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})

    access_token  = create_access_token(data={"user_id": user.id, "username": user.username})
    refresh_token = create_refresh_token(data={"user_id": user.id, "username": user.username})
    _set_auth_cookies(response, access_token, refresh_token)

    AuditService.log(db, user.id, "login", "user", user.id, None, {"username": user.username})
    return user


@router.post("/refresh", response_model=UserResponse)
def refresh_token(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = None,
    db: Session = Depends(get_db),
):
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw and payload:
        raw = payload.refresh_token

    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing refresh token")

    decoded = decode_token(raw)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid refresh token")

    user_id = decoded.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid refresh token payload")

    user = UserService.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found or inactive")

    new_access  = create_access_token(data={"user_id": user.id, "username": user.username})
    new_refresh = create_refresh_token(data={"user_id": user.id, "username": user.username})
    _set_auth_cookies(response, new_access, new_refresh)

    AuditService.log(db, user.id, "refresh", "user", user.id, None, {"username": user.username})
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
