"""对外多协议网关测试。

覆盖重点不是「能不能真的调到上游」（那需要外部 API），而是：
- 模型分类正确（agent vs llm，含 llm: 前缀强制）
- 四种协议的请求/响应形状转换正确
- 未配置时给出可执行提示而不是崩
"""
from __future__ import annotations

import pytest

from app.api.gateway_multi import (
    LLM_PREFIX,
    _anthropic_to_openai_messages,
    _openai_to_anthropic_response,
    _responses_input_to_messages,
    _to_responses_output,
    classify_model,
)


# ---------------------------------------------------------------------------
# 模型分类
# ---------------------------------------------------------------------------


def test_llm_prefix_forces_direct(monkeypatch) -> None:
    """llm: 前缀必须强制走直通，不受智能体同名影响。"""

    class _User:
        id = 1

    # 让智能体解析「命中」任意名字，验证前缀优先级更高
    monkeypatch.setattr(
        "app.api.v1.endpoints.openai_compat.find_local_agent",
        lambda model, user: {"slug": model},
    )

    kind, name = classify_model("llm:gpt-4o", _User())
    assert kind == "llm"
    assert name == "gpt-4o"


def test_agent_hit_takes_agent_path(monkeypatch) -> None:
    class _User:
        id = 1

    monkeypatch.setattr(
        "app.api.v1.endpoints.openai_compat.find_local_agent",
        lambda model, user: {"slug": "ppt", "response_mode": "ppt"},
    )

    kind, name = classify_model("ppt", _User())
    assert kind == "agent"


def test_unknown_model_falls_back_to_llm(monkeypatch) -> None:
    """未命中智能体时不该 400 —— 当作模型名走直通。"""
    class _User:
        id = 1

    monkeypatch.setattr(
        "app.api.v1.endpoints.openai_compat.find_local_agent",
        lambda model, user: None,
    )

    kind, name = classify_model("deepseek-chat", _User())
    assert kind == "llm"
    assert name == "deepseek-chat"


def test_empty_model_falls_back_to_llm(monkeypatch) -> None:
    class _User:
        id = 1

    monkeypatch.setattr(
        "app.api.v1.endpoints.openai_compat.find_local_agent",
        lambda model, user: None,
    )
    kind, name = classify_model("", _User())
    assert kind == "llm"


def test_llm_prefix_constant() -> None:
    assert LLM_PREFIX == "llm:"


# ---------------------------------------------------------------------------
# Anthropic 协议转换
# ---------------------------------------------------------------------------


def test_anthropic_system_extracted_to_messages() -> None:
    """Anthropic 的顶层 system 要变成 OpenAI 的 system 消息。"""
    body = {
        "system": "你是一个翻译助手",
        "messages": [{"role": "user", "content": "翻译 hello"}],
    }
    msgs = _anthropic_to_openai_messages(body)
    assert msgs[0] == {"role": "system", "content": "你是一个翻译助手"}
    assert msgs[1] == {"role": "user", "content": "翻译 hello"}


def test_anthropic_system_block_array() -> None:
    body = {
        "system": [{"type": "text", "text": "规则一"}, {"type": "text", "text": "规则二"}],
        "messages": [{"role": "user", "content": "hi"}],
    }
    msgs = _anthropic_to_openai_messages(body)
    assert msgs[0]["content"] == "规则一规则二"


def test_anthropic_content_block_array_flattened() -> None:
    """block 数组只保留 text 块（直通通道不支持 tool_use/image）。"""
    body = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "image", "source": {}},
                {"type": "text", "text": "第二段"},
            ],
        }],
    }
    msgs = _anthropic_to_openai_messages(body)
    assert msgs[0]["content"] == "第一段第二段"


def test_anthropic_response_shape() -> None:
    """响应必须是 Anthropic 形状：content 是 block 数组，usage 用 input/output。"""
    out = _openai_to_anthropic_response(
        text="你好", reasoning="", usage={"prompt_tokens": 10, "completion_tokens": 5},
        model="m", finish_reason="stop",
    )
    assert out["type"] == "message"
    assert out["role"] == "assistant"
    assert out["content"] == [{"type": "text", "text": "你好"}]
    assert out["stop_reason"] == "end_turn"
    assert out["usage"]["input_tokens"] == 10
    assert out["usage"]["output_tokens"] == 5


def test_anthropic_reasoning_becomes_thinking_block() -> None:
    out = _openai_to_anthropic_response(
        text="答", reasoning="想了一下", usage={"prompt_tokens": 1, "completion_tokens": 1},
        model="m", finish_reason="stop",
    )
    # ThinkingBlock 的 signature 是必填字段（anthropic SDK 要求），
    # 所以这里要连它一起断言，否则客户端解析会崩。
    assert out["content"][0]["type"] == "thinking"
    assert out["content"][0]["thinking"] == "想了一下"
    assert "signature" in out["content"][0]
    assert out["content"][1]["type"] == "text"


def test_anthropic_length_maps_to_max_tokens() -> None:
    out = _openai_to_anthropic_response(
        text="截断", reasoning="", usage={"prompt_tokens": 1, "completion_tokens": 1},
        model="m", finish_reason="length",
    )
    assert out["stop_reason"] == "max_tokens"


# ---------------------------------------------------------------------------
# Responses API 转换
# ---------------------------------------------------------------------------


def test_responses_instructions_to_system() -> None:
    body = {
        "instructions": "你是助手",
        "input": "你好",
    }
    msgs = _responses_input_to_messages(body)
    assert msgs[0] == {"role": "system", "content": "你是助手"}
    assert msgs[1] == {"role": "user", "content": "你好"}


def test_responses_input_item_array() -> None:
    body = {
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]},
        ],
    }
    msgs = _responses_input_to_messages(body)
    assert msgs == [{"role": "user", "content": "hi"}]


def test_responses_output_shape() -> None:
    """output 必须是 item 数组，不是 choices。"""
    out = _to_responses_output(
        text="回答", reasoning="", usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        model="m", finish_reason="stop",
    )
    assert out["object"] == "response"
    assert out["status"] == "completed"
    assert out["output_text"] == "回答"
    assert out["output"][0]["type"] == "message"
    assert out["output"][0]["content"][0]["type"] == "output_text"
    assert out["usage"]["input_tokens"] == 3
    assert out["usage"]["output_tokens"] == 2


def test_responses_reasoning_item() -> None:
    out = _to_responses_output(
        text="答", reasoning="想了", usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        model="m", finish_reason="stop",
    )
    assert out["output"][0]["type"] == "reasoning"
    assert out["output"][1]["type"] == "message"


def test_responses_incomplete_on_length() -> None:
    out = _to_responses_output(
        text="x", reasoning="", usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        model="m", finish_reason="length",
    )
    assert out["status"] == "incomplete"
    assert out["incomplete_details"] == {"reason": "max_output_tokens"}


# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------


def test_all_endpoints_registered() -> None:
    """四种协议端点都必须挂上。

    注意：新版 FastAPI 把 include_router 的结果包成 ``_IncludedRouter``
    懒加载对象，直接遍历 ``app.routes`` 看不到子路由。用 OpenAPI schema
    是最可靠的检查方式 —— 它一定会展开所有已注册路径。
    """
    from app.main import app

    schema = app.openapi()
    paths = set(schema.get("paths", {}))
    for expected in (
        "/v1/chat/completions",
        "/v1/messages",
        "/v1/responses",
        "/v1/embeddings",
        "/v1/images/generations",
        "/v1/models",
    ):
        assert expected in paths, f"端点未注册：{expected}"


# ---------------------------------------------------------------------------
# 直通通道的错误提示
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_no_provider_gives_actionable_error(monkeypatch) -> None:
    """没配 provider 时，错误要指向「去哪配」。"""
    from app.services.llm_providers import direct

    def _raise():
        raise RuntimeError("没有启用的提供商")

    monkeypatch.setattr(
        "app.services.llm_providers.spec.resolve_active_provider", _raise
    )

    with pytest.raises(direct.DirectLLMError) as exc_info:
        direct._resolve_provider(None)
    msg = str(exc_info.value)
    assert "AI 提供商" in msg
    assert "设为默认" in msg


def test_direct_helpers_handle_dict_and_object() -> None:
    """extract_* 要同时兼容 SDK 对象与裸 dict（上游可能直接回 JSON）。"""
    from app.services.llm_providers import direct

    as_dict = {
        "choices": [{"message": {"content": "文本", "reasoning_content": "推理"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    assert direct.extract_text(as_dict) == "文本"
    assert direct.extract_reasoning(as_dict) == "推理"
    assert direct.extract_usage(as_dict)["total_tokens"] == 8
    assert direct.extract_finish_reason(as_dict) == "stop"

    # 空响应不崩
    assert direct.extract_text({}) == ""
    assert direct.extract_usage({}) == {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    }


def test_extract_handles_wuwei_flat_response() -> None:
    """wuwei 的 LLMResponse 是扁平结构（content / reasoning_content）。

    这是真实踩过的坑：之前按 OpenAI 的 choices[0].message.content 取，
    拿到的永远是空串 —— 表现为「接口 200 但内容为 None」。
    """
    from wuwei.core.types import LLMResponse

    from app.services.llm_providers import direct

    resp = LLMResponse(content="扁平正文", reasoning_content="扁平推理")
    assert direct.extract_text(resp) == "扁平正文"
    assert direct.extract_reasoning(resp) == "扁平推理"


def test_extract_handles_wuwei_chunk() -> None:
    """流式 chunk 同样是扁平 content。"""
    from wuwei.llm.types import LLMResponseChunk

    from app.services.llm_providers import direct

    chunk = LLMResponseChunk(content="增量")
    assert direct.chunk_text(chunk) == "增量"


def test_to_wuwei_messages_converts_roles() -> None:
    """OpenAI messages 必须转成 wuwei 的 BaseMessage —— 网关不吃 dict。"""
    from app.services.llm_providers.direct import _to_wuwei_messages

    converted = _to_wuwei_messages([
        {"role": "system", "content": "规则"},
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
    ])
    assert len(converted) == 3
    # 必须是 wuwei 消息对象，不是 dict
    for item in converted:
        assert not isinstance(item, dict)
        assert hasattr(item, "content")
    assert converted[0].content == "规则"
    assert converted[1].content == "问题"


def test_to_wuwei_messages_flattens_text_blocks() -> None:
    """多段 content 里的 text 块要拼起来。"""
    from app.services.llm_providers.direct import _to_wuwei_messages

    converted = _to_wuwei_messages([
        {"role": "user", "content": [
            {"type": "text", "text": "第一段"},
            {"type": "text", "text": "第二段"},
        ]},
    ])
    assert converted[0].content == "第一段第二段"
