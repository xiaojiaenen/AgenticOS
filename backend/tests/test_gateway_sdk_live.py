"""真实 SDK 客户端调用我们的网关（本地起服务 + 真 HTTP）。

这是最高一级的验证：不是解析我们构造的 JSON，而是让 anthropic / openai
的 SDK 客户端**真的发请求**到我们的端点，走完整 HTTP + 流式解析链路。

与 test_gateway_sdk_contract 的分工：
- contract 测试：验证响应形状能被 SDK 模型解析（快，无需起服务）
- 这个测试：验证 SDK 客户端的完整调用路径（含 header 鉴权、SSE 解析）
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip("anthropic")
pytest.importorskip("openai")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    """起一个真实的 uvicorn 服务（模块级，只起一次）。"""
    import uvicorn

    from app.main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            with urllib.request.urlopen(base + "/api/v1/health/", timeout=2):
                break
        except Exception:
            time.sleep(0.25)
    else:
        pytest.skip("服务未能启动")

    yield base, port

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture()
def api_key():
    """建一个真实 API Key（必要时先建用户）。

    自己建用户而不是依赖库里已有数据 —— 否则测试在干净环境里全部 skip，
    等于没测。
    """
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.models import UserModel
    from app.db.session import create_db_session
    from app.services.api_key_service import create_api_key

    with create_db_session() as db:
        user = db.execute(select(UserModel).order_by(UserModel.id).limit(1)).scalar_one_or_none()
        if user is None:
            user = UserModel(
                email="sdk-live@example.test",
                name="SDK Live Test",
                password_hash=hash_password("SdkLive!2026"),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        uid = user.id

    result = create_api_key(uid, name=f"sdk-live-{int(time.time())}")
    key = result["key"] if isinstance(result, dict) else getattr(result, "key", None)
    if not key:
        pytest.skip("无法创建 API Key")
    return key


def test_anthropic_sdk_calls_our_gateway(live_server, api_key) -> None:
    """anthropic SDK 客户端能连上 /v1/messages 并解析响应。

    重点验证：SDK 用 ``x-api-key`` 头（不是 Bearer），且会严格解析
    Message 结构。上游不可用时跳过（这里测的是协议兼容性，不是模型能力）。
    """
    import anthropic

    base, _ = live_server
    client = anthropic.Anthropic(api_key=api_key, base_url=base)

    try:
        msg = client.messages.create(
            model="llm:test-model",
            max_tokens=32,
            messages=[{"role": "user", "content": "hi"}],
        )
    except anthropic.APIStatusError as exc:
        # 上游不可用（没配 provider / 模型不存在）—— 协议层没问题，
        # 用错误形状本身验证：SDK 能把我们的错误 JSON 解析成它的错误类型
        assert exc.status_code in (400, 401, 403, 500, 502, 503)
        return
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"上游不可用，跳过真实调用：{type(exc).__name__}")

    # 走到这里说明上游可用 —— 严格校验响应结构
    assert msg.type == "message"
    assert msg.role == "assistant"
    assert isinstance(msg.content, list)
    assert msg.usage.input_tokens >= 0
    assert msg.usage.output_tokens >= 0


def test_openai_sdk_calls_responses(live_server, api_key) -> None:
    """openai SDK 客户端能连上 /v1/responses 并解析响应。"""
    import openai

    base, _ = live_server
    client = openai.OpenAI(api_key=api_key, base_url=base + "/v1")

    try:
        resp = client.responses.create(
            model="llm:test-model",
            input="hi",
            max_output_tokens=32,
        )
    except openai.APIStatusError as exc:
        assert exc.status_code in (400, 401, 403, 500, 502, 503)
        return
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"上游不可用，跳过真实调用：{type(exc).__name__}")

    assert resp.object == "response"
    assert isinstance(resp.output, list)


def test_openai_sdk_calls_chat_completions(live_server, api_key) -> None:
    """openai SDK 客户端能连上 /v1/chat/completions（纯模型通道）。"""
    import openai

    base, _ = live_server
    client = openai.OpenAI(api_key=api_key, base_url=base + "/v1")

    try:
        completion = client.chat.completions.create(
            model="llm:test-model",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=32,
        )
    except openai.APIStatusError as exc:
        assert exc.status_code in (400, 401, 403, 500, 502, 503)
        return
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"上游不可用，跳过真实调用：{type(exc).__name__}")

    assert completion.object == "chat.completion"
    assert len(completion.choices) >= 1
    assert completion.choices[0].message.role == "assistant"


def test_unauthorized_errors_parse_in_sdk(live_server) -> None:
    """错误响应的形状也要能被 SDK 解析成它的错误类型。

    这是容易被忽略的一点：只对齐成功响应不够，客户端在鉴权失败时
    也会解析错误体。形状不对会抛「无法解析错误」而不是「401」。
    """
    import anthropic
    import openai

    base, _ = live_server

    anth = anthropic.Anthropic(api_key="sk-invalid", base_url=base)
    try:
        anth.messages.create(model="x", max_tokens=8, messages=[{"role": "user", "content": "hi"}])
        pytest.fail("无效 key 不该成功")
    except anthropic.AuthenticationError:
        pass  # SDK 正确解析成鉴权错误
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"SDK 未能解析成 AuthenticationError：{type(exc).__name__}: {exc}")

    oai = openai.OpenAI(api_key="sk-invalid", base_url=base + "/v1")
    try:
        oai.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        pytest.fail("无效 key 不该成功")
    except openai.AuthenticationError:
        pass
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"SDK 未能解析成 AuthenticationError：{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 用 mock 上游验证协议层（不依赖外部模型服务）
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_upstream(monkeypatch):
    """把直通通道的上游替换成固定响应，验证协议层端到端可用。

    为什么需要：真实上游不可用时，上面几个测试会 skip —— 但「协议层对不对」
    不该依赖外部服务。这里用 monkeypatch 固定上游返回，让 SDK 客户端
    真实走完 HTTP + 解析链路。
    """
    from app.services.llm_providers import direct

    class _FakeResp:
        content = "你好，我是助手"
        reasoning_content = ""
        usage = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
        finish_reason = "stop"

    async def _fake_complete(db, *, messages, model=None, role="chat", stream=False, **kw):
        if stream:
            async def _gen():
                for piece in ("你好", "，我是", "助手"):
                    class _C:
                        content = piece
                    yield _C()
            return None, model or "mock-model", _gen()
        return None, model or "mock-model", _FakeResp()

    monkeypatch.setattr(direct, "complete", _fake_complete)


def test_anthropic_sdk_end_to_end_with_mock(live_server, api_key, mock_upstream) -> None:
    """anthropic SDK 真实调用 /v1/messages（mock 上游），验证完整协议链路。"""
    import anthropic

    base, _ = live_server
    client = anthropic.Anthropic(api_key=api_key, base_url=base)

    msg = client.messages.create(
        model="llm:mock-model",
        max_tokens=64,
        messages=[{"role": "user", "content": "hi"}],
    )
    assert msg.type == "message"
    assert msg.role == "assistant"
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    assert "你好" in text
    assert msg.usage.input_tokens == 12
    assert msg.usage.output_tokens == 8


def test_anthropic_sdk_streaming_with_mock(live_server, api_key, mock_upstream) -> None:
    """anthropic SDK 的流式调用也要能解析我们的事件序列。"""
    import anthropic

    base, _ = live_server
    client = anthropic.Anthropic(api_key=api_key, base_url=base)

    chunks: list[str] = []
    with client.messages.stream(
        model="llm:mock-model",
        max_tokens=64,
        messages=[{"role": "user", "content": "hi"}],
    ) as stream:
        for event in stream:
            if getattr(event, "type", "") == "content_block_delta":
                delta = getattr(event, "delta", None)
                text = getattr(delta, "text", "") if delta else ""
                if text:
                    chunks.append(text)

    assert "".join(chunks) == "你好，我是助手"


def test_openai_sdk_responses_with_mock(live_server, api_key, mock_upstream) -> None:
    """openai SDK 真实调用 /v1/responses（mock 上游）。"""
    import openai

    base, _ = live_server
    client = openai.OpenAI(api_key=api_key, base_url=base + "/v1")

    resp = client.responses.create(
        model="llm:mock-model",
        input="hi",
        max_output_tokens=64,
    )
    assert resp.object == "response"
    assert resp.output_text == "你好，我是助手"
    assert isinstance(resp.output, list) and len(resp.output) >= 1


def test_openai_sdk_responses_streaming_with_mock(live_server, api_key, mock_upstream) -> None:
    """Responses 流式：SDK 会按 sequence_number 顺序解析事件。"""
    import openai

    base, _ = live_server
    client = openai.OpenAI(api_key=api_key, base_url=base + "/v1")

    collected: list[str] = []
    with client.responses.stream(
        model="llm:mock-model", input="hi", max_output_tokens=64,
    ) as stream:
        for event in stream:
            if getattr(event, "type", "") == "response.output_text.delta":
                collected.append(event.delta)

    assert "".join(collected) == "你好，我是助手"


def test_openai_sdk_chat_with_mock(live_server, api_key, mock_upstream) -> None:
    """openai SDK 真实调用 /v1/chat/completions（纯模型通道）。"""
    import openai

    base, _ = live_server
    client = openai.OpenAI(api_key=api_key, base_url=base + "/v1")

    completion = client.chat.completions.create(
        model="llm:mock-model",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64,
    )
    assert completion.choices[0].message.content == "你好，我是助手"
    assert completion.usage.prompt_tokens == 12
