"""回归：多条 system 消息必须在网关层合并成一条。

真实故障
--------
OpenAI 兼容端有硬校验 ``System message must be at the beginning.``
—— system 必须唯一且位于首位。wuwei 3.3.2 的 structured-output 逻辑
（``agent_runner.py:481-492``）在已有 system 提示词时又
``messages.insert(0, SystemMessage(...))``：

    [新 system（JSON Schema 说明）, 旧 system（智能体提示词）, user, ...]

上游直接 400，不是可重试错误，一路冒泡成 ``LLMError`` 把整轮对话打断。
用户看到的是「发消息立刻失败」。

修复放在 ``RetryingGateway``（全站唯一 LLM 出口）而不是改上游私有逻辑：
只把多条 system 合并到首位的一条，不改语义、不改顺序。
"""

from __future__ import annotations

from wuwei.core.message import AIMessage, HumanMessage, SystemMessage

from app.services.llm_providers.adapter import normalize_system_messages


def _roles(messages):
    return [m.role for m in messages]


def test_merges_leading_duplicate_system_messages():
    """上游插到最前的那条与原有 system 合并，只留一条且在首位。"""
    messages = [
        SystemMessage(content="只输出符合以下JSON Schema的JSON对象：{}"),
        SystemMessage(content="你是 AgenticOS 的助手"),
        HumanMessage(content="你好"),
    ]
    out = normalize_system_messages(messages)

    assert _roles(out) == ["system", "user"]
    assert "JSON Schema" in out[0].content
    assert "AgenticOS 的助手" in out[0].content
    # 用户消息原样保留
    assert out[1].content == "你好"


def test_keeps_single_leading_system_untouched():
    """已经合法的形态原样返回（不复制列表，避免无谓开销）。"""
    messages = [SystemMessage(content="sys"), HumanMessage(content="hi")]
    assert normalize_system_messages(messages) is messages


def test_no_system_messages_untouched():
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert normalize_system_messages(messages) is messages


def test_empty_list_untouched():
    messages: list = []
    assert normalize_system_messages(messages) is messages


def test_system_in_middle_is_hoisted_to_front():
    """system 出现在中间同样非法，合并后必须回到首位。"""
    messages = [
        HumanMessage(content="hi"),
        SystemMessage(content="后置的 system"),
        AIMessage(content="ok"),
    ]
    out = normalize_system_messages(messages)

    assert _roles(out) == ["system", "user", "assistant"]
    assert out[0].content == "后置的 system"


def test_empty_system_content_is_dropped():
    """空白 system 不参与合并，避免留下一个空的 system 块。"""
    messages = [
        SystemMessage(content="   "),
        SystemMessage(content="真正的提示词"),
        HumanMessage(content="hi"),
    ]
    out = normalize_system_messages(messages)

    assert _roles(out) == ["system", "user"]
    assert out[0].content == "真正的提示词"


def test_tool_round_preserved():
    """带工具调用的多轮消息顺序不能被破坏（只动 system）。"""
    messages = [
        SystemMessage(content="extra"),
        SystemMessage(content="main"),
        HumanMessage(content="算一下"),
        AIMessage(content=""),
    ]
    out = normalize_system_messages(messages)
    assert _roles(out) == ["system", "user", "assistant"]
