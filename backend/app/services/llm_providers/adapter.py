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
            # usage-only 帧：没有 choices，但有 usage。给一个空内容帧把循环带
            # 过去，网关末尾那句 ``if chunk.usage`` 才读得到。
            if getattr(chunk, "usage", None):
                return {"content": "", "reasoning_content": "", "finish_reason": None}
            return None

        saw_delta = bool(data.get("tool_calls_delta"))
        if saw_delta:
            self._stream_saw_tool_calls = True

        finish = data.get("finish_reason")
        if finish == "stop" and self._stream_saw_tool_calls:
            # 收尾只给 stop 但这一轮确实有工具调用：纠正成 tool_calls，
            # 否则网关不会组装 tool_calls_complete，工具调用被静默丢弃。
            data = {**data, "finish_reason": "tool_calls"}
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

        return LLMResponse(
            message=Message(
                role="assistant",
                content=getattr(message, "content", "") or "",
                reasoning_content=self._get_extra_field(message, "reasoning_content"),
                tool_calls=tool_calls,
            ),
            finish_reason=finish_reason,
            usage={
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            },
            model=getattr(raw_response, "model", None) or (self.model or ""),
            latency_ms=0,
        )

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
    """
    try:
        import openai
    except Exception:  # pragma: no cover —— openai 是我们的硬依赖，兜底而已
        return False

    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    if isinstance(exc, openai.APIStatusError):
        # 有 status_code 却没取到，说明是 SDK 之外的形态，保守不重试
        return False
    # 未归类的异常（例如 httpx 直接抛的 ReadError）只按连接层判断
    text = str(exc).lower()
    return "connection" in text or "timeout" in text


class RetryingGateway(LLMGateway):
    """给流式补上重试（wuwei 只对非流式做了重试 / fallback）。

    只在「还没产出任何内容」时重试：已经吐出的文本再重来一遍，用户会看到重复
    内容，更糟的是工具可能被执行两次。
    """

    def __init__(self, config: dict[str, Any], *, stream_attempts: int = 2) -> None:
        super().__init__(config)
        self._stream_attempts = max(1, int(stream_attempts or 1))

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        if not stream:
            # 非流式原样交给上游：它本来就有分类重试 + fallback
            return await super().generate(messages, tools=tools, **kwargs)
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
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001 —— 分类由 _is_retryable 决定
                last_error = exc
                if emitted or attempt >= self._stream_attempts - 1 or not _is_retryable(exc):
                    raise
                logger.warning(
                    "流式请求失败（第 %d/%d 次尝试），准备重试：%s",
                    attempt + 1,
                    self._stream_attempts,
                    exc,
                )
                await asyncio.sleep(2**attempt)
        if last_error is not None:  # pragma: no cover —— 循环内必 return 或 raise
            raise last_error
