"""OpenAI 兼容执行器（把 AgenticOS 的智能体暴露成 OpenAI 形状的响应）。

路径由 ``app/api/gateway_v1.py`` 统一挂载：``/v1/models`` 与
``/v1/chat/completions`` 已有"透传企业上游"的实现，本模块提供
**本地智能体**分支——当 model 命中本站智能体时直接执行，命中不了
才回落到上游透传。这样对外仍是标准的 OpenAI 端点，企业无需感知
背后走的是本地 Agent 还是上游。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.models import UserModel
from app.schemas.agent import AgentStreamRequest
from app.services.agent.service import AgentService

logger = logging.getLogger("openai_compat")

# 可被 OpenAI 客户端直接填进 model 字段的通用别名
GENERIC_MODEL_ALIASES = frozenset({
    "gpt-4o", "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "assistant", "agent", "default",
})

# AgenticOS 的响应模式名：无论用户是否安装对应智能体，都优先在本地解析
# （否则 model="general" 会被当成上游模型名转发出去，语义混乱）
LOCAL_MODE_NAMES = frozenset({"general", "ppt", "website", "email", "bigdata"})


def local_agent_slugs(user: UserModel) -> set[str]:
    """当前用户可用的本地智能体标识（slug + 名称小写）。"""
    from app.services.agent_profile_service import AgentProfileService

    items = AgentProfileService().list_user_agents(user).get("items", [])
    slugs: set[str] = set(GENERIC_MODEL_ALIASES) | set(LOCAL_MODE_NAMES)
    for item in items:
        slug = str(item.get("slug") or "").strip().lower()
        name = str(item.get("name") or "").strip().lower()
        if slug:
            slugs.add(slug)
        if name:
            slugs.add(name)
        mode = str(item.get("response_mode") or "").strip().lower()
        if mode:
            slugs.add(mode)
    return slugs


def is_local_agent(model: str, user: UserModel) -> bool:
    """model 是否命中本地智能体（决定走本地执行还是上游透传）。"""
    return (model or "").strip().lower() in local_agent_slugs(user)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="智能体名称或 slug，默认 general")
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    user: str | None = Field(default=None, description="透传用于审计")
    # AgenticOS 扩展（OpenAI 客户端会忽略未知字段）
    session_id: str | None = None
    approval_mode: str | None = Field(default=None, pattern="^(ask|auto|full)$")
    plan_mode: bool = False


def _extract_user_content(messages: list[ChatMessage]) -> str:
    """取最后一条 user 消息作为本轮输入。"""
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()
    return messages[-1].content.strip()


def _resolve_model_name(raw: str) -> str:
    """把 model 名解析为 response_mode（接受 slug、名称或通用模式名）。"""
    value = (raw or "general").strip().lower()
    aliases = {
        "gpt-4o": "general", "gpt-4": "general", "gpt-3.5-turbo": "general",
        "assistant": "general", "agent": "general", "default": "general",
    }
    return aliases.get(value, value)


async def local_models_payload(current_user: UserModel) -> dict[str, Any]:
    """OpenAI 形状的模型列表（本地智能体）。"""
    from app.services.agent_profile_service import AgentProfileService

    items = AgentProfileService().list_user_agents(current_user).get("items", [])
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": item["slug"],
                "object": "model",
                "created": int(
                    (item.get("created_at") and time.mktime(item["created_at"].timetuple()))
                    or now
                ),
                "owned_by": "agenticos",
                "display_name": item["name"],
                "description": item.get("description") or "",
            }
            for item in items
        ],
    }


async def run_local_completion(
    payload: ChatCompletionRequest,
    current_user: UserModel,
    agent_service: AgentService,
):
    prompt = _extract_user_content(payload.messages)
    if not prompt:
        raise HTTPException(status_code=400, detail="messages 中缺少有效的用户消息")

    response_mode = _resolve_model_name(payload.model)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    request = AgentStreamRequest(
        message=prompt,
        session_id=payload.session_id,
        response_mode=response_mode if response_mode in {
            "general", "ppt", "website", "email", "bigdata",
        } else "general",
        approval_mode=payload.approval_mode or "auto",
        plan_mode=payload.plan_mode,
    )

    async def run() -> tuple[str, str]:
        """返回 (正文, 推理摘要)。"""
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            agent_service.ensure_ready()
            await agent_service.ensure_session_access(request, current_user)
            async for event in agent_service.stream_chat(request, current_user):
                kind = event.get("event")
                data = event.get("data") or {}
                if kind == "delta":
                    text_parts.append(data.get("content") or "")
                elif kind == "reasoning_delta":
                    reasoning_parts.append(data.get("content") or "")
                elif kind == "error":
                    raise RuntimeError(data.get("message") or "agent error")
        except RuntimeError:
            raise
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return "".join(text_parts), "".join(reasoning_parts)

    if not payload.stream:
        try:
            text, reasoning = await run()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        message: dict[str, Any] = {"role": "assistant", "content": text}
        if reasoning:
            message["reasoning_content"] = reasoning
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": payload.model,
            "choices": [
                {"index": 0, "message": message, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    async def event_stream() -> AsyncIterator[bytes]:
        def _sse(obj: dict[str, Any]) -> bytes:
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()

        first = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": payload.model,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
            ],
        }
        yield _sse(first)

        text_parts: list[str] = []
        try:
            agent_service.ensure_ready()
            await agent_service.ensure_session_access(request, current_user)
            async for event in agent_service.stream_chat(request, current_user):
                kind = event.get("event")
                data = event.get("data") or {}
                if kind == "delta":
                    chunk = data.get("content") or ""
                    if not chunk:
                        continue
                    text_parts.append(chunk)
                    yield _sse({
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": payload.model,
                        "choices": [
                            {"index": 0, "delta": {"content": chunk}, "finish_reason": None},
                        ],
                    })
                elif kind == "error":
                    message = data.get("message") or "agent error"
                    yield _sse({
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": payload.model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                        "error": {"message": message},
                    })
        except Exception as exc:  # noqa: BLE001 —— 流已开始，只能以错误块收尾
            logger.exception("openai-compat stream failed: %s", completion_id)
            yield _sse({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": payload.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                "error": {"message": str(exc)},
            })

        yield _sse({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": payload.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        })
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )