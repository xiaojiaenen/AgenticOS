"""LDAP 登录与企业网关 Cookie 的联动。

适用前提：**平台的 LDAP 账号就是企业网关（百通 SSO）的同一套账号密码**。
在此形态下，平台登录时拿到的（用户名+密码）正是自动登录百通所需的凭据，
由此建立「平台会话 ↔ 网关 Cookie」的生命周期联动：

    LDAP 登录成功
      → upsert 本人绑定的凭据行（加密存域账号密码，供后续无人值守续期）
      → 后台自动登录拿 Cookie（不阻塞登录响应）
    Cookie 失效 → 自动重登
      → 重登也失败（域密码已改）→ 吊销该用户平台会话
      → 下一个请求 401 → 前端登出 → 用户重新 LDAP 登录
      → 新密码被本模块捕获 → Cookie 自动恢复

安全说明：这里会加密存储用户的域密码。这与共享池的既有机制一致
（auto_login 续期必须能读到密码），属于该功能的固有要求；
静态加密复用 EXTERNAL_SYSTEM_ENCRYPTION_KEY / AUTH_SECRET_KEY 派生密钥。
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.timezone import app_now
from app.db.models import LlmProviderCredentialModel, LlmProviderModel
from app.db.session import create_db_session
from app.services.llm_providers.credentials import encrypt, invalidate_cache

logger = logging.getLogger("agenticos.ldap.gateway_link")

# 自动登录失败信息里命中这些词 → 判定为「凭据本身的问题」（域密码已改/账号被锁）
# 而不是「上游流程变了」。判定不准时宁可保守：先不吊销，只标记失败。
_AUTH_FAILURE_KEYWORDS = ("密码", "账号", "认证", "password", "account", "credentials")


def list_enterprise_provider_ids() -> list[int]:
    """所有启用中的企业网关提供商。"""
    with create_db_session() as db:
        rows = db.scalars(
            select(LlmProviderModel.id).where(
                LlmProviderModel.provider_type == "enterprise_cookie",
                LlmProviderModel.enabled.is_(True),
            )
        ).all()
    return list(rows)


def upsert_user_credential(
    provider_id: int,
    user_id: int,
    *,
    username: str,
    password: str,
) -> tuple[int, bool]:
    """为用户 upsert 一条绑定凭据。返回 (credential_id, 是否新建)。

    密码变了要**立即**更新加密列 —— 否则后续自动登录还在用旧密码，
    每次都失败。Cookie 不动：SSO 会话可能仍然有效，续期任务会处理。
    """
    with create_db_session() as db:
        row = db.scalar(
            select(LlmProviderCredentialModel).where(
                LlmProviderCredentialModel.provider_id == provider_id,
                LlmProviderCredentialModel.user_id == user_id,
            )
        )
        created = row is None
        if row is None:
            row = LlmProviderCredentialModel(
                provider_id=provider_id,
                user_id=user_id,
                label=f"{username}（LDAP 绑定）",
                username=username,
                priority=10,  # 本人凭据优先于共享池
            )
            db.add(row)

        row.username = username
        row.password_encrypted = encrypt(password)
        db.flush()
        credential_id = row.id
        db.commit()

    invalidate_cache()
    return credential_id, created


def sync_ldap_enterprise_credentials(
    user_id: int, username: str, password: str
) -> list[tuple[int, int]]:
    """为用户同步所有企业网关的绑定凭据。返回 (provider_id, credential_id) 列表。

    在 LDAP 登录成功后调用 —— 此刻密码刚被 LDAP 验证过，是最新值。
    返回 provider_id 是因为后续自动登录（login_and_store）要靠它解析
    该网关的登录流（按钮文案/成功跳转/Cookie 轮询参数都在预设里）。
    """
    pairs: list[tuple[int, int]] = []
    for provider_id in list_enterprise_provider_ids():
        try:
            credential_id, _ = upsert_user_credential(
                provider_id, user_id, username=username, password=password
            )
            pairs.append((provider_id, credential_id))
        except Exception:  # noqa: BLE001 —— 单个提供商失败不阻断其他
            logger.warning(
                "upsert enterprise credential failed: provider=%s user=%s",
                provider_id, user_id, exc_info=True,
            )
    if pairs:
        logger.info(
            "已同步用户 %s 的企业网关绑定凭据：%s", user_id, pairs
        )
    return pairs


def looks_like_auth_failure(message: str) -> bool:
    lowered = (message or "").lower()
    return any(k in lowered for k in _AUTH_FAILURE_KEYWORDS)


def revoke_user_platform_sessions(user_id: int) -> int:
    """吊销用户全部平台会话（下次请求立即 401，前端登出）。"""
    from app.db.models import AuthSessionModel

    revoked = 0
    with create_db_session() as db:
        rows = db.scalars(
            select(AuthSessionModel).where(
                AuthSessionModel.user_id == user_id,
                AuthSessionModel.revoked_at.is_(None),
            )
        ).all()
        now = app_now()
        for row in rows:
            row.revoked_at = now
            revoked += 1
        db.commit()
    if revoked:
        logger.warning(
            "已吊销用户 %s 的 %d 个平台会话（企业网关凭据失效，需重新登录同步密码）",
            user_id, revoked,
        )
    return revoked


def handle_credential_auth_failure(
    credential_id: int, reason: str, *, allow_revoke: bool = True
) -> None:
    """网关凭据认证失败后的统一处理。

    - 标记凭据失效（退出轮换）—— 复用 mark_cookie_invalid；
    - 若该凭据**绑定到用户**且之前有过可用 Cookie（说明密码是在
      「上次可用」之后改的）→ 吊销其平台会话，强制重新登录以捕获新密码；
    - 登录时联动场景传 allow_revoke=False：密码刚被 LDAP 验证过，
      失败说明上游流程变了，吊销只会把刚登录的用户踢出去，毫无意义。
    """
    from app.services.llm_providers.credentials import mark_cookie_invalid

    mark_cookie_invalid(credential_id, reason)

    if not allow_revoke:
        return

    try:
        with create_db_session() as db:
            row = db.get(LlmProviderCredentialModel, credential_id)
            bound_user = getattr(row, "user_id", None) if row else None
            # 只有「之前成功过」才认定是密码变更 —— 从未成功过的绑定行
            # （比如首次自动登录就失败）可能是 SSO 改版，不该踢人
            had_cookie = bool(getattr(row, "cookie_encrypted", ""))
        if bound_user and had_cookie and looks_like_auth_failure(reason):
            revoke_user_platform_sessions(bound_user)
    except Exception:  # noqa: BLE001 —— 吊销失败不影响主流程
        logger.warning("auth-failure revocation failed", exc_info=True)
