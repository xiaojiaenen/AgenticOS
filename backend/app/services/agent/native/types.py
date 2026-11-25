"""自有核心类型层（全新系统，wuwei 已退役）。

干净的最小集合：
- 消息：BaseMessage + System/Human/AI/Tool 子类（多模态只保留 文本/图片 两种 part，
  对应聊天上传图片的唯一真实用途）；
- 工具调用：ToolCall / FunctionCall；
- LLM：LLMResponse / LLMResponseChunk / LLMError（含 finish_reason 归一化）；
- 事件：AgentEvent（引擎 → SSE mapper 的唯一事件契约）；
- 会话：AgentSession / Context（一次会话的配置与消息历史）。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── 多模态 part（仅 文本/图片：聊天上传图片的唯一用途）──────────────────


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    url: str
    detail: Literal["auto", "low", "high"] = "auto"


ContentPart = TextPart | ImagePart


# ── 工具调用 ──────────────────────────────────────────────────────────


class FunctionCall(BaseModel):
    """函数调用（arguments 为 dict）。"""

    name: str
    arguments: dict = Field(default_factory=dict)

    def to_openai(self) -> dict:
        import json as _json

        return {"name": self.name, "arguments": _json.dumps(self.arguments)}


class ToolCall(BaseModel):
    """工具调用"""

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    type: Literal["function"] = "function"
    function: FunctionCall

    def to_openai(self) -> dict:
        return {"id": self.id, "type": self.type, "function": self.function.to_openai()}


# ── 消息 ──────────────────────────────────────────────────────────────


class BaseMessage(BaseModel):
    """消息基类。"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str
    content: str = ""
    content_parts: list[ContentPart] = Field(default_factory=list)
    reasoning_content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)

    def to_openai(self) -> dict:
        result: dict[str, Any] = {"role": self.role}
        if self.content_parts:
            blocks: list[dict[str, Any]] = []
            has_text = any(isinstance(p, TextPart) for p in self.content_parts)
            if self.content and not has_text:
                blocks.append({"type": "text", "text": self.content})
            for part in self.content_parts:
                if isinstance(part, TextPart):
                    blocks.append({"type": "text", "text": part.text})
                elif isinstance(part, ImagePart):
                    blocks.append({"type": "image_url", "image_url": {"url": part.url, "detail": part.detail}})
            result["content"] = blocks
        else:
            result["content"] = self.content
        if self.name:
            result["name"] = self.name
        return result


class SystemMessage(BaseMessage):
    role: Literal["system"] = "system"

    def __init__(self, content: str, **kwargs):
        super().__init__(content=content, **kwargs)


class HumanMessage(BaseMessage):
    role: Literal["user"] = "user"

    def __init__(self, content: str, **kwargs):
        super().__init__(content=content, **kwargs)


class AIMessage(BaseMessage):
    role: Literal["assistant"] = "assistant"
    usage: dict | None = None

    def to_openai(self) -> dict:
        result = super().to_openai()
        if self.tool_calls:
            result["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        if self.reasoning_content:
            result["reasoning_content"] = self.reasoning_content
        return result


class ToolMessage(BaseMessage):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    name: str
    status: Literal["success", "error"] = "success"

    def to_openai(self) -> dict:
        return {
            "role": "tool",
            "content": self.content,
            "tool_call_id": self.tool_call_id,
        }


Message = BaseMessage


# ── LLM 响应 ──────────────────────────────────────────────────────────

FINISH_REASONS = frozenset({"stop", "tool_calls", "length", "content_filter"})


def normalize_finish_reason(reason: str | None) -> str:
    return {
        "eos": "stop",
        "end_turn": "stop",
        "stop_sequence": "stop",
        "completed": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
        "max_output_tokens": "length",
        "aborted": "cancelled",
        "abort": "cancelled",
        "failed": "error",
        "insufficient_system_resource": "error",
    }.get(reason or "", reason or "unknown")


class LLMResponse(BaseModel):
    """非流式响应（兼容 content/tool_calls 直接构造）。"""

    message: BaseMessage = Field(default_factory=lambda: BaseMessage(role="assistant"))

    from pydantic import model_validator

    @model_validator(mode="before")
    @classmethod
    def _adapt_legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        legacy = {k: value.pop(k) for k in ("content", "tool_calls", "reasoning_content") if k in value}
        if legacy and "message" not in value:
            value["message"] = BaseMessage(role="assistant", **legacy)
        return value
    finish_reason: str = "stop"
    raw_finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    usage_available: bool = False
    model: str = ""
    latency_ms: int = 0
    metadata: dict = Field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.message.content

    @property
    def reasoning_content(self) -> str | None:
        return self.message.reasoning_content

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls


class LLMResponseChunk(BaseModel):
    """流式增量。tool_calls_delta 元素：{"index","id","name","arguments"(JSON str)}。"""

    content: str
    reasoning_content: str | None = None
    tool_calls_delta: list[dict] | None = None
    tool_calls_complete: list[ToolCall] | None = None
    finish_reason: str | None = None
    raw_finish_reason: str | None = None
    usage_available: bool = False
    usage: dict[str, int] | None = None


class LLMError(Exception):
    """LLM 调用的统一异常（保留 provider / status_code / 分类 / details）。"""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        kind: str = "unknown",
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.kind = kind
        self.details = details or {}


# ── Agent 事件 ────────────────────────────────────────────────────────

AgentEventType = Literal[
    "run_start",
    "run_end",
    "llm_start",
    "llm_end",
    "text_delta",
    "reasoning_delta",
    "tool_start",
    "tool_end",
    "tool_error",
    "approval_required",
    "done",
    "error",
]


class AgentEvent(BaseModel):
    type: AgentEventType
    session_id: str
    step: int
    run_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    content: str
    usage: dict[str, int] = Field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    latency_ms: int = 0
    llm_calls: int = 0
    status: Literal["completed", "interrupted", "error", "incomplete", "cancelled", "unknown"] = "completed"
    interrupt: dict[str, Any] | None = None
    termination_reason: str | None = None
    steps_used: int = 0
    max_steps: int | None = None
    output: Any = None


# ── 会话 ──────────────────────────────────────────────────────────────


class Context:
    """单个会话的消息历史。"""

    def __init__(self) -> None:
        self._messages: list[BaseMessage] = []

    def add_user_message(self, content: str | BaseMessage) -> None:
        if isinstance(content, BaseMessage):
            self._messages.append(content)
        else:
            self._messages.append(HumanMessage(content=content))

    def add_system_message(self, content: str) -> None:
        self._messages.append(SystemMessage(content=content))

    def add_tool_message(self, content: str, tool_call_id: str | None, name: str | None = None) -> None:
        self._messages.append(ToolMessage(content=content, tool_call_id=tool_call_id or "", name=name or ""))

    def add_ai_message(
        self,
        content: str | None,
        tool_calls: list[ToolCall] | None = None,
        reasoning_content: str | None = None,
    ) -> BaseMessage:
        message = BaseMessage(
            role="assistant",
            content=content or "",
            reasoning_content=reasoning_content,
            tool_calls=tool_calls or [],
        )
        self._messages.append(message)
        return message

    def get_messages(self) -> list[BaseMessage]:
        return self._messages

    def get_last_message(self) -> BaseMessage | None:
        return self._messages[-1] if self._messages else None

    def reset(self) -> None:
        self._messages.clear()

    def replace_messages(self, messages: list[BaseMessage]) -> None:
        self._messages = list(messages)


@dataclass
class AgentSession:
    """一次会话的配置与上下文。"""

    session_id: str
    system_prompt: str = "你是一个有用的助手"
    max_steps: int = 10
    parallel_tool_calls: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    last_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    last_latency_ms: int = 0
    last_llm_calls: int = 0
    context: Context = field(init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.context = Context()
        self.context.add_system_message(self.system_prompt)
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.last_latency_ms = 0
        self.last_llm_calls = 0

    def to_dict(self) -> dict:
        return {
            "schema_version": 2,
            "session_id": self.session_id,
            "system_prompt": self.system_prompt,
            "max_steps": self.max_steps,
            "parallel_tool_calls": self.parallel_tool_calls,
            "metadata": self.metadata,
            "last_usage": self.last_usage,
            "last_latency_ms": self.last_latency_ms,
            "last_llm_calls": self.last_llm_calls,
            "context": {"messages": [m.model_dump(mode="json") for m in self.context.get_messages()]},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSession":
        session = cls(
            session_id=data["session_id"],
            system_prompt=data.get("system_prompt", "你是一个有用的助手"),
            max_steps=data.get("max_steps", 10),
            parallel_tool_calls=data.get("parallel_tool_calls", False),
            metadata={},
            last_usage=data.get("last_usage") or {},
            last_latency_ms=data.get("last_latency_ms", 0),
            last_llm_calls=data.get("last_llm_calls", 0),
        )
        session.metadata = dict(data.get("metadata") or {})
        messages = [BaseMessage.model_validate(m) for m in (data.get("context") or {}).get("messages", [])]
        session.context.replace_messages(messages)
        # ActionLog 收敛（metadata["action_log"] 可能是带标记/裸 dict 两种形态）
        from app.services.agent.native.action_log import coerce_action_log

        value = session.metadata.get("action_log")
        if value is not None:
            session.metadata["action_log"] = coerce_action_log(value)
        return session
