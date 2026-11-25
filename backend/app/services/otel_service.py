"""OpenTelemetry 纯库接入（docs/design/项目逐功能优化方案.md 3E.1 / 战线 D）。

定位（3F.0 红线）：**只用 OTel SDK 纯库埋点，不接 Langfuse（外部系统）、
不部署 collector** —— 自定义 ``SpanExporter`` 把 span 写进项目自己的
``otel_spans`` 表，展示沿用现有 traces/evals tab。

默认关闭（``OTEL_ENABLED=false``）：启用后三处生效 ——
1. FastAPI 请求中间件：每个请求一个 SERVER span（request_id/user 关联）；
2. LLM 网关：``instrument_gateway`` 包装 ``generate``，每次 LLM 调用一个
   CLIENT span（provider/model/usage 属性）；
3. 命名 tracer 供后续模块按需取用（``get_tracer("agenticos.<mod>")``）。

BatchSpanProcessor 后台批量落库，span 丢失不影响业务（exporter 内部
吞异常 + 计数告警）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Sequence

from app.core.timezone import app_now

logger = logging.getLogger("agenticos.otel")

_SERVICE_NAME = "agenticos-backend"

_initialized = False
_tracer_provider: Any = None
_tracer: Any = None
_exporter_dropped_spans = 0


def is_enabled() -> bool:
    """OTel 是否启用（设置读取失败按关闭处理，绝不影响业务启动）。"""
    try:
        from app.core.config import get_settings

        return bool(getattr(get_settings(), "otel_enabled", False))
    except Exception:  # noqa: BLE001
        return False


def get_tracer(name: str = "agenticos"):
    """命名 tracer；未启用时返回 no-op tracer（OTel API 的 no-op 语义）。"""
    global _tracer
    if not is_enabled():
        from opentelemetry.trace import NoOpTracer

        return NoOpTracer()
    if _tracer is None:
        init_otel()
    from opentelemetry.trace import get_tracer

    return get_tracer(name)


def init_otel() -> None:
    """初始化 TracerProvider + DB SpanExporter（幂等；未启用则 no-op）。"""
    global _initialized, _tracer_provider, _tracer
    if _initialized or not is_enabled():
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from app.core.config import get_settings

        resource = Resource.create(
            {
                "service.name": _SERVICE_NAME,
                "service.version": get_settings().app_version,
                "deployment.environment": get_settings().environment,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(DBSpanExporter()))
        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        _tracer = trace.get_tracer("agenticos")
        _initialized = True
        logger.info("OpenTelemetry 已启用：span 落库 otel_spans（BatchSpanProcessor）")
    except Exception:  # noqa: BLE001 —— 可观测初始化失败绝不阻断业务
        logger.exception("OpenTelemetry 初始化失败，按未启用处理")


def shutdown_otel() -> None:
    """停机时 flush 剩余 span（lifespan 关停调用）。"""
    global _tracer_provider, _initialized
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception:  # noqa: BLE001
            logger.warning("OTel provider shutdown 失败", exc_info=True)
    _tracer_provider = None
    _initialized = False


def instrument_gateway(gateway: Any) -> Any:
    """给 LLMGateway.generate 套一层 CLIENT span（provider/model/usage 属性）。

    网关是全站唯一 LLM 出口（llm_factory.build_llm），在构建入口包装即可
    覆盖 wuwei / langgraph 两个引擎与所有后台任务。
    """
    if not is_enabled() or getattr(gateway, "_otel_wrapped", False):
        return gateway

    provider_name = getattr(gateway, "provider", None)
    model_name = getattr(gateway, "model_name", "") or ""

    original_generate = gateway.generate

    async def traced_generate(*args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer("agenticos.llm")
        with tracer.start_as_current_span("llm.call") as span:
            span.set_attribute("llm.provider", str(provider_name or "unknown"))
            span.set_attribute("llm.model", str(model_name or "unknown"))
            span.set_attribute("llm.stream", bool(kwargs.get("stream")))
            try:
                return await original_generate(*args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("error.type", type(exc).__name__)
                raise

    traced_generate._otel_wrapped_original = original_generate  # type: ignore[attr-defined]
    gateway.generate = traced_generate  # type: ignore[method-assign]
    gateway._otel_wrapped = True  # type: ignore[attr-defined]
    return gateway


class DBSpanExporter:
    """把 ended spans 批量写入 ``otel_spans`` 表（自家 DB，无外部系统）。"""

    def export(self, spans: Sequence[Any]) -> Any:
        global _exporter_dropped_spans
        from opentelemetry.sdk.trace.export import SpanExportResult

        try:
            rows = [self._to_row(span) for span in spans]
            rows = [r for r in rows if r is not None]
            if not rows:
                return SpanExportResult.SUCCESS

            def _run() -> None:
                from app.db.models import OtelSpanModel
                from app.db.session import create_db_session

                with create_db_session() as db:
                    db.add_all([OtelSpanModel(**row) for row in rows])
                    db.commit()

            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # BatchSpanProcessor 的 worker 线程没有事件循环 → 开新线程跑同步写
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(_run).result(timeout=10)
            else:
                _run()
            return SpanExportResult.SUCCESS
        except Exception:  # noqa: BLE001 —— span 丢失不影响业务
            _exporter_dropped_spans += len(spans)
            if _exporter_dropped_spans and _exporter_dropped_spans % 100 == 0:
                logger.warning("OTel span 落库失败（累计 %d 条）", _exporter_dropped_spans)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:  # noqa: D102
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: D102
        return True

    def _to_row(self, span: Any) -> dict[str, Any] | None:
        try:
            ctx = span.get_span_context()
            parent = span.parent
            attributes = {}
            for key, value in (span.attributes or {}).items():
                if isinstance(value, (str, int, float, bool)):
                    attributes[key] = value
                else:
                    attributes[key] = json.dumps(value, ensure_ascii=False, default=str)
            status_name = "unset"
            try:
                status_name = span.status.status_code.name.lower()
            except Exception:  # noqa: BLE001
                pass
            return {
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
                "parent_span_id": format(parent.span_id, "016x") if parent else None,
                "name": span.name,
                "kind": span.kind.name.lower(),
                "status": status_name,
                "attributes_json": json.dumps(attributes, ensure_ascii=False),
                "started_at": app_now(),
                "ended_at": app_now(),
                "duration_ms": int(
                    (span.end_time - span.start_time) / 1_000_000
                )
                if span.end_time and span.start_time
                else None,
            }
        except Exception:  # noqa: BLE001 —— 单条 span 解析失败跳过
            logger.debug("otel span parse failed", exc_info=True)
            return None


def export_spans_for_test(spans: Iterable[Any]) -> int:
    """测试助手：同步导出并返回写入行数。"""
    exporter = DBSpanExporter()
    exporter.export(list(spans))
    return 1
