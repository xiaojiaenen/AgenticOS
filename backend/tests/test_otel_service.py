"""OpenTelemetry 纯库接入回归（docs/design/项目逐功能优化方案.md 战线 D / 3F.0）。

- 未启用（默认）：get_tracer 返回 no-op，instrument_gateway 原样返回；
- 启用：span 经 DBSpanExporter 落库 otel_spans（自家 DB，无外部系统）；
- instrument_gateway：generate 包装后语义不变（透传结果/异常）；
- exporter 异常吞掉并计数（span 丢失不影响业务）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult

from app.services import otel_service


@pytest.fixture(autouse=True)
def _reset():
    otel_service._initialized = False
    otel_service._tracer_provider = None
    otel_service._tracer = None
    yield
    otel_service._initialized = False
    otel_service._tracer_provider = None
    otel_service._tracer = None


def _make_span(name="llm.call", attrs=None, error=None):
    """构造一个 ended ReadableSpan（不依赖 SDK 内部 API 细节太多）。"""
    provider = TracerProvider()
    spans: list[ReadableSpan] = []
    provider.add_span_processor(_CaptureProcessor(spans))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span(name) as span:
        for key, value in (attrs or {}).items():
            span.set_attribute(key, value)
        if error:
            span.record_exception(error)
    provider.shutdown()
    return spans[0]


from opentelemetry.sdk.trace.export import SpanProcessor


class _CaptureProcessor(SpanProcessor):
    """SDK SpanProcessor ABC 的捕获实现（当前版本要求完整接口）。"""

    def __init__(self, sink):
        self.sink = sink

    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        self.sink.append(span)

    def shutdown(self) -> bool:
        return True

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


# ── 开关语义 ──────────────────────────────────────────────────────────


def test_disabled_by_default_returns_noop_tracer():
    with patch.object(otel_service, "is_enabled", return_value=False):
        from opentelemetry.trace import NoOpTracer

        assert isinstance(otel_service.get_tracer("x"), NoOpTracer)


def test_init_otel_noop_when_disabled():
    with patch.object(otel_service, "is_enabled", return_value=False):
        otel_service.init_otel()
    assert otel_service._initialized is False


# ── instrument_gateway ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_instrument_gateway_disabled_is_identity():
    with patch.object(otel_service, "is_enabled", return_value=False):
        calls = []

        async def generate(*args, **kwargs):
            calls.append(kwargs)
            return "resp"

        gateway = SimpleNamespace(generate=generate, provider="p", model_name="m")
        wrapped = otel_service.instrument_gateway(gateway)
        assert wrapped is gateway  # 未启用：原样返回，零开销


@pytest.mark.asyncio
async def test_instrument_gateway_enabled_passthrough_and_span():
    captured: list[ReadableSpan] = []
    with (
        patch.object(otel_service, "is_enabled", return_value=True),
        patch.object(
            otel_service,
            "get_tracer",
            return_value=_tracer_with_sink(captured),
        ),
    ):
        async def generate(*args, **kwargs):
            return {"ok": True}

        gateway = SimpleNamespace(generate=generate, provider="deepseek", model_name="flash")
        wrapped = otel_service.instrument_gateway(gateway)
        result = await wrapped.generate(messages=[], tools=None, stream=False)
        assert result == {"ok": True}  # 语义不变
        assert captured and captured[0].name == "llm.call"
        attrs = dict(captured[0].attributes or {})
        assert attrs["llm.provider"] == "deepseek"
        assert attrs["llm.model"] == "flash"
        assert attrs["llm.stream"] is False
        assert wrapped._otel_wrapped is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_instrument_gateway_records_exception():
    captured: list[ReadableSpan] = []
    with (
        patch.object(otel_service, "is_enabled", return_value=True),
        patch.object(otel_service, "get_tracer", return_value=_tracer_with_sink(captured)),
    ):
        async def generate(*args, **kwargs):
            raise RuntimeError("boom")

        gateway = SimpleNamespace(generate=generate, provider="p", model_name="m")
        wrapped = otel_service.instrument_gateway(gateway)
        with pytest.raises(RuntimeError):
            await wrapped.generate(messages=[])
        assert captured and captured[0].attributes["error.type"] == "RuntimeError"


def _tracer_with_sink(sink):
    provider = TracerProvider()
    provider.add_span_processor(_CaptureProcessor(sink))
    return provider.get_tracer("test")


# ── DBSpanExporter ────────────────────────────────────────────────────


def test_exporter_writes_spans_to_db():
    span = _make_span("llm.call", {"llm.provider": "p", "llm.model": "m"})
    exporter = otel_service.DBSpanExporter()
    result = exporter.export([span])
    assert result == SpanExportResult.SUCCESS

    from sqlalchemy import select

    from app.db.models import OtelSpanModel
    from app.db.session import create_db_session

    with create_db_session() as db:
        row = db.scalar(
            select(OtelSpanModel).where(OtelSpanModel.name == "llm.call").order_by(OtelSpanModel.id.desc())
        )
        assert row is not None
        assert row.trace_id and len(row.trace_id) == 32
        attrs = json.loads(row.attributes_json)
        assert attrs["llm.provider"] == "p"
        assert row.duration_ms is not None


def test_exporter_swallows_db_failure():
    """落库失败 → FAILURE 但不抛异常（span 丢失不影响业务）。"""
    span = _make_span("bad")
    exporter = otel_service.DBSpanExporter()
    with patch("app.db.session.create_db_session", side_effect=RuntimeError("db down")):
        result = exporter.export([span])
    assert result == SpanExportResult.FAILURE


def test_exporter_skips_unparseable_span():
    """解析失败的 span 被跳过而不是炸掉整批。"""
    garbage = SimpleNamespace(get_span_context=lambda: None)
    exporter = otel_service.DBSpanExporter()
    result = exporter.export([garbage, _make_span("ok")])
    assert result == SpanExportResult.SUCCESS
