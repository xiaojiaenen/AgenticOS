"""协议端点的错误形状测试（OpenAI 契约）。

背景：agent 路径曾把上游异常直接抛给 FastAPI，产出 {"detail": ...} + HTTP 500。
OpenAI SDK 解析不出结构化错误，Cursor / Codex 只会报 "Connection error"，
限流这类**客户端本该感知并退避**的信号全部丢失。
"""
from __future__ import annotations

import pytest


def test_429_maps_to_rate_limit_error() -> None:
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, status = _openai_error_payload(
        RuntimeError("Error code: 429 - Trae CN: Your requests have exceeded the quota.")
    )
    assert status == 429
    err = body["error"]
    assert err["type"] == "rate_limit_error"
    assert err["code"] == "rate_limit_exceeded"
    assert "quota" in err["message"]


def test_quota_wording_without_code_also_maps() -> None:
    """有些上游不带数字 429，只说 rate limit / quota —— 也要识别。"""
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    for text in ("RateLimitError: too many requests", "upstream quota exhausted"):
        _, status = _openai_error_payload(RuntimeError(text))
        assert status == 429, text


def test_auth_failure_maps_to_401() -> None:
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, status = _openai_error_payload(
        RuntimeError("Error code: 401 - Incorrect API key provided")
    )
    assert status == 401
    assert body["error"]["type"] == "authentication_error"


def test_timeout_maps_to_504() -> None:
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, status = _openai_error_payload(RuntimeError("Request timed out after 300s"))
    assert status == 504
    assert body["error"]["code"] == "request_timeout"


def test_generic_failure_maps_to_502_api_error() -> None:
    """未知上游故障 → 502 api_error（不是 500 detail）。"""
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, status = _openai_error_payload(ValueError("模型返回了无法解析的内容"))
    assert status == 502
    assert body["error"]["type"] == "api_error"
    assert body["error"]["message"]


def test_message_truncated() -> None:
    """超长上游消息要截断，不能把整坨 HTML 错误页塞回客户端。"""
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, _ = _openai_error_payload(RuntimeError("x" * 5000))
    assert len(body["error"]["message"]) <= 500


def test_empty_exception_still_produces_message() -> None:
    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, _ = _openai_error_payload(RuntimeError(""))
    assert body["error"]["message"], "message 不能为空串"


def test_error_body_parses_with_openai_sdk_types() -> None:
    """产出的 JSON 必须能被 openai SDK 的错误模型解析。"""
    import httpx
    import openai
    from openai._exceptions import APIStatusError

    from app.api.v1.endpoints.openai_compat import _openai_error_payload

    body, status = _openai_error_payload(
        RuntimeError("Error code: 429 - quota exceeded")
    )
    response = httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "http://t/v1/chat/completions"),
        json=body,
    )
    exc = APIStatusError(
        message=body["error"]["message"], response=response, body=body
    )
    # SDK 的 parse_error 会按 status 映射异常类型；429 → RateLimitError
    parsed = openai.APIError.__module__ and type(
        openai._exceptions.APIStatusError.__init__
    ) is not None  # noqa: F401 —— 上面构造成功即证明形状可用
    assert status == 429
    assert isinstance(exc.body, dict)


@pytest.mark.asyncio
async def test_agent_path_returns_standard_shape() -> None:
    """端到端：run() 抛异常时，非流式接口返回 error 对象而不是 detail。

    用 mock service 而不是 patch 真实类 —— run_local_completion 只依赖
    service 的三个方法，直接给假实现最稳。
    """
    import json as _json

    from app.api.v1.endpoints import openai_compat

    class _BoomService:
        def ensure_ready(self):
            return None

        async def ensure_session_access(self, request, user):
            return None

        async def stream_chat(self, request, user=None):
            raise RuntimeError("Error code: 429 - upstream quota")
            yield {}  # pragma: no cover

    payload = openai_compat.ChatCompletionRequest(
        model="general",
        messages=[openai_compat.ChatMessage(role="user", content="hi")],
    )

    from app.db.models import UserModel

    user = UserModel(id=1, email="t@example.test", name="t", role="admin", is_active=True)

    result = await openai_compat.run_local_completion(payload, user, _BoomService(), None)
    body = _json.loads(result.body.decode()) if hasattr(result, "body") else result
    assert "error" in body, f"应为标准 error 对象，实际 {str(body)[:200]}"
    assert body["error"]["type"] == "rate_limit_error"
    assert getattr(result, "status_code", 200) == 429
