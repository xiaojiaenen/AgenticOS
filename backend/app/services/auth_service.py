from __future__ import annotations

from datetime import timedelta
from math import ceil
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timezone import app_now
from app.db.models import AuthSessionModel, UserModel
from app.services import rate_limiter


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

    # ------------------------------------------------------------------
    # 登录/注册限流：已从 AuthRateLimitModel（MySQL 行级状态机）迁移到
    # app.services.rate_limiter 的 Redis 原子固定窗口实现（INCR+EXPIRE），
    # Redis 不可用时自动降级进程内计数。外部行为（失败计数、达到上限
    # 返回封禁剩余时间、封禁期内直接拒绝、成功后清除）与旧实现等价。
    # ------------------------------------------------------------------

    def _assert_rate_limit_allowed(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> None:
        remaining_seconds = rate_limiter.check_rate_limit(
            self.settings, scope, email=email, client_ip=client_ip
        )
        if remaining_seconds > 0:
            remaining_minutes = ceil(remaining_seconds / 60)
            raise AuthRateLimitError(f"尝试次数过多，请在 {remaining_minutes} 分钟后重试")

    def _record_failed_attempt(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> None:
        rate_limiter.record_failed_attempt(self.settings, scope, email=email, client_ip=client_ip)

    def _clear_rate_limit(self, scope: str, *, email: str | None = None, client_ip: str | None = None) -> None:
        rate_limiter.clear_rate_limit(self.settings, scope, email=email, client_ip=client_ip)

    def register(self, *, email: str, name: str, password: str, client_ip: str | None = None) -> dict[str, object]:
        normalized_email = email.strip().lower()
        self._assert_rate_limit_allowed("register", email=normalized_email, client_ip=client_ip)
        existing = self.db.scalar(select(UserModel).where(func.lower(UserModel.email) == normalized_email))
        if existing is not None:
            self._record_failed_attempt("register", email=normalized_email, client_ip=client_ip)
            raise AuthError("Email already registered")

        # Insert as "user" first to avoid the race condition where two
        # simultaneous registrations both see user_count==0 and both
        # become admin.
        user = UserModel(
            email=email,
            name=name,
            password_hash=hash_password(password),
            role="user",
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            self._record_failed_attempt("register", email=normalized_email, client_ip=client_ip)
            raise AuthError("Email already registered")
        self.db.refresh(user)

        # 仅当系统中尚不存在任何 admin 时，才将本用户提升为 admin。
        # 必须判断“是否存在其他 admin”，而不是“本用户是否已是 admin”
        # （后者对新建用户恒为真，会把每个注册用户都升成管理员）。
        self._maybe_promote_first_admin(user)

        self._clear_rate_limit("register", email=normalized_email, client_ip=client_ip)
        return self._auth_response(user)

    def _maybe_promote_first_admin(self, user: UserModel) -> None:
        """Promote *user* to admin only when no other admin exists yet.

        The check must ask "does any OTHER admin exist?", not "is this user
        already an admin?" — the latter is always true for a freshly inserted
        role=user row and would promote every registration.
        """
        from sqlalchemy import text as sa_text

        # Derived-table wrapper: MySQL rejects UPDATE targets inside subqueries
        # (error 1093); wrapping keeps this portable across MySQL and SQLite.
        result = self.db.execute(
            sa_text(
                """
                UPDATE users
                SET role = 'admin'
                WHERE id = :uid
                  AND NOT EXISTS (
                    SELECT 1 FROM (
                      SELECT id FROM users WHERE role = 'admin' AND id != :uid
                    ) AS other_admins
                  )
                """
            ),
            {"uid": user.id},
        )
        if result.rowcount > 0:
            self.db.commit()
            self.db.refresh(user)

    def login(self, *, email: str, password: str, client_ip: str | None = None) -> dict[str, object]:
        normalized_email = email.strip().lower()
        self._assert_rate_limit_allowed("login", email=normalized_email, client_ip=client_ip)
        user = self.db.scalar(select(UserModel).where(func.lower(UserModel.email) == normalized_email))
        if user is None or not verify_password(password, user.password_hash):
            self._record_failed_attempt("login", email=normalized_email, client_ip=client_ip)
            raise AuthError("Invalid email or password")
        if not user.is_active:
            self._record_failed_attempt("login", email=normalized_email, client_ip=client_ip)
            raise AuthError("User is disabled")
        self._clear_rate_limit("login", email=normalized_email, client_ip=client_ip)
        return self._auth_response(user)

    def login_with_code(self, *, email: str, code: str) -> dict[str, object]:
        """验证码登录"""
        # 注意：verify_code 是协程，必须走同步封装 verify_code_sync，
        # 否则协程对象恒为真会放行任意错误验证码。
        from app.services.verification_service import verify_code_sync

        normalized_email = email.strip().lower()

        # 验证验证码
        if not verify_code_sync(normalized_email, code, "login"):
            raise AuthError("验证码错误或已过期")

        # 查找用户
        user = self.db.scalar(select(UserModel).where(func.lower(UserModel.email) == normalized_email))
        if user is None:
            raise AuthError("用户不存在")
        if not user.is_active:
            raise AuthError("用户已被禁用")

        return self._auth_response(user)

    def register_with_code(self, *, email: str, name: str, password: str, code: str) -> dict[str, object]:
        """验证码注册"""
        # 注意：verify_code 是协程，必须走同步封装 verify_code_sync，
        # 否则协程对象恒为真会放行任意错误验证码。
        from app.services.verification_service import verify_code_sync

        normalized_email = email.strip().lower()

        # 验证验证码
        if not verify_code_sync(normalized_email, code, "register"):
            raise AuthError("验证码错误或已过期")

        # 检查邮箱是否已注册
        existing = self.db.scalar(select(UserModel).where(func.lower(UserModel.email) == normalized_email))
        if existing is not None:
            raise AuthError("Email already registered")

        # 创建用户 — insert as "user" first to avoid the race condition
        # where two simultaneous registrations both become admin.
        user = UserModel(
            email=email,
            name=name,
            password_hash=hash_password(password),
            role="user",
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AuthError("Email already registered")
        self.db.refresh(user)

        # 仅当系统中尚不存在任何 admin 时提升首个管理员（见 _maybe_promote_first_admin）
        self._maybe_promote_first_admin(user)
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
