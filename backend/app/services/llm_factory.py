"""LLM 构建入口：按「当前生效的 AI 提供商」构建 wuwei ``LLMGateway``。

**这是全站唯一的 LLM 构建入口。** 除测试外，``app/`` 里不允许出现
``LLMGateway.from_env()``（``tests/test_llm_entrypoint.py`` 静态钉住）——
那个调用直连 ``.env`` 里的 ``OPENAI_*``，会绕过管理端配置的提供商。
历史上记忆抽取、知识摄入、PPT 多智能体、公告生成四条链路就是这么被漏掉的：
管理员在界面上切了提供商，这四条链路仍然打老网关，界面显示已切换、实际一半
流量没走新提供商，而且没有任何日志提示。

提供商在数据库里配置（管理端「AI 提供商」），没有配置时自动回落
``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` / ``OPENAI_MODEL``，与改造前行为一致。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agenticos.llm")


def build_llm(
    *,
    role: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> Any:
    """按当前生效提供商构建网关。

    ``role`` 是「这一路负载属于哪种用途」（``chat`` / ``fast`` / ``reasoner``
    / ``vision`` / ``image``）。企业网关常常按用途分模型（深度思考一个、轻任务
    一个），传了 role 就按提供商的用途绑定取模型，取不到退回主模型。

    ``model`` 传值会**覆盖**提供商配置 —— 只在「确实要指定某个模型」时用；
    留空表示用提供商自己的模型，这也是绝大多数调用方该有的行为。

    ``max_tokens`` / ``timeout`` 留空时取全局默认（``AGENT_MAX_TOKENS`` /
    ``LLM_TIMEOUT``），避免每个调用点各写一份、改默认值要全仓搜。
    """
    from app.core.config import get_settings
    from app.services.llm_providers.runtime import build_gateway_for_active_provider
    from app.services.llm_providers.spec import (
        resolve_active_provider,
        resolve_model_for_role,
    )

    settings = get_settings()

    resolved_model = (model or "").strip() or None
    if resolved_model is None:
        resolved_model = resolve_model_for_role(resolve_active_provider(), role) or None

    return build_gateway_for_active_provider(
        max_tokens=max_tokens or settings.agent_max_tokens,
        timeout=timeout or settings.llm_timeout,
        model=resolved_model,
    )


def build_llm_for_user(
    user_id: int | None = None,
    *,
    max_tokens: int | None = None,
    timeout: int | None = None,
    model: str | None = None,
    role: str | None = None,
) -> Any:
    """``build_llm`` 的兼容别名。

    ``user_id`` 仅为兼容既有调用签名保留：提供商是**管理员全局切换**的，
    不按用户区分，因此这里不再有「用谁的 Cookie」这种决策。新代码直接用
    ``build_llm``，别再用这个名字（它容易让人以为能按用户切提供商）。
    """
    return build_llm(role=role, model=model, max_tokens=max_tokens, timeout=timeout)


def build_llm_optional(
    *,
    role: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    purpose: str = "",
) -> Any | None:
    """构建网关，失败时返回 ``None`` 并告警。

    给「没有 LLM 也能降级跑完」的后台任务用（记忆抽取退化成不抽取、知识摄入
    退化成规则编译）。这些任务在后台自动触发、没人盯着，直接抛异常只会让
    整个任务失败且看不到原因，所以这里把「没有可用网关」降级成一次 WARNING。

    注意日志文案：必须带上 ``purpose``，否则线上只会看到一串
    「ProviderUnavailable」而不知道是哪个链路在降级。
    """
    try:
        return build_llm(
            role=role, model=model, max_tokens=max_tokens, timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 —— 降级路径，任何异常都不该炸掉调用方
        logger.warning("%s：未取得 LLM 网关，降级运行（%s）", purpose or "后台任务", exc)
        return None
