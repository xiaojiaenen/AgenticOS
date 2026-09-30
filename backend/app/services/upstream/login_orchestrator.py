"""单上游 (agents.gree.com) 的自动登录编排：登录后写 cookie + 可选同步 sesame。"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.timezone import app_now
from app.services.upstream import credential_store
from app.services.upstream.auto_login_service import login_with_credentials

logger = logging.getLogger("agenticos.upstream.login")

_bg_tasks: set[asyncio.Task] = set()


async def sync_to_sesame(
    *,
    username: str,
    password: str,
    display_name: str | None = None,
) -> None:
    """可选：同步凭据到独立 Sesame 网关 cookie 池（流程与现有 auth 一致）。"""
    settings = get_settings()
    if not settings.sesame_gateway_url or not settings.sesame_internal_token:
        return

    try:
        import httpx

        url = f"{settings.sesame_gateway_url.rstrip('/')}/internal/sync-credentials"
        payload: dict[str, str] = {"username": username, "password": password}
        if display_name:
            payload["display_name"] = display_name
        headers = {
            "X-Internal-Token": settings.sesame_internal_token,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            logger.info(f"Sesame credential sync ok: user={username}")
        else:
            logger.warning(
                f"Sesame credential sync failed: user={username} "
                f"status={resp.status_code} body={resp.text[:200]}"
            )
    except Exception as e:
        logger.warning(f"Sesame credential sync error: user={username} {type(e).__name__}: {e}")


async def perform_auto_login(user_id: int) -> dict:
    """对该用户的上游凭据执行一次自动登录（与 sesame 相同的 Playwright 流程）。"""
    row = credential_store.get_credential_for_user(user_id)
    if row is None:
        return {"success": False, "message": "未配置上游凭据", "user_id": user_id}

    from app.core.encryption import decrypt_safe

    password = decrypt_safe(row.password_encrypted)
    if not password:
        credential_store.apply_login_result(user_id, success=False, cookie=None, expire_at=None, error="密码解密失败")
        return {"success": False, "message": "密码解密失败", "user_id": user_id}

    login_url = row.login_url or credential_store.get_upstream_login_url()
    success, msg, cookie, expire = await login_with_credentials(login_url, row.username, password)
    credential_store.apply_login_result(
        user_id,
        success=success,
        cookie=cookie,
        expire_at=expire,
        error=None if success else msg,
    )
    return {
        "success": success,
        "message": msg,
        "user_id": user_id,
        "upstream": credential_store.UPSTREAM_KEY,
        "login_url": login_url,
        "expire_at": expire.isoformat() if expire else None,
        "has_cookie": bool(cookie),
    }


async def sync_after_login(
    *,
    user_id: int,
    username: str,
    password: str,
    display_name: str | None = None,
) -> None:
    """LDAP/业务登录成功后：写本地凭据 → 后台自动登录 → 可选推 sesame。

    与 sesame internal sync 的时序一致：凭据先落库，自动登录 fire-and-forget。
    """
    settings = get_settings()
    if not settings.upstream_auto_login_enabled:
        logger.debug("upstream auto login disabled, skip sync_after_login")
        return
    if not username or not password:
        return

    try:
        credential_store.upsert_credentials(
            user_id=user_id,
            username=username,
            password=password,
            display_name=display_name,
            login_url=credential_store.get_upstream_login_url(),
            auto_refresh=True,
        )
    except Exception as e:
        logger.warning(f"upstream credential upsert failed user={user_id}: {e}")
        return

    async def _bg() -> None:
        # 本地自动登录（流程与 sesame 一致）
        try:
            result = await ensure_cookie_for_user(user_id)
            logger.info(
                f"upstream auto-login user={user_id} success={result.get('success')} "
                f"renewed={result.get('renewed')} msg={result.get('message')}"
            )
        except Exception as e:
            logger.warning(f"upstream auto-login error user={user_id}: {e}")
        # 可选同步 sesame
        await sync_to_sesame(username=username, password=password, display_name=display_name)

    task = asyncio.create_task(_bg())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def ensure_cookie_for_user(user_id: int) -> dict:
    """登录 AgenticOS 后确保上游 Cookie 可用；快过期则自动续期。"""
    settings = get_settings()
    if not settings.upstream_auto_login_enabled:
        return {"success": False, "message": "auto login disabled", "user_id": user_id}

    row = credential_store.get_credential_for_user(user_id)
    if row is None:
        return {"success": False, "message": "no upstream credential", "user_id": user_id}

    from datetime import timedelta

    from app.core.timezone import APP_TIMEZONE, app_now

    now = app_now()
    expire = row.expire_at
    if expire is not None and expire.tzinfo is None:
        expire = expire.replace(tzinfo=APP_TIMEZONE)
    buffer = timedelta(hours=int(getattr(settings, "upstream_cookie_refresh_buffer_hours", 2)))
    has_cookie = bool(row.cookie_encrypted)
    expiring_soon = expire is not None and expire <= (now + buffer)
    expired = expire is not None and expire <= now

    if has_cookie and row.status == "active" and not expired and not expiring_soon:
        return {
            "success": True,
            "message": "cookie ok",
            "user_id": user_id,
            "renewed": False,
            "expire_at": expire.isoformat() if expire else None,
        }

    result = await perform_auto_login(user_id)
    result["renewed"] = True
    return result


async def refresh_expired_credentials() -> int:
    """巡检：过期、快过期（预续期缓冲）、无 Cookie 的自动重登。返回处理数量。"""
    settings = get_settings()
    if not settings.upstream_auto_login_enabled:
        return 0
    from datetime import timedelta

    from app.db.models import UpstreamCredentialModel
    from app.db.session import create_db_session
    from sqlalchemy import select

    from app.core.timezone import APP_TIMEZONE

    now = app_now()
    buffer = timedelta(hours=int(getattr(settings, "upstream_cookie_refresh_buffer_hours", 2)))
    targets: list[int] = []
    with create_db_session() as db:
        rows = db.scalars(
            select(UpstreamCredentialModel).where(
                UpstreamCredentialModel.upstream_key == credential_store.UPSTREAM_KEY,
                UpstreamCredentialModel.auto_refresh.is_(True),
            )
        ).all()
        for row in rows:
            expire = row.expire_at
            if expire is not None and expire.tzinfo is None:
                expire = expire.replace(tzinfo=APP_TIMEZONE)
            expired = expire is not None and expire <= now
            expiring_soon = expire is not None and not expired and expire <= (now + buffer)
            no_cookie = not row.cookie_encrypted
            if expired or expiring_soon or no_cookie or row.status in {"pending", "failed", "expired"}:
                targets.append(row.user_id)

    count = 0
    for uid in targets:
        try:
            await perform_auto_login(uid)
            count += 1
        except Exception as e:
            logger.warning(f"refresh auto-login failed user={uid}: {e}")
    return count


def start_cookie_refresh_loop() -> asyncio.Task:
    """启动后台 cookie 续期循环（30 分钟 / 提前 2h 预刷新，与 sesame 对齐）。"""
    settings = get_settings()
    interval = max(60, int(settings.upstream_cookie_refresh_minutes) * 60)

    async def _loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                n = await refresh_expired_credentials()
                if n:
                    logger.info(f"upstream cookie refresh processed {n} credential(s)")
            except Exception as e:
                logger.warning(f"upstream cookie refresh loop error: {e}")

    return asyncio.create_task(_loop())
