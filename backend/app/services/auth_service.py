from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import UserModel


class AuthError(ValueError):
    pass


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _public_user(self, user: UserModel) -> dict[str, object]:
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active,
        }

    def _create_token(self, user: UserModel) -> str:
        return create_access_token(
            {"sub": str(user.id), "email": user.email, "role": user.role},
            secret=self.settings.auth_secret_key,
            expires_in_seconds=self.settings.auth_token_expire_minutes * 60,
        )

    def _auth_response(self, user: UserModel) -> dict[str, object]:
        return {
            "access_token": self._create_token(user),
            "token_type": "bearer",
            "user": self._public_user(user),
        }

    def register(self, *, email: str, name: str, password: str) -> dict[str, object]:
        existing = self.db.scalar(select(UserModel).where(UserModel.email == email))
        if existing is not None:
            raise AuthError("Email already registered")

        user_count = self.db.scalar(select(func.count(UserModel.id))) or 0
        user = UserModel(
            email=email,
            name=name,
            password_hash=hash_password(password),
            role="admin" if user_count == 0 else "user",
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._auth_response(user)

    def login(self, *, email: str, password: str) -> dict[str, object]:
        user = self.db.scalar(select(UserModel).where(UserModel.email == email))
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")
        if not user.is_active:
            raise AuthError("User is disabled")
        return self._auth_response(user)

    def get_user(self, user_id: int) -> UserModel | None:
        return self.db.get(UserModel, user_id)
