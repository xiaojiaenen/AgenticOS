"""原生 LLM 网关（wuwei 退役 A5-2）。

一个类承接原 ``wuwei LLMGateway + HardenedOpenAIAdapter + RetryingGateway``
三层职责，openai SDK 直连，**全部加固语义逐条保留**：

1. **usage 收尾帧**：请求带 ``stream_options.include_usage``，usage-only 帧
   不丢（原 wuwei 会跳过它，token 统计恒为 0）；
2. **工具调用收尾纠正**：流中出现工具调用增量而收尾只给 ``stop`` → 纠正为
   ``tool_calls``（否则工具调用被静默丢弃）；``length`` + 工具调用 → 保持
   ``length`` 并告警（截断的调用参数可能不完整，不执行是上游设计决定）；
3. **非流式宽容解析**：usage 缺失不崩（逐字段 getattr）；工具参数 JSON 坏
   时告警并按空参处理；``reasoning_content`` 别名兜底（reasoning/thinking）；
4. **system 消息合并**：OpenAI 兼容端要求 system 唯一且在首位，多条时合并；
5. **流式重试**：``llm_stream_retry_attempts``（默认 2）——只在「还没吐字」
   时重试，指数退避；已产出内容绝不重试（用户会看到半句重来、工具执行两次）；
6. **错误分类与包装**：按异常层级兜底判定（openai/httpx/文本），统一包成
   ``LLMError``（保留 __cause__ / provider / status_code / attempts / retryable）；
7. **usage 上游 total 保留**：聚合时不再强制 ``total = prompt + completion``，
   上报的 total（含 cached/reasoning tokens）原样透传。

请求构造只支持 openai 兼容协议（项目所有 provider 都是 OpenAI 兼容或
Cookie 型 OpenAI 兼容端点）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.services.agent.native.types import (
    FINISH_REASONS,
    BaseMessage,
    LLMError,
    LLMResponse,
    LLMResponseChunk,
    normalize_finish_reason,
)
from app.services.agent.native.tool_registry import Tool

logger = logging.getLogger("agenticos.llm.native")


# ── 请求构造 ──────────────────────────────────────────────────────────


def normalize_system_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """多条 system 合并为开头一条（OpenAI 兼容端硬校验）。"""
    if not messages:
        return messages
    system_indexes = [i for i, m in enumerate(messages) if getattr(m, "role", None) == "system"]
    if not system_indexes or system_indexes == [0]:
        return messages
    parts: list[str] = []
    for i in system_indexes:
        content = getattr(messages[i], "content", None)
        if isinstance(content, str) and content.strip():
            parts.append(content)
    merged_content = "\n\n".join(parts)
    first = messages[system_indexes[0]]
    first.content = merged_content
    rest = [m for i, m in enumerate(messages) if i not in set(system_indexes)]
    logger.info("合并 %d 条 system 消息为 1 条", len(system_indexes))
    return [first, *rest]


def _tool_arguments_to_dict(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("工具参数不是合法 JSON，按空参数处理：%s", str(raw)[:120])
        return {}


def message_to_openai(message: BaseMessage) -> dict[str, Any]:
    """BaseMessage → OpenAI chat 格式（含多模态图片与工具调用）。"""
    result: dict[str, Any] = {"role": message.role}
    if message.content_parts:
        blocks: list[dict] = []
        has_text = any(p.type == "text" for p in message.content_parts)
        if message.content and not has_text:
            blocks.append({"type": "text", "text": message.content})
        for part in message.content_parts:
            if part.type == "text":
                blocks.append({"type": "text", "text": part.text})
            elif part.type == "image":
                blocks.append({"type": "image_url", "image_url": {"url": part.url, "detail": part.detail}})
        result["content"] = blocks
    else:
        result["content"] = message.content or ""
    if message.tool_calls:
        result["tool_calls"] = [tc.to_openai() for tc in message.tool_calls]
    if message.role == "assistant" and message.reasoning_content:
        result["reasoning_content"] = message.reasoning_content
    if message.role == "tool":
        result["tool_call_id"] = message.tool_call_id or ""
        if message.name:
            result["name"] = message.name
    return result


def tools_to_openai(tools: list[Tool] | None) -> list[dict] | None:
    if not tools:
        return None
    return [tool.to_schema() for tool in tools]


def _parse_usage(usage: Any) -> dict[str, int]:
    """解析 usage；上游上报的 total 与 prompt+completion 不一致时原样保留。"""
    result: dict[str, int] = {}
    if usage is None:
        return result
    for src, dst in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = getattr(usage, src, None)
        if value is not None:
            result[dst] = int(value)
    # cached / reasoning tokens 明细（DeepSeek 与自建网关）
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
        if cached is not None:
            result["cached_tokens"] = int(cached)
    completion_details = getattr(usage, "completion_tokens_details", None)
    if completion_details is not None:
        reasoning = getattr(completion_details, "reasoning_tokens", None)
        if reasoning is not None:
            result["reasoning_tokens"] = int(reasoning)
    return result


def _get_reasoning(message: Any) -> str | None:
    """宽容读取思考内容字段（reasoning_content 及 reasoning/thinking 别名）。"""
    value = getattr(message, "reasoning_content", None)
    if value is not None:
        return value
    for alias in ("reasoning", "reasoning_text", "thinking"):
        candidate = getattr(message, alias, None)
        if candidate:
            return candidate
        model_extra = getattr(message, "model_extra", None)
        if isinstance(model_extra, dict):
            candidate = model_extra.get(alias)
        if candidate:
            return candidate
    return None


def _parse_tool_calls(message: Any) -> list:
    from app.services.agent.native.types import FunctionCall, ToolCall

    tool_calls: list[ToolCall] = []
    for item in getattr(message, "tool_calls", None) or []:
        function = getattr(item, "function", None)
        if function is None:
            continue
        tool_calls.append(
            ToolCall(
                id=getattr(item, "id", "") or f"call_{len(tool_calls)}",
                type="function",
                function=FunctionCall(
                    name=getattr(function, "name", "") or "",
                    arguments=_tool_arguments_to_dict(getattr(function, "arguments", "")),
                ),
            )
        )
    return tool_calls


# ── 网关 ──────────────────────────────────────────────────────────────


class NativeLLMGateway:
    """openai SDK 直连网关（provider/model/路由属性供用量记账读取）。"""

    def __init__(self, config: dict[str, Any], *, default_headers: dict | None = None, http_client: Any = None) -> None:
        self.provider = config.get("provider", "openai")
        self.model_name = config.get("model", "")
        self._api_key = config.get("api_key")
        self._base_url = config.get("base_url")
        self._max_tokens = config.get("max_tokens", 4096)
        self._timeout = config.get("timeout", 300)
        self._stream_attempts = max(
            1, int(get_settings().llm_stream_retry_attempts or 2)
        )
        # 采样参数（temperature/top_p/presence_penalty/frequency_penalty/seed）
        self._sampling = {
            key: config[key]
            for key in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "seed")
            if key in config
        }
        self._extra_body = dict(config.get("extra_body") or {})
        self._output_token_parameter = config.get("output_token_parameter") or "max_tokens"
        retry = config.get("retry") or {}
        self._sdk_max_retries = max(0, int(retry.get("max_attempts", 1)) - 1)

        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {
            "api_key": self._api_key or "missing-key",
            "max_retries": self._sdk_max_retries,
            "timeout": self._timeout,
        }
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        if default_headers:
            client_kwargs["default_headers"] = default_headers
        if http_client is not None:
            client_kwargs["http_client"] = http_client
        self.client = AsyncOpenAI(**client_kwargs)
        # 路由记账属性（route.attach_route 写入，usage_recorder 读取）
        self.route_provider_id: int | None = None
        self.route_provider_slug: str | None = None
        self.route_provider_name: str | None = None
        self.route_model: str | None = None
        self.route_credential_id: int | None = None
        self.route_account_label: str | None = None

    async def aclose(self) -> None:
        try:
            await self.client.close()
        except Exception:  # noqa: BLE001
            pass

    # ── 请求体 ────────────────────────────────────────────────────────

    def _build_request(
        self,
        messages: list[BaseMessage],
        tools: list[Tool] | None,
        stream: bool,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": kwargs.get("model") or self.model_name,
            "messages": [message_to_openai(m) for m in messages],
        }
        token_param = kwargs.get("output_token_parameter") or self._output_token_parameter
        max_tokens = kwargs.get("max_tokens") or self._max_tokens
        if max_tokens:
            request[token_param] = int(max_tokens)
        request.update(self._sampling)
        openai_tools = tools_to_openai(tools)
        if openai_tools:
            request["tools"] = openai_tools
        if self._extra_body:
            request["extra_body"] = dict(self._extra_body)
        if stream:
            request["stream"] = True
            request["stream_options"] = {"include_usage": True}
        return request

    # ── 公开入口 ──────────────────────────────────────────────────────

    async def generate(
        self,
        messages: list[BaseMessage],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> LLMResponse | AsyncIterator[LLMResponseChunk]:
        messages = normalize_system_messages(messages)
        if not stream:
            return await self._generate_once(messages, tools, **kwargs)
        return self._stream_with_retry(messages, tools, **kwargs)

    # ── 非流式 ────────────────────────────────────────────────────────

    async def _generate_once(
        self,
        messages: list[BaseMessage],
        tools: list[Tool] | None,
        **kwargs: Any,
    ) -> LLMResponse:
        request = self._build_request(messages, tools, stream=False, **kwargs)
        import time

        started = time.monotonic()
        try:
            raw = await self.client.chat.completions.create(**request)
        except Exception as exc:  # noqa: BLE001 —— 统一包装 LLMError
            logger.warning("LLM 非流式请求失败：%s: %s", type(exc).__name__, exc)
            raise self._as_llm_error(exc) from exc

        choices = list(getattr(raw, "choices", None) or [])
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None) if choice is not None else None
        if message is None:
            raise LLMError("上游非流式响应缺少 choices[0].message", provider=self.provider)

        tool_calls = _parse_tool_calls(message)
        finish_reason = getattr(choice, "finish_reason", None)
        finish_reason = normalize_finish_reason(finish_reason)
        if finish_reason not in FINISH_REASONS:
            finish_reason = "stop"
        if finish_reason == "length" and tool_calls:
            logger.warning(
                "模型在 finish_reason=length 时发起了 %d 个工具调用但输出被截断，不执行截断的调用",
                len(tool_calls),
            )
        reasoning = _get_reasoning(message)
        usage_dict = _parse_usage(getattr(raw, "usage", None))
        return LLMResponse(
            message=BaseMessage(
                role="assistant",
                content=getattr(message, "content", "") or "",
                reasoning_content=reasoning,
                tool_calls=tool_calls,
                usage=usage_dict or None,
            ),
            finish_reason=finish_reason,
            raw_finish_reason=getattr(choice, "finish_reason", None),
            usage=usage_dict,
            usage_available=bool(usage_dict),
            model=getattr(raw, "model", None) or self.model_name,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    # ── 流式 ──────────────────────────────────────────────────────────

    async def _stream_once(
        self,
        messages: list[BaseMessage],
        tools: list[Tool] | None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponseChunk]:
        request = self._build_request(messages, tools, stream=True, **kwargs)
        raw_stream = await self.client.chat.completions.create(**request)
        saw_tool_calls = False
        # 跨 delta 聚合工具调用（index → 字段累积）
        pending: dict[int, dict[str, str]] = {}
        usage_final: dict[str, int] | None = None

        async for chunk in raw_stream:
            choices = list(getattr(chunk, "choices", None) or [])
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                usage_final = _parse_usage(usage)

            if not choices:
                # usage-only 收尾帧：不能丢（原 wuwei 在这里把它跳过）
                if usage_final is not None:
                    yield LLMResponseChunk(
                        content="",
                        finish_reason=None,
                        usage_available=True,
                        usage=dict(usage_final),
                    )
                continue

            choice = choices[0]
            delta = getattr(choice, "delta", None)
            finish_reason = getattr(choice, "finish_reason", None)

            content = getattr(delta, "content", None) if delta is not None else None
            reasoning = _get_reasoning(delta) if delta is not None else None

            tool_calls_delta: list[dict] | None = None
            if delta is not None:
                raw_deltas = getattr(delta, "tool_calls", None) or []
                if raw_deltas:
                    saw_tool_calls = True
                    tool_calls_delta = []
                    for item in raw_deltas:
                        index = int(getattr(item, "index", 0) or 0)
                        fn = getattr(item, "function", None)
                        slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if getattr(item, "id", None):
                            slot["id"] = item.id
                        if fn is not None:
                            if getattr(fn, "name", None):
                                slot["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                slot["arguments"] += fn.arguments
                        tool_calls_delta.append(
                            {
                                "index": index,
                                "id": slot["id"] or None,
                                "name": slot["name"] or None,
                                "arguments": slot["arguments"],
                            }
                        )

            out_finish: str | None = None
            raw_finish: str | None = None
            tool_calls_complete = None
            if finish_reason:
                raw_finish = finish_reason
                normalized = normalize_finish_reason(finish_reason)
                if normalized == "stop" and saw_tool_calls:
                    # 收尾只给 stop 但确实有工具调用 → 纠正，否则调用被静默丢弃
                    normalized = "tool_calls"
                if normalized == "length" and saw_tool_calls:
                    logger.warning(
                        "模型在 finish_reason=length 时发起了工具调用但输出被截断，不执行截断的调用"
                    )
                if normalized == "tool_calls":
                    from app.services.agent.native.types import FunctionCall, ToolCall

                    tool_calls_complete = [
                        ToolCall(
                            id=slot["id"] or f"call_{index}",
                            type="function",
                            function=FunctionCall(name=slot["name"], arguments=_tool_arguments_to_dict(slot["arguments"])),
                        )
                        for index, slot in sorted(pending.items())
                    ]
                out_finish = normalized if normalized in FINISH_REASONS else "stop"
                saw_tool_calls = False
                pending = {}

            if not (content or reasoning or tool_calls_delta or out_finish or usage_final):
                continue

            yield LLMResponseChunk(
                content=content or "",
                reasoning_content=reasoning,
                tool_calls_delta=tool_calls_delta,
                tool_calls_complete=tool_calls_complete,
                finish_reason=out_finish,
                raw_finish_reason=raw_finish,
                usage_available=usage_final is not None,
                usage=dict(usage_final) if usage_final is not None else None,
            )

    async def _stream_with_retry(
        self,
        messages: list[BaseMessage],
        tools: list[Tool] | None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponseChunk]:
        last_error: Exception | None = None
        for attempt in range(self._stream_attempts):
            emitted = False
            try:
                async for chunk in self._stream_once(messages, tools, **kwargs):
                    if chunk.content or chunk.reasoning_content or chunk.tool_calls_complete:
                        emitted = True
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001 —— 分类由 _is_retryable 决定
                last_error = exc
                already_translated = isinstance(exc, LLMError)
                if emitted or attempt >= self._stream_attempts - 1 or not _is_retryable(exc):
                    logger.warning(
                        "LLM 流式请求失败（第 %d/%d 次尝试）：%s: %s",
                        attempt + 1,
                        self._stream_attempts,
                        type(exc).__name__,
                        exc,
                    )
                    if already_translated:
                        details = getattr(exc, "details", None)
                        if isinstance(details, dict):
                            details.setdefault("attempts", attempt + 1)
                        raise
                    raise self._as_llm_error(exc, attempts=attempt + 1) from exc
                logger.warning("流式请求失败（第 %d 次尝试），准备重试：%s", attempt + 1, exc)
                await asyncio.sleep(2**attempt)
        if last_error is not None:  # pragma: no cover —— 循环内必 return 或 raise
            raise self._as_llm_error(last_error) from last_error

    # ── 错误分类与包装 ────────────────────────────────────────────────

    def _as_llm_error(self, exc: Exception, attempts: int = 1) -> LLMError:
        if isinstance(exc, LLMError):
            details = exc.details or {}
            details.setdefault("attempts", attempts)
            details.setdefault(
                "retryable",
                _classify_error(exc) in {"rate_limit", "server_error", "connection_error", "timeout"},
            )
            return exc
        status_code = getattr(exc, "status_code", None)
        kind = _classify_error(exc)
        return LLMError(
            f"{type(exc).__name__}: {exc}",
            provider=self.provider,
            status_code=int(status_code) if status_code else None,
            kind=kind,
            details={"attempts": attempts, "retryable": kind in {"rate_limit", "server_error", "connection_error", "timeout"}},
        )


def _classify_error(exc: Exception) -> str:
    """按异常层级判定可重试类别（原 RetryingGateway._classify_error 语义）。"""
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        try:
            code = int(status_code)
        except (TypeError, ValueError):
            code = None
        if code is not None:
            if code == 401 or code == 403:
                return "auth_error"
            if code == 429:
                return "rate_limit"
            if 500 <= code < 600:
                return "server_error"
            if 400 <= code < 500:
                return "bad_request"

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    try:
        import httpx
    except Exception:  # pragma: no cover
        httpx = None  # type: ignore[assignment]
    if httpx is not None:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.TransportError):
            return "connection_error"
    try:
        import openai
    except Exception:  # pragma: no cover
        openai = None  # type: ignore[assignment]
    if openai is not None:
        if isinstance(exc, openai.APITimeoutError):
            return "timeout"
        if isinstance(exc, openai.APIConnectionError):
            return "connection_error"
        if isinstance(exc, openai.RateLimitError):
            return "rate_limit"
        if isinstance(exc, openai.AuthenticationError):
            return "auth_error"
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "connection" in text or "connect" in text:
        return "connection_error"
    if "rate limit" in text:
        return "rate_limit"
    # 流中断但没收到终止事件：上游网关/模型中途断开（生成网站这类长输出
    # 场景实测常见）。按文本匹配而非 isinstance —— 异常类型随 SDK 升级漂移。
    # 归为 connection_error 让「还没产出内容」的尝试得以重试，而不是把
    # ValueError 裸抛给用户（移植自旧 adapter.py 的线上 bugfix）。
    if "stream ended without a terminal event" in text or "stream produced no events" in text:
        return "connection_error"
    return "unknown"


def _is_retryable(exc: Exception) -> bool:
    return _classify_error(exc) in {"rate_limit", "server_error", "connection_error", "timeout"}
