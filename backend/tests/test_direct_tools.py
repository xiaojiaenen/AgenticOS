"""直通通道的工具与思考能力测试。

核心区分（这是需求的关键）：

- **不带的**：AgenticOS 的智能体编排 + 系统内置工具
- **必须保留的**：模型自身的 function calling 与 thinking

所以直通通道要把客户端声明的 tools 透传给模型（让模型自己决定调不调），
再把模型产出的 tool_calls 原样交给客户端执行。工具的真实执行在客户端，
我们只负责「让模型看得见 + 把意图转达」。
"""
from __future__ import annotations

import json

import pytest

from app.services.llm_providers.direct_tools import (
    ToolSpecError,
    openai_tools_to_wuwei,
    wuwei_tool_calls_to_openai,
)


# ---------------------------------------------------------------------------
# tools 定义转换
# ---------------------------------------------------------------------------


def test_openai_tools_converted_to_wuwei() -> None:
    """OpenAI 的 tools 定义要转成 wuwei Tool（模型才能看见）。"""
    tools = openai_tools_to_wuwei([{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }])
    assert len(tools) == 1
    assert tools[0].name == "get_weather"
    assert tools[0].description == "查询天气"
    assert "city" in tools[0].parameters.properties


def test_tools_without_parameters_still_work() -> None:
    """有的客户端省略 parameters —— 不能因此报错。"""
    tools = openai_tools_to_wuwei([{
        "type": "function",
        "function": {"name": "ping", "description": "无参工具"},
    }])
    assert len(tools) == 1
    assert tools[0].parameters.type == "object"
    assert tools[0].parameters.properties == {}


def test_tools_accept_flat_form() -> None:
    """也接受不带 type/function 包裹的扁平写法。"""
    tools = openai_tools_to_wuwei([{"name": "flat_tool", "description": "扁平"}])
    assert len(tools) == 1
    assert tools[0].name == "flat_tool"


def test_required_fields_not_in_properties_dropped() -> None:
    """required 里有但 properties 里没有的字段要去掉 —— 上游会因此报错。"""
    tools = openai_tools_to_wuwei([{
        "type": "function",
        "function": {
            "name": "t",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a", "ghost"],
            },
        },
    }])
    assert list(tools[0].parameters.required) == ["a"]


def test_bad_tool_entry_skipped_not_fatal() -> None:
    """一个坏定义不该让整次请求失败。"""
    tools = openai_tools_to_wuwei([
        {"type": "function", "function": {"name": "good"}},
        {"type": "function", "function": {}},  # 缺 name
        "not-a-dict",
    ])
    assert len(tools) == 1
    assert tools[0].name == "good"


def test_tools_must_be_array() -> None:
    with pytest.raises(ToolSpecError, match="必须是数组"):
        openai_tools_to_wuwei({"name": "x"})


def test_empty_tools_returns_empty() -> None:
    assert openai_tools_to_wuwei(None) == []
    assert openai_tools_to_wuwei([]) == []


# ---------------------------------------------------------------------------
# tool_calls 响应转换
# ---------------------------------------------------------------------------


def test_tool_calls_arguments_serialized_as_string() -> None:
    """arguments 必须是 JSON **字符串** —— 给对象客户端会崩。"""
    calls = wuwei_tool_calls_to_openai([{
        "id": "call_1",
        "function": {"name": "get_weather", "arguments": {"city": "北京"}},
    }])
    assert len(calls) == 1
    assert calls[0]["type"] == "function"
    assert calls[0]["function"]["name"] == "get_weather"
    assert isinstance(calls[0]["function"]["arguments"], str)
    assert json.loads(calls[0]["function"]["arguments"]) == {"city": "北京"}


def test_tool_calls_string_arguments_preserved() -> None:
    """已经是字符串的 arguments 原样保留（不重复序列化）。"""
    calls = wuwei_tool_calls_to_openai([{
        "id": "c1",
        "function": {"name": "t", "arguments": '{"x":1}'},
    }])
    assert calls[0]["function"]["arguments"] == '{"x":1}'


def test_tool_calls_missing_arguments_defaults_to_empty_object() -> None:
    calls = wuwei_tool_calls_to_openai([{"id": "c", "function": {"name": "t"}}])
    assert calls[0]["function"]["arguments"] == "{}"


def test_tool_calls_empty_returns_empty() -> None:
    assert wuwei_tool_calls_to_openai(None) == []
    assert wuwei_tool_calls_to_openai([]) == []


# ---------------------------------------------------------------------------
# Anthropic 协议的工具转换
# ---------------------------------------------------------------------------


def test_anthropic_tools_use_input_schema() -> None:
    """Anthropic 的 input_schema 要映射到 OpenAI 的 parameters。"""
    from app.api.gateway_multi import _anthropic_tools_to_openai

    out = _anthropic_tools_to_openai([{
        "name": "get_weather",
        "description": "查天气",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    }])
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "get_weather"
    assert out[0]["function"]["parameters"]["required"] == ["city"]


def test_anthropic_tool_use_input_is_object() -> None:
    """Anthropic 的 tool_use.input 是**对象**，不是 JSON 字符串。"""
    from app.api.gateway_multi import _openai_tool_calls_to_anthropic

    out = _openai_tool_calls_to_anthropic([{
        "id": "call_1",
        "type": "function",
        "function": {"name": "get_weather", "arguments": '{"city":"北京"}'},
    }])
    assert out[0]["type"] == "tool_use"
    assert out[0]["name"] == "get_weather"
    assert isinstance(out[0]["input"], dict)
    assert out[0]["input"] == {"city": "北京"}


def test_anthropic_tool_use_bad_json_does_not_crash() -> None:
    """arguments 不是合法 JSON 时不能崩，退化成空对象。"""
    from app.api.gateway_multi import _openai_tool_calls_to_anthropic

    out = _openai_tool_calls_to_anthropic([{
        "id": "c", "function": {"name": "t", "arguments": "{broken"},
    }])
    assert out[0]["input"] == {}


# ---------------------------------------------------------------------------
# tool 消息回灌
# ---------------------------------------------------------------------------


def test_tool_message_converted_for_roundtrip() -> None:
    """客户端执行完工具后的回灌消息要转成 wuwei ToolMessage。

    这是 function calling 的第二轮：模型给参数 → 客户端执行 →
    结果作为 tool 消息发回来 → 模型据此继续。
    """
    from app.services.llm_providers.direct import _to_wuwei_messages

    converted = _to_wuwei_messages([
        {"role": "user", "content": "北京天气如何"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "get_weather", "arguments": '{"city":"北京"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": "晴，25℃"},
    ])
    assert len(converted) == 3
    # 第三条应该是 ToolMessage 且带 tool_call_id
    last = converted[-1]
    assert type(last).__name__ == "ToolMessage"
    assert last.content == "晴，25℃"
    assert getattr(last, "tool_call_id", None) == "call_1"

    # assistant 消息上的 tool_calls 必须带进 AIMessage。
    #
    # 少了它，模型在第二轮看不到自己调过什么，会重复发起同一个调用 ——
    # 实测表现是「回灌后回答为空，且又返回一个 tool_calls」。
    assistant = converted[1]
    assert type(assistant).__name__ == "AIMessage"
    calls = getattr(assistant, "tool_calls", None)
    assert calls, "AIMessage 缺 tool_calls"
    assert calls[0].function.name == "get_weather"
    # wuwei 的 arguments 是 dict（与 OpenAI 的 JSON 字符串相反）
    assert calls[0].function.arguments == {"city": "北京"}


# ---------------------------------------------------------------------------
# SDK 契约：带 tool_calls 的响应仍能被解析
# ---------------------------------------------------------------------------


def test_chat_completion_with_tool_calls_parses_in_sdk() -> None:
    """带 tool_calls 的 chat 响应必须能被 openai SDK 解析。"""
    from openai.types.chat import ChatCompletion

    ChatCompletion.model_validate({
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "m",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city":"北京"}'},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


def test_anthropic_message_with_tool_use_parses_in_sdk() -> None:
    """带 tool_use block 的 Anthropic 响应必须能被 SDK 解析。"""
    pytest.importorskip("anthropic")
    from anthropic.types import Message as AnthropicMessage

    from app.api.gateway_multi import _openai_to_anthropic_response, _openai_tool_calls_to_anthropic

    payload = _openai_to_anthropic_response(
        text="", reasoning="", usage={"prompt_tokens": 1, "completion_tokens": 1},
        model="m", finish_reason="tool_calls",
    )
    payload["content"].extend(_openai_tool_calls_to_anthropic([{
        "id": "call_1", "type": "function",
        "function": {"name": "get_weather", "arguments": '{"city":"北京"}'},
    }]))
    AnthropicMessage.model_validate(payload)
    assert payload["stop_reason"] == "tool_use"


def test_tool_call_arguments_must_be_dict() -> None:
    """wuwei 的 ToolCall.arguments 要 dict，给字符串会被 pydantic 拒绝。

    这与 OpenAI 正好相反（OpenAI 要 JSON 字符串），是最容易搞错的地方。
    """
    from app.services.llm_providers.direct import _normalize_assistant_tool_calls

    calls = _normalize_assistant_tool_calls([{
        "id": "c1", "type": "function",
        "function": {"name": "t", "arguments": '{"a":1}'},
    }])
    assert len(calls) == 1
    assert isinstance(calls[0].function.arguments, dict)
    assert calls[0].function.arguments == {"a": 1}


def test_tool_call_bad_json_falls_back_to_empty() -> None:
    """arguments 不是合法 JSON 时退化成空对象，不能崩。"""
    from app.services.llm_providers.direct import _normalize_assistant_tool_calls

    calls = _normalize_assistant_tool_calls([{
        "id": "c", "type": "function",
        "function": {"name": "t", "arguments": "{broken"},
    }])
    assert calls[0].function.arguments == {}
