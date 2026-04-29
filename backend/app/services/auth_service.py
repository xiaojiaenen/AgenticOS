from __future__ import annotations

from datetime import timedelta
from math import ceil
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timezone import app_now
from app.db.models import AuthRateLimitModel, AuthSessionModel, UserModel


class AuthError(ValueError):
    pass


class AuthRateLimitError(AuthError):
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

    def _create_token(self, user: UserModel, session_id: str) -> str:
        return create_access_token(
            {"sub": str(user.id), "email": user.email, "role": user.role, "sid": session_id},
            secret=self.settings.auth_secret_key,
            expires_in_seconds=self.settings.auth_token_expire_minutes * 60,
        )

    def _issue_session(self, user: UserModel) -> str:
        now = app_now()
        session_id = uuid4().hex
        self.db.add(
            AuthSessionModel(
                session_id=session_id,
                user_id=user.id,
                expires_at=now + timedelta(minutes=self.settings.auth_token_expire_minutes),
                created_at=now,
                last_seen_at=now,
            )
        )
        self.db.commit()
        return session_id

    def _auth_response(self, user: UserModel) -> dict[str, object]:
        session_id = self._issue_session(user)
        return {
            "access_token": self._create_token(user, session_id),
            "token_type": "bearer",
            "user": self._public_user(user),
        }

    def _rate_limit_window(self) -> timedelta:
        return timedelta(seconds=self.settings.auth_rate_limit_window_seconds)

    def _rate_limit_block(self) -> timedelta:
        return timedelta(seconds=self.settings.auth_rate_limit_block_seconds)

    def _normalize_rate_limit_row(self, row: AuthRateLimitModel, *, now) -> AuthRateLimitModel:
        if row.blocked_until is not None and row.blocked_until <= now:
            row.blocked_until = None
        if now - row.window_started_at >= self._rate_limit_window():
            row.attempts = 0
            row.window_started_at = now
            row.blocked_until = None
        return row

    def _rate_limit_key(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> str:
        normalized_ip = (client_ip or "unknown").strip().lower() or "unknown"
        if scope == "login":
            normalized_email = (email or "").strip().lower()
            return f"{scope}:{normalized_email}:{normalized_ip}"
        return f"{scope}:{normalized_ip}"

    def _assert_rate_limit_allowed(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> None:
        key = self._rate_limit_key(scope, email=email, client_ip=client_ip)
        row = self.db.get(AuthRateLimitModel, key)
        if row is None:
            return

        now = app_now()
        row = self._normalize_rate_limit_row(row, now=now)
        if row.blocked_until is not None and row.blocked_until > now:
            remaining_seconds = max(1, int((row.blocked_until - now).total_seconds()))
            remaining_minutes = ceil(remaining_seconds / 60)
            self.db.add(row)
            self.db.commit()
            raise AuthRateLimitError(f"Too many attempts, please retry in {remaining_minutes} minute(s)")

        self.db.add(row)
        self.db.commit()

    def _record_failed_attempt(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> None:
        key = self._rate_limit_key(scope, email=email, client_ip=client_ip)
        now = app_now()
        row = self.db.get(AuthRateLimitModel, key)
        if row is None:
            row = AuthRateLimitModel(
                key=key,
                scope=scope,
                attempts=0,
                window_started_at=now,
            )
        else:
            row = self._normalize_rate_limit_row(row, now=now)

        row.attempts += 1
        row.updated_at = now
        if row.attempts >= self.settings.auth_rate_limit_max_attempts:
            row.blocked_until = now + self._rate_limit_block()
        self.db.add(row)
        self.db.commit()

    def _clear_rate_limit(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> None:
        key = self._rate_limit_key(scope, email=email, client_ip=client_ip)
        self.db.execute(delete(AuthRateLimitModel).where(AuthRateLimitModel.key == key))
        self.db.commit()

    def register(self, *, email: str, name: str, password: str, client_ip: str | None = None) -> dict[str, object]:
        normalized_email = email.strip().lower()
        self._assert_rate_limit_allowed("register", email=normalized_email, client_ip=client_ip)
        existing = self.db.scalar(select(UserModel).where(UserModel.email == email))
        if existing is not None:
            self._record_failed_attempt("register", email=normalized_email, client_ip=client_ip)
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
        self._clear_rate_limit("register", email=normalized_email, client_ip=client_ip)
        return self._auth_response(user)

    def login(self, *, email: str, password: str, client_ip: str | None = None) -> dict[str, object]:
        normalized_email = email.strip().lower()
        self._assert_rate_limit_allowed("login", email=normalized_email, client_ip=client_ip)
        user = self.db.scalar(select(UserModel).where(UserModel.email == email))
        if user is None or not verify_password(password, user.password_hash):
            self._record_failed_attempt("login", email=normalized_email, client_ip=client_ip)
            raise AuthError("Invalid email or password")
        if not user.is_active:
            self._record_failed_attempt("login", email=normalized_email, client_ip=client_ip)
            raise AuthError("User is disabled")
        self._clear_rate_limit("login", email=normalized_email, client_ip=client_ip)
        return self._auth_response(user)

    def get_user(self, user_id: int) -> UserModel | None:
        return self.db.get(UserModel, user_id)

    def is_session_active(self, user_id: int, session_id: str) -> bool:
        row = self.db.get(AuthSessionModel, session_id)
        if row is None or row.user_id != user_id:
            return False
        now = app_now()
        if row.revoked_at is not None or row.expires_at <= now:
            return False
        return True

    def revoke_session(self, session_id: str) -> None:
        row = self.db.get(AuthSessionModel, session_id)
        if row is None or row.revoked_at is not None:
            return
        row.revoked_at = app_now()
        self.db.add(row)
        self.db.commit()
