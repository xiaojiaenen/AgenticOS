"""上下文压缩可观测性回归（原 ObservableCompressionMiddleware 语义移植）。

原 wuwei ObservableCompressionMiddleware 的三个可观测性语义全部保留在
``native/context_compression.py`` 的 ``ContextCompressor``：

1. 压缩行为与上游一致（protect head/tail、tool 配对保护、去重）；
2. 摘要失败 → WARNING（含异常类型，同一异常节流）；
3. 真正压缩成功 → INFO（压缩前后条数与估算 token）。
"""

from __future__ import annotations

import pytest

from app.services.agent.native.context_compression import ContextCompressor
from app.services.agent.native.types import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)


def _make_compressor(trigger=200, keep=2, llm=None) -> ContextCompressor:
    return ContextCompressor(llm=llm, trigger_tokens=trigger, keep_recent_turns=keep, max_tokens=128000)


def _long_history(turns=8):
    """构造超长历史（超过 200 token 触发阈值）。"""
    msgs = [HumanMessage(content="系统提示词占位")]
    for i in range(turns):
        msgs.append(HumanMessage(content=f"第 {i} 轮用户消息，包含一些中文内容来推高 token 估算值。"))
        msgs.append(AIMessage(content=f"第 {i} 轮助手回复，同样包含足量的中文文本内容来推高估算。"))
    return msgs


class _FakeSession:
    def __init__(self):
        self.metadata = {}


class _FakeLLM:
    """可脚本化的 LLM 替身。"""

    def __init__(self, summary="## Resolved\n- done", fail=False):
        self.summary = summary
        self.fail = fail
        self.calls = 0

    async def generate(self, messages, tools=None, stream=False, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider throttled")
        from types import SimpleNamespace

        return SimpleNamespace(message=SimpleNamespace(content=self.summary))


# ── 压缩行为 ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_compresses_long_history():
    """超阈值历史被压缩：条数变少、摘要消息出现。"""
    compressor = _make_compressor()
    llm = _FakeLLM(summary="## Active Task\n测试任务")
    history = _long_history()
    session = _FakeSession()

    result = await compressor.compress_if_needed_full(history, session, llm)
    assert len(result) < len(history), "压缩后条数应减少"
    assert any(m.role == "system" and "Active Task" in m.content for m in result), "摘要以 system 角色注入"
    assert llm.calls == 1


@pytest.mark.anyio
async def test_below_trigger_untouched():
    """低于阈值的历史原样返回（零 LLM 调用）。"""
    compressor = _make_compressor(trigger=999_999)
    llm = _FakeLLM()
    history = _long_history()
    result = await compressor.compress_if_needed_full(history, _FakeSession(), llm)
    assert result == history
    assert llm.calls == 0


@pytest.mark.anyio
async def test_tool_pair_not_cut_midway():
    """切分点不在 tool_call 配对中间（保护逻辑移植）。"""
    compressor = _make_compressor(trigger=200, keep=2)
    llm = _FakeLLM(summary="## Active Task\nx")
    history = [HumanMessage(content="开头占位消息，内容足够长以推高估算值。")]
    from app.services.agent.native.types import FunctionCall, ToolCall

    ai = AIMessage(content="", tool_calls=[
        ToolCall(id="call-1", function=FunctionCall(name="t", arguments={}))
    ])
    history.append(ai)
    history.append(ToolMessage(content="result-1", tool_call_id="call-1", name="t"))
    for i in range(6):
        history.append(HumanMessage(content=f"后续消息 {i}，中文内容足够长。"))
        history.append(AIMessage(content=f"后续回复 {i}，中文内容足够长。"))
    session = _FakeSession()

    result = await compressor.compress_if_needed_full(history, session, llm)
    tool_ids = {m.tool_call_id for m in result if m.role == "tool"}
    declared = {tc.id for m in result if m.role == "assistant" for tc in m.tool_calls}
    assert tool_ids <= declared, "tool 结果不能成为孤立结果"


# ── 可观测性 ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_failure_is_logged(caplog):
    """摘要失败 → WARNING（含异常类型；原 ObservableCompression 语义移植）。"""
    compressor = _make_compressor()
    llm = _FakeLLM(fail=True)
    with caplog.at_level("WARNING", logger="agenticos.context_compression"):
        result = await compressor.compress_if_needed_full(_long_history(), _FakeSession(), llm)
    assert any("摘要生成失败" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_success_logs_info(caplog):
    """压缩成功 → INFO（含压缩前后条数）。"""
    compressor = _make_compressor()
    llm = _FakeLLM(summary="## Active Task\nx")
    with caplog.at_level("INFO", logger="agenticos.context_compression"):
        await compressor.compress_if_needed_full(_long_history(), _FakeSession(), llm)
    assert any("上下文已压缩" in r.message for r in caplog.records)


# ── factory 装配 ──────────────────────────────────────────────────────


def test_factory_uses_deepagents_summarization():
    """context_compression_enabled 时绑定 DeepAgents backend（内置 summarization 落盘）。

    彻底替换后：自研 ContextCompressor 保留为算法单元（上面的单测覆盖），
    factory 装配的是 DeepAgents FilesystemBackend —— 内置 SummarizationMiddleware
    把裁剪历史写进 backend 的 conversation_history/。
    """
    import inspect

    from app.services.agent.factory import AgentFactory

    src = inspect.getsource(AgentFactory._get_agent)
    assert "FilesystemBackend" in src, "factory 未绑定 DeepAgents backend"
    assert "context_compression_enabled" in src, "开关丢失"
    assert "deepagents_backend" in src, "未把 backend 传给引擎"
