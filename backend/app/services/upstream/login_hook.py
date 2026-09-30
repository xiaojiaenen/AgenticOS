"""Any successful AgenticOS login → ensure upstream cookie (auto, no manual step)."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("agenticos.upstream.login_hook")

_tasks: set[asyncio.Task] = set()


def schedule_upstream_cookie_after_login(user_id: int, *, username: str | None = None, password: str | None = None, display_name: str | None = None) -> None:
    """登录成功后 fire-and-forget：写凭据（若有账密）并保证 Cookie 可用/快过期则续期。"""

    async def _bg() -> None:
        try:
            if username and password:
                from app.services.upstream.login_orchestrator import sync_after_login

                await sync_after_login(
                    user_id=user_id,
                    username=username,
                    password=password,
                    display_name=display_name,
                )
            else:
                from app.services.upstream.login_orchestrator import ensure_cookie_for_user

                result = await ensure_cookie_for_user(user_id)
                logger.info(f"ensure_cookie after login user={user_id}: {result}")
        except Exception as e:
            logger.warning(f"upstream cookie after login failed user={user_id}: {e}")

    task = asyncio.create_task(_bg())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
