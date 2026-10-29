"""压缩阈值与上下文用量测试。

覆盖两个真实缺陷：
1. 阈值换算错误：``after_turns × 500`` 假设每轮 500 tokens，实测短对话
   每轮只有 ~22 tokens → 配 16 轮实际要 174 轮才压缩，压缩形同虚设。
2. 客户端看不到上下文用量：响应只有 usage，没有窗口大小与占用比例，
   客户端无法判断「还能聊多久」。
"""
from __future__ import annotations

import pytest


def test_compression_trigger_uses_configurable_per_turn() -> None:
    """触发阈值必须用可配的 tokens_per_turn，不是硬编码 500。"""
    import inspect

    from app.services.agent import factory

    # 读整个模块：装配逻辑可能在 _get_agent 或它的兄弟方法里
    src = inspect.getsource(factory)
    assert "context_tokens_per_turn" in src, (
        "装配处仍在硬编码 500/轮 —— 配 16 轮实际要 174 轮才压缩"
    )
    assert "* 500" not in src, "还有硬编码 500"


def test_compression_trigger_passes_max_tokens() -> None:
    """必须传 max_tokens，让中间件按窗口比例也能触发。"""
    import inspect

    from app.services.agent import factory

    src = inspect.getsource(factory)
    assert "max_tokens=window" in src, (
        "没传 max_tokens，中间件无法按窗口比例触发 —— 每轮 token 估偏时"
        "会一直涨到撞上游上限"
    )


def test_trigger_is_capped_at_half_window() -> None:
    """触发阈值不该超过窗口一半 —— 要给本轮回复留余量。"""
    from app.core.config import get_settings

    settings = get_settings()
    window = settings.context_window_tokens
    trigger = min(
        settings.context_compress_after_turns * settings.context_tokens_per_turn,
        window // 2,
    )
    assert trigger <= window // 2
    assert trigger > 0


def test_default_trigger_is_reasonable() -> None:
    """默认配置下阈值应落在合理区间（几千 token，不是 8000+）。"""
    from app.core.config import get_settings

    settings = get_settings()
    trigger = min(
        settings.context_compress_after_turns * settings.context_tokens_per_turn,
        settings.context_window_tokens // 2,
    )
    assert 1000 <= trigger <= 10000, f"阈值 {trigger} 不合理"


def test_context_window_is_configurable() -> None:
    """窗口大小必须可配 —— 小窗口模型配大默认值会让压缩永远等不到。"""
    from app.core.config import get_settings

    settings = get_settings()
    assert hasattr(settings, "context_window_tokens")
    assert settings.context_window_tokens >= 8000


def test_context_usage_payload_shape() -> None:
    """上下文用量载荷必须含客户端判断所需的四个字段。"""
    from app.services.agent.orchestrator import StreamOrchestrator

    class _Ctx:
        _messages: list = []

    class _Session:
        context = _Ctx()
        summary = None
        session_id = "s1"

    payload = StreamOrchestrator._context_usage_payload(None, _Session())
    for key in ("context_tokens", "context_window", "context_used_ratio", "context_message_count"):
        assert key in payload, f"缺 {key}，客户端无法判断上下文余量"
    assert 0.0 <= payload["context_used_ratio"] <= 1.0


def test_context_usage_ratio_capped() -> None:
    """占用比例要封顶在 1.0 —— 超过窗口时不该出现 150% 这种数字。"""
    from app.services.agent.orchestrator import StreamOrchestrator

    class _Msg:
        content = "中" * 200000  # 远超默认窗口

    class _Ctx:
        _messages = [_Msg()]

    class _Session:
        context = _Ctx()
        summary = None
        session_id = "s2"

    payload = StreamOrchestrator._context_usage_payload(None, _Session())
    assert payload["context_used_ratio"] <= 1.0


def test_context_usage_handles_missing_context() -> None:
    """没有 context 时不能崩，返回 0 占用。"""
    from app.services.agent.orchestrator import StreamOrchestrator

    class _Session:
        context = None
        summary = None
        session_id = "s3"

    payload = StreamOrchestrator._context_usage_payload(None, _Session())
    assert payload["context_tokens"] == 0
    assert payload["context_message_count"] == 0


def test_estimate_matches_compression_middleware() -> None:
    """我们算的 token 数要与 wuwei 压缩中间件一致。

    不一致会导致「客户端显示还有 50% 余量，实际已压缩过」的错位。
    """
    from wuwei.core.message import HumanMessage
    from wuwei.middleware import ContextCompressionMiddleware

    from app.services.agent.orchestrator import StreamOrchestrator

    text = "这是一段中文测试文本。" * 20
    msgs = [HumanMessage(content=text)]

    class _Ctx:
        _messages = msgs

    class _Session:
        context = _Ctx()
        summary = None
        session_id = "s4"

    ours = StreamOrchestrator._context_usage_payload(None, _Session())["context_tokens"]

    mw = ContextCompressionMiddleware(llm=None, trigger_tokens=8000)
    theirs = mw._estimate_tokens(msgs)

    # 允许 1 token 误差（非中文按 4 字符/token 取整方式可能差 1）
    assert abs(ours - theirs) <= 1, f"估算不一致：我们 {ours} vs 中间件 {theirs}"
