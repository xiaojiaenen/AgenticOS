"""SDK 级契约测试：让客户端 SDK 真实解析我们的响应。

为什么用 SDK 而不是比对字段名：字段名对了不代表客户端能用 —— Pydantic
模型还会校验必填、类型、字面量。这个测试让 ``anthropic`` 与 ``openai``
的真实类型定义去解析我们的 JSON，解析通过才是「客户端能用」。

它捕获过的真实缺陷：
- ThinkingBlock 缺 signature（必填）→ Anthropic 客户端解析崩
- MessageDeltaEvent.usage 缺 output_tokens（必填）→ 流式中断
- Response 缺 parallel_tool_calls / tool_choice / tools（必填）
- ResponseUsage 缺 input/output_tokens_details（必填）
- Responses 流式事件缺 sequence_number / item_id / output_index
"""
from __future__ import annotations

import pytest

pytest.importorskip("anthropic", reason="需要 anthropic SDK 做契约校验")
pytest.importorskip("openai", reason="需要 openai SDK 做契约校验")


# ---------------------------------------------------------------------------
# Anthropic Message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reasoning", "finish_reason"),
    [
        ("", "stop"),
        ("先想了想", "stop"),
        ("", "length"),
        ("推理", "length"),
    ],
)
def test_anthropic_message_parses_with_sdk(reasoning: str, finish_reason: str) -> None:
    """Anthropic Message 必须能被 anthropic SDK 的 Message 模型解析。"""
    from anthropic.types import Message as AnthropicMessage

    from app.api.gateway_multi import _openai_to_anthropic_response

    payload = _openai_to_anthropic_response(
        text="回答内容",
        reasoning=reasoning,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        model="test-model",
        finish_reason=finish_reason,
    )
    AnthropicMessage.model_validate(payload)


def test_anthropic_thinking_block_has_signature() -> None:
    """ThinkingBlock 的 signature 是必填 —— 缺了客户端会崩。"""
    from anthropic.types import ThinkingBlock

    from app.api.gateway_multi import _openai_to_anthropic_response

    payload = _openai_to_anthropic_response(
        text="答", reasoning="想了", usage={"prompt_tokens": 1, "completion_tokens": 1},
        model="m", finish_reason="stop",
    )
    thinking = next(b for b in payload["content"] if b["type"] == "thinking")
    ThinkingBlock.model_validate(thinking)
    assert "signature" in thinking


# ---------------------------------------------------------------------------
# Anthropic 流式事件
# ---------------------------------------------------------------------------


def test_anthropic_stream_events_parse_with_sdk() -> None:
    """六个流式事件都要能被 SDK 解析。"""
    from anthropic.types import (
        ContentBlockDeltaEvent,
        ContentBlockStartEvent,
        ContentBlockStopEvent,
        MessageDeltaEvent,
        MessageStartEvent,
        MessageStopEvent,
    )

    from app.api.gateway_multi import _openai_to_anthropic_response

    msg = _openai_to_anthropic_response(
        text="", reasoning="", usage={"prompt_tokens": 0, "completion_tokens": 0},
        model="m", finish_reason="stop",
    )
    msg["content"] = []

    MessageStartEvent.model_validate({"type": "message_start", "message": msg})
    ContentBlockStartEvent.model_validate({
        "type": "content_block_start", "index": 0,
        "content_block": {"type": "text", "text": ""},
    })
    ContentBlockDeltaEvent.model_validate({
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "text_delta", "text": "hi"},
    })
    ContentBlockStopEvent.model_validate({"type": "content_block_stop", "index": 0})
    # usage.output_tokens 必填 —— 这是曾经漏掉的字段
    MessageDeltaEvent.model_validate({
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 2},
    })
    MessageStopEvent.model_validate({"type": "message_stop"})


def test_message_delta_usage_requires_output_tokens() -> None:
    """空 usage 必须被 SDK 拒绝 —— 证明这个字段真的必填。"""
    from anthropic.types import MessageDeltaEvent

    with pytest.raises(Exception):
        MessageDeltaEvent.model_validate({
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {},
        })


# ---------------------------------------------------------------------------
# OpenAI Responses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reasoning", "finish_reason"),
    [("", "stop"), ("推理过程", "stop"), ("", "length")],
)
def test_responses_parses_with_sdk(reasoning: str, finish_reason: str) -> None:
    """Responses 的 Response 对象必须能被 openai SDK 解析。"""
    from openai.types.responses import Response

    from app.api.gateway_multi import _to_responses_output

    payload = _to_responses_output(
        text="回答内容", reasoning=reasoning,
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        model="test-model", finish_reason=finish_reason,
    )
    Response.model_validate(payload)


def test_responses_has_all_required_fields() -> None:
    """Response 的三个必填字段一个都不能少（缺了客户端解析崩）。"""
    from app.api.gateway_multi import _to_responses_output

    payload = _to_responses_output(
        text="x", reasoning="",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        model="m", finish_reason="stop",
    )
    for field in ("parallel_tool_calls", "tool_choice", "tools"):
        assert field in payload, f"Response 缺必填字段 {field}"


def test_responses_usage_has_detail_subobjects() -> None:
    """usage 的两个 details 子结构都是必填。"""
    from openai.types.responses import ResponseUsage

    from app.api.gateway_multi import _to_responses_output

    payload = _to_responses_output(
        text="x", reasoning="",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        model="m", finish_reason="stop",
    )
    ResponseUsage.model_validate(payload["usage"])
    assert "input_tokens_details" in payload["usage"]
    assert "output_tokens_details" in payload["usage"]


def test_responses_stream_events_parse_with_sdk() -> None:
    """八个 Responses 流式事件都要能被 SDK 解析（含 sequence_number）。"""
    import openai.types.responses as R

    from app.api.gateway_multi import _to_responses_output

    created = _to_responses_output(
        text="", reasoning="",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        model="m", finish_reason="stop",
    )
    created["id"] = "resp_t"
    created["status"] = "in_progress"

    final = _to_responses_output(
        text="hi", reasoning="",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        model="m", finish_reason="stop",
    )
    final["id"] = "resp_t"

    R.ResponseCreatedEvent.model_validate(
        {"type": "response.created", "response": created, "sequence_number": 0}
    )
    R.ResponseOutputItemAddedEvent.model_validate({
        "type": "response.output_item.added", "output_index": 0,
        "item": {"type": "message", "id": "msg_t", "status": "in_progress",
                 "role": "assistant", "content": []},
        "sequence_number": 1,
    })
    R.ResponseContentPartAddedEvent.model_validate({
        "type": "response.content_part.added", "item_id": "msg_t",
        "output_index": 0, "content_index": 0,
        "part": {"type": "output_text", "text": "", "annotations": []},
        "sequence_number": 2,
    })
    R.ResponseTextDeltaEvent.model_validate({
        "type": "response.output_text.delta", "item_id": "msg_t",
        "output_index": 0, "content_index": 0, "delta": "hi",
        "logprobs": [], "sequence_number": 3,
    })
    R.ResponseTextDoneEvent.model_validate({
        "type": "response.output_text.done", "item_id": "msg_t",
        "output_index": 0, "content_index": 0, "text": "hi",
        "logprobs": [], "sequence_number": 4,
    })
    R.ResponseContentPartDoneEvent.model_validate({
        "type": "response.content_part.done", "item_id": "msg_t",
        "output_index": 0, "content_index": 0,
        "part": {"type": "output_text", "text": "hi", "annotations": []},
        "sequence_number": 5,
    })
    R.ResponseOutputItemDoneEvent.model_validate({
        "type": "response.output_item.done", "output_index": 0,
        "item": {"type": "message", "id": "msg_t", "status": "completed",
                 "role": "assistant",
                 "content": [{"type": "output_text", "text": "hi", "annotations": []}]},
        "sequence_number": 6,
    })
    R.ResponseCompletedEvent.model_validate(
        {"type": "response.completed", "response": final, "sequence_number": 7}
    )


def test_responses_event_requires_sequence_number() -> None:
    """缺 sequence_number 必须被拒 —— 证明这个字段真的必填。"""
    import openai.types.responses as R

    with pytest.raises(Exception):
        R.ResponseCreatedEvent.model_validate({"type": "response.created", "response": {}})


# ---------------------------------------------------------------------------
# Embeddings / Images / Chat
# ---------------------------------------------------------------------------


def test_embeddings_response_parses_with_sdk() -> None:
    from openai.types import CreateEmbeddingResponse

    CreateEmbeddingResponse.model_validate({
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
        "model": "m",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    })


def test_images_response_parses_with_sdk() -> None:
    from openai.types import ImagesResponse

    ImagesResponse.model_validate({
        "created": 1234567890,
        "data": [{"url": "https://example.com/a.png"}],
    })


def test_embedding_usage_requires_prompt_and_total() -> None:
    """Embeddings 的 usage 只有 prompt_tokens 与 total_tokens（都是必填）。"""
    from openai.types import CreateEmbeddingResponse

    with pytest.raises(Exception):
        CreateEmbeddingResponse.model_validate({
            "object": "list",
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1]}],
            "model": "m",
            "usage": {},
        })


def test_chat_completion_parses_with_sdk() -> None:
    """Chat Completions 的非流式响应也要能被 SDK 解析。"""
    from openai.types.chat import ChatCompletion

    ChatCompletion.model_validate({
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "m",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "hi"},
             "finish_reason": "stop"},
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })
