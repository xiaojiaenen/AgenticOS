from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import Settings, get_settings
from app.db.models import UserModel
from app.schemas.auth import AuthLoginRequest, AuthRegisterRequest, AuthResponse, UserPublic
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _to_public(user: UserModel) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: AuthRegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return AuthService(db, settings).register(
            email=request.email,
            name=request.name,
            password=request.password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/login", response_model=AuthResponse)
def login(
    request: AuthLoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return AuthService(db, settings).login(email=request.email, password=request.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/me", response_model=UserPublic)
def me(user: UserModel = Depends(get_current_user)) -> UserPublic:
    return _to_public(user)


@router.post("/logout")
def logout() -> dict[str, bool]:
    return {"ok": True}
