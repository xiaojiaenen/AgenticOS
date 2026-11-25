"""网关适配层：自研 LLMGateway → LangChain BaseChatModel（迁移方案阶段 1）。

LLMGateway 是本项目的差异化资产（多提供商路由、企业 Cookie 账号池轮换、
RetryingGateway 的 usage 收尾帧/工具调用收尾/兼容网关 500 三类容错），
LangChain 生态没有任何等价物。这里不做"替换"，做**挂接**：LangGraph 的
模型节点通过 :class:`GatewayChatModel` 调用它，工具 schema 用 wuwei 的
``Tool`` 对象直传（gateway 的 OpenAIAdapter 本来就吃这个形态）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterator, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, PrivateAttr

_logger = logging.getLogger("agenticos.langgraph.chat_model")


def _args_to_dict(arguments: Any) -> dict:
    """wuwei FunctionCall.arguments 可能是 dict 或 JSON 字符串，统一成 dict。"""
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}
    return arguments if isinstance(arguments, dict) else {}


def lc_to_native_messages(messages: list[BaseMessage]) -> list[Any]:
    """LangChain 消息 → 自有 Message（原生网关的输入形态）。"""
    from app.services.agent.native.types import (
        AIMessage as NativeAIMessage,
        HumanMessage as NativeHumanMessage,
        SystemMessage as NativeSystemMessage,
        ToolMessage as NativeToolMessage,
        ToolCall as NativeToolCall,
        FunctionCall as NativeFunctionCall,
    )

    out: list[Any] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            ai = NativeAIMessage(content=_content_to_str(msg.content))
            reasoning = (msg.additional_kwargs or {}).get("reasoning_content")
            if reasoning:
                ai.reasoning_content = reasoning
            for call in msg.tool_calls or []:
                ai.tool_calls.append(
                    NativeToolCall(
                        id=str(call.get("id") or ""),
                        function=NativeFunctionCall(
                            name=str(call.get("name") or ""),
                            arguments=_args_to_dict(call.get("args")),
                        ),
                    )
                )
            usage = (msg.response_metadata or {}).get("usage") or (msg.additional_kwargs or {}).get("usage")
            if isinstance(usage, dict):
                ai.usage = usage
            out.append(ai)
        elif msg.type == "tool":
            out.append(
                NativeToolMessage(
                    content=_content_to_str(msg.content),
                    tool_call_id=str(getattr(msg, "tool_call_id", "") or ""),
                    name=str(getattr(msg, "name", "") or ""),
                )
            )
        elif msg.type == "system":
            out.append(NativeSystemMessage(content=_content_to_str(msg.content)))
        else:  # human / 未知 → user
            out.append(NativeHumanMessage(content=_content_to_str(msg.content)))
    return out


def _content_to_str(content: Any) -> str:
    """LangChain content 可能是 str 或多模态 part 列表；gateway 只收 str。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


class GatewayChatModel(BaseChatModel):
    """把 LLMGateway（多提供商 + Cookie 池 + 重试容错）挂进 LangGraph。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    gateway: Any = None
    #: 供 langgraph/cosmos 的模型名展示（与 profile.effective_model 一致）
    model_name: str = ""

    _usage_tracker: Any = PrivateAttr(default=None)

    @property
    def _llm_type(self) -> str:
        return "agenticos-gateway"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        """工具 schema 直传自有 ``Tool`` 列表（原生网关的输入形态）。

        LangGraph 的工具节点会传 LangChain BaseTool；这里把适配层挂在
        BaseTool 上（tools_adapter 给每个 LC 工具的 metadata 设了 ``wuwei_tool`` 项），
        让 gateway 继续走它自己验证过的请求构造路径。
        """
        wuwei_tools: list[Any] = []
        for tool in tools or []:
            metadata = getattr(tool, "metadata", None) or {}
            wuwei_tool = metadata.get("wuwei_tool") if isinstance(metadata, dict) else None
            wuwei_tools.append(wuwei_tool if wuwei_tool is not None else tool)
        return self.bind(tools=wuwei_tools, **kwargs)

    # ── 同步 generate（LangGraph 同步节点在 executor 线程里跑，无运行循环）──

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        import time

        native_msgs = lc_to_native_messages(messages)
        tools = kwargs.get("tools")
        tracker = self._usage_tracker
        started = time.monotonic()

        async def _collect():
            response = await self.gateway.generate(messages=native_msgs, tools=tools, stream=True)
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            usage: dict[str, Any] | None = None
            finish_reason: str | None = None
            async for chunk in response:
                if chunk.content:
                    content_parts.append(chunk.content)
                reasoning = getattr(chunk, "reasoning_content", None)
                if reasoning:
                    reasoning_parts.append(reasoning)
                complete = getattr(chunk, "tool_calls_complete", None)
                if complete:
                    tool_calls = [
                        {
                            "name": getattr(call.function, "name", ""),
                            "args": _args_to_dict(getattr(call.function, "arguments", {})),
                            "id": getattr(call, "id", None),
                        }
                        for call in complete
                    ]
                chunk_usage = getattr(chunk, "usage", None)
                if isinstance(chunk_usage, dict) and chunk_usage.get("total_tokens"):
                    usage = chunk_usage
                if getattr(chunk, "finish_reason", None):
                    finish_reason = chunk.finish_reason
            return "".join(content_parts), "".join(reasoning_parts), tool_calls, usage, finish_reason

        content, reasoning, tool_calls, usage, finish_reason = asyncio.run(_collect())
        if tracker is not None:
            tracker.record_llm_call(
                latency_ms=int((time.monotonic() - started) * 1000),
                usage_emitted=usage is not None,
            )

        additional: dict[str, Any] = {}
        if reasoning:
            additional["reasoning_content"] = reasoning
        if isinstance(usage, dict):
            additional["usage"] = usage
        message = AIMessage(
            content=content,
            additional_kwargs=additional,
            tool_calls=tool_calls,
            response_metadata={"finish_reason": finish_reason, "model": self.model_name},
        )
        generation = ChatGeneration(message=message, generation_info={"finish_reason": finish_reason})
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """原生异步生成（避免默认走 executor 线程调 _generate → asyncio.run）。"""
        import time

        wuwei_msgs = lc_to_native_messages(messages)
        tools = kwargs.get("tools")
        tracker = self._usage_tracker
        started = time.monotonic()

        async def _collect():
            response = await self.gateway.generate(messages=wuwei_msgs, tools=tools, stream=True)
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            usage: dict[str, int] | None = None
            finish_reason: str | None = None
            async for chunk in response:
                if chunk.content:
                    content_parts.append(chunk.content)
                reasoning = getattr(chunk, "reasoning_content", None)
                if reasoning:
                    reasoning_parts.append(reasoning)
                complete = getattr(chunk, "tool_calls_complete", None)
                if complete:
                    tool_calls = [
                        {
                            "name": getattr(call.function, "name", ""),
                            "args": _args_to_dict(getattr(call.function, "arguments", {})),
                            "id": getattr(call, "id", None),
                        }
                        for call in complete
                    ]
                chunk_usage = getattr(chunk, "usage", None)
                if isinstance(chunk_usage, dict) and chunk_usage.get("total_tokens"):
                    usage = chunk_usage
                if getattr(chunk, "finish_reason", None):
                    finish_reason = chunk.finish_reason
            return "".join(content_parts), "".join(reasoning_parts), tool_calls, usage, finish_reason

        content, reasoning, tool_calls, usage, finish_reason = await _collect()
        if tracker is not None:
            tracker.record_llm_call(
                latency_ms=int((time.monotonic() - started) * 1000),
                usage_emitted=usage is not None,
            )

        additional: dict[str, Any] = {}
        if reasoning:
            additional["reasoning_content"] = reasoning
        if isinstance(usage, dict):
            additional["usage"] = usage
        message = AIMessage(
            content=content,
            additional_kwargs=additional,
            tool_calls=tool_calls,
            response_metadata={"finish_reason": finish_reason, "model": self.model_name},
        )
        generation = ChatGeneration(message=message, generation_info={"finish_reason": finish_reason})
        return ChatResult(generations=[generation])

    # ── 流式 ─────────────────────────────────────────────────────────────

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        import time

        native_msgs = lc_to_native_messages(messages)
        tools = kwargs.get("tools")
        tracker = self._usage_tracker
        started = time.monotonic()

        response = await self.gateway.generate(messages=native_msgs, tools=tools, stream=True)
        # gateway.stream=True 返回 AsyncIterator[LLMResponseChunk]
        # 已发出的累积 args 快照（index → args），用于累积→增量换算
        _tc_emitted: dict[int, str] = {}
        usage_emitted = False
        async for chunk in response:
            content = chunk.content or ""
            reasoning = getattr(chunk, "reasoning_content", None)
            additional: dict[str, Any] = {}
            if reasoning:
                additional["reasoning_content"] = reasoning

            tool_call_chunks: list[dict[str, Any]] = []
            deltas = getattr(chunk, "tool_calls_delta", None)
            if deltas:
                # gateway 的 delta 是**累积快照**（每帧带全量 arguments）；
                # LangChain 的 AIMessageChunk 合并语义要求**增量**（字符串拼接），
                # 且 name/id 只能出现一次（重复会拼接成垃圾）。这里转成增量：
                # name/id 只在首帧发出，args 只发新后缀。
                for idx, call in enumerate(deltas):
                    if isinstance(call, dict):
                        call_id = call.get("id")
                        call_name = call.get("name")
                        call_args = call.get("arguments") or ""
                        call_index = call.get("index", idx)
                    else:
                        fn = getattr(call, "function", None)
                        call_id = getattr(call, "id", None)
                        call_name = getattr(fn, "name", None) if fn is not None else None
                        raw_args = getattr(fn, "arguments", None) if fn is not None else None
                        if isinstance(raw_args, dict):
                            raw_args = json.dumps(raw_args, ensure_ascii=False)
                        call_args = raw_args or ""
                        call_index = idx

                    prev = _tc_emitted.get(call_index)
                    if prev is None:
                        # 首帧：全量 id/name + 已累积的 args（此前帧未发出过）
                        tool_call_chunks.append(
                            {
                                "name": call_name,
                                "args": call_args,
                                "id": call_id,
                                "index": call_index,
                            }
                        )
                        _tc_emitted[call_index] = call_args
                    else:
                        new_suffix = call_args[len(prev):] if call_args.startswith(prev) else call_args
                        if not new_suffix:
                            continue
                        tool_call_chunks.append(
                            {
                                "name": None,
                                "args": new_suffix,
                                "id": None,
                                "index": call_index,
                            }
                        )
                        _tc_emitted[call_index] = call_args

            usage = getattr(chunk, "usage", None)
            usage_metadata = None
            if isinstance(usage, dict) and usage.get("total_tokens"):
                usage_metadata = {
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens") or 0),
                }
                additional["usage"] = usage

            message_chunk = AIMessageChunk(
                content=content,
                additional_kwargs=additional,
                tool_call_chunks=tool_call_chunks,
                usage_metadata=usage_metadata,
            )
            finish_reason = getattr(chunk, "finish_reason", None)
            generation_info = {"finish_reason": finish_reason} if finish_reason else None
            yield ChatGenerationChunk(message=message_chunk, generation_info=generation_info)
            if finish_reason:
                usage_emitted = True

        if tracker is not None:
            tracker.record_llm_call(
                latency_ms=int((time.monotonic() - started) * 1000),
                usage_emitted=usage_emitted,
            )
