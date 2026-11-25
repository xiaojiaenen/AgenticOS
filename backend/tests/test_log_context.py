"""结构化日志上下文测试（横切 2.4：request_id 贯穿一次请求的全部日志）。"""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.log_context import (
    RequestContextFilter,
    bind_request_context,
    context_fields,
    clear_request_context,
    new_request_id,
)


def test_bind_and_read_fields():
    clear_request_context()
    bind_request_context(request_id="abc123", path="/api/v1/x")
    assert context_fields() == {"request_id": "abc123", "path": "/api/v1/x"}
    # 增量绑定不覆盖
    bind_request_context(session_id="s1")
    assert context_fields()["session_id"] == "s1"
    assert context_fields()["request_id"] == "abc123"
    clear_request_context()
    assert context_fields() == {}


def test_bind_rejects_unknown_keys():
    clear_request_context()
    bind_request_context(evil_key="pwn", request_id="ok")
    assert "evil_key" not in context_fields()
    clear_request_context()


def test_filter_injects_fields_into_records(caplog):
    clear_request_context()
    filt = RequestContextFilter()
    logger = logging.getLogger("test.logctx")
    logger.propagate = True
    bind_request_context(request_id="rid-42", user_id=7)

    with caplog.at_level(logging.INFO, logger="test.logctx"):
        # caplog 的 handler 也要挂 filter 才能拿到字段
        for h in caplog.handler.handlers if hasattr(caplog.handler, "handlers") else [caplog.handler]:
            h.addFilter(filt)
        logger.info("hello")
    record = caplog.records[0]
    assert record.request_id == "rid-42"
    assert record.user_id == 7
    clear_request_context()

    # 未绑定时字段是 "-" 占位，不抛错
    with caplog.at_level(logging.INFO, logger="test.logctx"):
        logger.info("again")
    assert caplog.records[-1].request_id == "-"


def _build_app():
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.middleware("http")
    async def ctx_mw(request, call_next):
        from app.core.log_context import bind_request_context, clear_request_context, new_request_id

        rid = request.headers.get("x-request-id") or new_request_id()
        bind_request_context(request_id=rid, path=request.url.path)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            clear_request_context()

    @app.get("/ping")
    async def ping():
        # 业务深处读上下文：模拟 Agent 会话绑定 session_id
        bind_request_context(session_id="sess-9")
        fields = context_fields()
        return JSONResponse({"request_id": fields.get("request_id"), "session_id": fields.get("session_id")})

    return app


@pytest.mark.asyncio
async def test_request_middleware_roundtrip():

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ping")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "sess-9"
        assert body["request_id"]  # 自动生成
        assert resp.headers["X-Request-ID"] == body["request_id"]

        # 客户端传入的 request-id 被沿用
        resp2 = await client.get("/ping", headers={"X-Request-ID": "my-trace-id"})
        assert resp2.headers["X-Request-ID"] == "my-trace-id"
        assert resp2.json()["request_id"] == "my-trace-id"

    # 请求结束后上下文必须被清理（无脏字段泄漏到下一个无关任务）
    assert context_fields() == {}


def test_new_request_id_shape():
    rid = new_request_id()
    assert len(rid) == 16
    assert rid != new_request_id()
