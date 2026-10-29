"""直通模型通道：只调 LLM，不带工具、不带智能体。

为什么需要：对外网关原先只暴露「带工具的智能体」。但很多接入方要的只是
一个普通模型 —— 代码补全、翻译、分类、批量文本处理。给它们套上智能体
会带来两个问题：

1. **行为不可控**：智能体会自主调工具、多步推理，输出格式不稳定，
   对「给我翻译这句话」这种任务是负担。
2. **成本与延迟**：一次简单请求可能触发 10 步工具调用。

所以这里提供 ``direct`` 通道：一次 messages → 一次 completion，不装工具、
不启中间件、不落会话。语义与直接调 OpenAI 完全一致，只是经过我们的
provider 配置（这样密钥、负载均衡、审计都还在我们这边）。

设计取舍
--------
- **不落会话/不写 usage_events 的会话字段**：直通请求没有会话概念。
  用量仍记账（否则无法做配额），但 session_id 留空。
- **复用 build_gateway**：认证方式（API Key / Cookie 池）、TLS 策略、
  超时、采样参数都沿用既有逻辑，不重复实现。
- **多模态输入原样透传**：content 可以是字符串或 OpenAI 的多段数组，
  这里不做解析 —— 解析会丢掉模型支持但我们没实现的字段。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, AsyncIterator

from app.db.models import UserModel
from app.services.llm_providers import spec as provider_spec
from app.services.llm_providers.runtime import ProviderUnavailable, build_gateway
from app.services.llm_providers.spec import resolve_model_for_role

logger = logging.getLogger("agenticos.direct_llm")


class DirectLLMError(RuntimeError):
    """直通调用失败（上游错误、配置缺失等）。"""


def _normalize_assistant_tool_calls(raw_calls: list[Any]) -> list[Any]:
    """把 OpenAI 形状的 tool_calls 转成 wuwei ToolCall 对象。

    wuwei 的结构（与 OpenAI 同名但类型不同）::

        ToolCall{id: str, type: "function",
                 function: FunctionCall{name: str, arguments: dict}}

    注意 ``arguments`` 是 **dict**，不是 JSON 字符串 —— 与 OpenAI 相反。
    pydantic 会拒绝字符串形态。
    """
    import json as _json

    try:
        from wuwei.core.message import FunctionCall, ToolCall
    except Exception:  # noqa: BLE001
        return list(raw_calls)

    def _to_dict(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            if not raw.strip():
                return {}
            try:
                parsed = _json.loads(raw)
            except Exception:  # noqa: BLE001
                return {}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        if raw is None:
            return {}
        return {"value": raw}

    out: list[Any] = []
    for index, call in enumerate(raw_calls):
        if not isinstance(call, dict):
            out.append(call)
            continue

        fn = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = str(fn.get("name") or call.get("name") or "").strip()
        if not name:
            continue

        raw_args = fn.get("arguments") if "arguments" in fn else call.get("arguments")
        call_id = str(call.get("id") or call.get("tool_call_id") or f"call_{index}")

        try:
            out.append(
                ToolCall(
                    id=call_id,
                    type="function",
                    function=FunctionCall(name=name, arguments=_to_dict(raw_args)),
                )
            )
        except Exception:  # noqa: BLE001
            # 构造失败时保留原 dict —— 让上游适配器自己处理
            out.append(call)
    return out


def _infer_tool_name(messages: list[dict[str, Any]], call_id: str) -> str:
    """从 assistant 消息的 tool_calls 里反查工具名。

    OpenAI 的 tool 消息只带 tool_call_id，不带工具名；而 wuwei 的
    ToolMessage 两个都必填。这里按 call_id 回溯上一条 assistant 消息。
    """
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        for call in item.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            if str(call.get("id") or "") != call_id:
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(fn.get("name") or call.get("name") or "").strip()
            if name:
                return name
    return ""


def _to_wuwei_messages(messages: list[dict[str, Any]]) -> list[Any]:
    """把 OpenAI 形状的 messages 转成 wuwei 的 BaseMessage。

    wuwei 的网关要求它自己的消息类型，不能直接吃 dict —— 这是 3.2 起就有的
    契约（``generate(messages: list[BaseMessage], ...)``）。

    content 支持字符串与多段数组：多段时把 text 段拼起来，非 text 段
    （image_url 等）透传为 dict，交给上游 SDK 自己处理。
    """
    # wuwei 的类名是 HumanMessage / AIMessage（不是 UserMessage /
    # AssistantMessage）。名字对不上会 ImportError，而异常在请求路径上
    # 表现为「接口 502」，看不出是导入问题。
    from wuwei.core.message import (
        AIMessage,
        HumanMessage,
        SystemMessage,
    )

    role_map = {
        "system": SystemMessage,
        "user": HumanMessage,
        "assistant": AIMessage,
    }

    # tool 消息：客户端执行完工具后的回灌。wuwei 有 ToolMessage，
    # 需要 tool_call_id 关联到具体的调用。
    from wuwei.core.message import ToolMessage as _ToolMessage

    out: list[Any] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")

        if isinstance(content, list):
            # 多段：text 拼成字符串，其余保留原始段（多模态）
            parts: list[str] = []
            extra: list[Any] = []
            for seg in content:
                if isinstance(seg, dict) and seg.get("type") in ("text", "input_text"):
                    parts.append(str(seg.get("text") or ""))
                elif isinstance(seg, str):
                    parts.append(seg)
                else:
                    extra.append(seg)
            text = "".join(parts)
            if extra:
                # 有非文本段时保留数组形态（上游 SDK 认 OpenAI 的 content 数组）
                payload: Any = [{"type": "text", "text": text}] + extra if text else extra
            else:
                payload = text
        elif isinstance(content, str):
            payload = content
        else:
            payload = str(content or "")

        if role == "tool":
            # tool 结果回灌：ToolMessage 的 tool_call_id 与 name 都是**必填**。
            #
            # 缺 name 会 ValidationError（实测：pydantic 直接报 missing）。
            # OpenAI 的 tool 消息只有 tool_call_id，工具名在上一条 assistant
            # 消息的 tool_calls 里 —— 这里从消息自身或调用链推断。
            call_id = str(item.get("tool_call_id") or item.get("id") or "")
            tool_name = str(item.get("name") or "").strip()
            if not tool_name:
                tool_name = _infer_tool_name(messages, call_id) or "tool"
            text = payload if isinstance(payload, str) else str(payload or "")
            out.append(
                _ToolMessage(content=text, tool_call_id=call_id, name=tool_name)
            )
            continue

        cls = role_map.get(role, HumanMessage)

        # assistant 消息上的 tool_calls 必须带进 AIMessage。
        #
        # 少了它，模型在第二轮看不到「我上一轮调过 get_weather」，
        # 会重复发起同一个调用，而 tool 结果就成了无主数据 ——
        # 表现为「回灌后回答为空」。这是 function calling 多轮的关键。
        raw_calls = item.get("tool_calls")
        if role == "assistant" and isinstance(raw_calls, list) and raw_calls:
            normalized = _normalize_assistant_tool_calls(raw_calls)
            try:
                out.append(cls(content=payload, tool_calls=normalized))
            except TypeError:
                # 该版本 AIMessage 不接受 tool_calls，退化成纯文本
                out.append(cls(content=payload))
            continue

        try:
            out.append(cls(content=payload))
        except TypeError:
            # 某些版本的消息类只接受字符串
            text_only = payload if isinstance(payload, str) else ""
            out.append(cls(content=text_only))
    return out


def _resolve_provider(
    db,
    *,
    role: str = "chat",
    model: str | None = None,
):
    """解析要用的 provider 与模型名。

    ``model`` 显式给了就用它（但端点仍来自 provider）；否则按 role 取。

    用 ``resolve_active_provider()``（无参）而不是传 db：这是既有实现，
    内部已处理「默认 provider → 环境变量兜底」的完整顺序。直通通道不该
    重新实现一遍这套逻辑。
    """
    from app.services.llm_providers.spec import resolve_active_provider

    try:
        spec = resolve_active_provider()
    except Exception as exc:  # noqa: BLE001
        raise DirectLLMError(
            f"没有可用的 AI 提供商：{exc}\n"
            "请管理员到「AI 提供商」页面添加并设为默认。"
        ) from exc

    model_name = (model or "").strip() or resolve_model_for_role(spec, role)
    if not model_name:
        raise DirectLLMError(
            f"提供商「{spec.name}」没有可用的 {role} 模型。请在模型用途里绑定一个。"
        )
    return spec, model_name


async def complete(
    db,
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    role: str = "chat",
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop: list[str] | None = None,
    stream: bool = False,
    extra_body: dict[str, Any] | None = None,
    tools: Any = None,
    tool_choice: Any = None,
    thinking: Any = None,
):
    """一次直通 completion。返回 (gateway, model_name, 响应)。

    调用方负责把响应转成目标协议（OpenAI / Anthropic / Responses）。
    """
    spec, model_name = _resolve_provider(db, role=role, model=model)

    # build_gateway(spec, *, max_tokens, timeout, model) —— spec 是位置参数，
    # 不是关键字参数（曾经写成 spec=spec 会 TypeError）。
    try:
        gateway = build_gateway(
            spec,
            max_tokens=max_tokens or spec.max_tokens or 4096,
            timeout=spec.timeout_seconds,
            model=model_name,
        )
    except ProviderUnavailable as exc:
        raise DirectLLMError(str(exc)) from exc

    wuwei_messages = _to_wuwei_messages(messages)
    if not wuwei_messages:
        raise DirectLLMError("messages 转换后为空")

    # 客户端透传的 tools：**只声明不执行**。
    #
    # 「直通」指的是不经过 AgenticOS 的智能体编排与内置工具，但模型自身
    # 的 function calling 能力必须保留 —— 那是模型能力，不是我们的工具。
    # 工具的真实执行由客户端完成（这正是 OpenAI function calling 协议
    # 的设计：模型给参数，客户端执行后回灌）。
    from app.services.llm_providers.direct_tools import (
        ToolSpecError,
        openai_tools_to_wuwei,
    )

    try:
        wuwei_tools = openai_tools_to_wuwei(tools)
    except ToolSpecError as exc:
        raise DirectLLMError(str(exc)) from exc

    # 采样参数通过 kwargs 透传给上游（网关内部会筛掉不认识的键）
    gen_kwargs: dict[str, Any] = {}
    if temperature is not None:
        gen_kwargs["temperature"] = temperature
    if top_p is not None:
        gen_kwargs["top_p"] = top_p
    if max_tokens is not None:
        gen_kwargs["max_tokens"] = max_tokens
    if stop:
        gen_kwargs["stop"] = stop
    if extra_body:
        gen_kwargs.update(extra_body)
    # tool_choice 与 thinking 都是模型能力参数，直接透传。
    # thinking：Anthropic 的 {"type":"enabled","budget_tokens":N}，
    # OpenAI 兼容端点常见 {"type":"enabled"} 或直接 true。
    if tool_choice is not None:
        gen_kwargs["tool_choice"] = tool_choice
    if thinking is not None:
        gen_kwargs["thinking"] = thinking

    try:
        # 入口是 generate（不是 create）：
        #   async def generate(messages, tools=None, stream=False, **kwargs)
        #
        # 注意它是 **async 函数**：即使 stream=True 也要先 await，
        # 拿到的才是 AsyncIterator。直接把它当迭代器用会得到
        # ``'async for' requires an object with __aiter__ method``。
        result = await gateway.generate(
            wuwei_messages,
            # 传客户端声明的 tools（可能为空）。它们由客户端执行，
            # 我们只负责让模型看见并产出 tool_calls。
            tools=wuwei_tools or None,
            stream=stream,
            **gen_kwargs,
        )
        return gateway, model_name, result
    except Exception as exc:  # noqa: BLE001
        logger.warning("direct llm call failed: %s", exc, exc_info=True)
        raise DirectLLMError(f"上游调用失败：{type(exc).__name__}: {exc}") from exc


async def _stream(gateway, request: dict[str, Any]) -> AsyncIterator[Any]:
    """把 gateway 的流式响应包成异步迭代器（保留给旧调用方）。"""
    try:
        iterator = gateway.generate(
            request.pop("messages"), tools=None, stream=True, **request
        )
        async for chunk in iterator:
            yield chunk
    except Exception as exc:  # noqa: BLE001
        logger.warning("direct llm stream failed: %s", exc, exc_info=True)
        raise DirectLLMError(f"上游流式调用失败：{type(exc).__name__}: {exc}") from exc


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """同时支持属性访问与 dict 访问。"""
    if obj is None:
        return default
    value = getattr(obj, name, None)
    if value is None and isinstance(obj, dict):
        value = obj.get(name)
    return default if value is None else value


def extract_text(response: Any) -> str:
    """取正文。

    优先 wuwei 的扁平 ``content``；回落到 OpenAI 形状
    ``choices[0].message.content``（兼容上游直接回 JSON 的情况）。
    """
    content = _attr(response, "content")
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        parts = []
        for seg in content:
            if isinstance(seg, dict):
                if seg.get("type") in ("text", "output_text"):
                    parts.append(str(seg.get("text") or ""))
            elif isinstance(seg, str):
                parts.append(seg)
        joined = "".join(parts)
        if joined:
            return joined

    # OpenAI 形状回落
    choices = _attr(response, "choices")
    if isinstance(choices, list) and choices:
        message = _attr(choices[0], "message")
        if message is not None:
            inner = _attr(message, "content")
            if isinstance(inner, str):
                return inner
            if isinstance(inner, list):
                return "".join(
                    str(seg.get("text") or "")
                    for seg in inner
                    if isinstance(seg, dict) and seg.get("type") in ("text", "output_text")
                )
    return ""


def extract_reasoning(response: Any) -> str:
    """取推理内容。

    wuwei 用 ``reasoning_content``；OpenAI Responses 叫 ``reasoning``。
    两种都认。
    """
    for name in ("reasoning_content", "reasoning"):
        value = _attr(response, name)
        if isinstance(value, str) and value:
            return value
    # OpenAI 形状回落
    choices = _attr(response, "choices")
    if isinstance(choices, list) and choices:
        message = _attr(choices[0], "message")
        if message is not None:
            for name in ("reasoning_content", "reasoning"):
                value = _attr(message, name)
                if isinstance(value, str) and value:
                    return value
    return ""


def extract_usage(response: Any) -> dict[str, int]:
    """取 usage，归一成 prompt/completion/total。

    wuwei 的 usage 可能挂在 ``usage``，也可能是 ``model_extra`` 里的字段
    （不同上游塞的位置不一样），逐个找。
    """
    raw = _attr(response, "usage")
    if raw is None:
        extra = _attr(response, "model_extra")
        if isinstance(extra, dict):
            raw = extra.get("usage")

    def _get(source: Any, name: str) -> int:
        value = _attr(source, name)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    prompt = _get(raw, "prompt_tokens") or _get(raw, "input_tokens")
    completion = _get(raw, "completion_tokens") or _get(raw, "output_tokens")
    total = _get(raw, "total_tokens") or (prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def extract_finish_reason(response: Any) -> str:
    """取结束原因。wuwei 的响应不一定带这个字段，缺省 stop。"""
    for name in ("finish_reason", "stop_reason"):
        value = _attr(response, name)
        if isinstance(value, str) and value:
            return value
    choices = _attr(response, "choices")
    if isinstance(choices, list) and choices:
        value = _attr(choices[0], "finish_reason")
        if isinstance(value, str) and value:
            return value
    return "stop"


def extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    """取模型产出的 tool_calls，转成 OpenAI 形状。

    wuwei 的 LLMResponse 有 ``tool_calls`` 字段；这里统一转成客户端认识的
    结构（arguments 必须是 JSON 字符串）。
    """
    from app.services.llm_providers.direct_tools import wuwei_tool_calls_to_openai

    raw = _attr(response, "tool_calls")
    return wuwei_tool_calls_to_openai(raw)


def chunk_text(chunk: Any) -> str:
    """从流式 chunk 里取增量文本（wuwei chunk 同样是扁平 content）。"""
    content = _attr(chunk, "content")
    if isinstance(content, str):
        return content
    # OpenAI 形状回落
    choices = _attr(chunk, "choices")
    if isinstance(choices, list) and choices:
        delta = _attr(choices[0], "delta")
        if delta is not None:
            value = _attr(delta, "content")
            if isinstance(value, str):
                return value
    return ""


def new_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def now_ts() -> int:
    return int(time.time())
