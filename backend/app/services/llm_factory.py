"""LLM 构建：从环境配置（OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL）构建 wuwei LLMGateway。"""

from __future__ import annotations

import logging

logger = logging.getLogger("agenticos.llm")


def build_llm_for_user(
    user_id: int | None,
    *,
    max_tokens: int,
    timeout: int,
    model: str | None = None,
    prefer_cookie: bool = False,  # 兼容旧签名：已废弃，不再有 Cookie 上游
):
    """构建 wuwei LLMGateway。

    统一使用服务端配置的 OpenAI 兼容端点（``OPENAI_BASE_URL`` /
    ``OPENAI_API_KEY`` / ``OPENAI_MODEL``），不依赖任何用户态上游凭据。
    """
    from app.core.config import get_settings
    from wuwei.llm import LLMGateway

    settings = get_settings()
    resolved_model = model or settings.openai_model

    return LLMGateway.from_env(
        max_tokens=max_tokens,
        timeout=timeout,
        base_url=settings.openai_base_url,
        model=resolved_model,
        api_key=settings.openai_api_key,
    )
