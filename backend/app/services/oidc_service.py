"""OIDC 单点登录（M6-C，设计稿 4.4）。

Authlib 的标准授权码流程，claims → 本地用户的 **纯函数** 归一化与 upsert，
复用现有 ``AuthService._auth_response`` 签发本系统 JWT。

为什么要把归一化做成纯函数
------------------------
``claims_to_profile()`` / ``upsert_oidc_user()`` 不碰网络、不读全局单例，
因此可以在 ``tests/test_permissions.py`` 里用构造的 IdP claims 直接断言：
- 不同 IdP 的 claim 命名（``email`` / ``mail`` / ``preferred_username`` …）都归一到同一形状；
- 部门 claim 只在本地部门已存在时挂接（绝不凭 claim 自动建部门，避免外部数据
  直接写进组织架构）；
- 找不到 email 的 claims 直接拒绝（不生成无名账号）。
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import UserModel

logger = logging.getLogger(__name__)

# claims 里可能承载邮箱的字段，按优先级排列。
# 刻意不含 "sub"：OIDC 的 sub 是不透明标识符（可能是 uuid / 内部主键），
# 把它当邮箱会在 IdP 不返回邮箱时凭空造出 <sub>@域名 的假账号。
EMAIL_CLAIMS: tuple[str, ...] = ("email", "mail", "preferred_username", "upn")

# claims 里可能承载显示名的字段
NAME_CLAIMS: tuple[str, ...] = ("name", "display_name", "cn", "preferred_username", "given_name")

# claims 里可能承载部门的字段
DEPARTMENT_CLAIMS: tuple[str, ...] = ("department", "dept", "ou", "organization")

# 只有这些角色允许由 IdP 下发；其余一律按 user 处理（防 IdP 提权）
ALLOWED_OIDC_ROLES: frozenset[str] = frozenset({"admin", "dept_admin", "user"})


class OidcError(ValueError):
    """OIDC 配置或 claims 不可用。"""


def claims_to_profile(claims: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """把 IdP claims 归一化成内部用户画像（纯函数）。

    Raises:
        OidcError: 缺少可用的邮箱标识，或 IdP 试图下发白名单外的角色。
    """
    email = ""
    for key in EMAIL_CLAIMS:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            email = value.strip().lower()
            break
    if not email:
        raise OidcError("OIDC claims do not contain an email identifier")
    if "@" not in email:
        # preferred_username 常常是裸工号；补上邮件域（OIDC_EMAIL_DOMAIN 优先，
        # 未配置时复用 LDAP 的邮件域，与 LDAP 登录路径保持一致）
        domain = settings.oidc_email_domain or settings.ldap_email_domain
        email = f"{email}@{domain}"

    name = ""
    for key in NAME_CLAIMS:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            name = value.strip()
            break
    name = name or email

    role = "user"
    for key in ("role", "roles", "groups"):
        raw = claims.get(key)
        candidates: list[str] = []
        if isinstance(raw, str):
            candidates = [raw]
        elif isinstance(raw, (list, tuple)):
            candidates = [str(item) for item in raw]
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if normalized in ALLOWED_OIDC_ROLES:
                role = normalized
                break
        if role != "user":
            break

    department_claim = ""
    for key in DEPARTMENT_CLAIMS:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            department_claim = value.strip()
            break
        if isinstance(value, (list, tuple)) and value:
            department_claim = str(value[0]).strip()
            break

    return {
        "email": email,
        "name": name,
        "role": role,
        "department_claim": department_claim,
        "is_active": True,
    }


def upsert_oidc_user(db: Session, profile: dict[str, Any]) -> tuple[UserModel, bool]:
    """按邮箱 upsert 本地用户，返回 (user, created)。

    策略与 LDAP 登录路径一致：已存在则更新显示名/部门，绝不覆盖 ``password_hash``；
    ``auth_source`` 标记为 ``oidc`` 以便运营区分来源。
    """
    email = profile["email"]
    user = db.scalar(select(UserModel).where(func.lower(UserModel.email) == email))
    created = False
    if user is None:
        user_count = db.scalar(select(func.count(UserModel.id))) or 0
        user = UserModel(
            email=email,
            name=profile["name"],
            # OIDC 用户不走本地密码登录：随机不可知口令
            password_hash=secrets.token_hex(32),
            role="admin" if user_count == 0 else profile.get("role", "user"),
            is_active=bool(profile.get("is_active", True)),
            auth_source="oidc",
        )
        db.add(user)
        created = True
    else:
        user.name = profile["name"]
        if user.auth_source == "local":
            # 本地账号被 IdP 认领：保留本地密码但切换来源，避免锁掉已有用户
            user.auth_source = "oidc"

    _attach_department(db, user, profile.get("department_claim", ""))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, created


def _attach_department(db: Session, user: UserModel, department_claim: str) -> None:
    """按 IdP 的部门 claim 挂接**已存在**的同名部门。

    不会凭外部 claim 自动创建部门 —— 组织架构的权威来源是管理员在
    ``/departments`` 里的维护动作，IdP 只做对齐。
    """
    if not department_claim or user.department_id is not None:
        return
    from app.services.department_service import assign_user_department, get_department_by_name

    dept = get_department_by_name(db, department_claim)
    if dept is None:
        logger.info(
            "OIDC department %r for %s has no local counterpart; user left without a department",
            department_claim,
            user.email,
        )
        return
    assign_user_department(db, user, dept.id)


# ---------------------------------------------------------------------------
# Authlib 客户端
# ---------------------------------------------------------------------------


def is_oidc_configured(settings: Settings) -> bool:
    return bool(settings.oidc_enabled and settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret)


def build_oidc_client(settings: Settings):
    """构造 Authlib 的 OAuth 客户端（仅在配置完整时调用）。"""
    if not is_oidc_configured(settings):
        raise OidcError("OIDC is not configured (OIDC_ENABLED/OIDC_ISSUER/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET)")

    from authlib.integrations.starlette_client import OAuth

    oauth = OAuth()
    oauth.register(
        name="agenticos",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={"scope": settings.oidc_scopes},
    )
    return oauth
