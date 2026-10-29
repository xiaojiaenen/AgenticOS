"""ObservableCompressionMiddleware 测试。

核心契约：**行为必须与上游完全一致**（冷却、阈值、切分都不变），
只是多了日志。所以除了断言日志，还要断言压缩/不压缩的结果与上游相同。
"""
from __future__ import annotations

import logging

import pytest

from wuwei.core.message import AIMessage, HumanMessage, SystemMessage
from wuwei.graph.state import State
from wuwei.middleware import ContextCompressionMiddleware, MiddlewareContext

from app.services.agent.compression import ObservableCompressionMiddleware


class _SummaryLLM:
    """generate 返回带 message.content 的响应（wuwei LLMResponse 形态）。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def generate(self, messages=None, **kw):
        if self.fail:
            raise RuntimeError("429 quota exceeded")

        class _Msg:
            content = "## Resolved\n- 历史摘要"

        class _R:
            message = _Msg()

        return _R()


def _long_msgs(n: int) -> list:
    msgs = [SystemMessage(content="你是助手")]
    for i in range(n):
        msgs.append(HumanMessage(content=f"第{i}轮。" + "中文内容" * 60))
        msgs.append(AIMessage(content="OK"))
    return msgs


def _ctx(msgs) -> MiddlewareContext:
    # config 里给 model_call=None 会走 self.llm.generate 分支
    return MiddlewareContext(state=State(messages=list(msgs)), config={"session": None})


@pytest.mark.asyncio
async def test_compresses_like_upstream() -> None:
    """成功路径：与上游一样把超长上下文压短。"""
    upstream = ContextCompressionMiddleware(
        llm=_SummaryLLM(), trigger_tokens=100, keep_recent_turns=2, max_tokens=128000
    )
    ours = ObservableCompressionMiddleware(
        llm=_SummaryLLM(), trigger_tokens=100, keep_recent_turns=2, max_tokens=128000
    )
    msgs = _long_msgs(12)

    up_out = await upstream.before_llm(_ctx(msgs))
    our_out = await ours.before_llm(_ctx(msgs))

    assert len(up_out.state.messages) < len(msgs), "上游对照组应压缩"
    assert len(our_out.state.messages) == len(up_out.state.messages), (
        "子类压缩结果必须与上游一致 —— 只加日志，不改行为"
    )


@pytest.mark.asyncio
async def test_failure_is_logged(caplog) -> None:
    """摘要失败必须有 WARNING —— 这是本模块存在的意义。

    实测发现上游 _generate_structured_summary 自己就把异常吞了并返回 None，
    所以子类通常走的是「摘要为空」分支而不是异常分支。两个分支都要有日志，
    测试同时接受这两种形态 —— 关键是**绝不能静默**。
    """
    mw = ObservableCompressionMiddleware(
        llm=_SummaryLLM(fail=True), trigger_tokens=100, keep_recent_turns=2, max_tokens=128000
    )
    with caplog.at_level(logging.WARNING, logger="agenticos.context_compression"):
        out = await mw.before_llm(_ctx(_long_msgs(12)))

    # 行为仍与上游一致：失败 → 不压缩、不抛异常
    assert len(out.state.messages) == 25
    text = caplog.text
    assert ("摘要生成失败" in text) or ("摘要为空" in text), (
        f"上游吞异常时应命中「摘要为空」告警，实际日志：{text[:300]!r}"
    )


@pytest.mark.asyncio
async def test_success_logs_info(caplog) -> None:
    """压缩成功要有 INFO（前后条数与 token 估算）。"""
    mw = ObservableCompressionMiddleware(
        llm=_SummaryLLM(), trigger_tokens=100, keep_recent_turns=2, max_tokens=128000
    )
    with caplog.at_level(logging.INFO, logger="agenticos.context_compression"):
        await mw.before_llm(_ctx(_long_msgs(12)))
    assert "上下文已压缩" in caplog.text


@pytest.mark.asyncio
async def test_below_trigger_untouched() -> None:
    """未超阈值时不能动消息 —— 与上游一致。"""
    mw = ObservableCompressionMiddleware(
        llm=_SummaryLLM(), trigger_tokens=10_000_000, keep_recent_turns=2, max_tokens=128000
    )
    msgs = _long_msgs(3)
    out = await mw.before_llm(_ctx(msgs))
    assert len(out.state.messages) == len(msgs)


def test_factory_uses_observable_middleware() -> None:
    """装配处必须用带日志的子类。"""
    import inspect

    from app.services.agent import factory

    src = inspect.getsource(factory)
    assert "ObservableCompressionMiddleware(" in src
    assert "stack.add(ContextCompressionMiddleware(" not in src, (
        "factory 仍在直接装配上游基类 —— 摘要失败会继续静默"
    )
