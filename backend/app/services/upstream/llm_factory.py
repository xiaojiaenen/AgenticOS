"""本机 AgenticOS LLM 构建：默认用当前用户 Cookie 直连 agents.gree.com，无需 API Key。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agenticos.upstream.llm")

_LOCAL_API_KEY = "agenticos-local-session"


def _inject_cookie_client(adapter: Any, cookie: str, base_url: str) -> None:
    """OpenAI SDK 客户端改为 Cookie 认证（不使用 Bearer API Key）。"""
    try:
        from openai import AsyncOpenAI

        adapter.client = AsyncOpenAI(
            api_key=_LOCAL_API_KEY,
            base_url=base_url,
            default_headers={"Cookie": cookie, "User-Agent": "AgenticOS/1.0"},
            timeout=getattr(adapter, "timeout", None) or 300.0,
        )
    except Exception as e:
        logger.warning(f"failed to inject cookie client: {e}")


def build_llm_for_user(
    user_id: int | None,
    *,
    max_tokens: int,
    timeout: int,
    model: str | None = None,
    prefer_cookie: bool = True,
):
    """构建 wuwei LLMGateway。

    本机 AgenticOS **默认**使用登录用户的上游 Cookie 调 agents.gree.com，
    不需要也不使用 sk-agenticos-* API Key。
    无 Cookie 时回退到 OPENAI_BASE_URL / OPENAI_API_KEY。
    """
    from app.core.config import get_settings
    from wuwei.llm import LLMGateway

    settings = get_settings()
    resolved_model = model or settings.openai_model

    cookie = None
    base_url = settings.openai_base_url
    api_key = settings.openai_api_key

    if prefer_cookie and user_id:
        try:
            from app.services.upstream.credential_store import get_active_cookie, get_upstream_base_url

            cookie = get_active_cookie(user_id)
            if not cookie and settings.upstream_auto_login_enabled:
                # 会话内快速尝试一次自动登录（与 Sesame 同流程）
                try:
                    import asyncio

                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        # 不在 agent 创建路径上阻塞：仅用已有 Cookie
                        cookie = get_active_cookie(user_id)
                    else:
                        cookie = None
                except Exception:
                    cookie = get_active_cookie(user_id)
            if cookie:
                base_url = get_upstream_base_url()
                api_key = _LOCAL_API_KEY
                logger.info("LLM using local user cookie upstream base=%s user=%s", base_url, user_id)
        except Exception as e:
            logger.warning(f"cookie LLM resolve failed user={user_id}: {e}")

    llm = LLMGateway.from_env(
        max_tokens=max_tokens,
        timeout=timeout,
        base_url=base_url,
        model=resolved_model,
        api_key=api_key or _LOCAL_API_KEY,
    )

    if cookie and prefer_cookie:
        from app.services.upstream.credential_store import get_upstream_base_url

        _inject_cookie_client(llm.adapter, cookie, get_upstream_base_url())

    return llm
