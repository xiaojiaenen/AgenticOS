"""对 wuwei 网关的补强（不改 site-packages）。

为什么需要这一层：wuwei 的**非流式路径**做得比较完整（分类重试、超时、fallback），
而**流式路径**基本是「能跑就行」，两者能力不对等 —— 可我们的界面走的恰恰是流式。
三处实测确认的缺陷都在这里兜住：

1. **usage 收尾帧被吞**：``stream_options.include_usage`` 是适配器自己加的，上游
   按规范回一帧 ``choices: []`` + ``usage``，但 ``_generate_stream`` 先
   ``parse_stream_chunk``、拿到 ``None`` 就 ``continue``，那一帧的 usage 读不到，
   ``agent_usage_events`` 的 token 统计于是恒为 0。
2. **工具调用静默丢失**：网关只在 ``finish_reason == "tool_calls"`` 时组装完整调用。
   有些网关收尾只给 ``stop``，于是模型「说要调工具」却被当成普通回答结束。
3. **非流式缺 usage 直接崩**：上游 ``parse_response`` 直接取
   ``raw_response.usage.prompt_tokens``，兼容网关省略 usage 时抛 ``AttributeError``，
   把一次正常对话变成 500。

外加 ``RetryingGateway``：给流式补上「还没吐字就断了」的重试。约束是刻意的 ——
一旦已经产出内容就绝不重试，否则用户会看到半句话重来一遍、工具被执行两次。

这些补丁都建立在公开方法（``parse_stream_chunk`` / ``parse_response`` /
``generate``）之上，不碰私有属性；wuwei 升级时最坏情况是补丁失效退回原行为，
不会把请求打死。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from wuwei.core.errors import LLMError
from wuwei.core.message import FunctionCall, ToolCall
from wuwei.llm import LLMGateway
from wuwei.llm.adapters import OpenAIAdapter
# Message 是 ``BaseMessage`` 的别名，只在 wuwei.llm.types 里导出
from wuwei.llm.types import LLMResponse, LLMResponseChunk, Message

logger = logging.getLogger("agenticos.llm.adapter")

# ``LLMResponse.finish_reason`` 是 Literal，上游给出字面量之外的值（例如 vLLM 的
# ``insufficient_system_resource``）会直接 ValidationError，把响应变成 500。
_FINISH_REASONS = frozenset({"stop", "tool_calls", "length", "content_filter"})


class HardenedOpenAIAdapter(OpenAIAdapter):
    """标准适配器 + 三处容错。其余行为完全继承，不重复实现请求组装。"""

    def __init__(self, *args: Any, max_retries: int | None = None, **kwargs: Any) -> None:
        """``max_retries`` 必须显式取出来。

        父类把所有 ``**kwargs`` 塞进 ``default_params`` 并原样展开进请求体
        （``create(**request)``），所以 ``max_retries`` 要是顺着 kwargs 走，就会
        变成一个上游不认识的请求字段 —— 实测直接 ``TypeError: create() got an
        unexpected keyword argument 'max_retries'``。它本该作用于 SDK 客户端。
        """
        super().__init__(*args, **kwargs)
        # 本轮流里是否出现过工具调用增量。用于在收尾帧只给 stop 时纠正语义。
        self._stream_saw_tool_calls = False
        if max_retries is not None and max_retries >= 0:
            # with_options 复用同一个 httpx 客户端，不会多开连接池
            self.client = self.client.with_options(max_retries=max_retries)

    # ------------------------------------------------------------------
    # 流式
    # ------------------------------------------------------------------
    def parse_stream_chunk(self, chunk: Any) -> dict[str, Any] | None:
        data = super().parse_stream_chunk(chunk)

        if data is None:
            # 没有 choices 也没有 usage 的帧：上游返回 None，交给网关跳过。
            # （wuwei 3.2.2 的 ``parse_stream_chunk`` 对 usage-only 帧已经会
            # 返回 ``{"usage": ...}``，不再需要把它伪装成空内容帧。）
            return None

        saw_delta = bool(data.get("tool_calls_delta"))
        if saw_delta:
            self._stream_saw_tool_calls = True

        finish = data.get("finish_reason")
        if finish == "stop" and self._stream_saw_tool_calls:
            # 收尾只给 stop 但这一轮确实有工具调用：纠正成 tool_calls，
            # 否则网关不会组装 tool_calls_complete，工具调用被静默丢弃。
            data = {**data, "finish_reason": "tool_calls"}
        elif finish == "length" and self._stream_saw_tool_calls:
            # R-1：上游 ``adapters/openai.py:97`` 只在 finish_reason ∈
            # (stop, tool_calls) 时解析 tool_calls → finish_reason="length"
            # 时工具调用被**静默丢弃**，不报错、不记日志。
            #
            # 这里**不**把 length 改成 tool_calls：上游 runner 里有一句明确的
            # 设计决定——``if finish not in ("stop", "tool_calls"): pending = []``
            # （注释：No partial tools execute on length/abort/unknown）。
            # 截断的工具调用参数可能不完整，强行执行反而危险。
            # 这里只把「被丢弃」变成「可见」：记一条告警。
            logger.warning(
                "模型在 finish_reason=length 时发起了工具调用但输出被截断，"
                "该工具调用不会被执行（上游按设计不执行截断的工具调用）"
            )
        if finish:
            # 一轮结束即复位。异常中断没走到这里时，残留的标记最多让下一轮
            # 得到一个空的 tool_calls_complete（falsy），不会触发工具执行。
            self._stream_saw_tool_calls = False
        return data

    # ------------------------------------------------------------------
    # 非流式
    # ------------------------------------------------------------------
    def parse_response(self, raw_response: Any) -> LLMResponse:
        """比上游更宽容的解析。

        这里**有意重写而不是包一层 try/except**：上游实现只要 usage 缺失就整段
        失败，包住异常也只能拿到半个对象；逐字段 ``getattr`` 才能掏出「有内容、
        没计费」的响应。
        """
        choices = list(getattr(raw_response, "choices", None) or [])
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None) if choice is not None else None
        if message is None:
            raise ValueError("上游非流式响应缺少 choices[0].message")

        tool_calls: list[ToolCall] = []
        for item in getattr(message, "tool_calls", None) or []:
            function = getattr(item, "function", None)
            if function is None:
                continue
            raw_arguments = getattr(function, "arguments", "")
            if isinstance(raw_arguments, dict):
                arguments = raw_arguments
            else:
                try:
                    arguments = json.loads(raw_arguments) if raw_arguments else {}
                except (json.JSONDecodeError, TypeError):
                    # 上游实现是静默给空 dict，但那会让工具用错误参数执行。
                    # 至少留一条日志，排障时能看出是「参数被截断」而不是「模型乱调」。
                    logger.warning(
                        "工具 %s 的参数不是合法 JSON，按空参数处理：%s",
                        getattr(function, "name", "?"),
                        str(raw_arguments)[:120],
                    )
                    arguments = {}
            tool_calls.append(
                ToolCall(
                    id=getattr(item, "id", "") or f"call_{len(tool_calls)}",
                    type="function",
                    function=FunctionCall(
                        name=getattr(function, "name", "") or "", arguments=arguments
                    ),
                )
            )

        usage = getattr(raw_response, "usage", None)
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason not in _FINISH_REASONS:
            finish_reason = "stop"

        if finish_reason == "length" and tool_calls:
            # R-1：上游按 finish_reason 决定要不要解析 tool_calls，
            # finish_reason="length" 时工具调用被静默丢弃。这里始终解析
            # （工具调用是否存在不该由 finish_reason 决定），
            # 同时把「被截断」记成可见的告警而不是无声消失。
            logger.warning(
                "模型在 finish_reason=length 时发起了 %d 个工具调用但输出被截断，"
                "上游 runner 不会执行截断的工具调用",
                len(tool_calls),
            )

        # 用上游 3.2.2 的 parse_openai_usage：它优先采用上游上报的
        # total_tokens，并保留 cached_tokens / reasoning_tokens 明细。
        usage_dict = self._parse_usage(usage)
        # 非流式路径不需要「还原上游总数」的辅助键（上游 total 本身就是权威值）。
        usage_dict.pop("upstream_total_tokens", None)

        return LLMResponse(
            message=Message(
                role="assistant",
                content=getattr(message, "content", "") or "",
                reasoning_content=self._get_extra_field(message, "reasoning_content"),
                tool_calls=tool_calls,
            ),
            finish_reason=finish_reason,
            usage=usage_dict,
            model=getattr(raw_response, "model", None) or (self.model or ""),
            latency_ms=0,
        )

    # ── R-3：usage.total_tokens 被网关强制改写 ─────────────────────
    @staticmethod
    def _parse_usage(usage: Any) -> dict[str, int]:
        """解析 usage，并在需要时保留上游上报的 total_tokens。

        上游 ``llm/gateway.py`` 在流式聚合时无条件执行::

            usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)

        这会把「上游自己上报的 total_tokens」抹掉。若上游的 total 含有
        cached tokens / reasoning tokens（DeepSeek 与部分自建网关会这样），
        我们记的总数会偏小 → 按 token 计费/配额不准，且流式与非流式
        两条路径口径不一致。

        这里把上游的 total 另存一份，等 ``RetryingGateway`` 在流式出口处
        再还原回去（网关的改写发生在它自己内部，我们改不了那一行）。
        """
        result = dict(OpenAIAdapter._parse_usage(usage))
        total = result.get("total_tokens") or 0
        prompt = result.get("prompt_tokens") or 0
        completion = result.get("completion_tokens") or 0
        if total and total != prompt + completion:
            result["upstream_total_tokens"] = total
        return result

    def _get_extra_field(self, obj: Any, field_name: str) -> Any:
        """宽容读取思考内容字段。

        标准形态是 ``reasoning_content``（百通与 OpenAI 一致，能直接命中）。
        这里多认几个别名，是为了兼容自建网关把字段改成 ``reasoning`` 的情况 ——
        否则推理过程会被整段丢弃，表现为「模型在思考但界面空白」。
        """
        value = super()._get_extra_field(obj, field_name)
        if value is not None or field_name != "reasoning_content":
            return value
        for alias in ("reasoning", "reasoning_text", "thinking"):
            candidate = getattr(obj, alias, None)
            if candidate is None:
                model_extra = getattr(obj, "model_extra", None)
                if isinstance(model_extra, dict):
                    candidate = model_extra.get(alias)
            if candidate:
                return candidate
        return None


def _is_retryable(exc: Exception) -> bool:
    """按异常类型判断是否值得重试。

    wuwei 用 ``"500" in str(exc)`` 分类状态码 —— 一个端口是 5000 的 401 会被
    当成 5xx 重试三次（实测：3 次尝试、白等 3 秒）。这里读 ``status_code``。

    R-4：分类统一走 ``RetryingGateway._classify_error``，它在上游「异常类名
    白名单」之外补了按异常层级的兜底（httpx / openai 的连接与超时异常）。
    """
    return RetryingGateway._classify_error(exc) in {
        "rate_limit",
        "server_error",
        "connection_error",
        "timeout",
    }


class RetryingGateway(LLMGateway):
    """给流式补上重试（wuwei 只对非流式做了重试 / fallback）。

    只在「还没产出任何内容」时重试：已经吐出的文本再重来一遍，用户会看到重复
    内容，更糟的是工具可能被执行两次。

    另外补三处上游缺陷：

    - **R-4**：上游 ``_classify_error`` 靠「异常类名白名单」判定，
      兜底返回 ``unknown`` → **不可重试也不走 fallback，且不报错**。
      openai SDK 换版本或换供应商改个异常类名就会退化。这里按异常**层级**
      兜底判定。
    - **R-2**：上游定义了 ``LLMError`` 却全程不用，原始异常直接抛给调用方，
      调用方只能匹配字符串。这里统一包装成 ``LLMError``（保留 ``__cause__``
      与 ``details``）。
    - **R-3**：上游在流式聚合时把 ``total_tokens`` 强制改写成
      ``prompt + completion``，把上游上报的总数抹掉。这里在出口处还原。
    """

    def __init__(self, config: dict[str, Any], *, stream_attempts: int = 2) -> None:
        super().__init__(config)
        self._stream_attempts = max(1, int(stream_attempts or 1))

    # ── R-4：错误分类兜底 ─────────────────────────────────────────
    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """在上游分类的基础上，按异常**层级**兜底。

        上游只按异常**类名**白名单判定（``APIConnectionError`` /
        ``ConnectError`` / ``ReadError`` …），兜底返回 ``unknown``，
        而 ``_retryable`` 只认四类 → 未知异常既不重试也不走 fallback，
        而且**不会报错**，只是静默地不重试。
        """
        kind = LLMGateway._classify_error(exc)
        if kind != "unknown":
            return kind

        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return "timeout"

        try:
            import httpx
        except Exception:  # pragma: no cover —— httpx 是 openai 的依赖
            httpx = None  # type: ignore[assignment]

        if httpx is not None:
            if isinstance(exc, httpx.TimeoutException):
                return "timeout"
            if isinstance(exc, httpx.TransportError):
                return "connection_error"

        try:
            import openai
        except Exception:  # pragma: no cover —— openai 是我们的硬依赖
            openai = None  # type: ignore[assignment]

        if openai is not None:
            if isinstance(exc, openai.APITimeoutError):
                return "timeout"
            if isinstance(exc, openai.APIConnectionError):
                return "connection_error"

        # 最后按异常文本兜底（httpx / aiohttp 直接抛出的形态）
        text = str(exc).lower()
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "connection" in text or "connect" in text:
            return "connection_error"
        return kind

    # ── R-2：统一异常类型 ─────────────────────────────────────────
    @staticmethod
    def _as_llm_error(exc: Exception, *, attempts: int = 1) -> LLMError:
        """把原始异常包装成 ``LLMError``，保留诊断信息。

        上游 ``core/errors.py`` 定义了 ``LLMError``（还带一个为「携带诊断信息」
        设计的 ``details`` 字段），但网关全程没用过——调用方只能靠匹配字符串
        判断错误类型。这里把 status_code、异常类型、重试次数都放进 details。
        """
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        return LLMError(
            str(exc) or type(exc).__name__,
            details={
                "error_type": type(exc).__name__,
                "status_code": status,
                "attempts": attempts,
                "retryable": RetryingGateway._classify_error(exc)
                in {"rate_limit", "server_error", "connection_error", "timeout"},
            },
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        if not stream:
            # 非流式原样交给上游：它本来就有分类重试 + fallback
            try:
                return await super().generate(messages, tools=tools, **kwargs)
            except Exception as exc:  # noqa: BLE001 —— 统一包装成 LLMError
                logger.warning("LLM 非流式请求失败：%s: %s", type(exc).__name__, exc)
                raise self._as_llm_error(exc) from exc
        return self._stream_with_retry(messages, tools, **kwargs)

    async def _stream_with_retry(
        self,
        messages: list[Message],
        tools: list[Any] | None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponseChunk]:
        last_error: Exception | None = None
        for attempt in range(self._stream_attempts):
            emitted = False
            try:
                stream = await super().generate(
                    messages, tools=tools, stream=True, **kwargs
                )
                async for chunk in stream:
                    if chunk.content or chunk.reasoning_content or chunk.tool_calls_complete:
                        emitted = True
                    self._restore_upstream_total(chunk)
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001 —— 分类由 _is_retryable 决定
                last_error = exc
                if emitted or attempt >= self._stream_attempts - 1 or not _is_retryable(exc):
                    logger.warning(
                        "LLM 流式请求失败（第 %d/%d 次尝试）：%s: %s",
                        attempt + 1,
                        self._stream_attempts,
                        type(exc).__name__,
                        exc,
                    )
                    raise self._as_llm_error(exc, attempts=attempt + 1) from exc
                logger.warning(
                    "流式请求失败（第 %d/%d 次尝试），准备重试：%s",
                    attempt + 1,
                    self._stream_attempts,
                    exc,
                )
                await asyncio.sleep(2**attempt)
        if last_error is not None:  # pragma: no cover —— 循环内必 return 或 raise
            raise self._as_llm_error(last_error) from last_error

    # ── R-3：还原上游上报的 total_tokens ──────────────────────────
    @staticmethod
    def _restore_upstream_total(chunk: Any) -> None:
        """把网关改写掉的 ``total_tokens`` 还原成上游上报的值。

        网关在流式聚合时无条件执行 ``total = prompt + completion``，
        我们在适配器里另存了上游的原值（``upstream_total_tokens``），
        这里在 chunk 离开网关之前还原，并把辅助键摘掉（不能让它进入
        run 的 usage 统计）。
        """
        usage = getattr(chunk, "usage", None)
        if not isinstance(usage, dict):
            return
        upstream_total = usage.pop("upstream_total_tokens", None)
        if upstream_total is None:
            return
        try:
            upstream_total = int(upstream_total)
        except (TypeError, ValueError):
            return
        if upstream_total > (usage.get("total_tokens") or 0):
            usage["total_tokens"] = upstream_total
